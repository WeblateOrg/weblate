# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Translate Toolkit based file-format wrappers for multi string support."""

from __future__ import annotations

from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy

from weblate.checks.flags import Flags
from weblate.trans.util import get_string

from .base import TranslationUnit
from .ttkit import CSVUtf8Format


class MultiUnit(TranslationUnit):
    def __init__(self, parent, unit, template=None):
        super().__init__(parent, None, None)
        self.units = [unit]

    def merge(self, unit):
        self.units.append(unit)
        self._invalidate_target()

    @cached_property
    def locations(self):
        return ", ".join(unit.locations for unit in self.units)

    @cached_property
    def source(self):
        return get_string(unit.source for unit in self.units)

    @cached_property
    def target(self):
        return get_string(unit.target for unit in self.units)

    @cached_property
    def context(self):
        # Context should be same for all units
        return self.units[0].context

    @cached_property
    def id_hash(self):
        # Hash should be same for all units
        return self.units[0].id_hash

    @cached_property
    def notes(self):
        return "\n".join(unit.notes for unit in self.units if unit.notes)

    def is_translated(self):
        return any(unit.is_translated() for unit in self.units)

    def is_fuzzy(self, fallback=False):
        return any(unit.is_fuzzy(fallback) for unit in self.units)

    def has_content(self):
        return any(unit.has_content() for unit in self.units)

    def is_readonly(self):
        return any(unit.is_readonly() for unit in self.units)

    def set_target(self, target: str | list[str]):
        """Set translation unit target."""
        self._invalidate_target()

        # Mare sure we have a list
        if isinstance(target, str):
            target = [target]

        # Remove any extra units
        while len(target) < len(self.units):
            last = self.units.pop()
            self.parent.store.removeunit(last.unit)

        # Add missing units
        while len(target) > len(self.units):
            new = self.parent.create_unit(self.context, self.units[0].source)
            self.units.append(
                self.parent.unit_class(self.parent, new, self.units[0].template)
            )
            self.parent.store.addunit(new)

        for i, value in enumerate(target):
            self.units[i].set_target(value)

    def set_state(self, state):
        for unit in self.units:
            unit.set_state(state)

    @cached_property
    def flags(self):
        flags = Flags()
        for unit in self.units:
            flags.merge(unit.flags)
        return flags.format()

    def has_unit(self) -> bool:
        return all(unit.has_unit() for unit in self.units)

    def clone_template(self):
        for unit in self.units:
            if not unit.has_unit():
                unit.clone_template()

    def untranslate(self, language):
        for unit in self.units:
            unit.untranslate(language)


class MultiFormatMixin:
    has_multiple_strings: bool = True

    def merge_multi(self, iterable):
        result = {}
        for unit in iterable:
            id_hash = unit.id_hash
            if id_hash in result:
                result[id_hash].merge(unit)
            else:
                if not isinstance(unit, MultiUnit):
                    unit = MultiUnit(unit.parent, unit)
                result[id_hash] = unit
        return list(result.values())

    @cached_property
    def template_units(self):
        return self.merge_multi(super().template_units)

    def _get_all_bilingual_units(self):
        return self.merge_multi(super()._get_all_bilingual_units())

    def _build_monolingual_unit(self, unit):
        try:
            matching = self._template_index[unit.id_hash]
        except KeyError:
            return MultiUnit(self, self.unit_class(self, None, unit.units[0].template))
        matching_units = [unit.template for unit in matching.units]
        result = MultiUnit(
            self, self.unit_class(self, matching_units[0], unit.units[0].template)
        )
        for extra in matching_units[1:]:
            result.merge(self.unit_class(self, extra, unit.units[0].template))
        return result

    def _get_all_monolingual_units(self):
        return self.merge_multi(super()._get_all_monolingual_units())


class MultiCSVUtf8Format(MultiFormatMixin, CSVUtf8Format):
    name = gettext_lazy("Multivalue CSV file (UTF-8)")
    format_id = "csv-multi-utf-8"
