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

import io
import os

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.utils import find_command
from django.utils.translation import ugettext_lazy as _

from weblate.addons.base import BaseAddon, StoreBaseAddon, UpdateBaseAddon
from weblate.addons.events import EVENT_POST_ADD, EVENT_PRE_COMMIT
from weblate.addons.forms import GenerateMoForm, GettextCustomizeForm, MsgmergeForm
from weblate.formats.exporters import MoExporter


class GettextBaseAddon(BaseAddon):
    compat = {
        'file_format': frozenset(('po', 'po-mono')),
    }


class GenerateMoAddon(GettextBaseAddon):
    events = (EVENT_PRE_COMMIT,)
    name = 'weblate.gettext.mo'
    verbose = _('Generate MO files')
    description = _(
        'Automatically generates MO file for every changed PO file.'
    )
    settings_form = GenerateMoForm

    def pre_commit(self, translation, author):
        exporter = MoExporter(translation=translation)
        exporter.add_units(translation.unit_set.all())

        template = self.instance.configuration.get('path')
        if not template:
            template = '{{ filename|stripext }}.mo'

        output = self.render_repo_filename(template, translation)
        if not output:
            return

        with open(output, 'wb') as handle:
            handle.write(exporter.serialize())
        translation.addon_commit_files.append(output)


class UpdateLinguasAddon(GettextBaseAddon):
    events = (EVENT_POST_ADD,)
    name = 'weblate.gettext.linguas'
    verbose = _('Update LINGUAS file')
    description = _(
        'Updates the LINGUAS file when a new translation is added.'
    )

    @staticmethod
    def get_linguas_path(component):
        base = component.get_new_base_filename()
        if not base:
            return None
        return os.path.join(os.path.dirname(base), 'LINGUAS')

    @classmethod
    def can_install(cls, component, user):
        if not super(UpdateLinguasAddon, cls).can_install(component, user):
            return False
        if not component.is_valid_base_for_new():
            return False
        path = cls.get_linguas_path(component)
        return path and os.path.exists(path)

    def post_add(self, translation):
        path = self.get_linguas_path(translation.component)
        with io.open(path, 'r', encoding='utf-8') as handle:
            lines = handle.readlines()

        add = True
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Comment
            if stripped.startswith('#'):
                continue
            # Languages in one line
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

        with io.open(path, 'w', encoding='utf-8') as handle:
            handle.writelines(lines)

        translation.addon_commit_files.append(path)


class UpdateConfigureAddon(GettextBaseAddon):
    events = (EVENT_POST_ADD,)
    name = 'weblate.gettext.configure'
    verbose = _('Update ALL_LINGUAS variable in the "configure" file')
    description = _(
        'Updates the ALL_LINGUAS variable in "configure", '
        '"configure.in" or "configure.ac" files, when a new translation is added.'
    )

    @staticmethod
    def get_configure_paths(component):
        base = component.full_path
        return [
            os.path.join(base, 'configure'),
            os.path.join(base, 'configure.in'),
            os.path.join(base, 'configure.ac'),
        ]

    @classmethod
    def can_install(cls, component, user):
        if not super(UpdateConfigureAddon, cls).can_install(component, user):
            return False
        if not component.is_valid_base_for_new():
            return False
        for name in cls.get_configure_paths(component):
            if not os.path.exists(name):
                continue
            try:
                with io.open(name, encoding='utf-8') as handle:
                    if 'ALL_LINGUAS="' in handle.read():
                        return True
            except UnicodeDecodeError:
                continue
        return False

    def post_add(self, translation):
        for path in self.get_configure_paths(translation.component):
            if not os.path.exists(path):
                continue
            with io.open(path, 'r', encoding='utf-8') as handle:
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

            with io.open(path, 'w', encoding='utf-8') as handle:
                handle.writelines(lines)

            translation.addon_commit_files.append(path)


class MsgmergeAddon(GettextBaseAddon, UpdateBaseAddon):
    name = 'weblate.gettext.msgmerge'
    verbose = _('Update PO files to match POT (msgmerge)')
    description = _(
        'Update all PO files to match the POT file using msgmerge. This is '
        'triggered whenever new changes are pulled from the upstream '
        'repository.'
    )
    alert = 'MsgmergeAddonError'
    settings_form = MsgmergeForm

    @classmethod
    def can_install(cls, component, user):
        if not component.new_base or find_command('msgmerge') is None:
            return False
        return super(MsgmergeAddon, cls).can_install(component, user)

    def update_translations(self, component, previous_head):
        cmd = [
            'msgmerge',
            '--backup=none',
            '--update',
            'FILE',
            component.get_new_base_filename()
        ]
        if not self.instance.configuration.get('fuzzy', True):
            cmd.insert(1, '--no-fuzzy-matching')
        if self.instance.configuration.get('previous', True):
            cmd.insert(1, '--previous')
        try:
            width = component.addon_set.get(
                name='weblate.gettext.customize'
            ).configuration['width']
            if width != 77:
                cmd.insert(1, '--no-wrap')
        except ObjectDoesNotExist:
            pass
        for translation in component.translation_set.iterator():
            filename = translation.get_filename()
            if not os.path.exists(filename):
                continue
            cmd[-2] = filename
            self.execute_process(component, cmd)
        self.trigger_alerts(component)


class GettextCustomizeAddon(GettextBaseAddon, StoreBaseAddon):
    name = 'weblate.gettext.customize'
    verbose = _('Customize gettext output')
    description = _(
        'Allows customization of gettext output behavior, for example '
        'line wrapping.'
    )
    settings_form = GettextCustomizeForm

    def store_post_load(self, translation, store):
        store.store.wrapper.width = int(
            self.instance.configuration.get('width', 77)
        )


class GettextAuthorComments(GettextBaseAddon):
    events = (EVENT_PRE_COMMIT,)
    name = 'weblate.gettext.authors'
    verbose = _('Contributors in comment')
    description = _(
        'Update comment in the PO file header to include contributor name '
        'and years of contributions.'
    )

    def pre_commit(self, translation, author):
        if '<' in author:
            name, email = author.split('<')
            name = name.strip()
            email = email.rstrip('>')
        else:
            name = author
            email = None

        translation.store.store.updatecontributor(name, email)
        translation.store.save()
