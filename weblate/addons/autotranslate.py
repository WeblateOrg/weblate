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

from datetime import date

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_COMPONENT_UPDATE, EVENT_DAILY
from weblate.addons.forms import AutoAddonForm
from weblate.trans.tasks import auto_translate_component


class AutoTranslateAddon(BaseAddon):
    events = (EVENT_COMPONENT_UPDATE, EVENT_DAILY)
    name = "weblate.autotranslate.autotranslate"
    verbose = _("Automatic translation")
    description = _(
        "Automatically translates strings using machine translation or "
        "other components."
    )
    settings_form = AutoAddonForm
    multiple = True
    icon = "language.svg"

    def component_update(self, component):
        transaction.on_commit(
            lambda: auto_translate_component.delay(
                component.pk, **self.instance.configuration
            )
        )

    def daily(self, component):
        # Translate every component less frequenctly to reduce load.
        # The translation is anyway triggered on update, so it should
        # not matter that much that we run this less often.
        if settings.BACKGROUND_TASKS == "never":
            return
        today = date.today()
        if settings.BACKGROUND_TASKS == "monthly" and component.id % 30 != today.day:
            return
        if (
            settings.BACKGROUND_TASKS == "weekly"
            and component.id % 7 != today.weekday()
        ):
            return

        self.component_update(component)
