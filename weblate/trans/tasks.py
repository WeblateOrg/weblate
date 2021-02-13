#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
import os
from datetime import date, timedelta
from glob import glob
from time import time
from typing import List, Optional

from celery import current_task
from celery.schedules import crontab
from django.conf import settings
from django.db import transaction
from django.db.models import Count, F
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext, override
from filelock import Timeout

from weblate.addons.models import Addon
from weblate.auth.models import User, get_anonymous
from weblate.lang.models import Language
from weblate.trans.autotranslate import AutoTranslate
from weblate.trans.exceptions import FileParseError
from weblate.trans.models import (
    Change,
    Comment,
    Component,
    Project,
    Suggestion,
    Translation,
)
from weblate.utils.celery import app
from weblate.utils.data import data_dir
from weblate.utils.errors import report_error
from weblate.utils.files import remove_tree
from weblate.utils.stats import prefetch_stats
from weblate.vcs.base import RepositoryException


@app.task(
    trail=False, autoretry_for=(Timeout,), retry_backoff=600, retry_backoff_max=3600
)
def perform_update(cls, pk, auto=False, obj=None):
    try:
        if obj is None:
            if cls == "Project":
                obj = Project.objects.get(pk=pk)
            else:
                obj = Component.objects.get(pk=pk)
        if settings.AUTO_UPDATE in ("full", True) or not auto:
            obj.do_update()
        else:
            obj.update_remote_branch()
    except FileParseError:
        # This is stored as alert, so we can silently ignore here
        return


@app.task(
    trail=False, autoretry_for=(Timeout,), retry_backoff=600, retry_backoff_max=3600
)
def perform_load(
    pk: int,
    force: bool = False,
    langs: Optional[List[str]] = None,
    changed_template: bool = False,
    from_link: bool = False,
):
    component = Component.objects.get(pk=pk)
    component.create_translations(
        force=force, langs=langs, changed_template=changed_template, from_link=from_link
    )


@app.task(
    trail=False, autoretry_for=(Timeout,), retry_backoff=600, retry_backoff_max=3600
)
def perform_commit(pk, *args):
    component = Component.objects.get(pk=pk)
    component.commit_pending(*args)


@app.task(
    trail=False, autoretry_for=(Timeout,), retry_backoff=600, retry_backoff_max=3600
)
def perform_push(pk, *args, **kwargs):
    component = Component.objects.get(pk=pk)
    component.do_push(*args, **kwargs)


@app.task(trail=False)
def update_component_stats(pk):
    component = Component.objects.get(pk=pk)
    component.stats.ensure_basic()


@app.task(
    trail=False, autoretry_for=(Timeout,), retry_backoff=600, retry_backoff_max=3600
)
def commit_pending(hours=None, pks=None, logger=None):
    if pks is None:
        components = Component.objects.all()
    else:
        components = Component.objects.filter(translation__pk__in=pks).distinct()

    for component in prefetch_stats(components.prefetch()):
        if hours is None:
            age = timezone.now() - timedelta(hours=component.commit_pending_age)
        else:
            age = timezone.now() - timedelta(hours=hours)

        last_change = component.stats.last_changed
        if not last_change:
            continue
        if last_change > age:
            continue

        if not component.needs_commit():
            continue

        if logger:
            logger(f"Committing {component}")

        perform_commit.delay(component.pk, "commit_pending", None)


def cleanup_sources(project):
    """Remove stale source Unit objects."""
    for component in project.component_set.filter(template="").iterator():
        translation = component.source_translation
        # Skip translations with a filename (eg. when POT file is present)
        if translation.filename:
            continue
        with transaction.atomic():
            # Remove all units where there is just one referenced unit (self)
            translation.unit_set.annotate(Count("unit")).filter(
                unit__count__lte=1
            ).delete()


@app.task(trail=False)
def cleanup_project(pk):
    """Perform cleanup of project models."""
    try:
        project = Project.objects.get(pk=pk)
    except Project.DoesNotExist:
        return

    cleanup_sources(project)


