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

from weblate.addons.base import BaseAddon
from weblate.utils.render import render_template


class BaseScriptAddon(BaseAddon):
    """Base class for script executing addons."""
    icon = 'file-code-o'
    script = None
    add_file = None
    alert = 'AddonScriptError'

    def run_script(self, component=None, translation=None, env=None):
        command = [self.script]
        if translation:
            component = translation.component
            command.append(translation.get_filename())
        if component.is_repo_link:
            target = component.linked_component
        else:
            target = component
        environment = {
            'WL_VCS': target.vcs,
            'WL_REPO': target.repo,
            'WL_PATH': target.full_path,
            'WL_FILEMASK': component.filemask,
            'WL_TEMPLATE': component.template,
            'WL_NEW_BASE': component.new_base,
            'WL_FILE_FORMAT': component.file_format,
            'WL_BRANCH': component.branch,
        }
        if translation:
            environment['WL_LANGUAGE'] = translation.language_code
        if env is not None:
            environment.update(env)
        self.execute_process(component, command, environment)
        self.trigger_alerts(component)

    def post_push(self, component):
        self.run_script(component)

    def post_update(self, component, previous_head):
        self.run_script(component, env={'WL_PREVIOUS_HEAD': previous_head})

    def post_commit(self, translation):
        self.run_script(translation=translation)

    def pre_commit(self, translation, author):
        self.run_script(translation=translation)

        if self.add_file:
            filename = os.path.join(
                self.instance.component.full_path,
                render_template(
                    self.add_file,
                    translation=translation
                )
            )
            translation.addon_commit_files.append(filename)

    def post_add(self, translation):
        self.run_script(translation=translation)
