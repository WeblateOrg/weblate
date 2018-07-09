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

"""Test for translation models."""


import shutil
import os

from django.core.management.color import no_style
from django.db import connection
from django.http.request import HttpRequest
from django.test import TestCase, LiveServerTestCase
from django.test.utils import override_settings
from django.core.exceptions import ValidationError

from weblate.auth.models import User, Group
from weblate.checks.models import Check
from weblate.trans.models import (
    Project, Source, Unit, WhiteboardMessage, ComponentList, AutoComponentList,
    Component,
)
from weblate.lang.models import Language
from weblate.trans.tests.utils import RepoTestMixin, create_test_user
from weblate.utils.state import STATE_TRANSLATED


def fixup_languages_seq():
    # Reset sequence for Language objects as
    # we're manipulating with them in FixtureTestCase.setUpTestData
    # and that seems to affect sequence for other tests as well
    # on some PostgreSQL versions (probably sequence is not rolled back
    # in a transaction).
    commands = connection.ops.sequence_reset_sql(no_style(), [Language])
    if commands:
        with connection.cursor() as cursor:
            for sql in commands:
                cursor.execute(sql)


class BaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixup_languages_seq()


class BaseLiveServerTestCase(LiveServerTestCase):
    @classmethod
    def setUpTestData(cls):
        fixup_languages_seq()


class RepoTestCase(BaseTestCase, RepoTestMixin):
    """Generic class for tests working with repositories."""
    def setUp(self):
        self.clone_test_repos()


class ProjectTest(RepoTestCase):
    """Project object testing."""

    def test_create(self):
        project = self.create_project()
        self.assertTrue(os.path.exists(project.full_path))
        self.assertTrue(project.slug in project.full_path)

    def test_rename(self):
        component = self.create_link()
        self.assertTrue(
            Component.objects.filter(repo='weblate://test/test').exists()
        )
        project = component.project
        old_path = project.full_path
        self.assertTrue(os.path.exists(old_path))
        project.slug = 'changed'
        project.save()
        new_path = project.full_path
        self.addCleanup(shutil.rmtree, new_path, True)
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(new_path))
        self.assertTrue(
            Component.objects.filter(repo='weblate://changed/test').exists()
        )
        self.assertFalse(
            Component.objects.filter(repo='weblate://test/test').exists()
        )

    def test_delete(self):
        project = self.create_project()
        self.assertTrue(os.path.exists(project.full_path))
        project.delete()
        self.assertFalse(os.path.exists(project.full_path))

    def test_delete_all(self):
        project = self.create_project()
        self.assertTrue(os.path.exists(project.full_path))
        Project.objects.all().delete()
        self.assertFalse(os.path.exists(project.full_path))

    def test_wrong_path(self):
        project = self.create_project()

        with override_settings(DATA_DIR='/weblate-nonexisting:path'):
            # Invalidate cache
            project.invalidate_path_cache()

            self.assertRaisesMessage(
                ValidationError,
                'Could not create project directory',
                project.full_clean
            )

    def test_acl(self):
        """Test for ACL handling."""
        # Create user to verify ACL
        user = create_test_user()

        # Create project
        project = self.create_project()

        # Enable ACL
        project.access_control = Project.ACCESS_PRIVATE
        project.save()

        # Check user does not have access
        self.assertFalse(user.can_access_project(project))

        # Add to ACL group
        user.groups.add(Group.objects.get(name='Test@Translate'))

        # Need to fetch user again to clear permission cache
        user = User.objects.get(username='testuser')

        # We now should have access
        self.assertTrue(user.can_access_project(project))


class TranslationTest(RepoTestCase):
    """Translation testing."""
    def test_basic(self):
        component = self.create_component()
        translation = component.translation_set.get(language_code='cs')
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.all, 4)
        self.assertEqual(translation.stats.fuzzy, 0)

    def test_validation(self):
        """Translation validation"""
        component = self.create_component()
        translation = component.translation_set.get(language_code='cs')
        translation.full_clean()

    def test_update_stats(self):
        """Check update stats with no units."""
        component = self.create_component()
        translation = component.translation_set.get(language_code='cs')
        self.assertEqual(translation.stats.all, 4)
        self.assertEqual(translation.stats.all_words, 15)
        translation.unit_set.all().delete()
        translation.invalidate_cache()
        self.assertEqual(translation.stats.all, 0)
        self.assertEqual(translation.stats.all_words, 0)

    def test_commit_groupping(self):
        component = self.create_component()
        translation = component.translation_set.get(language_code='cs')
        request = HttpRequest()
        request.user = create_test_user()
        start_rev = component.repository.last_revision
        # Initial translation
        for unit in translation.unit_set.all():
            unit.translate(request, 'test2', STATE_TRANSLATED)
        # Translation completed, commit forced
        self.assertNotEqual(start_rev, component.repository.last_revision)
        start_rev = component.repository.last_revision
        # Translation from same author should not trigger commit
        for unit in translation.unit_set.all():
            unit.translate(request, 'test3', STATE_TRANSLATED)
        for unit in translation.unit_set.all():
            unit.translate(request, 'test4', STATE_TRANSLATED)
        self.assertEqual(start_rev, component.repository.last_revision)
        # Translation from other author should trigger commmit
        for i, unit in enumerate(translation.unit_set.all()):
            request.user = User.objects.create(
                full_name='User {}'.format(unit.pk),
                username='user-{}'.format(unit.pk),
                email='{}@example.com'.format(unit.pk)
            )
            # Fetch current pending state, it might have been
            # updated by background commit
            unit.pending = Unit.objects.get(pk=unit.pk).pending
            unit.translate(request, 'test', STATE_TRANSLATED)
            if i == 0:
                # First edit should trigger commit
                self.assertNotEqual(
                    start_rev, component.repository.last_revision
                )
                start_rev = component.repository.last_revision

        # No further commit now
        self.assertEqual(start_rev, component.repository.last_revision)

        # Commit pending changes
        translation.commit_pending(None)
        self.assertNotEqual(start_rev, component.repository.last_revision)


