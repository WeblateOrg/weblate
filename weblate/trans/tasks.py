# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import time
from contextlib import suppress
from datetime import datetime, timedelta
from glob import glob
from operator import itemgetter
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from celery.schedules import crontab
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, F, OuterRef
from django.http import Http404
from django.utils import timezone
from django.utils.timezone import make_aware
from django.utils.translation import gettext, override

from weblate.accounts.utils import remove_user
from weblate.auth.models import AuthenticatedHttpRequest, User, get_anonymous
from weblate.lang.models import Language
from weblate.logger import LOGGER
from weblate.trans.actions import ActionEvents
from weblate.trans.autotranslate import BatchAutoTranslate
from weblate.trans.component_copy import copy_component_addons
from weblate.trans.exceptions import FileParseError
from weblate.trans.models import (
    Category,
    Change,
    Comment,
    Component,
    ComponentList,
    PendingUnitChange,
    Project,
    Suggestion,
    Translation,
)
from weblate.trans.models.unit import fill_in_source_translation
from weblate.trans.removal import RemovalBatch, removal_batch_context
from weblate.utils.celery import app
from weblate.utils.data import data_dir
from weblate.utils.errors import report_error
from weblate.utils.files import remove_tree
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.stats import ProjectLanguage, prefetch_stats
from weblate.utils.views import parse_path
from weblate.vcs.base import RepositoryError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from weblate.trans.models.change import RevertUserEditsResult


@app.task(
    trail=False,
    autoretry_for=(WeblateLockTimeoutError,),
    retry_backoff=600,
    retry_backoff_max=3600,
)
def perform_update(
    cls: Literal["Project", "Component"],
    pk: int,
    auto: bool = False,
    obj=None,
    user_id: int = 0,
) -> None:
    request: AuthenticatedHttpRequest | None = None
    if user_id:
        request = AuthenticatedHttpRequest()
        request.user = User.objects.get(pk=user_id)
    # This is stored as alert, so we can silently ignore some exceptions here
    with suppress(FileParseError, RepositoryError, FileNotFoundError):
        if obj is None:
            if cls == "Project":
                obj = Project.objects.get(pk=pk)
            else:
                obj = Component.objects.get(pk=pk)
        obj.log_info("Updating remote repository")
        if settings.AUTO_UPDATE in {"full", True} or not auto:
            obj.do_update(request)
        else:
            obj.update_remote_branch()


@app.task(
    trail=False,
    autoretry_for=(WeblateLockTimeoutError,),
    retry_backoff=600,
    retry_backoff_max=3600,
)
def perform_load(
    pk: int,
    *,
    force: bool = False,
    force_scan: bool = False,
    langs: list[str] | None = None,
    changed_template: bool = False,
    from_link: bool = False,
    change: int | None = None,
    user_id: int | None = None,
) -> None:
    request: AuthenticatedHttpRequest | None = None
    if user_id:
        request = AuthenticatedHttpRequest()
        request.user = User.objects.get(pk=user_id)
    try:
        component = Component.objects.get(pk=pk)
    except Component.DoesNotExist:
        # Component was removed
        return
    component.create_translations_immediate(
        force=force,
        force_scan=force_scan,
        langs=langs,
        changed_template=changed_template,
        from_link=from_link,
        change=change,
        request=request,
    )


@app.task(
    trail=False,
    autoretry_for=(WeblateLockTimeoutError,),
    retry_backoff=600,
    retry_backoff_max=3600,
)
def perform_commit(
    pk,
    reason: str,
    *,
    user_id: int | None = None,
    force_scan: bool = False,
    previous_head: str | None = None,
) -> None:
    user = User.objects.get(pk=user_id) if user_id else None
    component = Component.objects.get(pk=pk)
    with component.repository.lock:
        component.commit_pending(reason, user=user)
        if force_scan:
            component.trigger_post_update(
                previous_head=previous_head,
                skip_push=False,
                user=user,
            )
            component.create_translations(force=True)


