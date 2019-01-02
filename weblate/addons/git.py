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

from django.utils.translation import ugettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_PRE_PUSH
from weblate.addons.forms import GitSquashForm


class GitSquashAddon(BaseAddon):
    name = 'weblate.git.squash'
    verbose = _('Squash Git commits')
    description = _('Squash Git commits prior to pushing changes.')
    settings_form = GitSquashForm
    compat = {
        'vcs': frozenset((
            'git', 'gerrit', 'subversion', 'github',
        )),
    }
    events = (EVENT_PRE_PUSH,)

    @classmethod
    def can_install(cls, component, user):
        if component.is_repo_link:
            return False
        return super(GitSquashAddon, cls).can_install(component, user)

    def squash_all(self, component, repository):
        with repository.lock:
            remote = repository.get_remote_branch_name()
            message = repository.execute([
                'log', '--format=%B', '{}..HEAD'.format(remote)
            ])
            repository.execute(['reset', '--soft', remote])
            repository.execute(['commit', '-m', message])

    def get_filenames(self, component):
        languages = {}
        for origin in [component] + list(component.get_linked_childs()):
            for translation in origin.translation_set.all():
                code = translation.language.code
                if code in languages:
                    languages[code].append(translation.filename)
                else:
                    languages[code] = [translation.filename]
        return languages

    def squash_language(self, component, repository):
        remote = repository.get_remote_branch_name()
        languages = self.get_filenames(component)

        messages = {}
        for code, filenames in languages.items():
            messages[code] = repository.execute([
                'log', '--format=%B', '{}..HEAD'.format(remote), '--'
            ] + filenames)

        repository.execute(['reset', '--soft', remote])

        for code, message in messages.items():
            if not message:
                continue
            repository.execute(
                ['commit', '-m', message, '--'] + languages[code]
            )

    def squash_file(self, component, repository):
        remote = repository.get_remote_branch_name()
        languages = self.get_filenames(component)

        messages = {}
        for filenames in languages.values():
            for filename in filenames:
                messages[filename] = repository.execute([
                    'log', '--format=%B', '{}..HEAD'.format(remote),
                    '--', filename
                ])

        repository.execute(['reset', '--soft', remote])

        for filename, message in messages.items():
            if not message:
                continue
            repository.execute(
                ['commit', '-m', message, '--', filename]
            )

    def pre_push(self, component):
        squash = self.instance.configuration['squash']
        repository = component.repository
        if not repository.needs_push():
            return
        method = getattr(self, 'squash_{}'.format(squash))
        with repository.lock:
            method(component, repository)
            # Commit any left files, those were most likely generated
            # by addon and do not exactly match patterns above
            if repository.needs_commit():
                repository.execute(['commit', '-m', 'Weblate squashed changes'])
