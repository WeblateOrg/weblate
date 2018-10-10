# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from datetime import timedelta
from glob import glob
import os
from shutil import rmtree
from time import time

from celery.schedules import crontab

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from whoosh.index import EmptyIndexError

from weblate.auth.models import get_anonymous
from weblate.celery import app

from weblate.checks.models import Check

from weblate.lang.models import Language

from weblate.trans.models import (
    Suggestion, Comment, Unit, Project, Translation, Source, Component,
    Change,
)
from weblate.trans.search import Fulltext
from weblate.utils.data import data_dir
from weblate.utils.files import remove_readonly


@app.task
def perform_update(cls, pk):
    if cls == 'Project':
        obj = Project.objects.get(pk=pk)
    else:
        obj = Component.objects.get(pk=pk)

    obj.do_update()


@app.task
def perform_load(pk, *args):
    component = Component.objects.get(pk=pk)
    component.create_translations(*args)


@app.task
def perform_commit(pk, *args):
    translation = Translation.objects.get(pk=pk)
    translation.commit_pending(*args)


@app.task
def commit_pending(hours=None, pks=None, logger=None):
    if pks is None:
        translations = Translation.objects.all()
    else:
        translations = Translation.objects.filter(pk__in=pks)

    for translation in translations.prefetch():
        if not translation.repo_needs_commit():
            continue

        if hours is None:
            age = timezone.now() - timedelta(
                hours=translation.component.commit_pending_age
            )

        last_change = translation.stats.last_changed
        if not last_change:
            continue
        if last_change > age:
            continue

        if logger:
            logger('Committing {0}'.format(translation))

        perform_commit.delay(translation.pk, 'commit_pending', None)


@app.task
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


@app.task
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
            source_ids = Unit.objects.filter(
                translation__component_id=pk
            ).values('id_hash').distinct()

            Source.objects.filter(
                component_id=pk
            ).exclude(
                id_hash__in=source_ids
            ).delete()


def cleanup_source_data(project):
    with transaction.atomic():
        # List all current unit content_hashs
        units = Unit.objects.filter(
            translation__component__project=project
        ).values('content_hash').distinct()

        # Remove source comments and checks for deleted units
        for obj in Comment, Check:
            obj.objects.filter(
                language=None, project=project
            ).exclude(
                content_hash__in=units
            ).delete()


def cleanup_language_data(project):
    for lang in Language.objects.all():
        with transaction.atomic():
            # List current unit content_hashs
            units = Unit.objects.filter(
                translation__language=lang,
                translation__component__project=project
            ).values('content_hash').distinct()

            # Remove checks, suggestions and comments for deleted units
            for obj in Check, Suggestion, Comment:
                obj.objects.filter(
                    language=lang, project=project
                ).exclude(
                    content_hash__in=units
                ).delete()


@app.task
def cleanup_project(pk):
    """Perform cleanup of project models."""
    project = Project.objects.get(pk=pk)

    cleanup_sources(project)
    cleanup_source_data(project)
    cleanup_language_data(project)


@app.task
def cleanup_suggestions():
    # Process suggestions
    anonymous_user = get_anonymous()
    suggestions = Suggestion.objects.prefetch_related('project', 'language')
    for suggestion in suggestions.iterator():
        with transaction.atomic():
            # Remove suggestions with same text as real translation
            units = Unit.objects.filter(
                content_hash=suggestion.content_hash,
                translation__language=suggestion.language,
                translation__component__project=suggestion.project,
            )

            if not units.exclude(target=suggestion.target).exists():
                suggestion.delete_log(
                    anonymous_user,
                    change=Change.ACTION_SUGGESTION_CLEANUP
                )
                continue

            # Remove duplicate suggestions
            sugs = Suggestion.objects.filter(
                content_hash=suggestion.content_hash,
                language=suggestion.language,
                project=suggestion.project,
                target=suggestion.target
            ).exclude(
                id=suggestion.id
            )
            if sugs.exists():
                suggestion.delete_log(
                    anonymous_user,
                    change=Change.ACTION_SUGGESTION_CLEANUP
                )


@app.task
def update_remotes():
    """Update all remote branches (without attempt to merge)."""
    non_linked = Component.objects.exclude(repo__startswith='weblate:')
    for component in non_linked.iterator():
        if settings.AUTO_UPDATE:
            component.do_update()
        else:
            component.update_remote_branch()


@app.task
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
        objects = Component.objects.filter(
            slug=component,
            project__slug=project
        ).exclude(
            repo__startswith='weblate:'
        )

        # Remove stale dirs
        if not objects.exists():
            rmtree(path, onerror=remove_readonly)


@app.task
def cleanup_old_suggestions():
    if not settings.SUGGESTION_CLEANUP_DAYS:
        return
    cutoff = timezone.now() - timedelta(days=settings.SUGGESTION_CLEANUP_DAYS)
    Suggestion.objects.filter(timestamp__lt=cutoff).delete()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        3600,
        commit_pending.s(),
        name='commit-pending',
    )
    sender.add_periodic_task(
        3600 * 24,
        update_remotes.s(),
        name='update-remotes',
    )
    sender.add_periodic_task(
        3600 * 24,
        cleanup_suggestions.s(),
        name='suggestions-cleanup',
    )
    sender.add_periodic_task(
        3600 * 24,
        cleanup_stale_repos.s(),
        name='cleanup-stale-repos',
    )
    sender.add_periodic_task(
        3600 * 24,
        cleanup_old_suggestions.s(),
        name='cleanup-old-suggestions',
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
