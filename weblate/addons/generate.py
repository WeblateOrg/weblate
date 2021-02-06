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

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_COMPONENT_UPDATE, EVENT_DAILY, EVENT_PRE_COMMIT
from weblate.addons.forms import GenerateForm, PseudolocaleAddonForm
from weblate.trans.models import Change
from weblate.utils.render import render_template
from weblate.utils.state import STATE_TRANSLATED


class GenerateFileAddon(BaseAddon):
    events = (EVENT_PRE_COMMIT,)
    name = "weblate.generate.generate"
    verbose = _("Statistics generator")
    description = _(
        "Generates a file containing detailed info about the translation status."
    )
    settings_form = GenerateForm
    multiple = True
    icon = "poll.svg"

    @classmethod
    def can_install(cls, component, user):
        if not component.translation_set.exists():
            return False
        return super().can_install(component, user)

    def pre_commit(self, translation, author):
        filename = self.render_repo_filename(
            self.instance.configuration["filename"], translation
        )
        if not filename:
            return
        content = render_template(
            self.instance.configuration["template"], translation=translation
        )
        with open(filename, "w") as handle:
            handle.write(content)
        translation.addon_commit_files.append(filename)


class PseudolocaleAddon(BaseAddon):
    events = (EVENT_COMPONENT_UPDATE, EVENT_DAILY)
    name = "weblate.generate.pseudolocale"
    verbose = _("Pseudolocale generation")
    description = _(
        "Generates a translation by adding prefix and suffix "
        "to source strings automatically."
    )
    settings_form = PseudolocaleAddonForm
    icon = "language.svg"

    def fetch_strings(self, component, key: str, query):
        translation = component.translation_set.get(pk=self.instance.configuration[key])
        return translation, {
            unit.source_unit_id: unit for unit in translation.unit_set.filter(query)
        }

    def do_update(self, component, query):
        updated = 0
        prefix = self.instance.configuration["prefix"]
        suffix = self.instance.configuration["suffix"]
        _source_translation, sources = self.fetch_strings(
            component, "source", Q(state__gte=STATE_TRANSLATED)
        )
        target_translation, targets = self.fetch_strings(component, "target", query)
        for source_id, unit in targets.items():
            if source_id not in sources:
                continue
            source_strings = sources[source_id].get_target_plurals(
                target_translation.plural.number
            )
            new_strings = [f"{prefix}{source}{suffix}" for source in source_strings]
            target_strings = unit.get_target_plurals()
            if new_strings != target_strings or unit.state < STATE_TRANSLATED:
                unit.translate(
                    None,
                    new_strings,
                    STATE_TRANSLATED,
                    change_action=Change.ACTION_AUTO,
                )
                updated += 1
        if updated > 0:
            target_translation.invalidate_cache()

    def daily(self, component):
        # Check all strings
        self.do_update(component, Q(state__lte=STATE_TRANSLATED))

    def component_update(self, component):
        # Update only non translated strings
        self.do_update(component, Q(state__lt=STATE_TRANSLATED))
