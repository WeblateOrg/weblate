# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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
from weblate.trans.models import SubProject, Project
from glob import glob
import tempfile
import git
import logging
import os
import re
import fnmatch

logger = logging.getLogger('weblate')


class Command(BaseCommand):
    help = 'imports projects with more subprojects'
    args = '<project> <gitrepo> <branch> <filemask>'

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
        logger.info('Initializing git repository...')
        gitrepo = git.Repo.init(workdir)
        gitrepo.git.remote('add', 'origin', repo)

        logger.info('Fetching remote git repository...')
        gitrepo.git.remote('update', 'origin')
        gitrepo.git.branch('--track', branch, 'origin/%s' % branch)

        logger.info('Updating working copy in git repository...')
        gitrepo.git.checkout(branch)

        return workdir

    def get_matching_files(self, workdir, filemask):
        '''
        Returns relative path of matched files.
        '''
        matches = glob(os.path.join(workdir, filemask))
        return [f.replace(workdir, '').strip('/') for f in matches]

    def handle(self, *args, **options):
        '''
        Automatic import of project.
        '''
        if len(args) != 4:
            raise CommandError('Not enough parameters!')

        # Read params
        prjname, repo, branch, filemask = args

        maskre = self.get_match_regexp(filemask)

        # Try to get project
        try:
            project = Project.objects.get(slug=prjname)
        except Project.DoesNotExist:
            raise CommandError(
                'Project %s does not exist, you need to create it first!' %
                prjname
            )

        # Do we have correct mask?
        if not '**' in filemask:
            raise CommandError(
                'You need to specify double wildcard '
                'for subproject part of the match!'
            )

        # Checkout git to temporary dir
        workdir = self.checkout_tmp(project, repo, branch)

        # Find matching files
        matches = self.get_matching_files(workdir, filemask)
        logger.info('Found %d matching files', len(matches))

        # Parse subproject names out of them
        names = set()
        for match in matches:
            names.add(self.get_name(maskre, match))
        logger.info('Found %d subprojects', len(names))

        # Create first subproject (this one will get full git repo)
        name = names.pop()
        logger.info('Creating subproject %s as main subproject', name)

        # Rename gitrepository to new name
        os.rename(
            workdir,
            os.path.join(project.get_path(), name)
        )

        SubProject.objects.create(
            name=name,
            slug=name,
            project=project,
            repo=repo,
            branch=branch,
            filemask=filemask.replace('**', name)
        )

        sharedrepo = 'weblate://%s/%s' % (project.slug, name)

        # Create remaining subprojects sharing git repository
        for name in names:
            logger.info('Creating subproject %s', name)
            SubProject.objects.create(
                name=name,
                slug=name,
                project=project,
                repo=sharedrepo,
                branch=branch,
                filemask=filemask.replace('**', name)
            )
