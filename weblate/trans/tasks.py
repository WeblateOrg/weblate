# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from __future__ import absolute_import, unicode_literals

import os
from datetime import timedelta
from glob import glob
from shutil import rmtree
from time import time

from celery.schedules import crontab
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import override
from django.utils.translation import ugettext as _
from django.utils.translation import ungettext
from filelock import Timeout
from whoosh.index import EmptyIndexError

from weblate.auth.models import User, get_anonymous
from weblate.celery import app
from weblate.checks.models import Check
from weblate.lang.models import Language
from weblate.trans.autotranslate import AutoTranslate
from weblate.trans.exceptions import FileParseError
from weblate.trans.models import (
    Change,
    Comment,
    Component,
    Project,
    Source,
    Suggestion,
    Translation,
    Unit,
)
from weblate.trans.search import Fulltext
from weblate.utils.data import data_dir
from weblate.utils.files import remove_readonly


@app.task(
    trail=False, autoretry_for=(Timeout,), retry_backoff=600, retry_backoff_max=3600
)
def perform_update(cls, pk, auto=False):
    try:
        if cls == 'Project':
            obj = Project.objects.get(pk=pk)
        else:
            obj = Component.objects.get(pk=pk)

        if not auto or settings.AUTO_UPDATE:
            obj.do_update()
        else:
            obj.update_remote_branch()
    except FileParseError:
        # This is stored as alert, so we can silently ignore here
        return


@app.task(
    trail=False, autoretry_for=(Timeout,), retry_backoff=600, retry_backoff_max=3600
)
def perform_load(pk, *args):
    component = Component.objects.get(pk=pk)
    component.create_translations(*args)


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
            logger('Committing {0}'.format(component))

        perform_commit.delay(component.pk, 'commit_pending', None)


@app.task(trail=False)
def cleanup_fulltext():
    """Remove stale units from fulltext"""
    fulltext = Fulltext()
    languages = list(Language.objects.values_list('code', flat=True)) + [None]
    # We operate only on target indexes as they will have all IDs anyway
    for lang in languages:
        if lang is None:
            index = fulltext.get_source_index()
        else:
            index = fulltext.get_target_index(lang)
        try:
            fields = index.reader().all_stored_fields()
        except EmptyIndexError:
            continue
        for item in fields:
            if Unit.objects.filter(pk=item['pk']).exists():
                continue
            fulltext.clean_search_unit(item['pk'], lang)


@app.task(trail=False)
def optimize_fulltext():
    fulltext = Fulltext()
    index = fulltext.get_source_index()
    index.optimize()
    languages = Language.objects.have_translation()
    for lang in languages:
        index = fulltext.get_target_index(lang.code)
        index.optimize()


def cleanup_sources(project):
    """Remove stale Source objects."""
    for pk in project.component_set.values_list('id', flat=True):
        with transaction.atomic():
            source_ids = (
                Unit.objects.filter(translation__component_id=pk)
                .values('id_hash')
                .distinct()
            )

            Source.objects.filter(component_id=pk).exclude(
                id_hash__in=source_ids
            ).delete()


def cleanup_source_data(project):
    with transaction.atomic():
        # List all current unit content_hashs
        units = (
            Unit.objects.filter(translation__component__project=project)
            .values('content_hash')
            .distinct()
        )

        # Remove source comments and checks for deleted units
        for obj in Comment, Check:
            obj.objects.filter(language=None, project=project).exclude(
                content_hash__in=units
            ).delete()


def cleanup_language_data(project):
    for lang in Language.objects.iterator():
        with transaction.atomic():
            # List current unit content_hashs
            units = (
                Unit.objects.filter(
                    translation__language=lang, translation__component__project=project
                )
                .values('content_hash')
                .distinct()
            )

            # Remove checks, suggestions and comments for deleted units
            for obj in Check, Suggestion, Comment:
                obj.objects.filter(language=lang, project=project).exclude(
                    content_hash__in=units
                ).delete()


@app.task(trail=False)
def cleanup_project(pk):
    """Perform cleanup of project models."""
    try:
        project = Project.objects.get(pk=pk)
    except Project.DoesNotExist:
        return

    cleanup_sources(project)
    cleanup_source_data(project)
    cleanup_language_data(project)


