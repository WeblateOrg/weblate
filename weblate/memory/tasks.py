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

import os.path
from time import sleep

from celery_batches import Batches

from django.utils.encoding import force_text

from whoosh.index import LockError

from weblate.celery import app
from weblate.memory.storage import (
    TranslationMemory, CATEGORY_USER_OFFSET, CATEGORY_SHARED,
    CATEGORY_PRIVATE_OFFSET,
)
from weblate.utils.celery import extract_batch_kwargs
from weblate.utils.data import data_dir
from weblate.utils.state import STATE_TRANSLATED


@app.task
def memory_backup(indent=2):
    filename = os.path.join(data_dir('backups'), 'memory.json')
    memory = TranslationMemory()
    with open(filename, 'w') as handle:
        memory.dump(handle, indent)


@app.task
def import_memory(project_id):
    from weblate.trans.models import Unit
    units = Unit.objects.filter(
        translation__component__project_id=project_id,
        state__gte=STATE_TRANSLATED,
    )
    for unit in units.iterator():
        update_memory(None, unit)


def update_memory(user, unit):
    component = unit.translation.component
    project = component.project

    categories = [
        CATEGORY_PRIVATE_OFFSET + project.pk,
    ]
    if user:
        categories.append(CATEGORY_USER_OFFSET + user.id)
    if unit.translation.component.project.use_shared_tm:
        categories.append(CATEGORY_SHARED)

    for category in categories:
        update_memory_task.delay(
            source_language=project.source_language.code,
            target_language=unit.translation.language.code,
            source=unit.source,
            target=unit.target,
            origin=component.log_prefix,
            category=category,
        )


@app.task(base=Batches, flush_every=1000, flush_interval=300, bind=True)
def update_memory_task(self, *args, **kwargs):
    def fixup_strings(data):
        result = {}
        for key, value in data.items():
            if isinstance(value, int):
                result[key] = value
            else:
                result[key] = force_text(value)
        return result

    data = extract_batch_kwargs(*args, **kwargs)

    memory = TranslationMemory()
    try:
        with memory.writer() as writer:
            for item in data:
                writer.add_document(**fixup_strings(item))
    except LockError:
        # Manually handle retries, it doesn't work
        # with celery-batches
        sleep(10)
        for unit in data:
            update_memory_task.delay(**unit)


@app.task
def memory_optimize():
    memory = TranslationMemory()
    memory.index.optimize()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        3600 * 24,
        memory_backup.s(),
        name='translation-memory-backup',
    )
    sender.add_periodic_task(
        3600 * 24 * 7,
        memory_optimize.s(),
        name='translation-memory-optimize',
    )
