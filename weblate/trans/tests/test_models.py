#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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
import os

from django.core.management.color import no_style
from django.db import connection
from django.test import LiveServerTestCase, TestCase
from django.test.utils import override_settings

from weblate.auth.models import Group, User
from weblate.checks.models import Check
from weblate.lang.models import Language, Plural
from weblate.trans.models import (
    Announcement,
    AutoComponentList,
    Comment,
    Component,
    ComponentList,
    Project,
    Suggestion,
    Unit,
    Vote,
)
from weblate.trans.tests.utils import RepoTestMixin, create_test_user
from weblate.utils.django_hacks import immediate_on_commit, immediate_on_commit_leave
from weblate.utils.files import remove_tree
from weblate.utils.state import STATE_TRANSLATED


def fixup_languages_seq():
    # Reset sequence for Language and Plural objects as
    # we're manipulating with them in FixtureTestCase.setUpTestData
    # and that seems to affect sequence for other tests as well
    # on some PostgreSQL versions (probably sequence is not rolled back
    # in a transaction).
    commands = connection.ops.sequence_reset_sql(no_style(), [Language, Plural])
    if commands:
        with connection.cursor() as cursor:
            for sql in commands:
                cursor.execute(sql)
    # Invalidate object cache for languages
    Language.objects.flush_object_cache()


class BaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixup_languages_seq()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        immediate_on_commit(cls)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        immediate_on_commit_leave(cls)


class BaseLiveServerTestCase(LiveServerTestCase):
    @classmethod
    def setUpTestData(cls):
        fixup_languages_seq()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        immediate_on_commit(cls)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        immediate_on_commit_leave(cls)


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
        self.assertTrue(Component.objects.filter(repo="weblate://test/test").exists())
        project = component.project
        old_path = project.full_path
        self.assertTrue(os.path.exists(old_path))
        self.assertTrue(
            os.path.exists(
                component.translation_set.get(language_code="cs").get_filename()
            )
        )
        project.name = "Changed"
        project.slug = "changed"
        project.save()
        new_path = project.full_path
        self.addCleanup(remove_tree, new_path, True)
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(new_path))
        self.assertTrue(
            Component.objects.filter(repo="weblate://changed/test").exists()
        )
        self.assertFalse(Component.objects.filter(repo="weblate://test/test").exists())
        component = Component.objects.get(pk=component.pk)
        self.assertTrue(
            os.path.exists(
                component.translation_set.get(language_code="cs").get_filename()
            )
        )

    def test_delete(self):
        project = self.create_project()
        self.assertTrue(os.path.exists(project.full_path))
        project.delete()
        self.assertFalse(os.path.exists(project.full_path))

    def test_delete_votes(self):
        component = self.create_po(suggestion_voting=True, suggestion_autoaccept=True)
        user = create_test_user()
        translation = component.translation_set.get(language_code="cs")
        unit = translation.unit_set.first()
        suggestion = Suggestion.objects.add(unit, "Test", None)
        Vote.objects.create(suggestion=suggestion, value=Vote.POSITIVE, user=user)
        component.project.delete()

    def test_delete_all(self):
        project = self.create_project()
        self.assertTrue(os.path.exists(project.full_path))
        Project.objects.all().delete()
        self.assertFalse(os.path.exists(project.full_path))

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
        user.groups.add(Group.objects.get(name="Test@Translate"))

        # Need to fetch user again to clear permission cache
        user = User.objects.get(username="testuser")

        # We now should have access
        self.assertTrue(user.can_access_project(project))


class TranslationTest(RepoTestCase):
    """Translation testing."""

    def test_basic(self):
        component = self.create_component()
        # Verify source translation
        translation = component.source_translation
        self.assertFalse(translation.unit_set.filter(num_words=0).exists())
        self.assertEqual(translation.stats.translated, 4)
        self.assertEqual(translation.stats.all, 4)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all_words, 15)
        # Verify target translation
        translation = component.translation_set.get(language_code="cs")
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.all, 4)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all_words, 15)

    def test_validation(self):
        """Translation validation."""
        component = self.create_component()
        translation = component.translation_set.get(language_code="cs")
        translation.full_clean()

    def test_update_stats(self):
        """Check update stats with no units."""
        component = self.create_component()
        translation = component.translation_set.get(language_code="cs")
        self.assertEqual(translation.stats.all, 4)
        self.assertEqual(translation.stats.all_words, 15)
        translation.unit_set.all().delete()
        translation.invalidate_cache()
        self.assertEqual(translation.stats.all, 0)
        self.assertEqual(translation.stats.all_words, 0)

    def test_commit_groupping(self):
        component = self.create_component()
        translation = component.translation_set.get(language_code="cs")
        user = create_test_user()
        start_rev = component.repository.last_revision
        # Initial translation
        for unit in translation.unit_set.iterator():
            unit.translate(user, "test2", STATE_TRANSLATED)
        # Translation completed, no commit forced
        self.assertEqual(start_rev, component.repository.last_revision)
        # Translation from same author should not trigger commit
        for unit in translation.unit_set.iterator():
            unit.translate(user, "test3", STATE_TRANSLATED)
        for unit in translation.unit_set.iterator():
            unit.translate(user, "test4", STATE_TRANSLATED)
        self.assertEqual(start_rev, component.repository.last_revision)
        # Translation from other author should trigger commmit
        for i, unit in enumerate(translation.unit_set.iterator()):
            user = User.objects.create(
                full_name=f"User {unit.pk}",
                username=f"user-{unit.pk}",
                email=f"{unit.pk}@example.com",
            )
            # Fetch current pending state, it might have been
            # updated by background commit
            unit.pending = Unit.objects.get(pk=unit.pk).pending
            unit.translate(user, "test", STATE_TRANSLATED)
            if i == 0:
                # First edit should trigger commit
                self.assertNotEqual(start_rev, component.repository.last_revision)
                start_rev = component.repository.last_revision

        # No further commit now
        self.assertEqual(start_rev, component.repository.last_revision)

        # Commit pending changes
        translation.commit_pending("test", None)
        self.assertNotEqual(start_rev, component.repository.last_revision)


