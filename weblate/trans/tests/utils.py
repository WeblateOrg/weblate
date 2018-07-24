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

import os.path
import shutil
import sys
from tarfile import TarFile
from tempfile import mkdtemp
from unittest import SkipTest

from django.conf import settings
from weblate.auth.models import User

from weblate.formats.models import FILE_FORMATS
from weblate.trans.models import Project, Component
from weblate.trans.search import Fulltext
from weblate.vcs.models import VCS_REGISTRY
from weblate.utils.files import remove_readonly

# Directory holding test data
TEST_DATA = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'data'
)

REPOWEB_URL = \
    'https://github.com/WeblateOrg/test/blob/master/%(file)s#L%(line)s'


def get_test_file(name):
    """Return filename of test file."""
    return os.path.join(TEST_DATA, name)


def create_test_user():
    return User.objects.create_user(
        'testuser',
        'weblate@example.org',
        'testpassword',
        full_name='Weblate Test',
    )


class RepoTestMixin(object):
    """Mixin for testing with test repositories."""
    git_base_repo_path = None
    git_repo_path = None
    mercurial_base_repo_path = None
    mercurial_repo_path = None
    subversion_base_repo_path = None
    subversion_repo_path = None

    @staticmethod
    def optional_extract(output, tarname):
        """Extract test repository data if needed

        Checks whether directory exists or is older than archive.
        """

        tarname = get_test_file(tarname)

        if (not os.path.exists(output) or
                os.path.getmtime(output) < os.path.getmtime(tarname)):

            # Remove directory if outdated
            if os.path.exists(output):
                shutil.rmtree(output, onerror=remove_readonly)

            # Extract new content
            tar = TarFile(tarname)
            tar.extractall(settings.DATA_DIR)
            tar.close()

            # Update directory timestamp
            os.utime(output, None)

    def clone_test_repos(self):
        # Path where to clone remote repo for tests
        self.git_base_repo_path = os.path.join(
            settings.DATA_DIR,
            'test-base-repo.git'
        )
        # Repository on which tests will be performed
        self.git_repo_path = os.path.join(
            settings.DATA_DIR,
            'test-repo.git'
        )

        # Path where to clone remote repo for tests
        self.mercurial_base_repo_path = os.path.join(
            settings.DATA_DIR,
            'test-base-repo.hg'
        )
        # Repository on which tests will be performed
        self.mercurial_repo_path = os.path.join(
            settings.DATA_DIR,
            'test-repo.hg'
        )

        # Path where to clone remote repo for tests
        self.subversion_base_repo_path = os.path.join(
            settings.DATA_DIR,
            'test-base-repo.svn'
        )
        # Repository on which tests will be performed
        self.subversion_repo_path = os.path.join(
            settings.DATA_DIR,
            'test-repo.svn'
        )

        # Extract repo for testing
        self.optional_extract(
            self.git_base_repo_path,
            'test-base-repo.git.tar'
        )

        # Remove possibly existing directory
        if os.path.exists(self.git_repo_path):
            shutil.rmtree(self.git_repo_path, onerror=remove_readonly)

        # Create repository copy for the test
        shutil.copytree(self.git_base_repo_path, self.git_repo_path)

        # Extract repo for testing
        self.optional_extract(
            self.mercurial_base_repo_path,
            'test-base-repo.hg.tar'
        )

        # Remove possibly existing directory
        if os.path.exists(self.mercurial_repo_path):
            shutil.rmtree(self.mercurial_repo_path, onerror=remove_readonly)

        # Create repository copy for the test
        shutil.copytree(
            self.mercurial_base_repo_path, self.mercurial_repo_path
        )

        # Extract repo for testing
        self.optional_extract(
            self.subversion_base_repo_path,
            'test-base-repo.svn.tar'
        )

        # Remove possibly existing directory
        if os.path.exists(self.subversion_repo_path):
            shutil.rmtree(self.subversion_repo_path, onerror=remove_readonly)

        # Create repository copy for the test
        shutil.copytree(
            self.subversion_base_repo_path,
            self.subversion_repo_path
        )

        # Remove possibly existing project directory
        test_repo_path = os.path.join(settings.DATA_DIR, 'vcs', 'test')
        if os.path.exists(test_repo_path):
            shutil.rmtree(test_repo_path, onerror=remove_readonly)

        # Remove indexes
        Fulltext.cleanup()

    def create_project(self):
        """Create test project."""
        project = Project.objects.create(
            name='Test',
            slug='test',
            web='https://weblate.org/'
        )
        self.addCleanup(shutil.rmtree, project.full_path, True)
        return project

    def format_local_path(self, path):
        """Format path for local access to the repository"""
        if sys.platform != 'win32':
            return 'file://{}'.format(path)
        return 'file:///{}'.format(path.replace('\\', '/'))

    def _create_component(self, file_format, mask, template='',
                          new_base='', vcs='git', branch=None, **kwargs):
        """Create real test component."""
        if file_format not in FILE_FORMATS:
            raise SkipTest(
                'File format {0} is not supported!'.format(file_format)
            )
        if 'project' not in kwargs:
            kwargs['project'] = self.create_project()

        repo = push = self.format_local_path(
            getattr(self, '{0}_repo_path'.format(vcs))
        )
        if vcs not in VCS_REGISTRY:
            raise SkipTest('VCS {0} not available!'.format(vcs))

        if 'new_lang' not in kwargs:
            kwargs['new_lang'] = 'contact'

        if 'push_on_commit' not in kwargs:
            kwargs['push_on_commit'] = False

        if 'name' not in kwargs:
            kwargs['name'] = 'Test'
        kwargs['slug'] = kwargs['name'].lower()

        if branch is None:
            branch = VCS_REGISTRY[vcs].default_branch

        result = Component.objects.create(
            repo=repo,
            push=push,
            branch=branch,
            filemask=mask,
            template=template,
            file_format=file_format,
            repoweb=REPOWEB_URL,
            save_history=True,
            new_base=new_base,
            vcs=vcs,
            **kwargs
        )
        result.addons_cache = {}
        return result

    def create_component(self):
        """Wrapper method for providing test component."""
        return self._create_component(
            'auto',
            'po/*.po',
        )

    def create_po(self, **kwargs):
        return self._create_component(
            'po',
            'po/*.po',
            **kwargs
        )

    def create_po_branch(self):
        return self._create_component(
            'po',
            'translations/*.po',
            branch='translations'
        )

    def create_po_push(self):
        return self.create_po(
            push_on_commit=True
        )

    def create_po_empty(self):
        return self._create_component(
            'po',
            'po-empty/*.po',
            new_base='po-empty/hello.pot',
            new_lang='add',
        )

    def create_po_mercurial(self):
        return self.create_po(
            vcs='mercurial'
        )

    def create_po_svn(self):
        return self.create_po(
            vcs='subversion'
        )

    def create_po_new_base(self, **kwargs):
        return self.create_po(
            new_base='po/hello.pot',
            **kwargs
        )

    def create_po_link(self):
        return self._create_component(
            'po',
            'po-link/*.po',
        )

    def create_po_mono(self):
        return self._create_component(
            'po-mono',
            'po-mono/*.po',
            'po-mono/en.po',
        )

    def create_ts(self, suffix='', **kwargs):
        return self._create_component(
            'ts',
            'ts{0}/*.ts'.format(suffix),
            **kwargs
        )

    def create_ts_mono(self):
        return self._create_component(
            'ts',
            'ts-mono/*.ts',
            'ts-mono/en.ts',
        )

    def create_iphone(self, **kwargs):
        return self._create_component(
            'strings',
            'iphone/*.lproj/Localizable.strings',
            **kwargs
        )

    def create_android(self, suffix='', **kwargs):
        return self._create_component(
            'aresource',
            'android{}/values-*/strings.xml'.format(suffix),
            'android{}/values/strings.xml'.format(suffix),
            **kwargs
        )

    def create_json(self):
        return self._create_component(
            'json',
            'json/*.json',
        )

    def create_json_mono(self, suffix='mono', **kwargs):
        return self._create_component(
            'json',
            'json-{}/*.json'.format(suffix),
            'json-{}/en.json'.format(suffix),
            **kwargs
        )

    def create_json_webextension(self):
        return self._create_component(
            'webextension',
            'webextension/_locales/*/messages.json',
            'webextension/_locales/en/messages.json',
        )

    def create_joomla(self):
        return self._create_component(
            'joomla',
            'joomla/*.ini',
            'joomla/en-GB.ini',
        )

    def create_tsv(self):
        return self._create_component(
            'csv',
            'tsv/*.txt',
        )

    def create_csv(self):
        return self._create_component(
            'csv',
            'csv/*.txt',
        )

    def create_csv_mono(self):
        return self._create_component(
            'csv',
            'csv-mono/*.csv',
            'csv-mono/en.csv',
        )

    def create_php_mono(self):
        return self._create_component(
            'php',
            'php-mono/*.php',
            'php-mono/en.php',
        )

    def create_java(self):
        return self._create_component(
            'properties',
            'java/swing_messages_*.properties',
            'java/swing_messages.properties',
        )

    def create_xliff(self, name='default'):
        return self._create_component(
            'xliff',
            'xliff/*/{0}.xlf'.format(name),
        )

    def create_xliff_mono(self):
        return self._create_component(
            'xliff',
            'xliff-mono/*.xlf',
            'xliff-mono/en.xlf',
        )

    def create_resx(self):
        return self._create_component(
            'resx',
            'resx/*.resx',
            'resx/en.resx',
        )

    def create_yaml(self):
        return self._create_component(
            'yaml',
            'yml/*.yml',
            'yml/en.yml',
        )

    def create_ruby_yaml(self):
        return self._create_component(
            'ruby-yaml',
            'ruby-yml/*.yml',
            'ruby-yml/en.yml',
        )

    def create_dtd(self):
        return self._create_component(
            'dtd',
            'dtd/*.dtd',
            'dtd/en.dtd',
        )

    def create_link(self, **kwargs):
        parent = self.create_iphone(*kwargs)
        return Component.objects.create(
            name='Test2',
            slug='test2',
            project=parent.project,
            repo='weblate://test/test',
            file_format='po',
            filemask='po/*.po',
            new_lang='contact',
        )


class TempDirMixin(object):
    tempdir = None

    def create_temp(self):
        self.tempdir = mkdtemp(suffix='weblate')

    def remove_temp(self):
        if self.tempdir:
            shutil.rmtree(self.tempdir, onerror=remove_readonly)
            self.tempdir = None
