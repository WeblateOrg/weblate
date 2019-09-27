# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

import os

from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from translate.storage.lisa import LISAfile

from weblate.addons.base import UpdateBaseAddon
from weblate.formats.txt import AppStoreParser


class BaseCleanupAddon(UpdateBaseAddon):
    @cached_property
    def template_store(self):
        return self.instance.component.template_store.store

    @staticmethod
    def build_index(storage):
        index = {}

        for unit in storage.units:
            index[unit.getid()] = unit

        return index

    @staticmethod
    def iterate_translations(component):
        for translation in component.translation_set.iterator():
            if translation.is_template:
                continue
            yield translation

    @classmethod
    def can_install(cls, component, user):
        if not component.has_template():
            return False
        return super(BaseCleanupAddon, cls).can_install(component, user)


class CleanupAddon(BaseCleanupAddon):
    name = 'weblate.cleanup.generic'
    verbose = _('Cleanup translation files')
    description = _(
        'Update all translation files to match the monolingual base file. '
        'For most file formats, this means removing stale translation keys '
        'no longer present in the base file.'
    )
    icon = 'eraser'

    def update_appstore(self, index, translation, storage):
        """Filter obsolete units in storage.

        This does simple filtering of units list.
        """
        for unit in storage.units:
            if unit.getid() not in index:
                filename = storage.get_filename(unit.filename)
                self.extra_files.append(filename)
                os.unlink(filename)

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

    def update_translations(self, component, previous_head):
        index = self.build_index(self.template_store)

        if isinstance(self.template_store, AppStoreParser):
            for translation in self.iterate_translations(component):
                self.update_appstore(
                    index, translation, translation.store.store
                )
        elif isinstance(self.template_store, LISAfile):
            for translation in self.iterate_translations(component):
                self.update_lisa(index, translation, translation.store.store)
        else:
            for translation in self.iterate_translations(component):
                self.update_units(index, translation, translation.store.store)