@app.task(
    trail=False,
    autoretry_for=(WeblateLockTimeoutError,),
    retry_backoff=600,
    retry_backoff_max=3600,
)
def perform_push(pk, *args, **kwargs) -> None:
    component = Component.objects.get(pk=pk)
    component.do_push(*args, **kwargs)


@app.task(trail=False)
def commit_pending(
    hours: int | None = None,
    pks: set[int] | None = None,
    logger: Callable[[str], None] | None = None,
) -> None:
    components = PendingUnitChange.objects.find_committable_components(
        pks=list(pks) if pks else None, hours=hours
    )

    if not components:
        return

    components = prefetch_stats(components)

    for component in components:
        if logger:
            logger(f"Committing {component}")

        perform_commit.delay(component.pk, "commit_pending")


@app.task(trail=False)
def revert_user_edits(
    target_user_id: int,
    acting_user_id: int,
    *,
    project_id: int | None = None,
    sitewide: bool = False,
) -> RevertUserEditsResult:
    if project_id is None and not sitewide:
        msg = "Either project_id or sitewide must be provided"
        raise ValueError(msg)

    target_user = User.objects.get(pk=target_user_id)
    acting_user = User.objects.get(pk=acting_user_id)
    project = Project.objects.get(pk=project_id) if project_id is not None else None
    return Change.objects.revert_user_edits(
        target_user,
        acting_user,
        project=project,
    )


@app.task(trail=False)
def cleanup_component(pk: int) -> None:
    """
    Perform cleanup of component models.

    - Remove stale source Unit objects.
    - Update variants.
    """
    try:
        component = Component.objects.get(pk=pk)
    except Component.DoesNotExist:
        return

    # Skip monolingual components, these handle cleanups based on the template
    if component.template:
        return

    # Remove stale variants
    with transaction.atomic():
        component.update_variants()

    translation = component.source_translation
    # Skip translations with a filename (eg. when POT file is present)
    if translation.filename:
        return

    # Remove all units where there is just one referenced unit (self)
    with transaction.atomic():
        deleted, details = (
            translation.unit_set.annotate(Count("unit"))
            .filter(unit__count__lte=1)
            .delete()
        )
        if deleted:
            translation.log_info("removed leaf units: %s", details)


@app.task(trail=False)
def cleanup_suggestions() -> None:
    # Process suggestions
    anonymous_user = get_anonymous()
    suggestions = Suggestion.objects.prefetch_related("unit")
    for suggestion in suggestions:
        with transaction.atomic():
            # Remove suggestions with same text as real translation
            if (
                suggestion.unit.target == suggestion.target
                and suggestion.unit.translated
            ):
                suggestion.delete_log(
                    anonymous_user, change=ActionEvents.SUGGESTION_CLEANUP
                )
                continue

            # Remove duplicate suggestions
            if (
                Suggestion.objects.filter(
                    unit=suggestion.unit, target=suggestion.target
                )
                .exclude(id=suggestion.id)
                .exists()
            ):
                suggestion.delete_log(
                    anonymous_user, change=ActionEvents.SUGGESTION_CLEANUP
                )


@app.task(trail=False)
def update_remotes() -> None:
    """Update all remote branches (without attempt to merge)."""
    if settings.AUTO_UPDATE not in {"full", "remote", True, False}:
        return

    now = timezone.now()
    components = (
        Component.objects.with_repo()
        .annotate(hourmod=F("id") % 24)
        .filter(hourmod=now.hour)
    )
    for component in components.prefetch().iterator(chunk_size=100):
        perform_update("Component", -1, auto=True, obj=component)


@app.task(trail=False)
def cleanup_repos() -> None:
    """Cleanup of all internal repositories."""
    now = timezone.now()

    components = (
        Component.objects.with_repo()
        .annotate(id_mod=F("id") % (30 * 24))
        .filter(id_mod=(now.day - 1) * 24 + now.hour)
    )
    for component in components.prefetch().iterator(chunk_size=100):
        try:
            with component.repository.lock:
                component.log_info("Performing repository maintenance")
                component.repository.maintenance()
        except (RepositoryError, WeblateLockTimeoutError):
            report_error("Repository maintenance failed", project=component.project)


