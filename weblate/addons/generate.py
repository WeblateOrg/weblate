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

from django.utils.translation import ugettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_PRE_COMMIT
from weblate.addons.forms import GenerateForm
from weblate.utils.render import render_template


class GenerateFileAddon(BaseAddon):
    events = (EVENT_PRE_COMMIT,)
    name = 'weblate.generate.generate'
    verbose = _('Statistics generator')
    description = _(
        'This addon generates a file containing detailed information '
        'about the translation.'
    )
    settings_form = GenerateForm
    multiple = True
    icon = 'bar-chart'
    has_summary = True

    @classmethod
    def can_install(cls, component, user):
        if not component.translation_set.exists():
            return False
        return super(GenerateFileAddon, cls).can_install(component, user)

    def pre_commit(self, translation, author):
        filename = os.path.join(
            self.instance.component.full_path,
            render_template(
                self.instance.configuration['filename'],
                translation=translation
            )
        )
        content = render_template(
            self.instance.configuration['template'],
            translation=translation
        )
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        with open(filename, 'w') as handle:
            handle.write(content)
        translation.addon_commit_files.append(filename)

    def get_summary(self):
        return self.instance.configuration['filename']
