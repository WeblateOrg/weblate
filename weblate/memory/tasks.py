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

from celery_batches import Batches

from whoosh.index import LockError

from weblate.celery import app
from weblate.memory.storage import (
    TranslationMemory, CATEGORY_USER, CATEGORY_SHARED, CATEGORY_PRIVATE_OFFSET,
)
from weblate.utils.celery import extract_batch_kwargs
from weblate.utils.data import data_dir


@app.task
def memory_backup(indent=2):
    filename = os.path.join(data_dir('backups'), 'memory.json')
    memory = TranslationMemory()
    with open(filename, 'w') as handle:
        memory.dump(handle, indent)


def update_memory(user, unit):
    categories = [(CATEGORY_USER, user.username)]
    component = unit.translation.component
    project = component.project
    if unit.translation.component.project.use_shared_tm:
        categories.append((CATEGORY_SHARED, component.log_prefix))
    else:
        categories.append((
            CATEGORY_PRIVATE_OFFSET + project.pk, component.log_prefix
        ))

    for category, origin in categories:
        update_memory_task.delay(
            source_language=project.source_language.code,
            target_language=unit.translation.language.code,
            source=unit.source,
            target=unit.target,
            origin=origin,
            category=category,
        )


@app.task(
    base=Batches, flush_every=1000, flush_interval=300, bind=True,
    max_retries=1000
)
def update_memory_task(self, *args, **kwargs):
    data = extract_batch_kwargs(*args, **kwargs)

    memory = TranslationMemory()
    try:
        with memory.writer() as writer:
            for item in data:
                writer.add_document(**item)
    except LockError as exc:
        raise self.retry(exc=exc)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        3600 * 24,
        memory_backup.s(),
        name='translation-memory-backup',
    )
