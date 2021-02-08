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
from weblate.trans.models.component import ComponentLockTimeout
from weblate.utils.celery import app


@app.task(
    trail=False,
    autoretry_for=(Component.DoesNotExist, ComponentLockTimeout),
    retry_backoff=60,
)
def sync_terminology(pk: int, component: Optional[Component] = None):
    if component is None:
        component = Component.objects.get(pk=pk)
    project = component.project
    translations = list(component.translation_set.all())

    # Add missing languages
    language_ids = {translation.language_id for translation in translations}
    missing = (
        Language.objects.filter(translation__component__project=project)
        .exclude(pk__in=language_ids)
        .distinct()
    )
    for language in missing:
        translations.append(component.add_new_language(language, None))

    # Sync terminology
    for translation in component.translation_set.all():
        translation.sync_terminology()

    return {"component": pk}
