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

import os

from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_PRE_COMMIT, EVENT_POST_ADD
from weblate.trans.exporters import MoExporter

GETTEXT_COMPAT = {
    'file_format': frozenset((
        'auto', 'po', 'po-unwrapped', 'po-mono', 'po-mono-unwrapped'
    )),
}


class GenerateMoAddon(BaseAddon):
    events = (EVENT_PRE_COMMIT,)
    name = 'weblate.gettext.mo'
    compat = GETTEXT_COMPAT
    verbose = _('Generate mo files')
    description = _(
        'Automatically generates mo file for every changed po file.'
    )

    def pre_commit(self, translation):
        exporter = MoExporter(translation=translation)
        exporter.add_units(translation)
        output = translation.get_filename()[:-2] + 'mo'
        with open(output, 'wb') as handle:
            handle.write(exporter.serialize())
        translation.addon_commit_files.append(output)

    @classmethod
    def is_compatible(cls, component):
        if not component.filemask.endswith('.po'):
            return False
        return super(GenerateMoAddon, cls).is_compatible(component)


class UpdateLinguasAddon(BaseAddon):
    events = (EVENT_POST_ADD,)
    name = 'weblate.gettext.linguas'
    compat = GETTEXT_COMPAT
    verbose = _('Update LINGUAS file')
    description = _(
        'Updates the LINGUAS file when adding new translation.'
    )

    @staticmethod
    def get_linguas_path(component):
        base = component.get_new_base_filename()
        if not base:
            return None
        return os.path.join(os.path.dirname(base), 'LINGUAS')

    @classmethod
    def is_compatible(cls, component):
        if not component.can_add_new_language():
            return False
        path = cls.get_linguas_path(component)
        if not path or not os.path.exists(path):
            return False
        return super(UpdateLinguasAddon, cls).is_compatible(component)

    def post_add(self, translation):
        path = self.get_linguas_path(translation.subproject)
        with open(path, 'r') as handle:
            lines = handle.readlines()

        add = True
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Comment
            if stripped.startswith('#'):
                continue
            # Langauges in one line
            if ' ' in stripped:
                lines[i] = '{} {}\n'.format(
                    stripped, translation.language_code
                )
                add = False
                break
            # Language is already there
            if stripped == translation:
                add = False
                break
        if add:
            lines.append('{}\n'.format(translation.language_code))

        with open(path, 'w') as handle:
            handle.writelines(lines)

        translation.addon_commit_files.append(path)


class UpdateConfigureAddon(BaseAddon):
    events = (EVENT_POST_ADD,)
    name = 'weblate.gettext.configure'
    compat = GETTEXT_COMPAT
    verbose = _('Update ALL_LINGUAS variable in the configure file')
    description = _(
        'Updates the ALL_LINGUAS variable in configure, '
        'configure.in or configure.ac files when adding new translation.'
    )

    @staticmethod
    def get_configure_paths(component):
        base = component.get_path()
        return [
            os.path.join(base, 'configure'),
            os.path.join(base, 'configure.in'),
            os.path.join(base, 'configure.ac'),
        ]

    @classmethod
    def is_compatible(cls, component):
        if not component.can_add_new_language():
            return False
        if not super(UpdateConfigureAddon, cls).is_compatible(component):
            return False
        for name in cls.get_configure_paths(component):
            if not os.path.exists(name):
                continue
            with open(name) as handle:
                if 'ALL_LINGUAS="' in handle.read():
                    return True
        return False

    def post_add(self, translation):
        for path in self.get_configure_paths(translation.subproject):
            if not os.path.exists(path):
                continue
            with open(path, 'r') as handle:
                lines = handle.readlines()

            for i, line in enumerate(lines):
                stripped = line.strip()
                # Comment
                if stripped.startswith('#'):
                    continue
                if not stripped.startswith('ALL_LINGUAS="'):
                    continue
                lines[i] = '{}{} {}\n'.format(
                    stripped[:13],
                    translation.language_code,
                    stripped[13:],
                )

            with open(path, 'w') as handle:
                handle.writelines(lines)

            translation.addon_commit_files.append(path)
