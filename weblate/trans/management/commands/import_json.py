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

import argparse
import json

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from weblate.trans.models import Component, Project


class Command(BaseCommand):
    """
    Command for mass importing of repositories into Weblate
    based on JSON data.
    """
    help = 'imports projects based on JSON data'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            '--project',
            default=None,
            required=True,
            help=(
                'Project where to operate'
            )
        )
        parser.add_argument(
            '--ignore',
            default=False,
            action='store_true',
            help=(
                'Ignore already existing entries'
            )
        )
        parser.add_argument(
            '--update',
            default=False,
            action='store_true',
            help=(
                'Update already existing entries'
            )
        )
        parser.add_argument(
            '--main-component',
            default=None,
            help=(
                'Define which component will be used as main for the'
                ' VCS repository'
            )
        )
        parser.add_argument(
            'json-file',
            type=argparse.FileType('r'),
            help='JSON file containing component defintion',
        )

    def handle(self, *args, **options):
        """Automatic import of components."""
        # Get project
        try:
            project = Project.objects.get(slug=options['project'])
        except Project.DoesNotExist:
            raise CommandError('Project does not exist!')

        # Get main component
        main_component = None
        if options['main_component']:
            try:
                main_component = Component.objects.get(
                    project=project,
                    slug=options['main_component']
                )
            except Component.DoesNotExist:
                raise CommandError('Main component does not exist!')

        try:
            data = json.load(options['json-file'])
        except ValueError:
            raise CommandError('Failed to parse JSON file!')
        finally:
            options['json-file'].close()

        for item in data:
            if ('filemask' not in item or
                    'name' not in item):
                raise CommandError('Missing required fields in JSON!')

            if 'slug' not in item:
                item['slug'] = slugify(item['name'])

            if 'repo' not in item:
                if main_component is None:
                    raise CommandError(
                        'No main component and no repository URL!'
                    )
                item['repo'] = main_component.get_repo_link_url()

            item['project'] = project

            try:
                component = Component.objects.get(
                    slug=item['slug'], project=item['project']
                )
                self.stderr.write(
                    'Component {0} already exists'.format(component)
                )
                if options['ignore']:
                    continue
                if options['update']:
                    for key in item:
                        if key in ('project', 'slug'):
                            continue
                        setattr(component, key, item[key])
                    component.save()
                    continue
                raise CommandError(
                    'Component already exists, use --ignore or --update!'
                )

            except Component.DoesNotExist:
                component = Component.objects.create(**item)
                self.stdout.write(
                    'Imported {0} with {1} translations'.format(
                        component,
                        component.translation_set.count()
                    )
                )
