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


from django.utils.translation import gettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_DAILY, EVENT_POST_ADD
from weblate.addons.tasks import language_consistency
from weblate.lang.models import Language


class LangaugeConsistencyAddon(BaseAddon):
    events = (EVENT_DAILY, EVENT_POST_ADD)
    name = "weblate.consistency.languages"
    verbose = _("Language consistency")
    description = _(
        "Ensures all components within a project have translations for every added "
        "translated language by creating empty translations in languages that "
        "have unadded components."
    )
    icon = "language.svg"
    project_scope = True

    def daily(self, component):
        language_consistency.delay(
            component.project_id,
            list(
                Language.objects.filter(translation__component=component).values_list(
                    "pk", flat=True
                )
            ),
        )

    def post_add(self, translation):
        language_consistency.delay(
            translation.component.project_id,
            [translation.language_id],
        )
