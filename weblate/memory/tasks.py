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

from django.db import transaction

from weblate.machinery.base import get_machinery_language
from weblate.memory.models import Memory
from weblate.utils.celery import app
from weblate.utils.state import STATE_TRANSLATED


@app.task(trail=False)
def import_memory(project_id, component_id=None):
    from weblate.trans.models import Project, Unit

    project = Project.objects.get(pk=project_id)

    components = project.component_set.all()
    if component_id:
        components = components.filter(id=component_id)

    for component in components.iterator():
        with transaction.atomic():
            units = Unit.objects.filter(
                translation__component=component, state__gte=STATE_TRANSLATED
            )
            if not component.intermediate:
                units = units.exclude(
                    translation__language_id=component.source_language_id
                )
            for unit in units.prefetch_related("translation", "translation__language"):
                update_memory(None, unit, component, project)


def update_memory(user, unit, component=None, project=None):
    component = component or unit.translation.component
    project = project or component.project
    params = {
        "source_language": get_machinery_language(component.source_language),
        "target_language": get_machinery_language(unit.translation.language),
        "source": unit.source,
        "target": unit.target,
        "origin": component.full_slug,
    }

    Memory.objects.update_entry(
        user=None, project=project, from_file=False, shared=False, **params
    )
    if project.contribute_shared_tm:
        Memory.objects.update_entry(
            user=None, project=None, from_file=False, shared=True, **params
        )
    if user:
        Memory.objects.update_entry(
            user=user, project=None, from_file=False, shared=False, **params
        )