@app.task(trail=False)
def cleanup_stale_repos(root: Path | None = None) -> bool:
    vcs_root = Path(data_dir("vcs"))
    if root is None:
        root = vcs_root

    yesterday = time.time() - 86400

    empty_dir = True
    for path in root.glob("*"):
        if not path.is_dir():
            empty_dir = False
            # Possibly a lock file
            continue
        git_dir = path / ".git"
        mercurial_dir = path / ".hg"
        if not git_dir.exists() and not mercurial_dir.exists():
            # Category dir
            if not cleanup_stale_repos(path):
                empty_dir = False
            continue

        # Skip recently modified paths
        if path.stat().st_mtime > yesterday:
            empty_dir = False
            continue

        try:
            # Find matching components
            component: Component = parse_path(
                None, path.relative_to(vcs_root).parts, (Component,)
            )
        except Http404:
            # Remove stale dir
            LOGGER.info("removing stale VCS path (not found): %s", path)
            remove_tree(path)
        else:
            if component.is_repo_link:
                LOGGER.info("removing stale VCS path (uses link): %s", root)
                remove_tree(path)
            else:
                empty_dir = False

    if empty_dir and root != vcs_root:
        try:
            # Find matching components
            parse_path(None, root.relative_to(vcs_root).parts, (Category, Project))
        except Http404:
            LOGGER.info("removing stale VCS path (not found): %s", root)
            root.rmdir()
        else:
            empty_dir = False
    return empty_dir


@app.task(trail=False)
def cleanup_old_suggestions() -> None:
    if not settings.SUGGESTION_CLEANUP_DAYS:
        return
    cutoff = timezone.now() - timedelta(days=settings.SUGGESTION_CLEANUP_DAYS)
    Suggestion.objects.filter(timestamp__lt=cutoff).delete()


@app.task(trail=False)
def cleanup_old_comments() -> None:
    if not settings.COMMENT_CLEANUP_DAYS:
        return
    cutoff = timezone.now() - timedelta(days=settings.COMMENT_CLEANUP_DAYS)
    Comment.objects.filter(timestamp__lt=cutoff).delete()


@app.task(trail=False)
def repository_alerts(threshold: int = settings.REPOSITORY_ALERT_THRESHOLD) -> None:
    non_linked = Component.objects.with_repo()
    for component in non_linked.iterator():
        try:
            if component.repository.count_missing() > threshold:
                component.add_alert("RepositoryOutdated")
            else:
                component.delete_alert("RepositoryOutdated")
            if component.repository.count_outgoing() > threshold:
                component.add_alert("RepositoryChanges")
            else:
                component.delete_alert("RepositoryChanges")
        except RepositoryError as error:
            report_error("Could not check repository status", project=component.project)
            component.add_alert("MergeFailure", error=component.error_text(error))


@app.task(trail=False)
def component_alerts(component_ids=None) -> None:
    if component_ids:
        components = Component.objects.filter(pk__in=component_ids)
    else:
        now = timezone.now()
        components = Component.objects.annotate(hourmod=F("id") % 24).filter(
            hourmod=now.hour
        )
    for component in components.prefetch().iterator(chunk_size=100):
        with transaction.atomic():
            component.update_alerts()


