# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from translate.storage.lisa import LISAfile
from translate.storage.resx import RESXFile

from weblate.addons.base import UpdateBaseAddon


class CleanupAddon(UpdateBaseAddon):
    name = 'weblate.cleanup.generic'
    verbose = _('Cleanup translation files')
    description = _(
        'Update all translation files to match the monolingual base file. '
        'For most file formats, this means removing stale translation keys '
        'no longer present in the base file.'
    )
    icon = 'eraser'

    @cached_property
    def template_store(self):
        return self.instance.component.template_store.store

    @classmethod
    def can_install(cls, component, user):
        if not component.has_template():
            return False
        return super(CleanupAddon, cls).can_install(component, user)

    @staticmethod
    def build_index(storage):
        index = {}

        for unit in storage.units:
            index[unit.getid()] = unit

        return index

    def update_units(self, index, translation, storage):
        """Filter obsolete units in storage.

        This does simple filtering of units list.
        """
        startlen = len(storage.units)

        # Remove extra units
        storage.units = [u for u in storage.units if u.getid() in index]

        if startlen != len(storage.units):
            storage.save()

    def update_lisa(self, index, translation, storage):
        """Filter obsolete units in LISA based storage.

        This removes the corresponding XML element.
        """
        changed = False

        # Remove extra units
        for unit in storage.units:
            if unit.getid() not in index:
                storage.body.remove(unit.xmlelement)
                changed = True

        if changed:
            storage.save()

    def update_resx(self, index, translation, storage, changes):
        """Filter obsolete units in RESX storage.

        This removes the corresponding XML element and
        also adds newly added units and changed ones.
        """
        sindex = self.build_index(storage)
        changed = False

        # Add missing units
        for unit in self.template_store.units:
            if unit.getid() not in sindex:
                storage.addunit(unit, True)
                changed = True

        # Remove extra units and apply target changes
        for unit in storage.units:
            unitid = unit.getid()
            if unitid not in index:
                storage.body.remove(unit.xmlelement)
                changed = True
            if unitid in changes:
                unit.target = index[unitid].target
                changed = True

        if changed:
            storage.save()

    @staticmethod
    def iterate_translations(component):
        for translation in component.translation_set.all():
            if translation.is_template:
                continue
            yield translation

    @staticmethod
    def find_changes(index, storage):
        """Find changed units in storage"""
        result = set()

        for unit in storage.units:
            unitid = unit.getid()
            if unitid not in index:
                continue
            if unit.target != index[unitid].target:
                result.add(unitid)

        return result

    def update_translations(self, component, previous_head):
        index = self.build_index(self.template_store)

        if isinstance(self.template_store, RESXFile):
            if previous_head:
                content = component.repository.get_file(
                    component.template, previous_head
                )
                changes = self.find_changes(
                    index,
                    RESXFile.parsestring(content)
                )
            else:
                # No previous revision, probably first commit
                changes = set()
            for translation in self.iterate_translations(component):
                self.update_resx(
                    index, translation, translation.store.store, changes
                )
        elif isinstance(self.template_store, LISAfile):
            for translation in self.iterate_translations(component):
                self.update_lisa(index, translation, translation.store.store)
        else:
            for translation in self.iterate_translations(component):
                self.update_units(index, translation, translation.store.store)
