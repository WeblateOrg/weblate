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
import re

from django.utils.functional import cached_property
from django.utils.text import slugify

from weblate.trans.models import SubProject
from weblate.utils.render import render_template


class ComponentDiscovery(object):
    def __init__(self, component, match, name_template,
                 language_regex='^[^.]+$', base_file_template='',
                 file_format='auto'):
        self.component = component
        self.path_match = re.compile('^' + match + '$')
        self.name_template = name_template
        self.base_file_template = base_file_template
        self.language_re = language_regex
        self.language_match = re.compile(language_regex)
        self.file_format = file_format

    @cached_property
    def matches(self):
        """Return matched files together with match groups and mask."""
        result = []
        for root, dummy, filenames in os.walk(self.component.full_path):
            for filename in filenames:
                path = os.path.relpath(
                    os.path.join(root, filename),
                    self.component.full_path
                )
                matches = self.path_match.match(path)
                if not matches:
                    continue
                # Check langauge regexp
                if not self.language_match.match(matches.group('language')):
                    continue
                # Calculate file mask for match
                mask = '{}*{}'.format(
                    path[:matches.start('language')],
                    path[matches.end('language'):],
                )
                result.append((path, matches.groupdict(), mask))

        return result

    @cached_property
    def matched_files(self):
        """Return list of matched files."""
        return [x[0] for x in self.matches]

    @cached_property
    def matched_components(self):
        """Return list of matched components."""
        result = {}
        for path, groups, mask in self.matches:
            if groups['component'] not in result:
                name = render_template(self.name_template, **groups)
                result[groups['component']] = {
                    'files': {path},
                    'languages': {groups['language']},
                    'base_file': render_template(
                        self.base_file_template, **groups
                    ),
                    'mask': mask,
                    'name': name,
                    'slug': slugify(name),
                }
            else:
                result[groups['component']]['files'].add(path)
                result[groups['component']]['languages'].add(
                    groups['language']
                )
        return result

    def perform(self, preview=False, remove=False):
        created = []
        matched = []
        deleted = []
        processed = set()

        main = self.component

        for match in self.matched_components.values():
            # Skip matches to main component
            if match['mask'] == main.filemask:
                continue

            try:
                found = main.get_linked_childs().filter(
                    filemask=match['mask']
                )[0]
                # Component exists
                matched.append((match, found))
                processed.add(found.id)
            except IndexError:
                # Create new component
                if preview:
                    component = None
                else:
                    component = SubProject.objects.create(
                        name=match['name'],
                        slug=match['slug'],
                        project=main.project,
                        repo=main.get_repo_link_url(),
                        branch=main.branch,
                        vcs=main.vcs,
                        push_on_commit=main.push_on_commit,
                        license=main.license,
                        license_url=main.license_url,
                        template=match['base_file'],
                        filemask=match['mask'],
                        file_format=self.file_format,
                        language_regex=self.language_re,
                    )
                    processed.add(component.id)
                created.append((match, component))


        if remove:
            for found in main.get_linked_childs().exclude(pk__in=processed):
                # Delete
                deleted.append((None, found))
                if not preview:
                    found.delete()

        return created, matched, deleted