@app.task(
    trail=False,
    autoretry_for=(Component.DoesNotExist, WeblateLockTimeoutError),
    retry_backoff=60,
)
@transaction.atomic
def component_after_save(
    pk: int,
    *,
    changed_git: bool,
    changed_setup: bool,
    changed_template: bool,
    changed_variant: bool,
    changed_enforced_checks: bool,
    skip_push: bool,
    create: bool,
    seed_source_component_id: int | None = None,
    copy_seed_addons: bool = False,
    seed_author: str | None = None,
) -> dict[Literal["component"], int]:
    component = Component.objects.get(pk=pk)
    component.after_save(
        changed_git=changed_git,
        changed_setup=changed_setup,
        changed_template=changed_template,
        changed_variant=changed_variant,
        changed_enforced_checks=changed_enforced_checks,
        skip_push=skip_push,
        create=create,
        seed_source_component_id=seed_source_component_id,
        copy_seed_addons=copy_seed_addons,
        seed_author=seed_author,
    )
    return {"component": pk}


@app.task(
    trail=False,
    autoretry_for=(Component.DoesNotExist, WeblateLockTimeoutError),
    retry_backoff=60,
)
@transaction.atomic
def update_enforced_checks(component: int | Component) -> None:
    if isinstance(component, int):
        component = Component.objects.get(pk=component)
    component.update_enforced_checks()


@app.task(trail=False)
@transaction.atomic
def component_removal(pk: int, uid: int) -> None:
    user = User.objects.get(pk=uid)
    try:
        component = Component.objects.get(pk=pk)
    except Component.DoesNotExist:
        return

    _component_removal(component, user)


def _component_removal(
    component: Component, user: User, batch: RemovalBatch | None = None
) -> None:
    if batch is not None:
        component.removal_batch = batch
    with component.repository.lock:
        component.acting_user = user
        component.project.change_set.create(
            action=ActionEvents.REMOVE_COMPONENT,
            target=component.slug,
            user=user,
            author=user,
        )
        component.delete()
        if component.allow_translation_propagation:
            components = component.project.component_set.filter(
                allow_translation_propagation=True
            ).exclude(pk=component.pk)
            if batch is not None:
                components = components.exclude(pk__in=batch.removed_component_ids)
            for current in components.iterator():
                current.schedule_update_checks()


def _collect_removal_targets(category: Category, batch: RemovalBatch) -> None:
    _collect_linked_removal_targets(
        category.component_set.values_list("id", flat=True).iterator(chunk_size=1000),
        batch,
    )

    for child in category.category_set.all():
        _collect_removal_targets(child, batch)


def _collect_linked_removal_targets(
    component_ids: Iterable[int], batch: RemovalBatch
) -> None:
    linked_frontier: set[int] = set()
    for component_id in component_ids:
        batch.mark_component(component_id)
        linked_frontier.add(component_id)

    while linked_frontier:
        children = Component.objects.filter(
            linked_component_id__in=linked_frontier
        ).values_list("id", flat=True)
        next_frontier = set()
        for component_id in children.iterator(chunk_size=1000):
            if component_id in batch.removed_component_ids:
                continue
            batch.mark_component(component_id)
            next_frontier.add(component_id)
        linked_frontier = next_frontier


def _category_removal(
    category: Category, user: User, batch: RemovalBatch | None = None
) -> None:
    for child in category.category_set.all():
        _category_removal(child, user, batch)
    for component in category.component_set.iterator():
        _component_removal(component, user, batch)
    category.project.change_set.create(
        action=ActionEvents.REMOVE_CATEGORY,
        target=category.slug,
        user=user,
        author=user,
    )
    category.delete()


@app.task(trail=False)
@transaction.atomic
def category_removal(pk: int, uid: int) -> None:
    user = User.objects.get(pk=uid)
    try:
        category = Category.objects.get(pk=pk)
    except Category.DoesNotExist:
        return
    batch = RemovalBatch()
    _collect_removal_targets(category, batch)
    with removal_batch_context(batch):
        _category_removal(category, user, batch)
    transaction.on_commit(batch.flush)


