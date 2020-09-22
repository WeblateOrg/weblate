#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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
from shutil import rmtree
from time import time
from typing import List, Optional

from celery.schedules import crontab
from django.conf import settings
from django.db import transaction
from django.db.models import F
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
    Unit,
)
from weblate.utils.celery import app
from weblate.utils.data import data_dir
from weblate.utils.errors import report_error
from weblate.utils.files import remove_readonly
from weblate.vcs.base import RepositoryException


@app.task(
    trail=False, autoretry_for=(Timeout,), retry_backoff=600, retry_backoff_max=3600
)
def perform_update(cls, pk, auto=False):
    try:
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


@app.task(
    trail=False, autoretry_for=(Timeout,), retry_backoff=600, retry_backoff_max=3600
)
def commit_pending(hours=None, pks=None, logger=None):
    if pks is None:
        components = Component.objects.all()
    else:
        components = Component.objects.filter(translation__pk__in=pks).distinct()

    for component in components.prefetch():
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
            logger("Committing {0}".format(component))

        perform_commit.delay(component.pk, "commit_pending", None)


def cleanup_sources(project):
    """Remove stale source Unit objects."""
    for component in project.component_set.filter(template="").iterator():
        with transaction.atomic():
            translation = component.source_translation

            source_ids = (
                Unit.objects.filter(translation__component=component)
                .exclude(translation=translation)
                .values_list("id_hash", flat=True)
                .distinct()
            )

            translation.unit_set.exclude(id_hash__in=source_ids).delete()


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
    non_linked = Component.objects.with_repo()

    if settings.AUTO_UPDATE not in ("full", "remote", True, False):
        return

    for component in non_linked.iterator():
        perform_update.delay("Component", component.pk, auto=True)


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
            rmtree(path, onerror=remove_readonly)


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
        components = Component.objects.filter(pk__in=component_ids).iterator()
    else:
        components = Component.objects.iterator()
    for component in components:
        component.update_alerts()


@app.task(trail=False, autoretry_for=(Component.DoesNotExist,), retry_backoff=60)
def component_after_save(
    pk, changed_git, changed_setup, changed_template, changed_variant, skip_push
):
    component = Component.objects.get(pk=pk)
    component.after_save(
        changed_git, changed_setup, changed_template, changed_variant, skip_push
    )


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
        auto = AutoTranslate(
            user, Translation.objects.get(pk=translation_id), filter_type, mode
        )
        if auto_source == "mt":
            auto.process_mt(engines, threshold)
        else:
            auto.process_others(component)

        if auto.updated == 0:
            return _("Automatic translation completed, no strings were updated.")

        return (
            ngettext(
                "Automatic translation completed, %d string was updated.",
                "Automatic translation completed, %d strings were updated.",
                auto.updated,
            )
            % auto.updated
        )


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
        return None
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