class ComponentListTest(RepoTestCase):
    """Test(s) for ComponentList model."""

    def test_slug(self):
        """Test ComponentList slug."""
        clist = ComponentList()
        clist.slug = "slug"
        self.assertEqual(clist.tab_slug(), "list-slug")

    def test_auto(self):
        self.create_component()
        clist = ComponentList.objects.create(name="Name", slug="slug")
        AutoComponentList.objects.create(
            project_match="^.*$", component_match="^.*$", componentlist=clist
        )
        self.assertEqual(clist.components.count(), 2)

    def test_auto_create(self):
        clist = ComponentList.objects.create(name="Name", slug="slug")
        AutoComponentList.objects.create(
            project_match="^.*$", component_match="^.*$", componentlist=clist
        )
        self.assertEqual(clist.components.count(), 0)
        self.create_component()
        self.assertEqual(clist.components.count(), 2)

    def test_auto_nomatch(self):
        self.create_component()
        clist = ComponentList.objects.create(name="Name", slug="slug")
        AutoComponentList.objects.create(
            project_match="^none$", component_match="^.*$", componentlist=clist
        )
        self.assertEqual(clist.components.count(), 0)


class ModelTestCase(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.component = self.create_component()


class SourceUnitTest(ModelTestCase):
    """Source Unit objects testing."""

    def test_source_unit(self):
        unit = Unit.objects.filter(translation__language_code="cs")[0]
        self.assertIsNotNone(unit.source_unit)
        unit = Unit.objects.filter(translation__language_code="en")[0]
        self.assertEqual(unit.source_unit, unit)

    def test_priority(self):
        unit = Unit.objects.filter(translation__language_code="cs")[0]
        self.assertEqual(unit.priority, 100)
        source = unit.source_unit
        source.extra_flags = "priority:200"
        source.save()
        unit2 = Unit.objects.get(pk=unit.pk)
        self.assertEqual(unit2.priority, 200)

    def test_check_flags(self):
        """Setting of Source check_flags changes checks for related units."""
        self.assertEqual(Check.objects.count(), 3)
        check = Check.objects.all()[0]
        unit = check.unit
        self.assertEqual(self.component.stats.allchecks, 3)
        source = unit.source_unit
        source.extra_flags = f"ignore-{check.check}"
        source.save()
        self.assertEqual(Check.objects.count(), 0)
        self.assertEqual(Component.objects.get(pk=self.component.pk).stats.allchecks, 0)


class UnitTest(ModelTestCase):
    def test_newlines(self):
        user = create_test_user()
        unit = Unit.objects.filter(
            translation__language_code="cs", source="Hello, world!\n"
        )[0]
        unit.translate(user, "new\nstring\n", STATE_TRANSLATED)
        self.assertEqual(unit.target, "new\nstring\n")
        # New object to clear all_flags cache
        unit = Unit.objects.get(pk=unit.pk)
        unit.flags = "dos-eol"
        unit.translate(user, "new\nstring", STATE_TRANSLATED)
        self.assertEqual(unit.target, "new\r\nstring\r\n")
        unit.translate(user, "other\r\nstring", STATE_TRANSLATED)
        self.assertEqual(unit.target, "other\r\nstring\r\n")

    def test_flags(self):
        unit = Unit.objects.filter(translation__language_code="cs")[0]
        unit.flags = "no-wrap, ignore-same"
        self.assertEqual(unit.all_flags.items(), {"no-wrap", "ignore-same"})

    def test_order_by_request(self):
        unit = Unit.objects.filter(translation__language_code="cs")[0]
        source = unit.source_unit
        source.extra_flags = "priority:200"
        source.save()

        # test both ascending and descending order works
        unit1 = Unit.objects.filter(translation__language_code="cs")
        unit1 = unit1.order_by_request({"sort_by": "-priority"})
        self.assertEqual(unit1[0].priority, 200)
        unit1 = Unit.objects.filter(translation__language_code="cs")
        unit1 = unit1.order_by_request({"sort_by": "priority"})
        self.assertEqual(unit1[0].priority, 100)

        # test if invalid sorting, then sorted in default order
        unit2 = Unit.objects.filter(translation__language_code="cs")
        unit2 = unit2.order()
        unit3 = Unit.objects.filter(translation__language_code="cs")
        unit3 = unit3.order_by_request({"sort_by": "invalid"})
        self.assertEqual(unit3[0], unit2[0])

        # test sorting by count
        unit4 = Unit.objects.filter(translation__language_code="cs")[2]
        Comment.objects.create(unit=unit4, comment="Foo")
        unit5 = Unit.objects.filter(translation__language_code="cs")
        unit5 = unit5.order_by_request({"sort_by": "-num_comments"})
        self.assertEqual(unit5[0].comment_set.count(), 1)
        unit5 = Unit.objects.filter(translation__language_code="cs")
        unit5 = unit5.order_by_request({"sort_by": "num_comments"})
        self.assertEqual(unit5[0].comment_set.count(), 0)

        # check all order options produce valid queryset
        order_options = [
            "priority",
            "position",
            "context",
            "num_words",
            "labels",
            "timestamp",
            "num_failing_checks",
        ]
        for order_option in order_options:
            ordered_unit = Unit.objects.filter(
                translation__language_code="cs"
            ).order_by_request({"sort_by": order_option})
            ordered_desc_unit = Unit.objects.filter(
                translation__language_code="cs"
            ).order_by_request({"sort_by": f"-{order_option}"})
            self.assertEqual(len(ordered_unit), 4)
            self.assertEqual(len(ordered_desc_unit), 4)

        # check sorting with multiple options work
        multiple_ordered_unit = Unit.objects.filter(
            translation__language_code="cs"
        ).order_by_request({"sort_by": "position,timestamp"})
        self.assertEqual(multiple_ordered_unit.count(), 4)

    def test_get_max_length_no_pk(self):
        unit = Unit.objects.filter(translation__language_code="cs")[0]
        unit.pk = False
        self.assertEqual(unit.get_max_length(), 10000)

    def test_get_max_length_empty_source_default_fallback(self):
        unit = Unit.objects.filter(translation__language_code="cs")[0]
        unit.pk = True
        unit.source = ""
        self.assertEqual(unit.get_max_length(), 100)

    def test_get_max_length_default_fallback(self):
        unit = Unit.objects.filter(translation__language_code="cs")[0]
        unit.pk = True
        unit.source = "My test source"
        self.assertEqual(unit.get_max_length(), 140)

    @override_settings(LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH=False)
    def test_get_max_length_empty_source_disabled_default_fallback(self):
        unit = Unit.objects.filter(translation__language_code="cs")[0]
        unit.pk = True
        unit.source = ""
        self.assertEqual(unit.get_max_length(), 10000)

    @override_settings(LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH=False)
    def test_get_max_length_disabled_default_fallback(self):
        unit = Unit.objects.filter(translation__language_code="cs")[0]
        unit.pk = True
        unit.source = "My test source"
        self.assertEqual(unit.get_max_length(), 10000)


class AnnouncementTest(ModelTestCase):
    """Test(s) for Announcement model."""

    def setUp(self):
        super().setUp()
        Announcement.objects.create(
            language=Language.objects.get(code="cs"), message="test cs"
        )
        Announcement.objects.create(
            language=Language.objects.get(code="de"), message="test de"
        )
        Announcement.objects.create(
            project=self.component.project, message="test project"
        )
        Announcement.objects.create(
            component=self.component,
            project=self.component.project,
            message="test component",
        )
        Announcement.objects.create(message="test global")

    def verify_filter(self, messages, count, message=None):
        """Verify whether messages have given count and first contains string."""
        self.assertEqual(len(messages), count)
        if message is not None:
            self.assertEqual(messages[0].message, message)

    def test_contextfilter_global(self):
        self.verify_filter(Announcement.objects.context_filter(), 1, "test global")

    def test_contextfilter_project(self):
        self.verify_filter(
            Announcement.objects.context_filter(project=self.component.project),
            1,
            "test project",
        )

    def test_contextfilter_component(self):
        self.verify_filter(
            Announcement.objects.context_filter(component=self.component), 2
        )

    def test_contextfilter_translation(self):
        self.verify_filter(
            Announcement.objects.context_filter(
                component=self.component, language=Language.objects.get(code="cs")
            ),
            3,
        )

    def test_contextfilter_language(self):
        self.verify_filter(
            Announcement.objects.context_filter(
                language=Language.objects.get(code="cs")
            ),
            1,
            "test cs",
        )
        self.verify_filter(
            Announcement.objects.context_filter(
                language=Language.objects.get(code="de")
            ),
            1,
            "test de",
        )