def cleanup_project_tokens(project: Project, user: User | None) -> None:
    """Remove project-scoped tokens before project groups are deleted."""
    other_project_groups = User.groups.through.objects.filter(
        user_id=OuterRef("pk"),
        group__defining_project__isnull=False,
    ).exclude(group__defining_project=project)
    project_tokens = (
        User.objects.filter(
            groups__defining_project=project,
            is_bot=True,
            username__startswith="bot-",
            email__endswith="@bots.noreply.weblate.org",
        )
        .exclude(username__contains=":")
        .exclude(full_name="Deleted User")
        .annotate(has_other_project_groups=Exists(other_project_groups))
        .filter(has_other_project_groups=False)
        .distinct()
        .order_by("pk")
    )
    username = user.username if user is not None else None
    for token_user in project_tokens.iterator():
        remove_user(
            token_user,
            None,
            activity="token-removed",
            project=project.name,
            username=username,
        )


@app.task(
    trail=False,
    autoretry_for=(IntegrityError,),
    retry_backoff=600,
    retry_backoff_max=3600,
)
def actual_project_removal(pk: int, uid: int | None) -> None:
    """
    Remove project.

    This is separated from project_removal to allow retry on integrity errors.
    """
    with transaction.atomic():
        user = get_anonymous() if uid is None else User.objects.get(pk=uid)
        try:
            project = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            return
        Change.objects.create(
            action=ActionEvents.REMOVE_PROJECT,
            target=project.slug,
            user=user,
            author=user,
        )
        cleanup_project_tokens(project, user)
        batch = RemovalBatch()
        with removal_batch_context(batch):
            project.delete()
        transaction.on_commit(batch.flush)


@app.task(trail=False)
def project_removal(pk: int, uid: int | None) -> None:
    """Backup project and schedule actual removal."""
    create_project_backup(pk)
    actual_project_removal.delay(pk, uid)


@app.task(
    trail=False,
    autoretry_for=(WeblateLockTimeoutError,),
    retry_backoff=600,
    retry_backoff_max=3600,
)
def auto_translate(  # noqa: PLR0913
    *,
    user_id: int | None,
    mode: str,
    q: str,
    auto_source: Literal["mt", "others"],
    source_component_id: int | None,
    engines: list[str],
    threshold: int,
    component_wide: bool = False,
    unit_ids: list[int] | None = None,
    translation_id: int | None = None,
    component_id: int | None = None,
    category_id: int | None = None,
    project_id: int | None = None,
    language_id: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"warnings": []}
    obj: Translation | Component | Category | ProjectLanguage
    user = User.objects.get(pk=user_id) if user_id else None
    with override(user.profile.language if user else "en"):
        try:
            if translation_id is not None:
                obj = Translation.objects.get(pk=translation_id)
                result["translation"] = obj.id
            elif component_id is not None:
                obj = Component.objects.get(pk=component_id)
                result["component"] = obj.id
            elif category_id is not None:
                obj = Category.objects.get(pk=category_id)
                result["category"] = obj.id
            elif project_id is not None:
                if language_id is None:
                    msg = "language_id must be provided when project_id is given"
                    raise ValueError(msg)
                obj = ProjectLanguage(
                    project=Project.objects.get(pk=project_id),
                    language=Language.objects.get(pk=language_id),
                )
                result["project"] = obj.project.id
                result["language"] = obj.language.id
            else:
                msg = "One of translation_id, component_id, category_id, or project_id must be provided"
                raise ValueError(msg)
        except ObjectDoesNotExist:
            result["message"] = gettext(
                "Automatic translation skipped because the target no longer exists."
            )
            return result
        auto = BatchAutoTranslate(
            obj,
            user=user,
            q=q,
            mode=mode,
            component_wide=component_wide,
            unit_ids=unit_ids,
        )
        try:
            message = auto.perform(
                auto_source=auto_source,
                engines=engines,
                threshold=threshold,
                source_component_ids=(
                    [source_component_id] if source_component_id is not None else None
                ),
            )
        except PermissionDenied as error:
            result.update({"message": str(error), "warnings": auto.get_warnings()})
        else:
            result.update({"message": message, "warnings": auto.get_warnings()})
        return result


