
# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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
"""Hook scripts handling"""

import subprocess
from weblate.trans.util import get_clean_env


def run_post_push_script(component):
    """Run post push hook"""
    run_hook(component, None, component.post_push_script)


def run_post_update_script(component, previous_head):
    """Run post update hook"""
    run_hook(
        component, None, component.post_update_script,
        env={'WL_PREVIOUS_HEAD': previous_head}
    )


def run_pre_commit_script(component, translation, filename):
    """Pre commit hook"""
    run_hook(
        component, translation, component.pre_commit_script, None, filename
    )


def run_post_commit_script(component, translation, filename):
    """Post commit hook"""
    run_hook(
        component, translation, component.post_commit_script, None, filename
    )


def run_post_add_script(component, translation, filename):
    """Post add hook"""
    run_hook(component, translation, component.post_add_script, None, filename)


def run_hook(component, translation, script, env=None, *args):
    """Generic script hook executor."""
    if script:
        command = [script]
        if args:
            command.extend(args)
        if component.is_repo_link:
            target = component.linked_subproject
        else:
            target = component
        environment = {
            'WL_VCS': target.vcs,
            'WL_REPO': target.repo,
            'WL_PATH': target.get_path(),
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
        try:
            subprocess.check_call(
                command,
                env=get_clean_env(environment),
                cwd=component.get_path(),
            )
            return True
        except (OSError, subprocess.CalledProcessError) as err:
            component.log_error(
                'failed to run hook script %s: %s',
                script,
                err
            )
            return False