class ComponentListTest(RepoTestCase):
    """Test(s) for ComponentList model."""

    def test_slug(self):
        """Test ComponentList slug."""
        clist = ComponentList()
        clist.slug = 'slug'
        self.assertEqual(clist.tab_slug(), 'list-slug')

    def test_auto(self):
        self.create_component()
        clist = ComponentList.objects.create(
            name='Name',
            slug='slug'
        )
        AutoComponentList.objects.create(
            project_match='^.*$',
            component_match='^.*$',
            componentlist=clist
        )
        self.assertEqual(
            clist.components.count(), 1
        )

    def test_auto_create(self):
        clist = ComponentList.objects.create(
            name='Name',
            slug='slug'
        )
        AutoComponentList.objects.create(
            project_match='^.*$',
            component_match='^.*$',
            componentlist=clist
        )
        self.assertEqual(
            clist.components.count(), 0
        )
        self.create_component()
        self.assertEqual(
            clist.components.count(), 1
        )

    def test_auto_nomatch(self):
        self.create_component()
        clist = ComponentList.objects.create(
            name='Name',
            slug='slug'
        )
        AutoComponentList.objects.create(
            project_match='^none$',
            component_match='^.*$',
            componentlist=clist
        )
        self.assertEqual(
            clist.components.count(), 0
        )


class ModelTestCase(RepoTestCase):
    def setUp(self):
        super(ModelTestCase, self).setUp()
        self.component = self.create_component()


class SourceTest(ModelTestCase):
    """Source objects testing."""
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
        """Setting of Source check_flags changes checks for related units."""
        self.assertEqual(Check.objects.count(), 3)
        check = Check.objects.all()[0]
        unit = check.related_units[0]
        source = unit.source_info
        source.check_flags = 'ignore-{0}'.format(check.check)
        source.save()
        self.assertEqual(Check.objects.count(), 0)


class UnitTest(ModelTestCase):
    @override_settings(MT_WEBLATE_LIMIT=15)
    def test_more_like(self):
        unit = Unit.objects.all()[0]
        self.assertEqual(Unit.objects.more_like_this(unit).count(), 0)

    @override_settings(MT_WEBLATE_LIMIT=0)
    def test_more_like_timeout(self):
        unit = Unit.objects.all()[0]
        self.assertRaisesMessage(
            Exception,
            'Request for more like {0} timed out.'.format(unit.pk),
            Unit.objects.more_like_this,
            unit
        )

    @override_settings(MT_WEBLATE_LIMIT=-1)
    def test_more_like_no_fork(self):
        unit = Unit.objects.all()[0]
        self.assertEqual(Unit.objects.more_like_this(unit).count(), 0)


class WhiteboardMessageTest(ModelTestCase):
    """Test(s) for WhiteboardMessage model."""
    def setUp(self):
        super(WhiteboardMessageTest, self).setUp()
        WhiteboardMessage.objects.create(
            language=Language.objects.get(code='cs'),
            message='test cs',
        )
        WhiteboardMessage.objects.create(
            language=Language.objects.get(code='de'),
            message='test de',
        )
        WhiteboardMessage.objects.create(
            project=self.component.project,
            message='test project',
        )
        WhiteboardMessage.objects.create(
            component=self.component,
            project=self.component.project,
            message='test component',
        )
        WhiteboardMessage.objects.create(
            message='test global',
        )

    def verify_filter(self, messages, count, message=None):
        """
        Verifies whether messages have given count and first
        contains string.
        """
        self.assertEqual(len(messages), count)
        if message is not None:
            self.assertEqual(messages[0].message, message)

    def test_contextfilter_global(self):
        self.verify_filter(
            WhiteboardMessage.objects.context_filter(),
            1,
            'test global'
        )

    def test_contextfilter_project(self):
        self.verify_filter(
            WhiteboardMessage.objects.context_filter(
                project=self.component.project,
            ),
            1,
            'test project'
        )

    def test_contextfilter_component(self):
        self.verify_filter(
            WhiteboardMessage.objects.context_filter(
                component=self.component,
            ),
            2
        )

    def test_contextfilter_translation(self):
        self.verify_filter(
            WhiteboardMessage.objects.context_filter(
                component=self.component,
                language=Language.objects.get(code='cs'),
            ),
            3,
        )

    def test_contextfilter_language(self):
        self.verify_filter(
            WhiteboardMessage.objects.context_filter(
                language=Language.objects.get(code='cs'),
            ),
            1,
            'test cs'
        )
        self.verify_filter(
            WhiteboardMessage.objects.context_filter(
                language=Language.objects.get(code='de'),
            ),
            1,
            'test de'
        )