@app.task(
    trail=False,
    autoretry_for=(WeblateLockTimeoutError,),
    retry_backoff=600,
    retry_backoff_max=3600,
)
def auto_translate_component(
    component_id: int,
    mode: str,
    q: str,
    auto_source: Literal["mt", "others"],
    engines: list[str],
    threshold: int,
    source_component_id: int | None = None,
    user_id: int | None = None,
):
    component_obj = Component.objects.get(pk=component_id)
    user = User.objects.get(pk=user_id) if user_id else None
    auto = BatchAutoTranslate(
        component_obj,
        user=user,
        q=q,
        mode=mode,
        component_wide=True,
    )
    auto.perform(
        auto_source=auto_source,
        engines=engines,
        threshold=threshold,
        source_component_ids=(
            [source_component_id] if source_component_id is not None else None
        ),
    )
    component_obj.run_batched_checks()
    return {"component": component_obj.id}


@app.task(trail=False)
def create_component(copy_from=None, copy_addons=False, in_task=False, **kwargs):
    kwargs["project"] = Project.objects.get(pk=kwargs["project"])
    kwargs["source_language"] = Language.objects.get(pk=kwargs["source_language"])
    if "secondary_language" in kwargs and kwargs["secondary_language"] is not None:
        kwargs["secondary_language"] = Language.objects.get(
            pk=kwargs["secondary_language"]
        )
    component = Component(**kwargs)
    # Perform validation to avoid creating duplicate components via background
    # tasks in discovery
    component.full_clean()
    component.save(force_insert=True)
    component.change_set.create(action=ActionEvents.CREATE_COMPONENT)
    if copy_from:
        source_component = Component.objects.filter(pk=copy_from).first()
        # Copy non-automatic component lists
        for clist in ComponentList.objects.filter(
            components__id=copy_from, autocomponentlist__isnull=True
        ):
            clist.components.add(component)
        # Copy add-ons
        if copy_addons and source_component is not None:
            copy_component_addons(
                component,
                source_component,
                same_project_only=False,
            )
    if in_task:
        return {"component": component.id}
    return component


@app.task(trail=False)
@transaction.atomic
def update_checks(pk: int, update_token: str, update_state: bool = False) -> None:
    try:
        component = Component.objects.get(pk=pk)
    except Component.DoesNotExist:
        return

    # Skip when further updates are scheduled
    latest_token = cache.get(component.update_checks_key)
    if latest_token and update_token != latest_token:
        return

    component.start_batched_checks()
    # Source translation as last
    translations = (
        *component.translation_set.exclude(
            pk=component.source_translation.pk
        ).prefetch(),
        component.source_translation,
    )
    for translation in translations:
        units = translation.unit_set.prefetch().prefetch_source()
        if update_state:
            units = units.select_for_update()
        fill_in_source_translation(units)
        for unit in units.prefetch_all_checks():
            # Reuse object to avoid fetching from the database
            unit.source_unit.translation = component.source_translation
            # Mark this as a batch update to avoid stats update on each unit
            unit.is_batch_update = True
            if update_state:
                unit.update_state()
            unit.run_checks()
    component.run_batched_checks()
    component.invalidate_cache()


@app.task(trail=False)
def daily_update_checks() -> None:
    if settings.BACKGROUND_TASKS == "never":
        return
    today = timezone.now()
    components = Component.objects.annotate(hourmod=F("id") % 24).filter(
        hourmod=today.hour
    )
    if settings.BACKGROUND_TASKS == "monthly":
        components = components.annotate(idmod=F("id") % 30).filter(idmod=today.day)
    elif settings.BACKGROUND_TASKS == "weekly":
        components = components.annotate(idmod=F("id") % 7).filter(
            idmod=today.weekday()
        )
    for component in components.iterator():
        component.schedule_update_checks()