@app.task(trail=False)
def cleanup_suggestions():
    # Process suggestions
    anonymous_user = get_anonymous()
    suggestions = Suggestion.objects.prefetch_related('project', 'language')
    for suggestion in suggestions.iterator():
        with transaction.atomic():
            # Remove suggestions with same text as real translation
            is_different = False
            # Do not rely on the SQL as MySQL compares strings case insensitive
            for unit in suggestion.related_units:
                if unit.target != suggestion.target or not unit.translated:
                    is_different = True
                    break

            if not is_different:
                suggestion.delete_log(
                    anonymous_user, change=Change.ACTION_SUGGESTION_CLEANUP
                )
                continue

            # Remove duplicate suggestions
            sugs = Suggestion.objects.filter(
                content_hash=suggestion.content_hash,
                language=suggestion.language,
                project=suggestion.project,
                target=suggestion.target,
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
    for component in non_linked.iterator():
        perform_update.delay('Component', component.pk, auto=True)


@app.task(trail=False)
def cleanup_stale_repos():
    prefix = data_dir('vcs')
    vcs_mask = os.path.join(prefix, '*', '*')

    yesterday = time() - 86400

    for path in glob(vcs_mask):
        if not os.path.isdir(path):
            continue

        # Skip recently modified paths
        if os.path.getmtime(path) > yesterday:
            continue

        # Parse path
        project, component = os.path.split(path[len(prefix) + 1:])

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
def repository_alerts(threshold=10):
    non_linked = Component.objects.with_repo()
    for component in non_linked.iterator():
        if component.repository.count_missing() > 10:
            component.add_alert('RepositoryOutdated', childs=True)
        else:
            component.delete_alert('RepositoryOutdated', childs=True)
        if component.repository.count_outgoing() > 10:
            component.add_alert('RepositoryChanges', childs=True)
        else:
            component.delete_alert('RepositoryChanges', childs=True)


@app.task(trail=False)
def component_alerts():
    for component in Component.objects.iterator():
        component.update_alerts()


@app.task(trail=False, autoretry_for=(Component.DoesNotExist,), retry_backoff=60)
def component_after_save(pk, changed_git, changed_setup, changed_template, skip_push):
    component = Component.objects.get(pk=pk)
    component.after_save(changed_git, changed_setup, changed_template, skip_push)


@app.task(trail=False)
def component_removal(pk, uid):
    user = User.objects.get(pk=uid)
    try:
        obj = Component.objects.get(pk=pk)
        Change.objects.create(
            project=obj.project,
            action=Change.ACTION_REMOVE_COMPONENT,
            target=obj.slug,
            user=user,
            author=user,
        )
        obj.delete()
    except Project.DoesNotExist:
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
    with override(user.profile.language if user else 'en'):
        auto = AutoTranslate(
            user,
            Translation.objects.get(pk=translation_id),
            filter_type,
            mode,
        )
        if auto_source == 'mt':
            auto.process_mt(engines, threshold)
        else:
            auto.process_others(component)

        if auto.updated == 0:
            return _('Automatic translation completed, no strings were updated.')

        return ungettext(
            'Automatic translation completed, %d string was updated.',
            'Automatic translation completed, %d strings were updated.',
            auto.updated,
        ) % auto.updated


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(3600, commit_pending.s(), name='commit-pending')
    sender.add_periodic_task(
        crontab(hour=3, minute=30), update_remotes.s(), name='update-remotes'
    )
    sender.add_periodic_task(3600 * 24, repository_alerts.s(), name='repository-alerts')
    sender.add_periodic_task(3600 * 24, component_alerts.s(), name='component-alerts')
    sender.add_periodic_task(
        3600 * 24, cleanup_suggestions.s(), name='suggestions-cleanup'
    )
    sender.add_periodic_task(
        3600 * 24, cleanup_stale_repos.s(), name='cleanup-stale-repos'
    )
    sender.add_periodic_task(
        3600 * 24, cleanup_old_suggestions.s(), name='cleanup-old-suggestions'
    )
    sender.add_periodic_task(
        3600 * 24, cleanup_old_comments.s(), name='cleanup-old-comments'
    )

    # Following fulltext maintenance tasks should not be
    # executed at same time
    sender.add_periodic_task(
        crontab(hour=2, minute=30, day_of_week='saturday'),
        cleanup_fulltext.s(),
        name='fulltext-cleanup',
    )
    sender.add_periodic_task(
        crontab(hour=2, minute=30, day_of_week='sunday'),
        optimize_fulltext.s(),
        name='fulltext-optimize',
    )