@app.task(trail=False)
def cleanup_suggestions():
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
                    anonymous_user, change=Change.ACTION_SUGGESTION_CLEANUP
                )
                continue

            # Remove duplicate suggestions
            sugs = Suggestion.objects.filter(
                unit=suggestion.unit, target=suggestion.target
            ).exclude(id=suggestion.id)
            # Do not rely on the SQL as MySQL compares strings case insensitive
            for other in sugs:
                if other.target == suggestion.target:
                    suggestion.delete_log(
                        anonymous_user, change=Change.ACTION_SUGGESTION_CLEANUP
                    )
                    break


@app.task(trail=False)
def update_remotes():
    """Update all remote branches (without attempt to merge)."""
    if settings.AUTO_UPDATE not in ("full", "remote", True, False):
        return

    for component in Component.objects.with_repo().iterator():
        perform_update("Component", -1, auto=True, obj=component)


@app.task(trail=False)
def cleanup_stale_repos():
    prefix = data_dir("vcs")
    vcs_mask = os.path.join(prefix, "*", "*")

    yesterday = time() - 86400

    for path in glob(vcs_mask):
        if not os.path.isdir(path):
            continue

        # Skip recently modified paths
        if os.path.getmtime(path) > yesterday:
            continue

        # Parse path
        project, component = os.path.split(path[len(prefix) + 1 :])

        # Find matching components
        objects = Component.objects.with_repo().filter(
            slug=component, project__slug=project
        )

        # Remove stale dirs
        if not objects.exists():
            remove_tree(path)


@app.task(trail=False)
def cleanup_old_suggestions():
    if not settings.SUGGESTION_CLEANUP_DAYS:
        return
    cutoff = timezone.now() - timedelta(days=settings.SUGGESTION_CLEANUP_DAYS)
    Suggestion.objects.filter(timestamp__lt=cutoff).delete()


@app.task(trail=False)
def cleanup_old_comments():
    if not settings.COMMENT_CLEANUP_DAYS:
        return
    cutoff = timezone.now() - timedelta(days=settings.COMMENT_CLEANUP_DAYS)
    Comment.objects.filter(timestamp__lt=cutoff).delete()


@app.task(trail=False)
def repository_alerts(threshold=settings.REPOSITORY_ALERT_THRESHOLD):
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
        except RepositoryException as error:
            report_error(cause="Could not check repository status")
            component.add_alert("MergeFailure", error=component.error_text(error))


@app.task(trail=False)
def component_alerts(component_ids=None):
    if component_ids:
        components = Component.objects.filter(pk__in=component_ids)
    else:
        components = Component.objects.all()
    for component in components.prefetch():
        component.update_alerts()


@app.task(trail=False, autoretry_for=(Component.DoesNotExist,), retry_backoff=60)
def component_after_save(
    pk, changed_git, changed_setup, changed_template, changed_variant, skip_push, create
):
    component = Component.objects.get(pk=pk)
    component.after_save(
        changed_git, changed_setup, changed_template, changed_variant, skip_push, create
    )
    return {"component": pk}


@app.task(trail=False)
def component_removal(pk, uid):
    user = User.objects.get(pk=uid)
    try:
        obj = Component.objects.get(pk=pk)
        obj.acting_user = user
        Change.objects.create(
            project=obj.project,
            action=Change.ACTION_REMOVE_COMPONENT,
            target=obj.slug,
            user=user,
            author=user,
        )
        obj.delete()
        if obj.allow_translation_propagation:
            components = obj.project.component_set.filter(
                allow_translation_propagation=True
            ).exclude(pk=obj.pk)
            for component_id in components.values_list("id", flat=True):
                update_checks.delay(component_id)
    except Component.DoesNotExist:
        return


