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

from collections import OrderedDict

from django.utils.translation import ugettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_POST_COMMIT
from weblate.addons.forms import GitSquashForm

from weblate.utils.errors import report_error

from weblate.vcs.base import RepositoryException


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
    events = (EVENT_POST_COMMIT,)
    icon = 'compress'
    repo_scope = True

    @classmethod
    def can_install(cls, component, user):
        if component.is_repo_link:
            return False
        return super(GitSquashAddon, cls).can_install(component, user)

    def squash_all(self, component, repository, base=None, author=None):
        with repository.lock:
            remote = base if base else repository.get_remote_branch_name()
            message = repository.execute([
                'log', '--format=%B', '{}..HEAD'.format(remote)
            ])
            repository.execute(['reset', '--soft', remote])
            cmd = ['commit', '-m', message]
            if author:
                cmd.append('--author')
                cmd.append(author)
            repository.execute(cmd)

    def get_filenames(self, component):
        languages = {}
        for origin in [component] + list(component.get_linked_childs()):
            for translation in origin.translation_set.all():
                code = translation.language.code
                if code not in languages:
                    languages[code] = []
                languages[code].extend(translation.store.get_filenames())
        return languages

    def squash_language(self, component, repository):
        remote = repository.get_remote_branch_name()
        languages = self.get_filenames(component)

        messages = {}
        for code, filenames in languages.items():
            if not filenames:
                continue
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

    def squash_author(self, component, repository):
        remote = repository.get_remote_branch_name()
        # Get list of pending commits with authors
        commits = [
            x.split(None, 1) for x in reversed(repository.execute([
                'log', '--format=%H %aE', '{}..HEAD'.format(remote),
            ]).splitlines())
        ]

        tmp = 'weblate-squash-tmp'
        repository.delete_branch(tmp)
        try:
            # Create local branch for upstream
            repository.execute(['branch', tmp, remote])
            # Checkout upstream branch
            repository.execute(['checkout', tmp])
            while commits:
                commit, author = commits.pop(0)
                # Remember current revision for final squash
                base = repository.get_last_revision()
                # Cherry pick current commit (this should work
                # unless something is messed up)
                repository.execute(['cherry-pick', commit])
                handled = []
                # Pick other commits by same author
                for i, other in enumerate(commits):
                    if other[1] != author:
                        continue
                    try:
                        repository.execute(['cherry-pick', other[0]])
                        handled.append(i)
                    except RepositoryException:
                        # If fails, continue to another author, we will
                        # pick this commit later (it depends on some other)
                        repository.execute(['cherry-pick', '--abort'])
                        break
                # Remove processed commits from list
                for i in reversed(handled):
                    del commits[i]
                # Squash all current commits from one author
                self.squash_all(component, repository, base, author)

            # Update working copy with squashed commits
            repository.execute(['checkout', repository.branch])
            repository.execute(['reset', '--hard', tmp])
            repository.delete_branch(tmp)

        except RepositoryException as error:
            report_error(error)
            # Revert to original branch without any changes
            repository.execute(['checkout', repository.branch])
            repository.delete_branch(tmp)

    def post_commit(self, translation):
        component = translation.component
        if (component.repo_needs_merge()
                and not component.update_branch(method='rebase')):
            return
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
                repository.execute([
                    'commit', '-m', self.get_commit_message(component)
                ])
