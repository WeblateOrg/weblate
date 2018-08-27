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

from celery import shared_task

from django.utils import timezone

from weblate.trans.models import Project, Component, Translation


@shared_task
def perform_update(cls, pk):
    if cls == 'Project':
        obj = Project.objects.get(pk=pk)
    else:
        obj = Component.objects.get(pk=pk)

    obj.do_update()


@shared_task
def perform_load(pk, *args):
    component = Component.objects.get(pk=pk)
    component.create_translations(*args)


@shared_task
def perform_commit(pk, *args):
    translation = Translation.objects.get(pk=pk)
    translation.commit_pending(*args)


@shared_task
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

        last_change = translation.last_change
        if last_change is None:
            continue
        if last_change > age:
            continue

        if logger:
            logger('Committing {0}'.format(translation))

        perform_commit.delay(translation.pk, 'commit_pending', None)
