# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""
Tests for translation models.
"""

from __future__ import print_function

import shutil
import os

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError

from weblate.trans.models import (
    Project, Source, Unit, WhiteboardMessage, Check, ComponentList,
    get_related_units,
)
from weblate import appsettings
from weblate.trans.tests import OverrideSettings
from weblate.trans.tests.utils import get_test_file, RepoTestMixin


class RepoTestCase(TestCase, RepoTestMixin):
    """
    Generic class for tests working with repositories.
    """
    def setUp(self):
        self.clone_test_repos()


class ProjectTest(RepoTestCase):
    """
    Project object testing.
    """

    def test_create(self):
        project = self.create_project()
        self.assertTrue(os.path.exists(project.get_path()))
        self.assertTrue(project.slug in project.get_path())

    def test_rename(self):
        project = self.create_project()
        old_path = project.get_path()
        self.assertTrue(os.path.exists(old_path))
        project.slug = 'changed'
        project.save()
        new_path = project.get_path()
        self.addCleanup(shutil.rmtree, new_path, True)
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(new_path))

    def test_delete(self):
        project = self.create_project()
        self.assertTrue(os.path.exists(project.get_path()))
        project.delete()
        self.assertFalse(os.path.exists(project.get_path()))

    def test_delete_all(self):
        project = self.create_project()
        self.assertTrue(os.path.exists(project.get_path()))
        Project.objects.all().delete()
        self.assertFalse(os.path.exists(project.get_path()))

    def test_wrong_path(self):
        project = self.create_project()

        with OverrideSettings(DATA_DIR='/weblate-nonexisting-path'):
            # Invalidate cache, pylint: disable=W0212
            project._dir_path = None

            self.assertRaisesMessage(
                ValidationError,
                'Could not create project directory',
                project.full_clean
            )

    def test_acl(self):
        """
        Test for ACL handling.
        """
        # Create user to verify ACL
        user = User.objects.create_user(
            'testuser',
            'noreply@example.com',
            'testpassword'
        )

        # Create project
        project = self.create_project()

        # Enable ACL
        project.enable_acl = True
        project.save()

        # Check user does not have access
        self.assertFalse(project.has_acl(user))

        # Add ACL
        permission = Permission.objects.get(codename='weblate_acl_test')
        user.user_permissions.add(permission)

        # Need to fetch user again to clear permission cache
        user = User.objects.get(username='testuser')

        # We now should have access
        self.assertTrue(project.has_acl(user))


class TranslationTest(RepoTestCase):
    """
    Translation testing.
    """
    def test_basic(self):
        project = self.create_subproject()
        translation = project.translation_set.get(language_code='cs')
        self.assertEqual(translation.translated, 0)
        self.assertEqual(translation.total, 4)
        self.assertEqual(translation.fuzzy, 0)

    def test_extra_file(self):
        """
        Test extra commit file handling.
        """
        subproject = self.create_subproject()
        subproject.pre_commit_script = get_test_file(
            '../../../../examples/hook-generate-mo'
        )
        appsettings.PRE_COMMIT_SCRIPT_CHOICES.append(
            (subproject.pre_commit_script, 'hook-generate-mo')
        )
        subproject.pre_commit_script = get_test_file(
            '../../../../examples/hook-update-linguas'
        )
        appsettings.PRE_COMMIT_SCRIPT_CHOICES.append(
            (subproject.pre_commit_script, 'hook-update-linguas')
        )
        subproject.extra_commit_file = 'po/%(language)s.mo\npo/LINGUAS'
        subproject.save()
        subproject.full_clean()
        translation = subproject.translation_set.get(language_code='cs')
        # change backend file
        with open(translation.get_filename(), 'a') as handle:
            handle.write(' ')
        # Test committing
        translation.git_commit(
            None, 'TEST <test@example.net>', timezone.now(),
            force_commit=True
        )
        linguas = os.path.join(subproject.get_path(), 'po', 'LINGUAS')
        with open(linguas, 'r') as handle:
            data = handle.read()
            self.assertIn('\ncs\n', data)
        self.assertFalse(translation.repo_needs_commit())

    def test_validation(self):
        """
        Translation validation
        """
        project = self.create_subproject()
        translation = project.translation_set.get(language_code='cs')
        translation.full_clean()

    def test_update_stats(self):
        """
        Check update stats with no units.
        """
        project = self.create_subproject()
        translation = project.translation_set.get(language_code='cs')
        translation.update_stats()
        translation.unit_set.all().delete()
        translation.update_stats()


class WhiteboardMessageTest(TestCase):
    """Test(s) for WhiteboardMessage model."""

    def test_can_be_imported(self):
        """Test that whiteboard model can be imported.

        Rather dumb test just to make sure there are no obvious parsing errors.
        """
        WhiteboardMessage()


class ComponentListTest(TestCase):
    """Test(s) for ComponentList model."""

    def test_can_be_imported(self):
        """Test that ComponentList model can be imported.

        Rather dumb test just to make sure there are no obvious parsing errors.
        """
        ComponentList()


class ModelTestCase(RepoTestCase):
    def setUp(self):
        super(ModelTestCase, self).setUp()
        self.subproject = self.create_subproject()


class SourceTest(ModelTestCase):
    """
    Source objects testing.
    """
    def test_exists(self):
        self.assertTrue(Source.objects.exists())

    def test_source_info(self):
        unit = Unit.objects.all()[0]
        self.assertIsNotNone(unit.source_info)

    def test_priority(self):
        unit = Unit.objects.all()[0]
        self.assertEqual(unit.priority, 100)
        source = unit.source_info
        source.priority = 200
        source.save()
        unit2 = Unit.objects.get(pk=unit.pk)
        self.assertEqual(unit2.priority, 200)

    def test_check_flags(self):
        """
        Setting of Source check_flags changes checks for related units.
        """
        self.assertEqual(Check.objects.count(), 3)
        check = Check.objects.all()[0]
        unit = get_related_units(check)[0]
        source = unit.source_info
        source.check_flags = 'ignore-{0}'.format(check.check)
        source.save()
        self.assertEqual(Check.objects.count(), 0)


class UnitTest(ModelTestCase):
    @OverrideSettings(MT_WEBLATE_LIMIT=15)
    def test_more_like(self):
        unit = Unit.objects.all()[0]
        self.assertEqual(Unit.objects.more_like_this(unit).count(), 0)

    @OverrideSettings(MT_WEBLATE_LIMIT=0)
    def test_more_like_timeout(self):
        unit = Unit.objects.all()[0]
        self.assertRaisesMessage(
            Exception, 'Request timed out.', Unit.objects.more_like_this, unit
        )

    @OverrideSettings(MT_WEBLATE_LIMIT=-1)
    def test_more_like_no_fork(self):
        unit = Unit.objects.all()[0]
        self.assertEqual(Unit.objects.more_like_this(unit).count(), 0)
