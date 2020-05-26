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

from datetime import date

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_COMPONENT_UPDATE, EVENT_DAILY
from weblate.addons.forms import AutoAddonForm
from weblate.trans.tasks import auto_translate


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
        self.daily(component)

    def daily(self, component):
        # Translate every component once in a week to reduce load
        if component.id % 7 != date.today().weekday():
            return

        for translation in component.translation_set.iterator():
            if translation.is_source:
                continue
            transaction.on_commit(
                lambda: auto_translate.delay(
                    None, translation.pk, **self.instance.configuration
                )
            )
