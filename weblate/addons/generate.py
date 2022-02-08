#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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
from weblate.utils.state import STATE_EMPTY, STATE_FUZZY, STATE_TRANSLATED


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


class LocaleGenerateAddonBase(BaseAddon):
    events = (EVENT_COMPONENT_UPDATE, EVENT_DAILY)
    multiple = True
    icon = "language.svg"

    def fetch_strings(self, translation, query):
        return {
            unit.source_unit_id: unit for unit in translation.unit_set.filter(query)
        }

    def generate_translation(
        self,
        source_translation,
        target_translation,
        query,
        prefix: str = "",
        suffix: str = "",
        target_state: int = STATE_TRANSLATED,
    ):
        updated = 0
        sources = self.fetch_strings(source_translation, Q(state__gte=STATE_TRANSLATED))
        targets = self.fetch_strings(target_translation, query)
        for source_id, unit in targets.items():
            if source_id not in sources:
                continue
            source_strings = sources[source_id].get_target_plurals(
                target_translation.plural.number
            )
            last_string = ""
            for i, source_string in enumerate(source_strings):
                if source_string:
                    last_string = source_string
                else:
                    source_strings[i] = last_string
            new_strings = [f"{prefix}{source}{suffix}" for source in source_strings]
            target_strings = unit.get_target_plurals()
            if new_strings != target_strings or unit.state < STATE_TRANSLATED:
                unit.translate(
                    None,
                    new_strings,
                    target_state,
                    change_action=Change.ACTION_AUTO,
                )
                updated += 1
        if updated > 0:
            target_translation.invalidate_cache()
        return updated

    def daily(self, component):
        raise NotImplementedError()

    def component_update(self, component):
        raise NotImplementedError()


class PseudolocaleAddon(LocaleGenerateAddonBase):
    name = "weblate.generate.pseudolocale"
    verbose = _("Pseudolocale generation")
    description = _(
        "Generates a translation by adding prefix and suffix "
        "to source strings automatically."
    )
    settings_form = PseudolocaleAddonForm

    def daily(self, component):
        # Check all strings
        self.do_update(component, Q(state__lte=STATE_TRANSLATED))

    def component_update(self, component):
        # Update only untranslated strings
        self.do_update(component, Q(state__lt=STATE_TRANSLATED))

    def do_update(self, component, query):
        self.generate_translation(
            component.translation_set.get(pk=self.instance.configuration["source"]),
            component.translation_set.get(pk=self.instance.configuration["target"]),
            prefix=self.instance.configuration["prefix"],
            suffix=self.instance.configuration["suffix"],
            query=query,
        )


class PrefillAddon(LocaleGenerateAddonBase):
    name = "weblate.generate.prefill"
    verbose = _("Prefill translation with source")
    description = _("Fills in translation strings with source string.")

    def daily(self, component):
        # Check all strings
        self.do_update(component)

    def component_update(self, component):
        # Update only untranslated strings
        self.do_update(component)

    def do_update(self, component):
        source_translation = component.source_translation
        updated = 0
        for translation in component.translation_set.prefetch():
            if translation.is_source:
                continue
            updated += self.generate_translation(
                source_translation,
                translation,
                target_state=STATE_FUZZY,
                query=Q(state=STATE_EMPTY),
            )
        if updated:
            component.commit_pending("add-on", None)
