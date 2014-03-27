# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
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
# In Django 1.5, this should come from django.utils.text
from django.template.defaultfilters import slugify
from weblate.trans.models import SubProject, Project
from weblate.trans.formats import FILE_FORMATS
from weblate.trans.util import is_repo_link
from glob import glob
from optparse import make_option
import tempfile
import git
import os
import re
import shutil
import fnmatch
import weblate


class Command(BaseCommand):
    help = 'imports projects with more subprojects'
    args = '<project> <gitrepo> <branch> <filemask>'
    option_list = BaseCommand.option_list + (
        make_option(
            '--name-template',
            default='%s',
            help='Python formatting string, transforming the filemask '
                 'match to a project name'
        ),
        make_option(
            '--base-file-template',
            default='',
            help='Python formatting string, transforming the filemask '
                 'match to a monolingual base file name'
        ),
        make_option(
            '--file-format',
            default='auto',
            help='File format type, defaults to autodetection',
        ),
    )

    def format_string(self, template, match):
        '''
        Formats template string with match.
        '''
        if '%s' in template:
            return template % match
        return template

    def get_name(self, maskre, path):
        matches = maskre.match(path)
        return matches.group(1)

    def get_match_regexp(self, filemask):
        '''
        Prepare regexp for file matching
        '''
        match = fnmatch.translate(filemask)
        match = match.replace('.*.*', '(.*.*)')
        return re.compile(match)

    def checkout_tmp(self, project, repo, branch):
        '''
        Checkouts project to temporary location.
        '''
        # Create temporary working dir
        workdir = tempfile.mkdtemp(dir=project.get_path())
        os.chmod(workdir, 0755)

        # Initialize git repository
        weblate.logger.info('Initializing git repository...')
        gitrepo = git.Repo.init(workdir)
        gitrepo.git.remote('add', 'origin', repo)

        weblate.logger.info('Fetching remote git repository...')
        gitrepo.git.remote('update', 'origin')
        gitrepo.git.branch('--track', branch, 'origin/%s' % branch)

        weblate.logger.info('Updating working copy in git repository...')
        gitrepo.git.checkout(branch)

        return workdir

    def get_matching_files(self, repo, filemask):
        '''
        Returns relative path of matched files.
        '''
        matches = glob(os.path.join(repo, filemask))
        return [f.replace(repo, '').strip('/') for f in matches]

    def get_matching_subprojects(self, repo, filemask):
        '''
        Scan the master repository for names matching our mask
        '''
        # Find matching files
        matches = self.get_matching_files(repo, filemask)
        weblate.logger.info('Found %d matching files', len(matches))

        # Parse subproject names out of them
        names = set()
        maskre = self.get_match_regexp(filemask)
        for match in matches:
            names.add(self.get_name(maskre, match))
        weblate.logger.info('Found %d subprojects', len(names))
        return names

    def handle(self, *args, **options):
        '''
        Automatic import of project.
        '''
        if len(args) != 4:
            raise CommandError('Invalid number of parameters!')

        if options['file_format'] not in FILE_FORMATS:
            raise CommandError(
                'Invalid file format: %s' % options['file_format']
            )

        # Read params, pylint: disable=W0632
        prjname, repo, branch, filemask = args

        # Try to get project
        try:
            project = Project.objects.get(slug=prjname)
        except Project.DoesNotExist:
            raise CommandError(
                'Project %s does not exist, you need to create it first!' %
                prjname
            )

        # Do we have correct mask?
        if '**' not in filemask:
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
                filemask
            )
        else:
            matches, sharedrepo = self.import_initial(
                project, repo, branch, filemask, options['name_template'],
                options['file_format'], options['base_file_template']
            )

        # Create remaining subprojects sharing git repository
        for match in matches:
            name = self.format_string(options['name_template'], match)
            template = self.format_string(options['base_file_template'], match)
            slug = slugify(name)
            subprojects = SubProject.objects.filter(
                Q(name=name) | Q(slug=slug),
                project=project
            )
            if subprojects.exists():
                weblate.logger.warn(
                    'Subproject %s already exists, skipping',
                    name
                )
                continue

            weblate.logger.info('Creating subproject %s', name)
            SubProject.objects.create(
                name=name,
                slug=slug,
                project=project,
                repo=sharedrepo,
                branch=branch,
                template=template,
                file_format=options['file_format'],
                filemask=filemask.replace('**', match)
            )

    def import_initial(self, project, repo, branch, filemask, name_template,
                       file_format, base_file_template):
        '''
        Import the first repository of a project
        '''
        # Checkout git to temporary dir
        workdir = self.checkout_tmp(project, repo, branch)
        matches = self.get_matching_subprojects(workdir, filemask)

        # Create first subproject (this one will get full git repo)
        match = matches.pop()
        name = self.format_string(name_template, match)
        template = self.format_string(base_file_template, match)
        slug = slugify(name)

        if SubProject.objects.filter(project=project, slug=slug).exists():
            weblate.logger.warn(
                'Subproject %s already exists, skipping and using it '
                'as main subproject',
                name
            )
            shutil.rmtree(workdir)
            return matches, 'weblate://%s/%s' % (project.slug, slug)

        weblate.logger.info('Creating subproject %s as main subproject', name)

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
            file_format=file_format,
            template=template,
            filemask=filemask.replace('**', match)
        )

        sharedrepo = 'weblate://%s/%s' % (project.slug, slug)

        return matches, sharedrepo
