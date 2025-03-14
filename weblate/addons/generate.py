# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import F, Q
from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.forms import GenerateForm, PseudolocaleAddonForm
from weblate.checks.flags import Flags
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Translation
from weblate.utils.errors import report_error
from weblate.utils.render import render_template
from weblate.utils.state import (
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_READONLY,
    STATE_TRANSLATED,
)

if TYPE_CHECKING:
    from weblate.auth.models import User


class GenerateFileAddon(BaseAddon):
    events: set[AddonEvent] = {
        AddonEvent.EVENT_PRE_COMMIT,
    }
    name = "weblate.generate.generate"
    verbose = gettext_lazy("Statistics generator")
    description = gettext_lazy(
        "Generates a file containing detailed info about the translation status."
    )
    settings_form = GenerateForm
    multiple = True
    icon = "poll.svg"

    @classmethod
    def can_install(cls, component, user: User | None):
        if not component.translation_set.exists():
            return False
        return super().can_install(component, user)

    def pre_commit(self, translation, author: str, store_hash: bool) -> None:
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
    events: set[AddonEvent] = {
        AddonEvent.EVENT_COMPONENT_UPDATE,
        AddonEvent.EVENT_DAILY,
    }
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
        *,
        prefix: str = "",
        suffix: str = "",
        var_prefix: str = "",
        var_suffix: str = "",
        var_multiplier: float = 0.0,
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
            new_strings = []
            for source in source_strings:
                multi = int(var_multiplier * len(source))
                new_strings.append(
                    f"{prefix}{var_prefix * multi}{source}{var_suffix * multi}{suffix}"
                )
            target_strings = unit.get_target_plurals()
            if new_strings != target_strings or unit.state < STATE_TRANSLATED:
                unit.translate(
                    self.user,
                    new_strings,
                    target_state,
                    change_action=ActionEvents.AUTO,
                    propagate=False,
                )
                updated += 1
        if updated > 0:
            target_translation.invalidate_cache()
        return updated

    def daily(self, component) -> None:
        raise NotImplementedError

    def component_update(self, component) -> None:
        raise NotImplementedError


class PseudolocaleAddon(LocaleGenerateAddonBase):
    name = "weblate.generate.pseudolocale"
    verbose = gettext_lazy("Pseudolocale generation")
    description = gettext_lazy(
        "Generates a translation by adding prefix and suffix "
        "to source strings automatically."
    )
    settings_form = PseudolocaleAddonForm
    user_name = "pseudolocale"
    user_verbose = "Pseudolocale add-on"

    def daily(self, component) -> None:
        # Check all strings
        query = Q(state__lte=STATE_TRANSLATED)
        if self.instance.configuration.get("include_readonly", False):
            query |= Q(state=STATE_READONLY)
        self.do_update(component, query)

    def component_update(self, component) -> None:
        # Update only untranslated strings
        self.do_update(component, Q(state__lt=STATE_TRANSLATED))

    def get_target_translation(self, component):
        return component.translation_set.get(pk=self.instance.configuration["target"])

    def do_update(self, component, query) -> None:
        try:
            source_translation = component.translation_set.get(
                pk=self.instance.configuration["source"]
            )
            target_translation = self.get_target_translation(component)
        except Translation.DoesNotExist:
            # Uninstall misconfigured add-on
            report_error("add-on error", project=component.project)
            self.instance.disable()
            return
        var_multiplier = self.instance.configuration.get("var_multiplier")
        # As it is optional, it can be stored as None
        if var_multiplier is None:
            var_multiplier = 0.1
        self.generate_translation(
            source_translation,
            target_translation,
            prefix=self.instance.configuration.get("prefix", ""),
            suffix=self.instance.configuration.get("suffix", ""),
            var_prefix=self.instance.configuration.get("var_prefix", ""),
            var_suffix=self.instance.configuration.get("var_suffix", ""),
            var_multiplier=var_multiplier,
            query=query,
        )

    def post_uninstall(self) -> None:
        try:
            target_translation = self.get_target_translation(self.instance.component)
            flags = Flags(target_translation.check_flags)
            flags.remove("ignore-all-checks")
            target_translation.check_flags = flags.format()
            target_translation.save(update_fields=["check_flags"])
        except Translation.DoesNotExist:
            pass
        super().post_uninstall()

    def post_configure_run(self) -> None:
        super().post_configure_run()
        try:
            target_translation = self.get_target_translation(self.instance.component)
            flags = Flags(target_translation.check_flags)
            flags.merge("ignore-all-checks")
            target_translation.check_flags = flags.format()
            target_translation.save(update_fields=["check_flags"])
        except Translation.DoesNotExist:
            pass


class PrefillAddon(LocaleGenerateAddonBase):
    name = "weblate.generate.prefill"
    verbose = gettext_lazy("Prefill translation with source")
    description = gettext_lazy("Fills in translation strings with source string.")
    user_name = "prefill"
    user_verbose = "Prefill add-on"

    def daily(self, component) -> None:
        # Check all strings
        self.do_update(component)

    def component_update(self, component) -> None:
        # Update only untranslated strings
        self.do_update(component)

    def do_update(self, component) -> None:
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


class FillReadOnlyAddon(LocaleGenerateAddonBase):
    name = "weblate.generate.fill_read_only"
    verbose = gettext_lazy("Fill read-only strings with source")
    description = gettext_lazy(
        "Fills in translation of read-only strings with source string."
    )
    user_name = "fill"
    user_verbose = "Fill read-only add-on"

    def daily(self, component) -> None:
        self.do_update(component)

    def component_update(self, component) -> None:
        self.do_update(component)

    def do_update(self, component) -> None:
        source_translation = component.source_translation
        updated = 0
        for translation in component.translation_set.prefetch():
            if translation.is_source:
                continue
            updated += self.generate_translation(
                source_translation,
                translation,
                target_state=STATE_READONLY,
                query=Q(state=STATE_READONLY) & ~Q(target=F("source")),
            )
        if updated:
            component.commit_pending("add-on", None)
