# -*- coding: utf-8 -*-
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
from time import sleep

from celery.schedules import crontab
from celery_batches import Batches
from django.utils.encoding import force_str
from whoosh.index import LockError

from weblate.memory.models import Memory
from weblate.memory.storage import TranslationMemory
from weblate.utils.celery import app, extract_batch_kwargs
from weblate.utils.data import data_dir
from weblate.utils.state import STATE_TRANSLATED


@app.task(trail=False)
def memory_backup(indent=2):
    if not os.path.exists(data_dir("backups")):
        os.makedirs(data_dir("backups"))
    filename = data_dir("backups", "memory.json")
    memory = TranslationMemory()
    with open(filename, "w") as handle:
        memory.dump(handle, indent)


@app.task(trail=False)
def import_memory(project_id, component_id=None):
    from weblate.trans.models import Project, Unit

    project = Project.objects.get(pk=project_id)

    components = project.component_set.all()
    if component_id:
        components = components.filter(id=component_id)

    for component in components.iterator():
        units = (
            Unit.objects.filter(
                translation__component=component, state__gte=STATE_TRANSLATED
            )
            .exclude(translation__language=project.source_language)
            .prefetch_related("translation__language")
        )
        for unit in units.iterator():
            update_memory(None, unit, component, project)


def update_memory(user, unit, component=None, project=None):
    component = component or unit.translation.component
    project = project or component.project
    params = {
        "source_language": project.source_language,
        "target_language": unit.translation.language,
        "source": unit.source,
        "target": unit.target,
        "origin": component.full_slug,
    }

    Memory.objects.get_or_create(
        user=None, project=project, from_file=False, shared=False, **params
    )
    if project.contribute_shared_tm:
        Memory.objects.get_or_create(
            user=None, project=None, from_file=False, shared=True, **params
        )
    if user:
        Memory.objects.get_or_create(
            user=user, project=None, from_file=False, shared=False, **params
        )


@app.task(trail=False, base=Batches, flush_every=1000, flush_interval=300, bind=True)
def update_memory_task(self, *args, **kwargs):
    def fixup_strings(data):
        result = {}
        for key, value in data.items():
            if isinstance(value, int):
                result[key] = value
            else:
                result[key] = force_str(value)
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


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        crontab(hour=1, minute=0), memory_backup.s(), name="translation-memory-backup"
    )