@app.task(trail=False)
def project_removal(pk, uid):
    user = User.objects.get(pk=uid)
    try:
        obj = Project.objects.get(pk=pk)
        Change.objects.create(
            action=Change.ACTION_REMOVE_PROJECT, target=obj.slug, user=user, author=user
        )
        obj.delete()
    except Project.DoesNotExist:
        return


@app.task(trail=False)
def auto_translate(
    user_id,
    translation_id,
    mode,
    filter_type,
    auto_source,
    component,
    engines,
    threshold,
):
    if user_id:
        user = User.objects.get(pk=user_id)
    else:
        user = None
    with override(user.profile.language if user else "en"):
        translation = Translation.objects.get(pk=translation_id)
        translation.log_info(
            "starting automatic translation %s: %s: %s",
            current_task.request.id,
            auto_source,
            ", ".join(engines) if engines else component,
        )
        auto = AutoTranslate(user, translation, filter_type, mode)
        if auto_source == "mt":
            auto.process_mt(engines, threshold)
        else:
            auto.process_others(component)
        translation.log_info("completed automatic translation")

        if auto.updated == 0:
            message = _("Automatic translation completed, no strings were updated.")
        else:
            message = (
                ngettext(
                    "Automatic translation completed, %d string was updated.",
                    "Automatic translation completed, %d strings were updated.",
                    auto.updated,
                )
                % auto.updated
            )
        return {"translation": translation_id, "message": message}


@app.task(trail=False)
def create_component(addons_from=None, in_task=False, **kwargs):
    kwargs["project"] = Project.objects.get(pk=kwargs["project"])
    kwargs["source_language"] = Language.objects.get(pk=kwargs["source_language"])
    component = Component.objects.create(**kwargs)
    Change.objects.create(action=Change.ACTION_CREATE_COMPONENT, component=component)
    if addons_from:
        addons = Addon.objects.filter(
            component__pk=addons_from, project_scope=False, repo_scope=False
        )
        for addon in addons:
            # Avoid installing duplicate addons
            if component.addon_set.filter(name=addon.name).exists():
                continue
            if not addon.addon.can_install(component, None):
                continue
            addon.addon.create(component, configuration=addon.configuration)
    if in_task:
        return {"component": component.id}
    return component


@app.task(trail=False)
def update_checks(pk):
    component = Component.objects.get(pk=pk)
    for translation in component.translation_set.exclude(
        pk=component.source_translation.pk
    ).iterator():
        for unit in translation.unit_set.iterator():
            unit.run_checks()
    for unit in component.source_translation.unit_set.iterator():
        unit.run_checks()
    for translation in component.translation_set.iterator():
        translation.invalidate_cache()


@app.task(trail=False)
def daily_update_checks():
    # Update every component roughly once in a month
    components = Component.objects.annotate(idmod=F("id") % 30).filter(
        idmod=date.today().day
    )
    for component_id in components.values_list("id", flat=True):
        update_checks.delay(component_id)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(3600, commit_pending.s(), name="commit-pending")
    sender.add_periodic_task(
        crontab(hour=3, minute=30), update_remotes.s(), name="update-remotes"
    )
    sender.add_periodic_task(
        crontab(hour=0, minute=30), daily_update_checks.s(), name="daily-update-checks"
    )
    sender.add_periodic_task(3600 * 24, repository_alerts.s(), name="repository-alerts")
    sender.add_periodic_task(3600 * 24, component_alerts.s(), name="component-alerts")
    sender.add_periodic_task(
        3600 * 24, cleanup_suggestions.s(), name="suggestions-cleanup"
    )
    sender.add_periodic_task(
        3600 * 24, cleanup_stale_repos.s(), name="cleanup-stale-repos"
    )
    sender.add_periodic_task(
        3600 * 24, cleanup_old_suggestions.s(), name="cleanup-old-suggestions"
    )
    sender.add_periodic_task(
        3600 * 24, cleanup_old_comments.s(), name="cleanup-old-comments"
    )
