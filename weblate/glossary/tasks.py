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
from typing import Optional

from weblate.lang.models import Language
from weblate.trans.models import Component
from weblate.utils.celery import app
from weblate.utils.lock import WeblateLockTimeout


@app.task(
    trail=False,
    autoretry_for=(Component.DoesNotExist, WeblateLockTimeout),
    retry_backoff=60,
)
def sync_glossary_languages(pk: int, component: Optional[Component] = None):
    """Add missing glossary languages."""
    if component is None:
        component = Component.objects.get(pk=pk)

    language_ids = set(component.translation_set.values_list("language_id", flat=True))
    missing = (
        Language.objects.filter(translation__component__project=component.project)
        .exclude(pk__in=language_ids)
        .distinct()
    )
    for language in missing:
        component.add_new_language(language, None, create_translations=False)
    if missing:
        component.create_translations(request=None)


@app.task(
    trail=False,
    autoretry_for=(Component.DoesNotExist, WeblateLockTimeout),
    retry_backoff=60,
)
def sync_terminology(pk: int, component: Optional[Component] = None):
    """Sync terminology and add missing glossary languages."""
    if component is None:
        component = Component.objects.get(pk=pk)

    sync_glossary_languages(pk, component)

    component.source_translation.sync_terminology()

    return {"component": pk}
