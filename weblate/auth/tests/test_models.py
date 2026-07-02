# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from secrets import token_hex
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import Group as DjangoGroup

from weblate.auth import permissions as auth_permissions
from weblate.auth.data import SELECTION_ALL, SELECTION_MANUAL
from weblate.auth.models import (
    Group,
    Permission,
    Role,
    TeamMembership,
    User,
    UserBlock,
    get_anonymous,
)
from weblate.auth.utils import format_membership_limit_language_codes
from weblate.lang.models import Language
from weblate.trans.models import Category, ComponentLink, ComponentList, Project
from weblate.trans.tests.test_views import FixtureComponentTestCase
from weblate.utils.stats import CategoryLanguage, ProjectLanguage


class ModelTest(FixtureComponentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.translation = self.get_translation()
        self.group = Group.objects.create(name="Test", language_selection=SELECTION_ALL)
        self.group.projects.add(self.project)

    def test_num_queries(self) -> None:
        with self.assertNumQueries(4):
            self.assertEqual(len(self.user.component_permissions), 0)
            self.assertEqual(len(self.user.project_permissions), 2)

    def test_cached_memberships_are_materialized(self) -> None:
        self.group.projects.remove(self.project)
        power_user = Role.objects.get(name="Power user")
        czech = Language.objects.get(code="cs")
        german = Language.objects.get(code="de")
        other_component = self.create_link_existing(
            slug="test-cached", name="Test cached"
        )

        component_group = Group.objects.create(
            name="Cached components", language_selection=SELECTION_MANUAL
        )
        component_group.roles.add(power_user)
        component_group.components.add(self.component)
        component_group.languages.add(czech)

        componentlist = ComponentList.objects.create(
            name="Cached memberships", slug="cached-memberships"
        )
        componentlist.components.add(other_component)
        componentlist_group = Group.objects.create(
            name="Cached component lists", language_selection=SELECTION_MANUAL
        )
        componentlist_group.roles.add(power_user)
        componentlist_group.componentlists.add(componentlist)
        componentlist_group.languages.add(czech)

        project_group = Group.objects.create(
            name="Cached projects", language_selection=SELECTION_MANUAL
        )
        project_group.roles.add(power_user)
        project_group.projects.add(self.project)
        project_group.languages.add(czech, german)

        self.user.groups.add(component_group, componentlist_group, project_group)
        TeamMembership.objects.get(
            user=self.user, group=project_group
        ).limit_languages.add(czech)
        self.user.clear_permissions_cache()

        memberships = self.user.cached_memberships

        self.assertIsInstance(memberships, list)
        self.assertNotIsInstance(memberships[0], TeamMembership)
        with self.assertNumQueries(1) as context:
            self.assertIn(self.component.pk, self.user.component_permissions)
            self.assertIn(other_component.pk, self.user.component_permissions)
            self.assertIn(self.project.pk, self.user.project_permissions)
            self.assertFalse(self.user.group_enforces_2fa())
        self.assertIn("weblate_auth_userblock", context.captured_queries[0]["sql"])

    def test_anonymous_project_permissions(self) -> None:
        anonymous = User.objects.get(username=settings.ANONYMOUS_USER_NAME)
        group = Group.objects.create(
            name="Anonymous projects",
            project_selection=SELECTION_ALL,
            language_selection=SELECTION_ALL,
        )
        anonymous.groups.add(group)
        anonymous.clear_permissions_cache()

        self.assertIn(-SELECTION_ALL, anonymous.project_permissions)

    def test_anonymous_user_is_not_shared(self) -> None:
        anonymous = get_anonymous()
        self.assertIsInstance(anonymous.cached_memberships, list)
        self.assertEqual(anonymous.profile.second_factors, [])

        fresh_anonymous = get_anonymous()

        self.assertIsNot(anonymous, fresh_anonymous)
        self.assertIsNot(anonymous.profile, fresh_anonymous.profile)
        self.assertIs(anonymous.profile.user, anonymous)
        self.assertIs(fresh_anonymous.profile.user, fresh_anonymous)
        self.assertNotIn("cached_memberships", fresh_anonymous.__dict__)
        self.assertNotIn("second_factors", fresh_anonymous.profile.__dict__)

    def test_anonymous_user_cache_clear_refreshes_prototype(self) -> None:
        self.addCleanup(get_anonymous.cache_clear)
        anonymous = get_anonymous()
        User.objects.filter(pk=anonymous.pk).update(full_name="Updated anonymous")

        self.assertEqual(get_anonymous().full_name, anonymous.full_name)

        get_anonymous.cache_clear()

        self.assertEqual(get_anonymous().full_name, "Updated anonymous")

    def test_format_membership_limit_language_codes_order(self) -> None:
        membership = TeamMembership.objects.create(user=self.user, group=self.group)
        membership.limit_languages.add(Language.objects.get(code="de"))
        membership.limit_languages.add(Language.objects.get(code="cs"))

        self.assertEqual(format_membership_limit_language_codes(membership), "cs, de")

    def test_num_queries_mixed_group_resolution(self) -> None:
        self.group.projects.remove(self.project)

        power_user = Role.objects.get(name="Power user")
        cs = Language.objects.get(code="cs")
        de = Language.objects.get(code="de")
        other_component = self.create_link_existing(
            slug="test-second", name="Test second"
        )

        component_group = Group.objects.create(
            name="Components", language_selection=SELECTION_MANUAL
        )
        component_group.roles.add(power_user)
        component_group.components.add(self.component)
        component_group.languages.add(cs)

        componentlist = ComponentList.objects.create(
            name="Component list", slug="component-list"
        )
        componentlist.components.add(other_component)
        componentlist_group = Group.objects.create(
            name="Component lists", language_selection=SELECTION_MANUAL
        )
        componentlist_group.roles.add(power_user)
        componentlist_group.componentlists.add(componentlist)
        componentlist_group.languages.add(cs)

        project_group = Group.objects.create(
            name="Projects", language_selection=SELECTION_MANUAL
        )
        project_group.roles.add(power_user)
        project_group.projects.add(self.project)
        project_group.languages.add(cs, de)

        self.user.groups.add(component_group, componentlist_group, project_group)
        self.user.clear_permissions_cache()

        with self.assertNumQueries(9):
            self.assertEqual(len(self.user.component_permissions), 2)
            self.assertIn(self.component.pk, self.user.component_permissions)
            self.assertIn(other_component.pk, self.user.component_permissions)
            self.assertIn(self.project.pk, self.user.project_permissions)

    def test_project(self) -> None:
        # No permissions
        self.assertFalse(self.user.can_access_project(self.project))
        self.assertFalse(self.user.has_perm("unit.edit", self.translation))

        # Access permission on adding to group
        self.user.clear_permissions_cache()
        self.user.groups.add(self.group)
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertFalse(self.user.has_perm("unit.edit", self.translation))

        # Translate permission on adding role to group
        self.user.clear_permissions_cache()
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
        self.user.clear_permissions_cache()
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
        self.user.clear_permissions_cache()
        self.assertFalse(self.user.can_access_project(self.project))
        self.assertFalse(self.user.has_perm("unit.edit", self.translation))

        # Permissions should exist after adding to a component list
        self.user.clear_permissions_cache()
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
        self.user.clear_permissions_cache()
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertFalse(self.user.has_perm("unit.edit", self.translation))

        # Adding Czech language should unlock it
        self.user.clear_permissions_cache()
        self.group.languages.add(Language.objects.get(code="cs"))
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertTrue(self.user.has_perm("unit.edit", self.translation))

    def test_membership_limit_languages(self) -> None:
        self.user.groups.add(self.group)
        self.group.roles.add(Role.objects.get(name="Power user"))
        membership = TeamMembership.objects.get(user=self.user, group=self.group)
        membership.limit_languages.set(Language.objects.filter(code="de"))

        self.user.clear_permissions_cache()
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertFalse(self.user.has_perm("unit.edit", self.translation))

        membership.limit_languages.add(Language.objects.get(code="cs"))

        self.user.clear_permissions_cache()
        self.assertTrue(self.user.has_perm("unit.edit", self.translation))

    def test_membership_limit_excludes_global_permissions(self) -> None:
        user = User.objects.create_user("limited-global", "limited-global@example.com")
        user.groups.clear()
        role = Role.objects.create(name="Limited global")
        role.permissions.add(Permission.objects.get(codename="user.edit"))
        group = Group.objects.create(
            name="Limited global", language_selection=SELECTION_ALL
        )
        group.roles.add(role)
        user.groups.add(group)

        user.clear_permissions_cache()
        self.assertTrue(user.has_perm("user.edit"))

        membership = TeamMembership.objects.get(user=user, group=group)
        membership.limit_languages.set(Language.objects.filter(code="cs"))

        user.clear_permissions_cache()
        self.assertFalse(user.has_perm("user.edit"))

    def test_membership_limit_intersects_team_languages(self) -> None:
        self.user.groups.add(self.group)
        self.group.language_selection = SELECTION_MANUAL
        self.group.save()
        self.group.roles.add(Role.objects.get(name="Power user"))
        self.group.languages.set(Language.objects.filter(code="de"), clear=True)
        membership = TeamMembership.objects.get(user=self.user, group=self.group)
        membership.limit_languages.set(Language.objects.filter(code="cs"))

        self.user.clear_permissions_cache()
        self.assertFalse(self.user.can_access_project(self.project))
        self.assertEqual(self.user.get_project_permissions(self.project), [])
        self.assertFalse(self.user.has_perm("unit.edit", self.translation))

        self.group.languages.add(Language.objects.get(code="cs"))

        self.user.clear_permissions_cache()
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertTrue(self.user.has_perm("unit.edit", self.translation))

    def test_team_language_selection_keeps_project_permissions(self) -> None:
        self.user.groups.add(self.group)
        self.group.language_selection = SELECTION_MANUAL
        self.group.save()
        self.group.roles.add(Role.objects.get(name="Administration"))
        self.group.languages.set(Language.objects.filter(code="cs"), clear=True)

        self.user.clear_permissions_cache()
        self.assertTrue(self.user.has_perm("project.edit", self.project))
        self.assertTrue(self.user.has_perm("translation.add", self.component))
        self.assertEqual(
            list(self.user.managed_projects.values_list("slug", flat=True)),
            [self.project.slug],
        )

    def test_membership_limit_per_role(self) -> None:
        self.project.translation_review = True
        self.project.save(update_fields=["translation_review"])
        review_group = Group.objects.create(
            name="Review", language_selection=SELECTION_ALL
        )
        review_group.projects.add(self.project)
        review_group.roles.add(Role.objects.get(name="Review strings"))

        translate_group = Group.objects.create(
            name="Translate", language_selection=SELECTION_ALL
        )
        translate_group.projects.add(self.project)
        translate_group.roles.add(Role.objects.get(name="Translate"))

        self.user.groups.add(review_group, translate_group)
        TeamMembership.objects.get(
            user=self.user, group=review_group
        ).limit_languages.set(Language.objects.filter(code="de"))

        self.user.clear_permissions_cache()
        self.assertTrue(self.user.has_perm("unit.edit", self.translation))
        self.assertFalse(self.user.has_perm("unit.review", self.translation))

        TeamMembership.objects.get(
            user=self.user, group=review_group
        ).limit_languages.add(Language.objects.get(code="cs"))

        self.user.clear_permissions_cache()
        result = self.user.has_perm("unit.review", self.translation)
        self.assertTrue(result, getattr(result, "reason", result))

    def test_membership_limit_project_language_permissions(self) -> None:
        self.user.groups.add(self.group)
        self.group.roles.add(
            Role.objects.get(name="Automatic translation"),
            Role.objects.get(name="Manage languages"),
        )
        membership = TeamMembership.objects.get(user=self.user, group=self.group)
        membership.limit_languages.set(Language.objects.filter(code="de"))
        unlimited = User.objects.create_user("unlimited", "unlimited@example.com")
        unlimited.groups.add(self.group)

        czech = Language.objects.get(code="cs")
        german = Language.objects.get(code="de")
        category = Category.objects.create(
            project=self.project,
            name="Membership limit",
            slug=f"membership-limit-{token_hex(4)}",
        )
        self.component.category = category
        self.component.save(update_fields=["category"])

        self.user.clear_permissions_cache()
        self.assertFalse(self.user.has_perm("translation.auto", self.project))
        self.assertFalse(self.user.has_perm("translation.auto", category))
        self.assertFalse(self.user.has_perm("translation.auto", self.component))
        self.assertFalse(self.user.has_perm("translation.add", self.component))
        self.assertFalse(
            self.user.has_perm(
                "translation.delete", ProjectLanguage(self.project, czech)
            )
        )
        self.assertFalse(
            self.user.has_perm("translation.auto", ProjectLanguage(self.project, czech))
        )
        self.assertFalse(
            self.user.has_perm("translation.delete", CategoryLanguage(category, czech))
        )
        self.assertFalse(
            self.user.has_perm("translation.auto", CategoryLanguage(category, czech))
        )
        self.assertTrue(
            self.user.has_perm(
                "translation.delete", ProjectLanguage(self.project, german)
            )
        )
        self.assertTrue(
            self.user.has_perm(
                "translation.auto", ProjectLanguage(self.project, german)
            )
        )
        self.assertTrue(
            self.user.has_perm("translation.delete", CategoryLanguage(category, german))
        )
        self.assertTrue(
            self.user.has_perm("translation.auto", CategoryLanguage(category, german))
        )

        def fail_translation_set(_obj):
            msg = "Permission checks should not materialize translations"
            raise AssertionError(msg)

        def fail_component_scope(_obj):
            msg = "Unrestricted project permissions should not check components"
            raise AssertionError(msg)

        with (
            patch.object(
                ProjectLanguage, "translation_set", property(fail_translation_set)
            ),
            patch.object(
                CategoryLanguage, "translation_set", property(fail_translation_set)
            ),
            patch.object(
                auth_permissions,
                "_get_language_scope_components",
                side_effect=fail_component_scope,
            ),
        ):
            self.assertTrue(
                self.user.has_perm(
                    "translation.delete", ProjectLanguage(self.project, german)
                )
            )
            self.assertTrue(
                self.user.has_perm(
                    "translation.delete", CategoryLanguage(category, german)
                )
            )

        shared_project = Project.objects.create(
            name="Shared membership limit",
            slug=f"shared-membership-limit-{token_hex(4)}",
            access_control=Project.ACCESS_PRIVATE,
        )
        shared_category = Category.objects.create(
            project=shared_project,
            name="Shared membership limit",
            slug=f"shared-membership-limit-{token_hex(4)}",
        )
        ComponentLink.objects.create(
            component=self.component,
            project=shared_project,
            category=shared_category,
        )
        self.group.projects.add(shared_project)
        self.user.clear_permissions_cache()
        shared_project_language = ProjectLanguage(shared_project, german)
        shared_category_language = CategoryLanguage(shared_category, german)
        self.assertTrue(shared_project_language.translation_set)
        self.assertTrue(shared_category_language.translation_set)
        self.assertFalse(shared_project_language.action_translation_set.exists())
        self.assertFalse(shared_category_language.action_translation_set.exists())
        self.assertFalse(
            self.user.has_perm("translation.delete", shared_project_language)
        )
        self.assertFalse(
            self.user.has_perm("translation.delete", shared_category_language)
        )

        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        self.user.clear_permissions_cache()
        self.assertFalse(
            self.user.has_perm(
                "translation.delete", ProjectLanguage(self.project, german)
            )
        )
        self.assertFalse(
            self.user.has_perm("translation.delete", CategoryLanguage(category, german))
        )

        self.group.components.add(self.component)
        self.user.clear_permissions_cache()
        self.assertTrue(
            self.user.has_perm(
                "translation.delete", ProjectLanguage(self.project, german)
            )
        )
        self.assertTrue(
            self.user.has_perm("translation.delete", CategoryLanguage(category, german))
        )

        source = self.component.source_language
        membership.limit_languages.add(source)
        self.user.clear_permissions_cache()
        self.assertFalse(
            self.user.has_perm(
                "translation.delete", ProjectLanguage(self.project, source)
            )
        )
        self.assertFalse(
            self.user.has_perm("translation.delete", CategoryLanguage(category, source))
        )

        self.group.roles.add(Role.objects.get(name="Administration"))
        self.user.clear_permissions_cache()
        self.assertFalse(self.user.has_perm("project.edit", self.project))
        self.assertFalse(self.user.managed_projects.filter(pk=self.project.pk).exists())
        self.assertFalse(
            User.objects.all_admins(self.project).filter(pk=self.user.pk).exists()
        )
        self.assertTrue(
            User.objects.all_admins(self.project).filter(pk=unlimited.pk).exists()
        )

    def test_group_removal_removes_admin(self) -> None:
        self.user.groups.add(self.group)
        self.group.admins.add(self.user)

        self.user.groups.remove(self.group)

        self.assertFalse(self.group.admins.filter(pk=self.user.pk).exists())

    def test_group_reverse_clear_removes_admin(self) -> None:
        self.user.groups.add(self.group)
        self.group.admins.add(self.user)

        self.group.user_set.clear()

        self.assertFalse(self.group.admins.filter(pk=self.user.pk).exists())

    def test_group_reverse_set_removes_admin(self) -> None:
        self.user.groups.add(self.group)
        self.group.admins.add(self.user)

        self.group.user_set.set([])

        self.assertFalse(self.group.admins.filter(pk=self.user.pk).exists())

    def test_membership_delete_removes_admin(self) -> None:
        self.user.groups.add(self.group)
        self.group.admins.add(self.user)

        TeamMembership.objects.get(user=self.user, group=self.group).delete()

        self.assertFalse(self.group.admins.filter(pk=self.user.pk).exists())

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

    def test_store_and_log_audit_state(self) -> None:
        actor = User.objects.create_user("auditor", "auditor@example.com", "x")
        audit_group = Group.objects.create(
            name="Audit group",
            defining_project=self.project,
            language_selection=SELECTION_ALL,
        )

        self.user.store_audit_state()
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        self.user.groups.add(audit_group)
        self.user.log_audit_state(None, actor=actor)

        self.user.auditlog_set.get(
            activity="superuser-granted", params__username=actor.username
        )
        self.user.auditlog_set.get(
            activity="team-add",
            params__team=audit_group.name,
            params__username=actor.username,
        )
        self.user.store_audit_state()

    def test_store_audit_state_requires_consumption(self) -> None:
        self.user.store_audit_state()

        with self.assertRaisesMessage(ValueError, "Audit state is already stored!"):
            self.user.store_audit_state()

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
        self.user.clear_permissions_cache()
        self.assertEqual(
            set(self.user.allowed_projects.values_list("slug", flat=True)),
            {public_project.slug, protected_project.slug},
        )
        group = Group.objects.create(
            name="All projects", project_selection=SELECTION_ALL
        )
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        self.assertEqual(
            set(self.user.allowed_projects.values_list("slug", flat=True)),
            {public_project.slug, protected_project.slug, self.project.slug},
        )

    def test_blocked_project_access_query(self) -> None:
        public_project = Project.objects.create(
            slug="public", name="Public", access_control=Project.ACCESS_PUBLIC
        )
        UserBlock.objects.create(user=self.user, project=public_project)

        self.user.clear_permissions_cache()

        self.assertNotIn(public_project, self.user.allowed_projects)

    def test_needs_project_filter(self) -> None:
        Project.objects.create(
            slug="public", name="Public", access_control=Project.ACCESS_PUBLIC
        )

        self.user.clear_permissions_cache()
        self.assertTrue(self.user.needs_project_filter)

        group = Group.objects.create(
            name="All projects", project_selection=SELECTION_ALL
        )
        self.user.groups.add(group)
        self.user.clear_permissions_cache()

        self.assertFalse(self.user.needs_project_filter)

    def test_needs_project_filter_all_projects_query(self) -> None:
        group = Group.objects.create(
            name="All projects", project_selection=SELECTION_ALL
        )
        self.user.groups.add(group)
        self.user.clear_permissions_cache()

        self.assertIn(-SELECTION_ALL, self.user.project_permissions)
        with self.assertNumQueries(0):
            self.assertFalse(self.user.needs_project_filter)

    def test_needs_project_filter_all_projects_with_block_query(self) -> None:
        group = Group.objects.create(
            name="All projects", project_selection=SELECTION_ALL
        )
        self.user.groups.add(group)
        UserBlock.objects.create(user=self.user, project=self.project)
        self.user.clear_permissions_cache()

        self.assertIn(-SELECTION_ALL, self.user.project_permissions)
        self.assertEqual(self.user.project_permissions[self.project.pk], [(None, None)])
        with self.assertNumQueries(0):
            self.assertTrue(self.user.needs_project_filter)

    def test_needs_project_filter_avoids_count_query(self) -> None:
        self.assertNotIn(-SELECTION_ALL, self.user.project_permissions)

        with self.assertNumQueries(1) as context:
            self.assertTrue(self.user.needs_project_filter)

        self.assertNotIn("COUNT(", context.captured_queries[0]["sql"].upper())
