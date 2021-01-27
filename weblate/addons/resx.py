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

from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from translate.storage.resx import RESXFile

from weblate.addons.cleanup import BaseCleanupAddon


class ResxUpdateAddon(BaseCleanupAddon):
    name = "weblate.resx.update"
    verbose = _("Update RESX files")
    description = _(
        "Update all translation files to match the monolingual upstream base file. "
        "Unused strings are removed, and new ones added as copies of the source "
        "string."
    )
    icon = "refresh.svg"
    compat = {"file_format": {"resx"}}

    @cached_property
    def template_store(self):
        return self.instance.component.template_store.store

    @staticmethod
    def build_index(storage):
        index = {}

        for unit in storage.units:
            index[unit.getid()] = unit

        return index

    def build_indexes(self):
        index = self.build_index(self.template_store)
        if self.instance.component.intermediate:
            intermediate = self.build_index(
                self.instance.component.intermediate_store.store
            )
        else:
            intermediate = {}
        return index, intermediate

    @staticmethod
    def get_index(index, intermediate, translation):
        if intermediate and translation.is_source:
            return intermediate
        return index

    def update_resx(self, index, translation, storage, changes):
        """Filter obsolete units in RESX storage.

        This removes the corresponding XML element and also adds newly added, and
        changed units.
        """
        sindex = self.build_index(storage.store)
        changed = False

        # Add missing units
        for unit in self.template_store.units:
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
    def find_changes(index, storage):
        """Find changed string IDs in upstream repository."""
        result = set()

        for unit in storage.units:
            unitid = unit.getid()
            if unitid not in index:
                continue
            if unit.target != index[unitid].target:
                result.add(unitid)

        return result

    def update_translations(self, component, previous_head):
        index, intermediate = self.build_indexes()

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
