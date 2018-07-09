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

from django.conf import settings
from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.text import slugify

from weblate.logger import LOGGER
from weblate.trans.models import Component
from weblate.utils.render import render_template
from weblate.trans.util import path_separator


class ComponentDiscovery(object):
    def __init__(self, component, match, name_template,
                 language_regex='^[^.]+$', base_file_template='',
                 new_base_template='',
                 file_format='auto', path=None):
        self.component = component
        if path is None:
            self.path = self.component.full_path
        else:
            self.path = path
        self.path_match = re.compile('^' + match + '$')
        self.name_template = name_template
        self.base_file_template = base_file_template
        self.new_base_template = new_base_template
        self.language_re = language_regex
        self.language_match = re.compile(language_regex)
        self.file_format = file_format

    @cached_property
    def matches(self):
        """Return matched files together with match groups and mask."""
        result = []
        base = os.path.realpath(self.path)
        for root, dummy, filenames in os.walk(self.path, followlinks=True):
            for filename in filenames:
                fullname = os.path.join(root, filename)

                # Skip files outside our root
                if not os.path.realpath(fullname).startswith(base):
                    continue

                # Calculate relative path
                path = path_separator(os.path.relpath(fullname, self.path))

                # Check match against our regexp
                matches = self.path_match.match(path)
                if not matches:
                    continue

                # Check language regexp
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
            if mask not in result:
                name = render_template(self.name_template, **groups)
                result[mask] = {
                    'files': {path},
                    'languages': {groups['language']},
                    'base_file': render_template(
                        self.base_file_template, **groups
                    ),
                    'new_base': render_template(
                        self.new_base_template, **groups
                    ),
                    'mask': mask,
                    'name': name,
                    'slug': slugify(name),
                }
            else:
                result[mask]['files'].add(path)
                result[mask]['languages'].add(groups['language'])
        return result

    def create_component(self, main, match, **params):
        max_length = settings.COMPONENT_NAME_LENGTH

        def get_val(key, extra=0):
            result = match[key]
            if len(result) > max_length - extra:
                result = result[:max_length - extra]
            return result

        name = get_val('name')
        slug = get_val('slug')
        simple_keys = (
            'project', 'branch', 'vcs', 'push_on_commit', 'license_url',
            'license',
        )
        for key in simple_keys:
            if key not in params:
                params[key] = getattr(main, key)
        if 'repo' not in params:
            params['repo'] = main.get_repo_link_url()

        components = Component.objects.filter(project=params['project'])

        if components.filter(Q(slug=slug) | Q(name=name)).exists():
            base_name = get_val('name', 4)
            base_slug = get_val('slug', 4)

            for i in range(1, 1000):
                name = '{} {}'.format(base_name, i)
                slug = '{}-{}'.format(base_slug, i)

                if components.filter(Q(slug=slug) | Q(name=name)).exists():
                    continue
                break

        if self.component:
            self.component.log_info('Creating component %s', name)
        else:
            LOGGER.info('Creating component %s', name)
        return Component.objects.create(
            name=name,
            slug=slug,
            template=match['base_file'],
            filemask=match['mask'],
            file_format=self.file_format,
            language_regex=self.language_re,
            **params
        )

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
                    component = self.create_component(main, match)
                    processed.add(component.id)
                created.append((match, component))

        if remove:
            for found in main.get_linked_childs().exclude(pk__in=processed):
                # Delete
                deleted.append((None, found))
                if not preview:
                    found.delete()

        return created, matched, deleted
