# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils.text import slugify
from weblate.trans.models import SubProject, Project
from weblate.trans.formats import FILE_FORMATS
from weblate.trans.util import is_repo_link
from weblate.trans.vcs import GitRepository
from glob import glob
from optparse import make_option
import tempfile
import os
import re
import shutil
import fnmatch
from weblate.logger import LOGGER


class Command(BaseCommand):
    """
    Command for mass importing of repositories into Weblate.
    """
    help = 'imports projects with more components'
    args = '<project> <gitrepo> <branch> <filemask>'
    option_list = BaseCommand.option_list + (
        make_option(
            '--name-template',
            default='%s',
            help=(
                'Python formatting string, transforming the filemask '
                'match to a project name'
            )
        ),
        make_option(
            '--component-regexp',
            default=None,
            help=(
                'Regular expression to match component out of filename'
            )
        ),
        make_option(
            '--base-file-template',
            default='',
            help=(
                'Python formatting string, transforming the filemask '
                'match to a monolingual base file name'
            )
        ),
        make_option(
            '--file-format',
            default='auto',
            help='File format type, defaults to autodetection',
        ),
        make_option(
            '--vcs',
            default='git',
            help='Version control system to use',
        ),
    )

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.filemask = None
        self.component_re = None
        self.file_format = None
        self.name_template = None
        self.base_file_template = None
        self.vcs = None
        self.logger = LOGGER
        self._mask_regexp = None

    def format_string(self, template, match):
        '''
        Formats template string with match.
        '''
        if '%s' in template:
            return template % match
        return template

    def get_name(self, path):
        """
        Returns file name from patch based on filemask.
        """
        matches = self.match_regexp.match(path)
        if matches is None:
            self.logger.warning('Skipping %s', path)
            return None
        return matches.group('name')

    @property
    def match_regexp(self):
        '''
        Returns regexp for file matching
        '''
        if self.component_re is not None:
            return self.component_re
        if self._mask_regexp is None:
            match = fnmatch.translate(self.filemask)
            match = match.replace('.*.*', '(?P<name>.*)')
            self._mask_regexp = re.compile(match)
        return self._mask_regexp

    def checkout_tmp(self, project, repo, branch):
        '''
        Checkouts project to temporary location.
        '''
        # Create temporary working dir
        workdir = tempfile.mkdtemp(dir=project.get_path())
        os.chmod(workdir, 0755)

        # Initialize git repository
        self.logger.info('Cloning git repository...')
        gitrepo = GitRepository.clone(repo, workdir)
        self.logger.info('Updating working copy in git repository...')
        gitrepo.configure_branch(branch)

        return workdir

    def get_matching_files(self, repo):
        '''
        Returns relative path of matched files.
        '''
        matches = glob(os.path.join(repo, self.filemask))
        return [f.replace(repo, '').strip('/') for f in matches]

    def get_matching_subprojects(self, repo):
        '''
        Scan the master repository for names matching our mask
        '''
        # Find matching files
        matches = self.get_matching_files(repo)
        self.logger.info('Found %d matching files', len(matches))

        # Parse subproject names out of them
        names = set()
        for match in matches:
            name = self.get_name(match)
            if name:
                names.add(name)
        self.logger.info('Found %d subprojects', len(names))
        return sorted(names)

    def handle(self, *args, **options):
        '''
        Automatic import of project.
        '''

        # Check params
        if len(args) != 4:
            raise CommandError('Invalid number of parameters!')

        if options['file_format'] not in FILE_FORMATS:
            raise CommandError(
                'Invalid file format: %s' % options['file_format']
            )

        # Read params
        repo = args[1]
        branch = args[2]
        self.filemask = args[3]
        self.vcs = options['vcs']
        self.file_format = options['file_format']
        self.name_template = options['name_template']
        self.base_file_template = options['base_file_template']
        if options['component_regexp']:
            try:
                self.component_re = re.compile(
                    options['component_regexp'],
                    re.MULTILINE | re.DOTALL
                )
            except re.error as error:
                raise CommandError(
                    'Failed to compile regullar expression "{0}": {1}'.format(
                        options['component_regexp'], error
                    )
                )
            if 'name' not in self.component_re.groupindex:
                raise CommandError(
                    'Component regullar expression lacks named group "name"'
                )

        # Try to get project
        try:
            project = Project.objects.get(slug=args[0])
        except Project.DoesNotExist:
            raise CommandError(
                'Project %s does not exist, you need to create it first!' %
                args[0]
            )

        # Do we have correct mask?
        if '**' not in self.filemask:
            raise CommandError(
                'You need to specify double wildcard '
                'for subproject part of the match!'
            )

        if is_repo_link(repo):
            sharedrepo = repo
            try:
                sub_project = SubProject.objects.get(
                    project=project,
                    slug=repo.rsplit('/', 1)[-1]
                )
            except SubProject.DoesNotExist:
                raise CommandError(
                    'SubProject %s does not exist, '
                    'you need to create it first!' % repo
                )
            matches = self.get_matching_subprojects(
                sub_project.get_path(),
            )
        else:
            matches, sharedrepo = self.import_initial(project, repo, branch)

        # Create remaining subprojects sharing git repository
        for match in matches:
            name = self.format_string(self.name_template, match)
            template = self.format_string(self.base_file_template, match)
            slug = slugify(name)
            subprojects = SubProject.objects.filter(
                Q(name=name) | Q(slug=slug),
                project=project
            )
            if subprojects.exists():
                self.logger.warn(
                    'Component %s already exists, skipping',
                    name
                )
                continue

            self.logger.info('Creating component %s', name)
            SubProject.objects.create(
                name=name,
                slug=slug,
                project=project,
                repo=sharedrepo,
                branch=branch,
                template=template,
                file_format=self.file_format,
                filemask=self.filemask.replace('**', match)
            )

    def import_initial(self, project, repo, branch):
        '''
        Import the first repository of a project
        '''
        # Checkout git to temporary dir
        workdir = self.checkout_tmp(project, repo, branch)
        matches = self.get_matching_subprojects(workdir)

        # Create first subproject (this one will get full git repo)
        match = matches.pop()
        name = self.format_string(self.name_template, match)
        template = self.format_string(self.base_file_template, match)
        slug = slugify(name)

        if SubProject.objects.filter(project=project, slug=slug).exists():
            self.logger.warn(
                'Component %s already exists, skipping and using it '
                'as main component',
                name
            )
            shutil.rmtree(workdir)
            return matches, 'weblate://%s/%s' % (project.slug, slug)

        self.logger.info('Creating component %s as main one', name)

        # Rename gitrepository to new name
        os.rename(
            workdir,
            os.path.join(project.get_path(), slug)
        )

        SubProject.objects.create(
            name=name,
            slug=slug,
            project=project,
            repo=repo,
            branch=branch,
            file_format=self.file_format,
            vcs=self.vcs,
            template=template,
            filemask=self.filemask.replace('**', match)
        )

        sharedrepo = 'weblate://%s/%s' % (project.slug, slug)

        return matches, sharedrepo
