# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy
from translate.storage.resx import RESXFile

from weblate.addons.cleanup import BaseCleanupAddon

if TYPE_CHECKING:
    from weblate.trans.models import Component, Translation, Unit

    IndexType = dict[int, Unit]


class ResxUpdateAddon(BaseCleanupAddon):
    name = "weblate.resx.update"
    verbose = gettext_lazy("Update RESX files")
    description = gettext_lazy(
        "Update all translation files to match the monolingual upstream base file. "
        "Unused strings are removed, and new ones added as copies of the source "
        "string."
    )
    icon = "refresh.svg"
    compat = {"file_format": {"resx"}}

    @staticmethod
    def build_index(storage) -> IndexType:
        return {unit.getid(): unit for unit in storage.units}

    def build_indexes(self, component: Component):
        index = self.build_index(component.template_store.store)
        if component.intermediate:
            intermediate = self.build_index(component.intermediate_store.store)
        else:
            intermediate = {}
        return index, intermediate

    @staticmethod
    def get_index(index: IndexType, intermediate: IndexType, translation: Translation):
        if intermediate and translation.is_source:
            return intermediate
        return index

    def update_resx(
        self, index: IndexType, translation: Translation, storage, changes: set[int]
    ) -> None:
        """
        Filter obsolete units in RESX storage.

        This removes the corresponding XML element and also adds newly added, and
        changed units.
        """
        sindex = self.build_index(storage.store)
        changed = False

        # Add missing units
        for unit in translation.component.template_store.store.units:
            if unit.getid() not in sindex:
                storage.store.addunit(unit, True)
                changed = True

        # Remove extra units and apply target changes
        for unit in storage.store.units:
            unitid = unit.getid()
            if unitid not in index:
                storage.store.body.remove(unit.xmlelement)
                changed = True
            if unitid in changes:
                unit.target = index[unitid].target
                changed = True

        if changed:
            storage.save()

    @staticmethod
    def find_changes(index: IndexType, storage) -> set[int]:
        """Find changed string IDs in upstream repository."""
        result = set()

        for unit in storage.units:
            unitid = unit.getid()
            if unitid not in index:
                continue
            if unit.target != index[unitid].target:
                result.add(unitid)

        return result

    def update_translations(self, component: Component, previous_head: str) -> None:
        index, intermediate = self.build_indexes(component)

        if previous_head:
            content = component.repository.get_file(component.template, previous_head)
            changes = self.find_changes(index, RESXFile.parsestring(content))
        else:
            # No previous revision, probably first commit
            changes = set()
        for translation in self.iterate_translations(component):
            self.update_resx(
                self.get_index(index, intermediate, translation),
                translation,
                translation.store,
                changes,
            )
