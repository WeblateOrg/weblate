# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib.auth.models import Group as DjangoGroup

from weblate.auth.data import SELECTION_ALL, SELECTION_MANUAL
from weblate.auth.models import Group, Role, User
from weblate.lang.models import Language
from weblate.trans.models import ComponentList, Project
from weblate.trans.tests.test_views import FixtureTestCase


class ModelTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.translation = self.get_translation()
        self.group = Group.objects.create(name="Test", language_selection=SELECTION_ALL)
        self.group.projects.add(self.project)

    def test_num_queries(self) -> None:
        with self.assertNumQueries(8):
            self.user._fetch_permissions()  # noqa: SLF001

    def test_project(self) -> None:
        # No permissions
        self.assertFalse(self.user.can_access_project(self.project))
        self.assertFalse(self.user.has_perm("unit.edit", self.translation))

        # Access permission on adding to group
        self.user.clear_cache()
        self.user.groups.add(self.group)
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertFalse(self.user.has_perm("unit.edit", self.translation))

        # Translate permission on adding role to group
        self.user.clear_cache()
        self.group.roles.add(Role.objects.get(name="Power user"))
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertTrue(self.user.has_perm("unit.edit", self.translation))

    def test_component(self) -> None:
        self.group.projects.remove(self.project)

        # Add user to group of power users
        self.user.groups.add(self.group)
        self.group.roles.add(Role.objects.get(name="Power user"))

        # No permissions as component list is empty
        self.assertFalse(self.user.can_access_project(self.project))
        self.assertFalse(self.user.has_perm("unit.edit", self.translation))

        # Permissions should exist after adding to a component list
        self.user.clear_cache()
        self.group.components.add(self.component)
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertTrue(self.user.has_perm("unit.edit", self.translation))

    def test_componentlist(self) -> None:
        # Add user to group of power users
        self.user.groups.add(self.group)
        self.group.roles.add(Role.objects.get(name="Power user"))

        # Assign component list to a group
        clist = ComponentList.objects.create(name="Test", slug="test")
        self.group.componentlists.add(clist)

        # No permissions as component list is empty
        self.user.clear_cache()
        self.assertFalse(self.user.can_access_project(self.project))
        self.assertFalse(self.user.has_perm("unit.edit", self.translation))

        # Permissions should exist after adding to a component list
        self.user.clear_cache()
        clist.components.add(self.component)
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertTrue(self.user.has_perm("unit.edit", self.translation))

    def test_languages(self) -> None:
        # Add user to group with german language
        self.user.groups.add(self.group)
        self.group.language_selection = SELECTION_MANUAL
        self.group.save()
        self.group.roles.add(Role.objects.get(name="Power user"))
        self.group.languages.set(Language.objects.filter(code="de"), clear=True)

        # Permissions should deny access
        self.user.clear_cache()
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertFalse(self.user.has_perm("unit.edit", self.translation))

        # Adding Czech language should unlock it
        self.user.clear_cache()
        self.group.languages.add(Language.objects.get(code="cs"))
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertTrue(self.user.has_perm("unit.edit", self.translation))

    def test_groups(self) -> None:
        # Add test group
        self.user.groups.add(self.group)
        self.assertEqual(self.user.groups.count(), 3)

        # Add same named Django group
        self.user.groups.add(DjangoGroup.objects.create(name="Test"))
        self.assertEqual(self.user.groups.count(), 3)

        # Add different Django group
        self.user.groups.add(DjangoGroup.objects.create(name="Second"))
        self.assertEqual(self.user.groups.count(), 4)

        # Remove Weblate group
        self.user.groups.remove(Group.objects.get(name="Test"))
        self.assertEqual(self.user.groups.count(), 3)

        # Remove Django group
        self.user.groups.remove(DjangoGroup.objects.get(name="Second"))
        self.assertEqual(self.user.groups.count(), 2)

        # Set Weblate group
        self.user.groups.set(Group.objects.filter(name="Test"))
        self.assertEqual(self.user.groups.count(), 1)

        # Set Django group
        self.user.groups.set(DjangoGroup.objects.filter(name="Second"))
        self.assertEqual(self.user.groups.count(), 1)

    def test_user(self) -> None:
        # Create user with Django User fields
        user = User.objects.create(
            username="test",
            first_name="First",
            last_name="Last",
            is_staff=True,
            is_superuser=True,
        )
        self.assertEqual(user.full_name, "First Last")
        self.assertTrue(user.is_superuser)

        user, created = User.objects.get_or_create(
            username="test", defaults={"first_name": "Test First"}
        )
        self.assertFalse(created)
        self.assertEqual(user.full_name, "First Last")
        self.assertTrue(user.is_superuser)

        user, created = User.objects.get_or_create(
            username="test2",
            defaults={
                "first_name": "Test First",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        self.assertTrue(created)
        self.assertEqual(user.full_name, "Test First")
        self.assertEqual(user.username, "test2")
        self.assertTrue(user.is_superuser)

    def test_projects(self) -> None:
        public_project = Project.objects.create(
            slug="public", name="Public", access_control=Project.ACCESS_PUBLIC
        )
        protected_project = Project.objects.create(
            slug="protected", name="Protected", access_control=Project.ACCESS_PROTECTED
        )
        self.user.clear_cache()
        self.assertEqual(
            set(self.user.allowed_projects.values_list("slug", flat=True)),
            {public_project.slug, protected_project.slug},
        )
        group = Group.objects.create(
            name="All projects", project_selection=SELECTION_ALL
        )
        self.user.groups.add(group)
        self.user.clear_cache()
        self.assertEqual(
            set(self.user.allowed_projects.values_list("slug", flat=True)),
            {public_project.slug, protected_project.slug, self.project.slug},
        )
