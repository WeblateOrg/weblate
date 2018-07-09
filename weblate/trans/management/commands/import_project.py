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

import tempfile
import os
import re
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from weblate.lang.models import Language
from weblate.trans.models import Component, Project
from weblate.trans.discovery import ComponentDiscovery
from weblate.formats.models import FILE_FORMATS
from weblate.trans.util import is_repo_link
from weblate.vcs.models import VCS_REGISTRY
from weblate.logger import LOGGER


class Command(BaseCommand):
    """Command for mass importing of repositories into Weblate."""
    help = 'imports projects with more components'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            '--name-template',
            default='%s',
            help=(
                'Python formatting string, transforming the filemask '
                'match to a project name'
            )
        )
        parser.add_argument(
            '--base-file-template',
            default='',
            help=(
                'Python formatting string, transforming the filemask '
                'match to a monolingual base file name'
            )
        )
        parser.add_argument(
            '--file-format',
            default='auto',
            help='File format type, defaults to autodetection',
        )
        parser.add_argument(
            '--language-regex',
            default='^[^.]+$',
            help=(
                'Language filter regular expression to be used for created'
                ' components'
            ),
        )
        parser.add_argument(
            '--license',
            default='',
            help='License of imported components',
        )
        parser.add_argument(
            '--license-url',
            default='',
            help='License URL of imported components',
        )
        parser.add_argument(
            '--vcs',
            default=settings.DEFAULT_VCS,
            help='Version control system to use',
        )
        parser.add_argument(
            '--push-url',
            default='',
            help='Set push URL for the project',
        )
        parser.add_argument(
            '--push-url-same',
            action='store_true',
            default=False,
            help='Set push URL for the project to same as pull',
        )
        parser.add_argument(
            '--disable-push-on-commit',
            action='store_false',
            default=settings.DEFAULT_PUSH_ON_COMMIT,
            dest='push_on_commit',
            help='Disable push on commit for created components',
        )
        parser.add_argument(
            '--push-on-commit',
            action='store_true',
            default=settings.DEFAULT_PUSH_ON_COMMIT,
            dest='push_on_commit',
            help='Enable push on commit for created components',
        )
        parser.add_argument(
            '--main-component',
            default=None,
            help=(
                'Define which component will be used as main - including full'
                ' VCS repository'
            )
        )
        parser.add_argument(
            'project',
            help='Existing project slug',
        )
        parser.add_argument(
            'repo',
            help='VCS repository URL',
        )
        parser.add_argument(
            'branch',
            help='VCS repository branch',
        )
        parser.add_argument(
            'filemask',
            help='File mask',
        )

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.filemask = None
        self.component_re = None
        self.file_format = None
        self.language_regex = None
        self.license = None
        self.license_url = None
        self.main_component = None
        self.name_template = None
        self.base_file_template = None
        self.vcs = None
        self.push_url = None
        self.logger = LOGGER
        self.push_on_commit = True
        self.discovery = None

    def checkout_tmp(self, project, repo, branch):
        """Checkout project to temporary location."""
        # Create temporary working dir
        workdir = tempfile.mkdtemp(dir=project.full_path)
        # Make the temporary directory readable by others
        os.chmod(workdir, 0o755)

        # Initialize git repository
        self.logger.info('Cloning git repository...')
        gitrepo = VCS_REGISTRY[self.vcs].clone(repo, workdir)
        self.logger.info('Updating working copy in git repository...')
        with gitrepo.lock:
            gitrepo.configure_branch(branch)

        return workdir

    def parse_options(self, repo, options):
        """Parse parameters"""
        self.filemask = options['filemask']
        self.vcs = options['vcs']
        if options['push_url_same']:
            self.push_url = repo
        else:
            self.push_url = options['push_url']
        self.file_format = options['file_format']
        self.language_regex = options['language_regex']
        self.main_component = options['main_component']
        self.name_template = options['name_template']
        if '%s' in self.name_template:
            self.name_template = self.name_template.replace(
                '%s', '{{ component }}'
            )
        self.license = options['license']
        self.license_url = options['license_url']
        self.push_on_commit = options['push_on_commit']
        self.base_file_template = options['base_file_template']
        if '%s' in self.base_file_template:
            self.base_file_template = self.base_file_template.replace(
                '%s', '{{ component }}'
            )

        # Is file format supported?
        if self.file_format not in FILE_FORMATS:
            raise CommandError(
                'Invalid file format: {0}'.format(options['file_format'])
            )

        # Is vcs supported?
        if self.vcs not in VCS_REGISTRY:
            raise CommandError(
                'Invalid vcs: {0}'.format(options['vcs'])
            )

        # Do we have correct mask?
        # - if there is **, then it's simple mask (it's invalid in regexp)
        # - validate regexp otherwise
        if '**' in self.filemask and '*' in self.filemask.replace('**', ''):
            match = re.escape(self.filemask)
            match = match.replace(r'\*\*', '(?P<component>[[WILDCARD]])', 1)
            match = match.replace(r'\*\*', '(?P=component)')
            match = match.replace(r'\*', '(?P<language>[[WILDCARD]])', 1)
            match = match.replace(r'\*', '(?P=language)')
            match = match.replace('[[WILDCARD]]', '[^/]*')
            self.filemask = match
        else:
            try:
                compiled = re.compile(self.filemask)
            except re.error as error:
                raise CommandError(
                    'Failed to compile regular expression "{0}": {1}'.format(
                        self.filemask, error
                    )
                )
            if ('component' not in compiled.groupindex or
                    'language' not in compiled.groupindex):
                raise CommandError(
                    'Component regular expression lacks named group '
                    '"component" and/or "language"'
                )

    def handle(self, *args, **options):
        """Automatic import of project."""
        # Read params
        repo = options['repo']
        branch = options['branch']
        self.parse_options(repo, options)

        # Try to get project
        try:
            project = Project.objects.get(slug=options['project'])
        except Project.DoesNotExist:
            raise CommandError(
                'Project "{0}" not found, please create it first!'.format(
                    options['project']
                )
            )

        # Get or create main component
        if is_repo_link(repo):
            try:
                component = Component.objects.get_linked(repo)
                # Avoid operating on link
                if component.is_repo_link:
                    component = component.linked_component
            except Component.DoesNotExist:
                raise CommandError(
                    'Component "{0}" not found, '
                    'please create it first!'.format(
                        repo
                    )
                )
        else:
            component = self.import_initial(project, repo, branch)

        discovery = self.get_discovery(component)
        discovery.perform()

    def get_discovery(self, component, path=None):
        """Return discovery object after doing basic sanity check."""
        if self.discovery is not None:
            self.discovery.component = component
        else:
            self.discovery = ComponentDiscovery(
                component,
                self.filemask,
                self.name_template,
                self.language_regex,
                self.base_file_template,
                self.file_format,
                path=path
            )
            self.logger.info(
                'Found %d matching files',
                len(self.discovery.matched_files)
            )

            if not self.discovery.matched_files:
                raise CommandError('Your mask did not match any files!')

            self.logger.info(
                'Found %d components',
                len(self.discovery.matched_components)
            )
            langs = set()
            for match in self.discovery.matched_components.values():
                langs.update(match['languages'])
            self.logger.info('Found %d languages', len(langs))

            # Do some basic sanity check on languages
            if Language.objects.filter(code__in=langs).count() == 0:
                raise CommandError(
                    'None of matched languages exists, maybe you have '
                    'mixed * and ** in the mask?'
                )
        return self.discovery

    def import_initial(self, project, repo, branch):
        """Import the first repository of a project"""
        # Checkout git to temporary dir
        workdir = self.checkout_tmp(project, repo, branch)
        # Create fake discovery without existing component
        discovery = self.get_discovery(None, workdir)

        components = project.component_set.all()

        component = None

        # Create first component (this one will get full git repo)
        if self.main_component:
            match = None
            for match in discovery.matched_components.values():
                if match['slug'] == self.main_component:
                    break
            if match is None or match['slug'] != self.main_component:
                raise CommandError(
                    'Specified --main-component was not found in matches!'
                )
        else:
            # Try if one is already there
            for match in discovery.matched_components.values():
                try:
                    component = components.get(
                        repo=repo, filemask=match['mask']
                    )
                except Component.DoesNotExist:
                    continue
            # Pick random
            if component is None:
                match = list(discovery.matched_components.values())[0]

        try:
            if component is None:
                component = components.get(slug=match['slug'])
            self.logger.warning(
                'Component %s already exists, skipping and using it '
                'as a main component',
                match['slug']
            )
            shutil.rmtree(workdir)
        except Component.DoesNotExist:
            self.logger.info(
                'Creating component %s as main one', match['slug']
            )

            # Rename gitrepository to new name
            os.rename(workdir, os.path.join(project.full_path, match['slug']))

            # Create new component
            component = discovery.create_component(
                None,
                match,
                project=project,
                repo=repo,
                branch=branch,
                vcs=self.vcs,
                push_on_commit=self.push_on_commit,
                license=self.license,
                license_url=self.license_url,
            )

        return component