@app.task(trail=False)
def cleanup_project_backups() -> None:
    from weblate.trans.backups import PROJECTBACKUP_PREFIX  # noqa: PLC0415

    # This intentionally does not use Project objects to remove stale backups
    # for removed projects as well.
    rootdir = data_dir(PROJECTBACKUP_PREFIX)
    backup_cutoff = timezone.now() - timedelta(days=settings.PROJECT_BACKUP_KEEP_DAYS)
    for projectdir in glob(os.path.join(rootdir, "*")):
        if not os.path.isdir(projectdir):
            continue
        if projectdir.endswith("import"):
            # Keep imports for shorter time, but more of them
            cutoff = timezone.now() - timedelta(days=1)
            max_count = 30
        else:
            cutoff = backup_cutoff
            max_count = settings.PROJECT_BACKUP_KEEP_COUNT
        backups = sorted(
            (
                (
                    path,
                    make_aware(
                        datetime.fromtimestamp(int(path.split(".")[0]))  # noqa: DTZ006
                    ),
                )
                for path in os.listdir(projectdir)
                if path.endswith((".zip", ".zip.part"))
            ),
            key=itemgetter(1),
            reverse=True,
        )
        while len(backups) > max_count:
            remove = backups.pop()
            os.unlink(os.path.join(projectdir, remove[0]))

        for backup in backups:
            if backup[1] < cutoff:
                os.unlink(os.path.join(projectdir, backup[0]))


@app.task(trail=False)
def create_project_backup(pk: int, uid: int | None = None) -> None:
    from weblate.trans.backups import ProjectBackup  # noqa: PLC0415

    project = Project.objects.get(pk=pk)
    user = User.objects.get(pk=uid) if uid else None
    backup = ProjectBackup()
    backup.backup_project(project, user)


@app.task(trail=False)
def remove_project_backup_download(name: str) -> None:
    if staticfiles_storage.exists(name):
        staticfiles_storage.delete(name)


@app.task(trail=False)
def cleanup_project_backup_download() -> None:
    from weblate.trans.backups import PROJECTBACKUP_PREFIX  # noqa: PLC0415

    if not staticfiles_storage.exists(PROJECTBACKUP_PREFIX):
        return
    cutoff = timezone.now() - timedelta(hours=2)
    for name in staticfiles_storage.listdir(PROJECTBACKUP_PREFIX)[1]:
        full_name = os.path.join(PROJECTBACKUP_PREFIX, name)
        if staticfiles_storage.get_created_time(full_name) < cutoff:
            staticfiles_storage.delete(full_name)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    sender.add_periodic_task(3600, commit_pending.s(), name="commit-pending")
    sender.add_periodic_task(3600, update_remotes.s(), name="update-remotes")
    sender.add_periodic_task(3600, cleanup_repos.s(), name="cleanup-repos")
    sender.add_periodic_task(
        crontab(minute=30), daily_update_checks.s(), name="daily-update-checks"
    )
    sender.add_periodic_task(
        crontab(hour=3, minute=45), repository_alerts.s(), name="repository-alerts"
    )
    sender.add_periodic_task(3600, component_alerts.s(), name="component-alerts")
    sender.add_periodic_task(
        crontab(hour=0, minute=40), cleanup_suggestions.s(), name="suggestions-cleanup"
    )
    sender.add_periodic_task(
        crontab(hour=0, minute=40), cleanup_stale_repos.s(), name="cleanup-stale-repos"
    )
    sender.add_periodic_task(
        crontab(hour=0, minute=45),
        cleanup_old_suggestions.s(),
        name="cleanup-old-suggestions",
    )
    sender.add_periodic_task(
        crontab(hour=0, minute=50),
        cleanup_old_comments.s(),
        name="cleanup-old-comments",
    )
    sender.add_periodic_task(
        crontab(hour=2, minute=30),
        cleanup_project_backups.s(),
        name="cleanup-project-backups",
    )
    sender.add_periodic_task(
        3600,
        cleanup_project_backup_download.s(),
        name="cleanup-project-backup-download",
    )
