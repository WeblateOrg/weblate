# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from copy import copy
from datetime import UTC, datetime, timedelta
from io import BytesIO

import responses
from django.core.files import File
from django.urls import reverse
from rest_framework.test import APITestCase
from weblate_language_data.languages import LANGUAGES

from weblate.accounts.models import Subscription
from weblate.auth.models import Group, Role, User
from weblate.lang.models import Language
from weblate.memory.models import Memory
from weblate.screenshots.models import Screenshot
from weblate.trans.models import (
    Category,
    Change,
    Component,
    ComponentList,
    Project,
    Translation,
    Unit,
)
from weblate.trans.tests.test_models import fixup_languages_seq
from weblate.trans.tests.utils import RepoTestMixin, get_test_file
from weblate.utils.data import data_dir
from weblate.utils.django_hacks import immediate_on_commit, immediate_on_commit_leave
from weblate.utils.state import STATE_EMPTY, STATE_TRANSLATED

TEST_PO = get_test_file("cs.po")
TEST_POT = get_test_file("hello-charset.pot")
TEST_DOC = get_test_file("cs.html")
TEST_ZIP = get_test_file("translations.zip")
TEST_BADPLURALS = get_test_file("cs-badplurals.po")
TEST_SCREENSHOT = get_test_file("screenshot.png")


class APIBaseTest(APITestCase, RepoTestMixin):
    CREATE_GLOSSARIES: bool = True

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        immediate_on_commit(cls)

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        immediate_on_commit_leave(cls)

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        fixup_languages_seq()

    def setUp(self) -> None:
        Language.objects.flush_object_cache()
        self.clone_test_repos()
        self.component = self.create_component()
        self.translation_kwargs = {
            "language__code": "cs",
            "component__slug": "test",
            "component__project__slug": "test",
        }
        self.component_kwargs = {"slug": "test", "project__slug": "test"}
        self.project_kwargs = {"slug": "test"}
        self.tearDown()
        self.user = User.objects.create_user("apitest", "apitest@example.org", "x")
        group = Group.objects.get(name="Users")
        self.user.groups.add(group)

    def create_acl(self):
        project = Project.objects.create(
            name="ACL", slug="acl", access_control=Project.ACCESS_PRIVATE
        )
        return self._create_component(
            "po-mono", "po-mono/*.po", "po-mono/en.po", project=project
        )

    def authenticate(self, superuser: bool = False) -> None:
        if self.user.is_superuser != superuser:
            self.user.is_superuser = superuser
            self.user.save()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.user.auth_token.key)

    def do_request(
        self,
        name,
        kwargs=None,
        *,
        data=None,
        code=200,
        authenticated: bool = True,
        superuser: bool = False,
        method="get",
        request=None,
        headers=None,
        skip=(),
        format: str = "multipart",  # noqa: A002
    ):
        if authenticated:
            self.authenticate(superuser)
        url = name if name.startswith(("http:", "/")) else reverse(name, kwargs=kwargs)
        response = getattr(self.client, method)(
            url, request, format=format, headers=headers
        )
        content = response.content if hasattr(response, "content") else "<stream>"

        self.assertEqual(
            response.status_code,
            code,
            f"Unexpected status code {response.status_code}: {content}",
        )
        if data is not None:
            for item in skip:
                del response.data[item]
            self.maxDiff = None
            self.assertEqual(response.data, data)
        return response


class UserAPITest(APIBaseTest):
    def test_list(self) -> None:
        response = self.client.get(reverse("api:user-list"))
        self.assertEqual(response.data["count"], 2)
        self.assertNotIn("email", response.data["results"][0])
        self.authenticate(True)
        response = self.client.get(reverse("api:user-list"))
        self.assertEqual(response.data["count"], 2)
        self.assertIsNotNone(response.data["results"][0]["email"])

    def test_get(self) -> None:
        response = self.do_request(
            "api:user-detail",
            kwargs={"username": User.objects.filter(is_active=True)[0].username},
            method="get",
            superuser=True,
            code=200,
        )
        self.assertEqual(response.data["username"], "apitest")

    def test_filter(self) -> None:
        response = self.client.get(reverse("api:user-list"), {"username": "api"})
        self.assertEqual(response.data["count"], 1)

    def test_create(self) -> None:
        self.do_request("api:user-list", method="post", code=403)
        self.do_request(
            "api:user-list",
            method="post",
            superuser=True,
            code=201,
            request={
                "full_name": "Name",
                "username": "name",
                "email": "email@test.com",
                "is_active": True,
            },
        )
        self.assertEqual(User.objects.count(), 3)

    def test_delete(self) -> None:
        self.do_request(
            "api:user-list",
            method="post",
            superuser=True,
            code=201,
            request={
                "full_name": "Name",
                "username": "name",
                "email": "email@test.com",
                "is_active": True,
            },
        )
        self.do_request(
            "api:user-detail",
            kwargs={"username": "name"},
            method="delete",
            superuser=True,
            code=204,
        )
        self.assertEqual(User.objects.count(), 3)
        self.assertEqual(User.objects.filter(is_active=True).count(), 1)

    def test_add_group(self) -> None:
        group = Group.objects.get(name="Viewers")
        self.do_request(
            "api:user-groups",
            kwargs={"username": User.objects.filter(is_active=True)[0].username},
            method="post",
            code=403,
            request={"group_id": group.id},
        )
        self.do_request(
            "api:user-groups",
            kwargs={"username": User.objects.filter(is_active=True)[0].username},
            method="post",
            superuser=True,
            code=400,
            request={"group_id": -1},
        )
        self.do_request(
            "api:user-groups",
            kwargs={"username": User.objects.filter(is_active=True)[0].username},
            method="post",
            superuser=True,
            code=200,
            request={"group_id": group.id},
        )

    def test_remove_group(self) -> None:
        group = Group.objects.get(name="Viewers")
        username = User.objects.filter(is_active=True)[0].username
        self.do_request(
            "api:user-groups",
            kwargs={"username": username},
            method="post",
            code=403,
            request={"group_id": group.id},
        )
        self.do_request(
            "api:user-groups",
            kwargs={"username": username},
            method="post",
            superuser=True,
            code=400,
            request={"group_id": -1},
        )
        response = self.do_request(
            "api:user-groups",
            kwargs={"username": username},
            method="post",
            superuser=True,
            code=200,
            request={"group_id": group.id},
        )
        self.assertIn(
            f"http://example.com/api/groups/{group.id}/", response.data["groups"]
        )
        response = self.do_request(
            "api:user-groups",
            kwargs={"username": username},
            method="delete",
            superuser=True,
            code=200,
            request={"group_id": group.id},
        )
        self.assertNotIn(
            "http://example.com/api/groups/{group.id}/", response.data["groups"]
        )

    def test_list_notifications(self) -> None:
        response = self.do_request(
            "api:user-notifications",
            kwargs={"username": User.objects.filter(is_active=True)[0].username},
            method="get",
            superuser=True,
            code=200,
        )
        self.assertEqual(response.data["count"], 10)

    def test_post_notifications(self) -> None:
        self.do_request(
            "api:user-notifications",
            kwargs={"username": User.objects.filter(is_active=True)[0].username},
            method="post",
            code=403,
        )
        self.do_request(
            "api:user-notifications",
            kwargs={"username": User.objects.filter(is_active=True)[0].username},
            method="post",
            superuser=True,
            code=201,
            request={
                "notification": "RepositoryNotification",
                "scope": 10,
                "frequency": 1,
            },
        )
        self.assertEqual(Subscription.objects.count(), 11)

    def test_get_notifications(self) -> None:
        user = User.objects.filter(is_active=True)[0]
        self.do_request(
            "api:user-notifications-details",
            kwargs={"username": user.username, "subscription_id": 1000},
            method="get",
            code=404,
        )
        self.do_request(
            "api:user-notifications-details",
            kwargs={
                "username": user.username,
                "subscription_id": Subscription.objects.filter(user=user)[0].id,
            },
            method="get",
            code=200,
        )

    def test_put_notifications(self) -> None:
        user = User.objects.filter(is_active=True)[0]
        response = self.do_request(
            "api:user-notifications-details",
            kwargs={
                "username": user.username,
                "subscription_id": Subscription.objects.filter(
                    user=user, notification="NewAnnouncementNotificaton"
                )[0].id,
            },
            method="put",
            superuser=True,
            code=200,
            request={
                "notification": "RepositoryNotification",
                "scope": 10,
                "frequency": 1,
            },
        )
        self.assertEqual(response.data["notification"], "RepositoryNotification")

    def test_patch_notifications(self) -> None:
        user = User.objects.filter(is_active=True)[0]
        response = self.do_request(
            "api:user-notifications-details",
            kwargs={
                "username": user.username,
                "subscription_id": Subscription.objects.filter(
                    user=user, notification="NewAnnouncementNotificaton"
                )[0].id,
            },
            method="patch",
            superuser=True,
            code=200,
            request={"notification": "RepositoryNotification"},
        )
        self.assertEqual(response.data["notification"], "RepositoryNotification")

    def test_delete_notifications(self) -> None:
        user = User.objects.filter(is_active=True)[0]
        self.do_request(
            "api:user-notifications-details",
            kwargs={
                "username": user.username,
                "subscription_id": Subscription.objects.filter(user=user)[0].id,
            },
            method="delete",
            superuser=True,
            code=204,
        )
        self.assertEqual(Subscription.objects.count(), 9)

    def test_statistics(self) -> None:
        user = User.objects.filter(is_active=True)[0]
        request = self.do_request(
            "api:user-statistics",
            kwargs={"username": user.username},
            superuser=True,
        )
        self.assertEqual(request.data["commented"], user.profile.commented)

    def test_put(self) -> None:
        self.do_request(
            "api:user-detail",
            kwargs={"username": User.objects.filter(is_active=True)[0].username},
            method="put",
            code=403,
        )
        self.do_request(
            "api:user-detail",
            kwargs={"username": User.objects.filter(is_active=True)[0].username},
            method="put",
            superuser=True,
            code=200,
            request={
                "full_name": "Name",
                "username": "apitest",
                "email": "apitest@example.org",
                "is_active": True,
            },
        )
        self.assertEqual(User.objects.filter(is_active=True)[0].full_name, "Name")

    def test_patch(self) -> None:
        self.do_request(
            "api:user-detail",
            kwargs={"username": User.objects.filter(is_active=True)[0].username},
            method="patch",
            code=403,
        )
        self.do_request(
            "api:user-detail",
            kwargs={"username": User.objects.filter(is_active=True)[0].username},
            method="patch",
            superuser=True,
            code=200,
            request={"full_name": "Other"},
        )
        self.assertEqual(User.objects.filter(is_active=True)[0].full_name, "Other")


class GroupAPITest(APIBaseTest):
    def test_list(self) -> None:
        response = self.client.get(reverse("api:group-list"))
        self.assertEqual(response.data["count"], 2)
        self.authenticate(True)
        response = self.client.get(reverse("api:group-list"))
        self.assertEqual(response.data["count"], 7)

    def test_get(self) -> None:
        response = self.do_request(
            "api:group-detail",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="get",
            superuser=True,
            code=200,
        )
        self.assertEqual(response.data["name"], "Users")

    def test_create(self) -> None:
        self.do_request("api:group-list", method="post", code=403)
        self.do_request(
            "api:group-list",
            method="post",
            superuser=True,
            code=201,
            format="json",
            request={"name": "Group", "project_selection": 0, "language_selection": 0},
        )
        self.assertEqual(Group.objects.count(), 8)

    def test_create_project(self) -> None:
        self.do_request(
            "api:group-list",
            method="post",
            superuser=True,
            code=201,
            format="json",
            request={
                "name": "Group",
                "project_selection": 0,
                "language_selection": 0,
                "defining_project": reverse(
                    "api:project-detail", kwargs=self.project_kwargs
                ),
            },
        )
        self.assertEqual(Group.objects.count(), 8)
        group = Group.objects.get(name="Group")
        self.assertEqual(group.defining_project, self.component.project)

    def test_add_role(self) -> None:
        role = Role.objects.get(name="Administration")
        self.do_request(
            "api:group-roles",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            code=403,
            request={"role_id": role.id},
        )
        self.do_request(
            "api:group-roles",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=400,
            request={"role_id": -1},
        )
        self.do_request(
            "api:group-roles",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=200,
            request={"role_id": role.id},
        )

    def test_remove_role(self) -> None:
        role = Role.objects.get(name="Administration")
        group = Group.objects.get(name="Users")

        self.do_request(
            "api:group-roles",
            kwargs={"id": group.id},
            method="post",
            superuser=True,
            code=200,
            request={"role_id": role.id},
        )

        self.do_request(
            "api:group-delete-roles",
            kwargs={"id": group.id, "role_id": role.id},
            method="delete",
            code=403,
        )

        self.do_request(
            "api:group-delete-roles",
            kwargs={"id": group.id, "role_id": 99999},
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:group-delete-roles",
            kwargs={"id": group.id, "role_id": role.id},
            method="delete",
            superuser=True,
            code=204,
        )

        self.assertEqual(group.roles.filter(pk=role.id).count(), 0)

    def test_add_component(self) -> None:
        self.do_request(
            "api:group-components",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            code=403,
            request={"component_id": self.component.pk},
        )
        self.do_request(
            "api:group-components",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=400,
            request={"component_id": -1},
        )
        self.do_request(
            "api:group-components",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=200,
            request={"component_id": self.component.pk},
        )

    def test_remove_component(self) -> None:
        self.do_request(
            "api:group-components",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=200,
            request={"component_id": self.component.pk},
        )
        self.do_request(
            "api:group-delete-components",
            kwargs={
                "id": Group.objects.get(name="Users").id,
                "component_id": self.component.pk,
            },
            method="delete",
            code=403,
        )
        self.do_request(
            "api:group-delete-components",
            kwargs={"id": Group.objects.get(name="Users").id, "component_id": 1000},
            method="delete",
            superuser=True,
            code=404,
        )
        self.do_request(
            "api:group-delete-components",
            kwargs={
                "id": Group.objects.get(name="Users").id,
                "component_id": self.component.pk,
            },
            method="delete",
            superuser=True,
            code=204,
        )
        self.assertEqual(Group.objects.get(name="Users").components.count(), 0)

    def test_add_project(self) -> None:
        self.do_request(
            "api:group-projects",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            code=403,
            request={"project_id": Project.objects.get(slug="test").pk},
        )
        self.do_request(
            "api:group-projects",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=400,
            request={"project_id": -1},
        )
        self.do_request(
            "api:group-projects",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=200,
            request={"project_id": Project.objects.get(slug="test").pk},
        )

    def test_remove_project(self) -> None:
        self.do_request(
            "api:group-projects",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=200,
            request={"project_id": Project.objects.get(slug="test").pk},
        )
        self.do_request(
            "api:group-delete-projects",
            kwargs={
                "id": Group.objects.get(name="Users").id,
                "project_id": Project.objects.get(slug="test").pk,
            },
            method="delete",
            code=403,
        )
        self.do_request(
            "api:group-delete-projects",
            kwargs={"id": Group.objects.get(name="Users").id, "project_id": 100000},
            method="delete",
            superuser=True,
            code=404,
        )
        self.do_request(
            "api:group-delete-projects",
            kwargs={
                "id": Group.objects.get(name="Users").id,
                "project_id": Project.objects.get(slug="test").pk,
            },
            method="delete",
            superuser=True,
            code=204,
        )
        self.assertEqual(Group.objects.get(name="Users").projects.count(), 0)

    def test_add_language(self) -> None:
        self.do_request(
            "api:group-languages",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            code=403,
            request={"language_code": "cs"},
        )
        self.do_request(
            "api:group-languages",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=400,
            request={"language_code": "invalid"},
        )
        self.do_request(
            "api:group-languages",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=200,
            request={"language_code": "cs"},
        )

    def test_remove_language(self) -> None:
        self.do_request(
            "api:group-languages",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=200,
            request={"language_code": "cs"},
        )
        self.do_request(
            "api:group-delete-languages",
            kwargs={"id": Group.objects.get(name="Users").id, "language_code": "cs"},
            method="delete",
            code=403,
        )
        self.do_request(
            "api:group-delete-languages",
            kwargs={
                "id": Group.objects.get(name="Users").id,
                "language_code": "invalid",
            },
            method="delete",
            superuser=True,
            code=404,
        )
        self.do_request(
            "api:group-delete-languages",
            kwargs={"id": Group.objects.get(name="Users").id, "language_code": "cs"},
            method="delete",
            superuser=True,
            code=204,
        )

    def test_add_componentlist(self) -> None:
        clist = ComponentList.objects.create(name="Name", slug="name")
        clist.autocomponentlist_set.create()
        self.do_request(
            "api:group-componentlists",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            code=403,
            request={"component_list_id": ComponentList.objects.get().pk},
        )
        self.do_request(
            "api:group-componentlists",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=400,
            request={"component_list_id": -1},
        )
        self.do_request(
            "api:group-componentlists",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=200,
            request={"component_list_id": ComponentList.objects.get().pk},
        )

    def test_remove_componentlist(self) -> None:
        clist = ComponentList.objects.create(name="Name", slug="name")
        clist.autocomponentlist_set.create()
        self.do_request(
            "api:group-componentlists",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=200,
            request={"component_list_id": ComponentList.objects.get().pk},
        )
        self.do_request(
            "api:group-delete-componentlists",
            kwargs={
                "id": Group.objects.get(name="Users").id,
                "component_list_id": ComponentList.objects.get().pk,
            },
            method="delete",
            code=403,
        )
        self.do_request(
            "api:group-delete-componentlists",
            kwargs={
                "id": Group.objects.get(name="Users").id,
                "component_list_id": 100000,
            },
            method="delete",
            superuser=True,
            code=404,
        )
        self.do_request(
            "api:group-delete-componentlists",
            kwargs={
                "id": Group.objects.get(name="Users").id,
                "component_list_id": ComponentList.objects.get().pk,
            },
            method="delete",
            superuser=True,
            code=204,
        )
        self.assertEqual(Group.objects.get(name="Users").componentlists.count(), 0)

    def test_delete(self) -> None:
        self.do_request(
            "api:group-detail",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="delete",
            superuser=True,
            code=204,
        )
        self.assertEqual(Group.objects.count(), 6)

    def test_put(self) -> None:
        self.do_request(
            "api:group-list",
            method="post",
            superuser=True,
            code=201,
            format="json",
            request={"name": "Group", "project_selection": 0, "language_selection": 0},
        )
        self.do_request(
            "api:group-detail",
            kwargs={"id": Group.objects.get(name="Group").id},
            method="put",
            code=403,
        )
        self.do_request(
            "api:group-detail",
            kwargs={"id": Group.objects.get(name="Group").id},
            method="put",
            superuser=True,
            code=200,
            format="json",
            request={"name": "Group", "project_selection": 0, "language_selection": 1},
        )
        self.assertEqual(Group.objects.get(name="Group").language_selection, 1)

    def test_patch(self) -> None:
        self.do_request(
            "api:group-detail",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="patch",
            code=403,
        )
        self.do_request(
            "api:group-detail",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="patch",
            superuser=True,
            code=200,
            request={"language_selection": 1},
        )
        self.assertEqual(Group.objects.get(name="Users").language_selection, 1)

    def test_grant_admin(self) -> None:
        group = Group.objects.create(name="Test Group")
        response = self.do_request(
            "api:group-grant-admin",
            kwargs={"id": group.id},
            method="post",
            superuser=True,
            request={"user_id": self.user.id},
        )
        self.assertIn("Administration rights granted.", response.data)

        # Invalid user ID
        response = self.do_request(
            "api:group-grant-admin",
            kwargs={"id": group.id},
            method="post",
            superuser=True,
            request={"user_id": -1},
            code=400,
        )

        # Missing user ID
        response = self.do_request(
            "api:group-grant-admin",
            kwargs={"id": group.id},
            method="post",
            superuser=True,
            code=400,
        )

    def test_group_admin_edit(self) -> None:
        user = User.objects.create_user(username="testuser", password="12345")
        group = Group.objects.create(name="Test Group")
        response = self.do_request(
            "api:group-grant-admin",
            kwargs={"id": group.id},
            method="post",
            superuser=False,
            request={"user_id": user.id},
            code=404,
        )
        group.admins.add(self.user)
        response = self.do_request(
            "api:group-grant-admin",
            kwargs={"id": group.id},
            method="post",
            superuser=False,
            request={"user_id": user.id},
        )
        self.assertIn("Administration rights granted.", response.data)

    def test_revoke_admin(self) -> None:
        group = Group.objects.create(name="Test Group")
        user = User.objects.create_user(username="testuser", password="12345")
        group.admins.add(user)

        response = self.do_request(
            "api:group-revoke-admin",
            kwargs={"id": group.id, "user_pk": 6555555},
            method="delete",
            superuser=True,
            code=400,
        )
        response = self.do_request(
            "api:group-revoke-admin",
            kwargs={"id": group.id, "user_pk": user.id},
            method="delete",
            superuser=True,
        )

        admins_ids = [admin["id"] for admin in response.data.get("admins", [])]
        self.assertNotIn(user.id, admins_ids)


class RoleAPITest(APIBaseTest):
    def test_list_roles(self) -> None:
        response = self.client.get(reverse("api:role-list"))
        self.assertEqual(response.data["count"], 2)
        self.authenticate(True)
        response = self.client.get(reverse("api:role-list"))
        self.assertEqual(response.data["count"], 15)

    def test_get_role(self) -> None:
        role = Role.objects.get(name="Access repository")
        response = self.client.get(reverse("api:role-detail", kwargs={"id": role.pk}))
        self.assertEqual(response.data["name"], role.name)

    def test_create(self) -> None:
        self.do_request("api:role-list", method="post", code=403)
        self.do_request(
            "api:role-list",
            method="post",
            superuser=True,
            code=400,
            format="json",
            request={"name": "Role", "permissions": ["invalid.codename"]},
        )
        self.do_request(
            "api:role-list",
            method="post",
            superuser=True,
            code=201,
            format="json",
            request={"name": "Role", "permissions": ["suggestion.add", "comment.add"]},
        )
        self.assertEqual(Role.objects.count(), 16)
        self.assertEqual(Role.objects.get(name="Role").permissions.count(), 2)

    def test_delete(self) -> None:
        self.do_request(
            "api:role-detail",
            kwargs={"id": Role.objects.all()[0].pk},
            method="delete",
            superuser=True,
            code=204,
        )
        self.assertEqual(Role.objects.count(), 14)

    def test_put(self) -> None:
        self.do_request(
            "api:role-detail",
            kwargs={"id": Role.objects.order_by("id").all()[0].pk},
            method="put",
            code=403,
        )
        self.do_request(
            "api:role-detail",
            kwargs={"id": Role.objects.order_by("id").all()[0].pk},
            method="put",
            superuser=True,
            code=200,
            format="json",
            request={"name": "Role", "permissions": ["suggestion.add"]},
        )
        self.assertEqual(Role.objects.order_by("id").all()[0].name, "Role")
        self.assertEqual(Role.objects.order_by("id").all()[0].permissions.count(), 1)
        self.assertEqual(
            Role.objects.order_by("id").all()[0].permissions.get().codename,
            "suggestion.add",
        )
        # Add permission
        self.do_request(
            "api:role-detail",
            kwargs={"id": Role.objects.order_by("id").all()[0].pk},
            method="put",
            superuser=True,
            code=200,
            format="json",
            request={"name": "Role", "permissions": ["suggestion.add", "comment.add"]},
        )
        self.assertEqual(Role.objects.order_by("id").all()[0].permissions.count(), 2)
        # Remove permission
        self.do_request(
            "api:role-detail",
            kwargs={"id": Role.objects.order_by("id").all()[0].pk},
            method="put",
            superuser=True,
            code=200,
            format="json",
            request={"name": "Role", "permissions": ["comment.add"]},
        )
        self.assertEqual(Role.objects.order_by("id").all()[0].permissions.count(), 1)
        self.assertEqual(
            Role.objects.order_by("id").all()[0].permissions.get().codename,
            "comment.add",
        )

    def test_patch(self) -> None:
        role = Role.objects.get(name="Access repository")
        self.assertEqual(role.permissions.count(), 3)
        self.do_request(
            "api:role-detail",
            kwargs={"id": role.pk},
            method="patch",
            code=403,
        )
        self.do_request(
            "api:role-detail",
            kwargs={"id": role.pk},
            method="patch",
            superuser=True,
            code=200,
            request={"name": "New Role"},
        )
        self.assertEqual(Role.objects.get(pk=role.pk).name, "New Role")
        self.do_request(
            "api:role-detail",
            kwargs={"id": role.pk},
            method="patch",
            superuser=True,
            code=200,
            format="json",
            request={"permissions": ["comment.add"]},
        )
        self.assertEqual(Role.objects.get(pk=role.pk).permissions.count(), 4)


class ProjectAPITest(APIBaseTest):
    def test_list_projects(self) -> None:
        response = self.client.get(reverse("api:project-list"))
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["slug"], "test")

    def test_list_projects_acl(self) -> None:
        self.create_acl()
        response = self.client.get(reverse("api:project-list"))
        self.assertEqual(response.data["count"], 1)
        self.authenticate(True)
        response = self.client.get(reverse("api:project-list"))
        self.assertEqual(response.data["count"], 2)

    def test_get_project(self) -> None:
        response = self.client.get(
            reverse("api:project-detail", kwargs=self.project_kwargs)
        )
        self.assertEqual(response.data["slug"], "test")

    def test_repo_op_denied(self) -> None:
        for operation in ("push", "pull", "reset", "cleanup", "commit"):
            self.do_request(
                "api:project-repository",
                self.project_kwargs,
                code=403,
                method="post",
                request={"operation": operation},
            )

    def test_repo_ops(self) -> None:
        for operation in ("push", "pull", "reset", "cleanup", "commit"):
            self.do_request(
                "api:project-repository",
                self.project_kwargs,
                method="post",
                superuser=True,
                request={"operation": operation},
            )

    def test_repo_invalid(self) -> None:
        self.do_request(
            "api:project-repository",
            self.project_kwargs,
            code=400,
            method="post",
            superuser=True,
            request={"operation": "invalid"},
        )

    def test_repo_status_denied(self) -> None:
        self.do_request("api:project-repository", self.project_kwargs, code=403)

    def test_repo_status(self) -> None:
        self.do_request(
            "api:project-repository",
            self.project_kwargs,
            superuser=True,
            data={"needs_push": False, "needs_merge": False, "needs_commit": False},
            skip=("url",),
        )

    def test_components(self) -> None:
        request = self.do_request("api:project-components", self.project_kwargs)
        self.assertEqual(request.data["count"], 2)

    def test_changes(self) -> None:
        request = self.do_request("api:project-changes", self.project_kwargs)
        self.assertEqual(request.data["count"], 30)

    def test_statistics(self) -> None:
        request = self.do_request("api:project-statistics", self.project_kwargs)
        self.assertEqual(request.data["total"], 16)

    def test_languages(self) -> None:
        request = self.do_request("api:project-languages", self.project_kwargs)
        self.assertEqual(len(request.data), 4)
        response = self.do_request(
            "api:project-languages",
            self.project_kwargs,
            request={
                "format": "json-flat",
            },
        )
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 4)
        for item in data:
            self.assertIsInstance(item, dict)

    def test_delete(self) -> None:
        self.do_request(
            "api:project-detail", self.project_kwargs, method="delete", code=403
        )
        self.do_request(
            "api:project-detail",
            self.project_kwargs,
            method="delete",
            superuser=True,
            code=204,
        )
        self.assertEqual(Project.objects.count(), 0)

    def test_create(self) -> None:
        self.do_request(
            "api:project-list",
            method="post",
            code=403,
            request={
                "name": "API project",
                "slug": "api-project",
                "web": "https://weblate.org/",
            },
        )
        self.do_request(
            "api:project-list",
            method="post",
            code=201,
            superuser=True,
            request={
                "name": "API project",
                "slug": "api-project",
                "web": "https://weblate.org/",
            },
        )
        self.assertEqual(Project.objects.count(), 2)

    def test_create_with_source_language(self) -> None:
        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=403,
            format="json",
            request={
                "name": "API project",
                "slug": "api-project",
                "source_language": {
                    "code": "ru",
                    "name": "Russian",
                    "direction": "ltr",
                },
                "repo": self.format_local_path(self.git_repo_path),
                "filemask": "po/*.po",
                "file_format": "po",
                "new_lang": "none",
            },
        )
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            format="json",
            request={
                "name": "API project",
                "slug": "api-project",
                "source_language": {
                    "code": "ru",
                    "name": "Russian",
                    "direction": "ltr",
                },
                "repo": self.format_local_path(self.git_repo_path),
                "filemask": "po/*.po",
                "file_format": "po",
                "new_lang": "none",
            },
        )
        error_response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            format="json",
            request={
                "name": "API project 2",
                "slug": "api-project-2",
                "repo": self.format_local_path(self.git_repo_path),
                "filemask": "po/*.po",
                "file_format": "po",
                "new_lang": "none",
                "source_language": {
                    "code": "invalid",
                    "name": "Invalid",
                    "direction": "ltr",
                },
            },
        )
        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(Component.objects.count(), 3)
        self.assertEqual(response.data["source_language"]["code"], "ru")
        self.assertEqual(
            Component.objects.get(slug="api-project").source_language.code, "ru"
        )
        self.assertEqual(
            error_response.data,
            {
                "type": "validation_error",
                "errors": [
                    {
                        "code": "invalid",
                        "detail": "Language with this language code was not found.",
                        "attr": "source_language.code",
                    }
                ],
            },
        )

    def test_create_with_source_language_string(self, format="json") -> None:  # noqa: A002
        payload = {
            "name": "API project",
            "slug": "api-project",
            "source_language": '{"code": "ru"}',
            "repo": self.format_local_path(self.git_repo_path),
            "filemask": "po/*.po",
            "file_format": "po",
            "new_lang": "none",
        }
        # Request with wrong payload format should fail
        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            format=format,
            request=payload,
        )
        # Correct payload
        payload["source_language"] = "ru"
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            format=format,
            request=payload,
        )
        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(Component.objects.count(), 3)
        self.assertEqual(response.data["source_language"]["code"], "ru")
        self.assertEqual(
            Component.objects.get(slug="api-project").source_language.code, "ru"
        )

    def test_create_with_source_language_string_multipart(self) -> None:
        self.test_create_with_source_language_string(format="multipart")

    def test_create_component(self) -> None:
        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=403,
            request={
                "name": "API project",
                "slug": "api-project",
                "web": "https://weblate.org/",
            },
        )
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={
                "name": "API project",
                "slug": "api-project",
                "repo": self.format_local_path(self.git_repo_path),
                "filemask": "po/*.po",
                "file_format": "po",
                "push": "https://username:password@github.com/example/push.git",
                "new_lang": "none",
            },
        )
        self.assertEqual(Component.objects.count(), 3)
        component = Component.objects.get(slug="api-project", project__slug="test")
        self.assertEqual(
            component.push,
            "https://username:password@github.com/example/push.git",
        )
        self.assertFalse(component.manage_units)
        self.assertFalse(response.data["manage_units"])
        self.assertEqual(response.data["push"], "https://github.com/example/push.git")
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={
                "name": "Other",
                "slug": "other",
                "repo": self.format_local_path(self.git_repo_path),
                "filemask": "android/values-*/strings.xml",
                "file_format": "aresource",
                "template": "android/values/strings.xml",
                "new_lang": "none",
            },
        )
        self.assertEqual(Component.objects.count(), 4)
        component = Component.objects.get(slug="other", project__slug="test")
        self.assertTrue(component.manage_units)
        self.assertTrue(response.data["manage_units"])
        # Creating duplicate
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={
                "name": "Other",
                "slug": "other",
                "repo": self.format_local_path(self.git_repo_path),
                "filemask": "android/values-*/strings.xml",
                "file_format": "aresource",
                "template": "android/values/strings.xml",
                "new_lang": "none",
            },
        )

    def test_create_component_category(self) -> None:
        category = self.component.project.category_set.create(
            name="Category", slug="category"
        )
        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={
                "name": "API project",
                "slug": "api-project",
                "repo": self.format_local_path(self.git_repo_path),
                "filemask": "po/*.po",
                "file_format": "po",
                "push": "https://username:password@github.com/example/push.git",
                "new_lang": "none",
                "category": reverse("api:category-detail", kwargs={"pk": category.pk}),
            },
        )
        self.assertEqual(Component.objects.count(), 3)

    def test_create_component_autoshare(self) -> None:
        repo = self.component.repo
        branch = self.component.branch
        link_repo = self.component.get_repo_link_url()
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={
                "name": "C 1",
                "slug": "c-1",
                "repo": repo,
                "branch": branch,
                "filemask": "po/*.po",
                "file_format": "po",
                "new_lang": "none",
            },
        )
        self.assertEqual(response.data["repo"], repo)
        self.assertEqual(response.data["branch"], branch)
        component = Component.objects.get(slug="c-1")
        self.assertEqual(component.repo, link_repo)
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={
                "name": "C 2",
                "slug": "c-2",
                "repo": repo,
                "branch": "translations",
                "filemask": "translations/*.po",
                "file_format": "po",
                "new_lang": "none",
            },
        )
        self.assertEqual(response.data["repo"], repo)
        self.assertEqual(response.data["branch"], "translations")
        component = Component.objects.get(slug="c-2")
        self.assertEqual(component.repo, repo)
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={
                "name": "C 3",
                "slug": "c-3",
                "repo": repo,
                "branch": branch,
                "filemask": "po/*.po",
                "file_format": "po",
                "new_lang": "none",
                "disable_autoshare": "1",
            },
        )
        self.assertEqual(response.data["repo"], repo)
        self.assertEqual(response.data["branch"], branch)
        component = Component.objects.get(slug="c-3")
        self.assertEqual(component.repo, repo)

    def test_create_component_blank_request(self) -> None:
        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={},
        )

    def test_create_component_no_format(self) -> None:
        repo_url = self.format_local_path(self.git_repo_path)
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={
                "name": "API project",
                "slug": "api-project",
                "repo": repo_url,
                "filemask": "po/*.po",
                "new_lang": "none",
            },
        )
        self.maxDiff = None
        self.assertEqual(
            {
                "errors": [
                    {
                        "attr": "file_format",
                        "code": "required",
                        "detail": "This field is required.",
                    }
                ],
                "type": "validation_error",
            },
            response.data,
        )

    def test_create_component_link(self) -> None:
        repo_url = self.format_local_path(self.git_repo_path)
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={
                "name": "API project",
                "slug": "api-project",
                "repo": "weblate://test/test",
                "filemask": "po/*.po",
                "file_format": "po",
                "new_lang": "none",
            },
        )
        self.assertEqual(Component.objects.count(), 3)
        component = Component.objects.get(slug="api-project", project__slug="test")
        self.assertEqual(component.repo, "weblate://test/test")
        self.assertEqual(component.full_path, self.component.full_path)
        self.assertEqual(response.data["repo"], repo_url)

        # Verify that the repo was not checked out
        real_path = os.path.join(data_dir("vcs"), *component.get_url_path())
        self.assertFalse(os.path.exists(real_path))

    def test_create_component_no_push(self) -> None:
        repo_url = self.format_local_path(self.git_repo_path)
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={
                "name": "API project",
                "slug": "api-project",
                "repo": repo_url,
                "filemask": "po/*.po",
                "file_format": "po",
                "new_lang": "none",
            },
        )
        self.assertEqual(Component.objects.count(), 3)
        # Verify auto linking is in place
        self.assertEqual(
            Component.objects.get(slug="api-project", project__slug="test").repo,
            "weblate://test/test",
        )
        self.assertEqual(response.data["repo"], repo_url)
        self.assertEqual(
            response.data["linked_component"],
            "http://example.com"
            + reverse("api:component-detail", kwargs=self.component_kwargs),
        )

    def test_create_component_empty_push(self) -> None:
        repo_url = self.format_local_path(self.git_repo_path)
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={
                "name": "API project",
                "slug": "api-project",
                "repo": repo_url,
                "push": "",
                "filemask": "po/*.po",
                "file_format": "po",
                "new_lang": "none",
            },
        )
        self.assertEqual(Component.objects.count(), 3)
        # Verify auto linking is in place
        self.assertEqual(
            Component.objects.get(slug="api-project", project__slug="test").repo,
            "weblate://test/test",
        )
        self.assertEqual(response.data["repo"], repo_url)
        self.assertEqual(
            response.data["linked_component"],
            "http://example.com"
            + reverse("api:component-detail", kwargs=self.component_kwargs),
        )

    def test_create_component_no_match(self) -> None:
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={
                "name": "API project",
                "slug": "api-project",
                "repo": self.format_local_path(self.git_repo_path),
                "filemask": "po/*.invalid-po",
                "file_format": "po",
                "new_lang": "none",
            },
        )
        self.assertEqual(Component.objects.count(), 2)
        self.maxDiff = None
        self.assertEqual(
            {
                "errors": [
                    {
                        "attr": "filemask",
                        "code": "invalid",
                        "detail": "The file mask did not match any files.",
                    }
                ],
                "type": "validation_error",
            },
            response.data,
        )

    def test_create_component_local(self) -> None:
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={
                "name": "Local project",
                "slug": "local-project",
                "repo": "local:",
                "vcs": "local",
                "filemask": "*.strings",
                "template": "en.strings",
                "file_format": "strings-utf8",
                "new_lang": "none",
            },
        )
        self.assertEqual(response.data["repo"], "local:")
        self.assertEqual(Component.objects.count(), 3)

    def test_create_component_local_nonexisting(self) -> None:
        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={
                "name": "Local project",
                "slug": "local-project",
                "repo": "local:",
                "vcs": "local",
                "filemask": "*.xliff",
                "template": "en.xliff",
                "file_format": "xliff",
                "new_lang": "none",
            },
        )

    def test_create_component_local_url(self) -> None:
        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={
                "name": "Local project",
                "slug": "local-project",
                "repo": "local:",
                "filemask": "*.xliff",
                "file_format": "xliff",
                "new_lang": "none",
            },
        )

    def test_patch(self) -> None:
        self.do_request(
            "api:project-detail", self.project_kwargs, method="patch", code=403
        )
        response = self.do_request(
            "api:project-detail",
            self.project_kwargs,
            method="patch",
            superuser=True,
            code=200,
            format="json",
            request={"slug": "new-slug"},
        )
        self.assertEqual(response.data["slug"], "new-slug")

    def test_create_component_docfile(self) -> None:
        with open(TEST_DOC, "rb") as handle:
            response = self.do_request(
                "api:project-components",
                self.project_kwargs,
                method="post",
                code=201,
                superuser=True,
                request={
                    "docfile": handle,
                    "name": "Local project",
                    "slug": "local-project",
                    "file_format": "html",
                    "new_lang": "add",
                    "edit_template": "0",
                },
            )
        self.assertEqual(response.data["repo"], "local:")
        self.assertEqual(response.data["filemask"], "local-project/*.html")
        self.assertEqual(Component.objects.count(), 3)

    def test_create_component_docfile_mask(self) -> None:
        with open(TEST_DOC, "rb") as handle:
            response = self.do_request(
                "api:project-components",
                self.project_kwargs,
                method="post",
                code=201,
                superuser=True,
                request={
                    "docfile": handle,
                    "name": "Local project",
                    "slug": "local-project",
                    "file_format": "html",
                    "new_lang": "add",
                    "filemask": "doc/*.html",
                    "edit_template": "0",
                },
            )
        self.assertEqual(response.data["repo"], "local:")
        self.assertEqual(response.data["filemask"], "doc/*.html")
        self.assertEqual(Component.objects.count(), 3)

    def test_create_component_docfile_mask_outside(self) -> None:
        with open(TEST_DOC, "rb") as handle:
            self.do_request(
                "api:project-components",
                self.project_kwargs,
                method="post",
                code=400,
                superuser=True,
                request={
                    "docfile": handle,
                    "name": "Local project",
                    "slug": "local-project",
                    "file_format": "html",
                    "new_lang": "add",
                    "filemask": "../doc/*.html",
                },
            )
        self.assertEqual(Component.objects.count(), 2)

    def test_create_component_docfile_missing(self) -> None:
        with open(TEST_DOC, "rb") as handle:
            self.do_request(
                "api:project-components",
                self.project_kwargs,
                method="post",
                code=400,
                superuser=True,
                request={
                    "docfile": handle,
                    "file_format": "html",
                    "new_lang": "add",
                },
            )
        with open(TEST_DOC, "rb") as handle:
            self.do_request(
                "api:project-components",
                self.project_kwargs,
                method="post",
                code=400,
                superuser=True,
                request={
                    "docfile": handle,
                    "name": "Local project",
                    "slug": "local-project",
                    "new_lang": "add",
                },
            )

    def test_create_component_docfile_json(self) -> None:
        with open(TEST_DOC, "rb") as handle:
            self.do_request(
                "api:project-components",
                self.project_kwargs,
                method="post",
                code=400,
                superuser=True,
                format="json",
                request={
                    "docfile": handle.read(),
                    "name": "Local project",
                    "slug": "local-project",
                    "file_format": "html",
                    "new_lang": "add",
                    "edit_template": "0",
                },
            )

    def test_create_component_docfile_language(self) -> None:
        with open(TEST_DOC, "rb") as handle:
            response = self.do_request(
                "api:project-components",
                self.project_kwargs,
                method="post",
                code=201,
                superuser=True,
                request={
                    "docfile": handle,
                    "name": "Local project",
                    "slug": "local-project",
                    "source_language": "cs",
                    "file_format": "html",
                    "new_lang": "add",
                    "edit_template": "0",
                },
            )
        self.assertEqual(response.data["repo"], "local:")
        self.assertEqual(response.data["template"], "local-project/cs.html")
        self.assertEqual(Component.objects.count(), 3)

    def test_create_component_zipfile(self) -> None:
        with open(TEST_ZIP, "rb") as handle:
            response = self.do_request(
                "api:project-components",
                self.project_kwargs,
                method="post",
                code=201,
                superuser=True,
                request={
                    "zipfile": handle,
                    "name": "Local project",
                    "slug": "local-project",
                    "filemask": "*.po",
                    "new_base": "project.pot",
                    "file_format": "po",
                    "new_lang": "none",
                },
            )
        self.assertEqual(response.data["repo"], "local:")
        self.assertEqual(Component.objects.count(), 3)

    def test_create_component_zipfile_bad_params(self) -> None:
        with open(TEST_ZIP, "rb") as handle:
            self.do_request(
                "api:project-components",
                self.project_kwargs,
                method="post",
                code=400,
                superuser=True,
                request={
                    "zipfile": handle,
                    "name": "Local project",
                    "slug": "local-project",
                    "filemask": "missing/*.po",
                    "new_base": "missing-project.pot",
                    "file_format": "po",
                    "new_lang": "none",
                },
            )
        with open(TEST_ZIP, "rb") as handle:
            self.do_request(
                "api:project-components",
                self.project_kwargs,
                method="post",
                code=400,
                superuser=True,
                request={
                    "zipfile": handle,
                    "name": "Local project",
                    "slug": "local-project",
                    "filemask": "missing/*.po",
                    "file_format": "po",
                    "new_lang": "none",
                },
            )
        with open(TEST_PO, "rb") as handle:
            self.do_request(
                "api:project-components",
                self.project_kwargs,
                method="post",
                code=400,
                superuser=True,
                request={
                    "zipfile": handle,
                    "name": "Local project",
                    "slug": "local-project",
                    "filemask": "*.po",
                    "new_base": "project.pot",
                    "file_format": "po",
                    "push": "https://username:password@github.com/example/push.git",
                    "new_lang": "none",
                },
            )

    def test_create_component_overwrite(self) -> None:
        translation = self.component.translation_set.get(language_code="cs")
        trasnslation_filename = translation.get_filename()
        self.assertTrue(os.path.exists(trasnslation_filename))
        with open(TEST_PO, "rb") as handle:
            self.do_request(
                "api:project-components",
                self.project_kwargs,
                method="post",
                code=400,
                superuser=True,
                request={
                    "zipfile": handle,
                    "name": "Local project",
                    "slug": self.component.slug,
                    "filemask": "*.po",
                    "new_base": "project.pot",
                    "file_format": "po",
                    "push": "https://username:password@github.com/example/push.git",
                    "new_lang": "none",
                },
            )
        self.assertTrue(
            os.path.exists(self.component.full_path),
            f"File {self.component.full_path} does not exist",
        )

        self.assertTrue(
            os.path.exists(trasnslation_filename),
            f"File {trasnslation_filename} does not exist",
        )

    def test_create_component_enforced(self) -> None:
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={
                "name": "Local project",
                "slug": "local-project",
                "repo": "local:",
                "vcs": "local",
                "filemask": "*.strings",
                "template": "en.strings",
                "file_format": "strings-utf8",
                "new_lang": "none",
                "enforced_checks": "",
            },
        )
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={
                "name": "Local project",
                "slug": "local-project",
                "repo": "local:",
                "vcs": "local",
                "filemask": "*.strings",
                "template": "en.strings",
                "file_format": "strings-utf8",
                "new_lang": "none",
                "enforced_checks": '""',
            },
        )
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            format="json",
            request={
                "name": "Local project",
                "slug": "local-project",
                "repo": "local:",
                "vcs": "local",
                "filemask": "*.strings",
                "template": "en.strings",
                "file_format": "strings-utf8",
                "new_lang": "none",
                "enforced_checks": "",
            },
        )
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            format="json",
            request={
                "name": "Local project",
                "slug": "local-project",
                "repo": "local:",
                "vcs": "local",
                "filemask": "*.strings",
                "template": "en.strings",
                "file_format": "strings-utf8",
                "new_lang": "none",
                "enforced_checks": ["xxx"],
            },
        )
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            format="json",
            request={
                "name": "Local project",
                "slug": "local-project",
                "repo": "local:",
                "vcs": "local",
                "filemask": "*.strings",
                "template": "en.strings",
                "file_format": "strings-utf8",
                "new_lang": "none",
                "enforced_checks": ["same"],
            },
        )
        self.assertEqual(response.data["repo"], "local:")
        self.assertEqual(response.data["enforced_checks"], ["same"])
        self.assertEqual(Component.objects.count(), 3)
        component = Component.objects.get(slug="local-project")
        self.assertEqual(component.enforced_checks, ["same"])

    def test_download_private_project_translations(self) -> None:
        project = self.component.project
        project.access_control = Project.ACCESS_PRIVATE
        project.save(update_fields=["access_control"])
        self.do_request(
            "api:project-file",
            self.project_kwargs,
            method="get",
            code=404,
            request={"format": "zip"},
        )

    def test_download_project_translations_prohibited(self) -> None:
        self.authenticate()
        self.user.groups.clear()
        self.user.clear_cache()
        self.do_request(
            "api:project-file",
            self.project_kwargs,
            method="get",
            code=403,
            request={"format": "zip"},
        )

    def test_download_project_translations(self) -> None:
        response = self.do_request(
            "api:project-file",
            self.project_kwargs,
            method="get",
            code=200,
            superuser=True,
            request={"format": "zip"},
        )
        self.assertEqual(response.headers["content-type"], "application/zip")

    def test_download_project_translations_converted(self) -> None:
        response = self.do_request(
            "api:project-file",
            self.project_kwargs,
            method="get",
            code=200,
            superuser=True,
            request={"format": "zip:csv"},
        )
        self.assertEqual(response.headers["content-type"], "application/zip")

    def test_download_project_translations_target_language(self) -> None:
        response = self.do_request(
            "api:project-file",
            self.project_kwargs,
            method="get",
            code=200,
            superuser=True,
            request={"format": "zip", "language_code": "cs"},
        )
        self.assertEqual(response.headers["content-type"], "application/zip")

    def test_credits(self) -> None:
        self.do_request(
            "api:component-credits",
            self.component_kwargs,
            method="get",
            code=401,
            authenticated=False,
        )

        # mandatory date parameters
        self.do_request(
            "api:component-credits", self.component_kwargs, method="get", code=400
        )

        start = datetime.now(tz=UTC) - timedelta(days=1)
        end = datetime.now(tz=UTC) + timedelta(days=1)

        response = self.do_request(
            "api:component-credits",
            self.component_kwargs,
            method="get",
            code=200,
            request={"start": start.isoformat(), "end": end.isoformat()},
        )
        self.assertEqual(response.data, [])

        response = self.do_request(
            "api:component-credits",
            self.component_kwargs,
            method="get",
            code=200,
            request={"start": start.isoformat(), "end": end.isoformat(), "lang": "fr"},
        )
        self.assertEqual(response.data, [])

    @responses.activate
    def test_install_machinery(self) -> None:
        """Test the machinery settings API endpoint for various scenarios."""
        from weblate.machinery.tests import AlibabaTranslationTest, DeepLTranslationTest

        # unauthenticated get
        self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="get",
            code=403,
            authenticated=True,
            superuser=False,
        )

        # unauthenticated post
        self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="post",
            code=403,
            authenticated=True,
            superuser=False,
            request={"service": "weblate"},
        )

        # missing service
        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={},
        )

        # unknown service
        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={"service": "unknown"},
        )

        # create configuration: no form
        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={"service": "weblate"},
        )

        # missing required field
        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={
                "service": "deepl",
                "configuration": {"wrong": ""},
            },
            format="json",
        )

        # invalid field with multipart
        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={
                "service": "deepl",
                "configuration": "{malformed_json",
            },
        )

        # create configuration: valid form with multipart
        DeepLTranslationTest.mock_response()
        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={
                "service": "deepl",
                "configuration": '{"key": "x", "url": "https://api.deepl.com/v2/"}',
            },
        )

        # create configuration: valid form with json
        AlibabaTranslationTest().mock_response()
        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={
                "service": "alibaba",
                "configuration": {
                    "key": "alibaba-key-v1",
                    "secret": "alibaba-secret",
                    "region": "alibaba-region",
                },
            },
            format="json",
        )

        # update configuration: incorrect method
        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={
                "service": "deepl",
                "configuration": {
                    "key": "deepl-key-v1",
                    "url": "https://api.deepl.com/v2/",
                },
            },
            format="json",
        )

        # update configuration: valid method
        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="patch",
            code=200,
            superuser=True,
            request={
                "service": "deepl",
                "configuration": {
                    "key": "deepl-key-v2",
                    "url": "https://api.deepl.com/v2/",
                },
            },
            format="json",
        )

        # list configurations
        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="get",
            code=200,
            superuser=True,
        )
        self.assertIn("weblate", response.data)
        self.assertEqual(response.data["deepl"]["key"], "deepl-key-v2")
        self.assertEqual(response.data["alibaba"]["key"], "alibaba-key-v1")

        # remove configuration
        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="patch",
            code=200,
            superuser=True,
            request={"service": "deepl", "configuration": None},
            format="json",
        )

        # check configuration no longer exists
        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="get",
            code=200,
            superuser=True,
        )
        self.assertNotIn("deepl", response.data)

        # invalid replace all configurations (missing required config)
        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="put",
            code=400,
            superuser=True,
            request={
                "deepl": {"key": "deepl-key-valid", "url": "https://api.deepl.com/v2/"},
                "unknown": {"key": "alibaba-key-invalid"},
            },
            format="json",
        )

        # invalid replace all configurations (missing required config)
        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="put",
            code=400,
            superuser=True,
            request={
                "deepl": {"key": "deepl-key-valid", "url": "https://api.deepl.com/v2/"},
                "alibaba": {"key": "alibaba-key-invalid"},
            },
            format="json",
        )

        # replace all configurations
        new_config = {
            "deepl": {"key": "deepl-key-v3", "url": "https://api.deepl.com/v2/"},
            "alibaba": {
                "key": "alibaba-key-v2",
                "secret": "alibaba-secret",
                "region": "alibaba-region",
            },
        }

        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="put",
            code=201,
            superuser=True,
            request=new_config,
            format="json",
        )

        # check all configurations
        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="get",
            superuser=True,
        )

        self.assertEqual(new_config, response.data)


class ComponentAPITest(APIBaseTest):
    def setUp(self) -> None:
        super().setUp()
        shot = Screenshot.objects.create(
            name="Obrazek", translation=self.component.source_translation
        )
        with open(TEST_SCREENSHOT, "rb") as handle:
            shot.image.save("screenshot.png", File(handle))

    def test_list_components(self) -> None:
        response = self.client.get(reverse("api:component-list"))
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"][0]["slug"], "test")
        self.assertEqual(response.data["results"][0]["project"]["slug"], "test")
        self.assertEqual(response.data["results"][1]["slug"], "glossary")
        self.assertEqual(response.data["results"][1]["project"]["slug"], "test")

    def test_list_components_acl(self) -> None:
        self.create_acl()
        response = self.client.get(reverse("api:component-list"))
        self.assertEqual(response.data["count"], 2)
        self.authenticate(True)
        response = self.client.get(reverse("api:component-list"))
        self.assertEqual(response.data["count"], 4)

    def test_get_component(self) -> None:
        response = self.client.get(
            reverse("api:component-detail", kwargs=self.component_kwargs)
        )
        self.assertEqual(response.data["slug"], "test")
        self.assertEqual(response.data["project"]["slug"], "test")

    def test_get_lock(self) -> None:
        response = self.client.get(
            reverse("api:component-lock", kwargs=self.component_kwargs)
        )
        self.assertEqual(response.data, {"locked": False})

    def test_set_lock_denied(self) -> None:
        self.authenticate()
        url = reverse("api:component-lock", kwargs=self.component_kwargs)
        response = self.client.post(url, {"lock": True})
        self.assertEqual(response.status_code, 403)

    def test_set_lock(self) -> None:
        self.authenticate(True)
        url = reverse("api:component-lock", kwargs=self.component_kwargs)
        response = self.client.get(url)
        self.assertEqual(response.data, {"locked": False})
        response = self.client.post(url, {"lock": True})
        self.assertEqual(response.data, {"locked": True})
        response = self.client.post(url, {"lock": False})
        self.assertEqual(response.data, {"locked": False})

    def test_repo_status_denied(self) -> None:
        self.do_request("api:component-repository", self.component_kwargs, code=403)

    def test_repo_status(self) -> None:
        self.do_request(
            "api:component-repository",
            self.component_kwargs,
            superuser=True,
            data={
                "needs_push": False,
                "needs_merge": False,
                "needs_commit": False,
                "merge_failure": None,
            },
            skip=("remote_commit", "weblate_commit", "status", "url"),
        )

    def test_statistics(self) -> None:
        self.do_request(
            "api:component-statistics",
            self.component_kwargs,
            data={"count": 4},
            skip=("results", "previous", "next"),
        )
        response = self.do_request(
            "api:component-statistics",
            self.component_kwargs,
            request={
                "format": "json-flat",
            },
        )
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 4)
        for item in data:
            self.assertIsInstance(item, dict)

    def test_new_template_404(self) -> None:
        self.do_request("api:component-new-template", self.component_kwargs, code=404)

    def test_new_template(self) -> None:
        self.component.new_base = "po/cs.po"
        self.component.save()
        self.do_request("api:component-new-template", self.component_kwargs)

    def test_monolingual_404(self) -> None:
        self.do_request(
            "api:component-monolingual-base", self.component_kwargs, code=404
        )

    def test_monolingual(self) -> None:
        component = self.create_po_mono(name="mono", project=self.component.project)
        self.do_request(
            "api:component-monolingual-base",
            {"project__slug": component.project.slug, "slug": component.slug},
        )

    def test_translations(self) -> None:
        request = self.do_request("api:component-translations", self.component_kwargs)
        self.assertEqual(request.data["count"], 4)

    def test_changes(self) -> None:
        request = self.do_request("api:component-changes", self.component_kwargs)
        self.assertEqual(request.data["count"], 22)

    def test_screenshots(self) -> None:
        request = self.do_request("api:component-screenshots", self.component_kwargs)
        self.assertEqual(request.data["count"], 1)
        self.assertEqual(request.data["results"][0]["name"], "Obrazek")

    def test_patch(self) -> None:
        self.do_request(
            "api:component-detail", self.component_kwargs, method="patch", code=403
        )
        response = self.do_request(
            "api:component-detail",
            self.component_kwargs,
            method="patch",
            superuser=True,
            code=200,
            format="json",
            request={"name": "New Name"},
        )
        self.assertEqual(response.data["name"], "New Name")

    def test_put(self) -> None:
        self.do_request(
            "api:component-detail", self.component_kwargs, method="put", code=403
        )
        component = self.client.get(
            reverse("api:component-detail", kwargs=self.component_kwargs), format="json"
        ).json()
        component["name"] = "New Name"
        response = self.do_request(
            "api:component-detail",
            self.component_kwargs,
            method="put",
            superuser=True,
            code=200,
            format="json",
            request=component,
        )
        self.assertEqual(response.data["name"], "New Name")

    def test_delete(self) -> None:
        self.assertEqual(Component.objects.count(), 2)
        self.do_request(
            "api:component-detail", self.component_kwargs, method="delete", code=403
        )
        self.do_request(
            "api:component-detail",
            self.component_kwargs,
            method="delete",
            superuser=True,
            code=204,
        )
        self.assertEqual(Component.objects.count(), 1)

    def test_create_translation(self) -> None:
        self.component.new_lang = "add"
        self.component.new_base = "po/hello.pot"
        self.component.save()
        self.do_request(
            "api:component-translations",
            self.component_kwargs,
            method="post",
            code=201,
            request={"language_code": "fa"},
        )

    def test_create_translation_existing(self) -> None:
        self.component.new_lang = "add"
        self.component.new_base = "po/hello.pot"
        self.component.save()
        self.do_request(
            "api:component-translations",
            self.component_kwargs,
            method="post",
            code=400,
            request={"language_code": "cs"},
        )

    def test_create_translation_invalid_language_code(self) -> None:
        self.do_request(
            "api:component-translations",
            self.component_kwargs,
            method="post",
            code=400,
            request={"language_code": "invalid"},
        )

    def test_create_translation_prohibited(self) -> None:
        self.do_request(
            "api:component-translations",
            self.component_kwargs,
            method="post",
            code=403,
            request={"language_code": "fa"},
        )

    def test_download_translation_zip_ok(self) -> None:
        response = self.do_request(
            "api:component-file",
            self.component_kwargs,
            method="get",
            code=200,
            superuser=True,
        )
        self.assertEqual(response.headers["content-type"], "application/zip")
        response = self.do_request(
            "api:component-file",
            self.component_kwargs,
            method="get",
            code=200,
            superuser=True,
            request={"format": "zip"},
        )
        self.assertEqual(response.headers["content-type"], "application/zip")

    def test_download_translation_zip_converted(self) -> None:
        response = self.do_request(
            "api:component-file",
            self.component_kwargs,
            method="get",
            code=200,
            superuser=True,
            request={"format": "zip:csv"},
        )
        self.assertEqual(response.headers["content-type"], "application/zip")

    def test_download_translation_zip_prohibited(self) -> None:
        project = self.component.project
        project.access_control = Project.ACCESS_PROTECTED
        project.save(update_fields=["access_control"])
        self.do_request(
            "api:component-file",
            self.component_kwargs,
            method="get",
            code=403,
        )

    def test_links(self) -> None:
        self.do_request(
            "api:component-links",
            self.component_kwargs,
            method="get",
            code=200,
        )
        self.do_request(
            "api:component-links",
            self.component_kwargs,
            method="post",
            code=403,
            request={"project_slug": "test"},
        )
        self.do_request(
            "api:component-links",
            self.component_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={"project_slug": "test"},
        )
        self.create_acl()
        self.do_request(
            "api:component-links",
            self.component_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={"project_slug": "acl"},
        )
        delete_kwargs = {"project_slug": "acl"}
        delete_kwargs.update(self.component_kwargs)
        self.do_request(
            "api:component-delete-links",
            delete_kwargs,
            method="delete",
            code=403,
        )
        self.do_request(
            "api:component-delete-links",
            delete_kwargs,
            method="delete",
            code=204,
            superuser=True,
        )

    def test_credits(self) -> None:
        self.do_request(
            "api:component-credits",
            self.component_kwargs,
            method="get",
            code=401,
            authenticated=False,
        )

        # mandatory date parameters
        self.do_request(
            "api:component-credits", self.component_kwargs, method="get", code=400
        )

        start = datetime.now(tz=UTC) - timedelta(days=1)
        end = datetime.now(tz=UTC) + timedelta(days=1)

        response = self.do_request(
            "api:component-credits",
            self.component_kwargs,
            method="get",
            code=200,
            request={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "sort_by": "count",
                "sort_order": "ascending",
            },
        )
        self.assertEqual(response.data, [])

        response = self.do_request(
            "api:component-credits",
            self.component_kwargs,
            method="get",
            code=200,
            request={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "lang": "fr",
                "sort_by": "count",
                "sort_order": "ascending",
            },
        )
        self.assertEqual(response.data, [])


class LanguageAPITest(APIBaseTest):
    def test_list_languages(self) -> None:
        response = self.client.get(reverse("api:language-list"))
        self.assertEqual(response.data["count"], 4)

    def test_get_language(self) -> None:
        response = self.client.get(
            reverse("api:language-detail", kwargs={"code": "cs"})
        )
        self.assertEqual(response.data["name"], "Czech")
        # Check plural exists
        self.assertEqual(response.data["plural"]["type"], 22)
        self.assertEqual(response.data["plural"]["number"], 3)
        # Check for aliases, with recent language-data there are 3
        self.assertGreaterEqual(len(response.data["aliases"]), 2)

    def test_create(self) -> None:
        self.do_request("api:language-list", method="post", code=403)
        # Ensure it throws error without plural data
        self.do_request(
            "api:language-list",
            method="post",
            superuser=True,
            code=400,
            format="json",
            request={
                "code": "new_lang",
                "name": "New Language",
                "direction": "rtl",
                "population": 100,
            },
        )
        response = self.do_request(
            "api:language-list",
            method="post",
            superuser=True,
            code=201,
            format="json",
            request={
                "code": "new_lang",
                "name": "New Language",
                "direction": "rtl",
                "population": 100,
                "plural": {"number": 2, "formula": "n != 1"},
            },
        )
        self.assertEqual(Language.objects.count(), len(LANGUAGES) + 1)
        self.assertEqual(response.data["code"], "new_lang")
        # Check that languages without translation are shown
        # only to super users
        response = self.do_request("api:language-list", method="get", code=200)
        self.assertEqual(response.data["count"], 4)
        response = self.do_request(
            "api:language-list", method="get", superuser=True, code=200
        )
        self.assertEqual(response.data["count"], len(LANGUAGES) + 1)
        self.do_request(
            "api:language-detail", kwargs={"code": "new_lang"}, method="get", code=404
        )
        self.do_request(
            "api:language-detail",
            kwargs={"code": "new_lang"},
            superuser=True,
            method="get",
            code=200,
        )
        # Creation with duplicate code gives 400
        response = self.do_request(
            "api:language-list",
            method="post",
            superuser=True,
            code=400,
            format="json",
            request={
                "code": "new_lang",
                "name": "New Language",
                "direction": "rtl",
                "population": 100,
                "plural": {"number": 2, "formula": "n != 1"},
            },
        )

    def test_delete(self) -> None:
        self.do_request(
            "api:language-list",
            method="post",
            superuser=True,
            code=201,
            format="json",
            request={
                "code": "new_lang",
                "name": "New Language",
                "direction": "rtl",
                "population": 100,
                "plural": {"number": 2, "formula": "n != 1"},
            },
        )
        self.do_request(
            "api:language-detail",
            kwargs={"code": "new_lang"},
            method="delete",
            superuser=True,
            code=204,
        )
        self.assertEqual(Language.objects.count(), len(LANGUAGES))

    def test_put(self) -> None:
        self.do_request(
            "api:language-detail",
            kwargs={"code": "cs"},
            method="put",
            code=403,
        )
        self.do_request(
            "api:language-detail",
            kwargs={"code": "cs"},
            method="put",
            superuser=True,
            code=200,
            format="json",
            request={
                "code": "cs",
                "name": "New Language",
                "direction": "rtl",
                "population": 100,
                "plural": {"number": 2, "formula": "n != 1"},
            },
        )
        self.assertEqual(Language.objects.get(code="cs").name, "New Language")

    def test_patch(self) -> None:
        self.do_request(
            "api:language-detail",
            kwargs={"code": "cs"},
            method="put",
            code=403,
        )
        self.do_request(
            "api:language-detail",
            kwargs={"code": "cs"},
            method="patch",
            superuser=True,
            code=200,
            request={"name": "New Language"},
        )
        self.assertEqual(Language.objects.get(code="cs").name, "New Language")


class MemoryAPITest(APIBaseTest):
    def test_get(self) -> None:
        self.do_request(
            "api:memory-list",
            method="get",
            superuser=True,
            code=200,
        )

        self.do_request(
            "api:memory-list",
            method="get",
            superuser=False,
            code=403,
        )

    def test_delete(self) -> None:
        self.do_request(
            "api:memory-detail",
            kwargs={"pk": Memory.objects.all()[0].pk},
            method="delete",
            superuser=True,
            code=204,
        )


class TranslationAPITest(APIBaseTest):
    def test_list_translations(self) -> None:
        response = self.client.get(reverse("api:translation-list"))
        self.assertEqual(response.data["count"], 8)

    def test_list_translations_acl(self) -> None:
        self.create_acl()
        response = self.client.get(reverse("api:translation-list"))
        self.assertEqual(response.data["count"], 8)
        self.authenticate(True)
        response = self.client.get(reverse("api:translation-list"))
        self.assertEqual(response.data["count"], 16)

    def test_get_translation(self) -> None:
        response = self.client.get(
            reverse("api:translation-detail", kwargs=self.translation_kwargs)
        )
        self.assertEqual(response.data["language_code"], "cs")

    def test_download(self) -> None:
        response = self.do_request(
            "api:translation-file",
            kwargs=self.translation_kwargs,
            code=200,
        )
        self.assertContains(response, "Project-Id-Version: Weblate Hello World 2016")

    def test_download_modified(self) -> None:
        response = self.do_request(
            "api:translation-file",
            kwargs=self.translation_kwargs,
            headers={"If-Modified-Since": "Wed, 21 Oct 2015 07:28:00 GMT"},
            code=200,
        )
        self.assertContains(response, "Project-Id-Version: Weblate Hello World 2016")
        self.do_request(
            "api:translation-file",
            kwargs=self.translation_kwargs,
            headers={"If-Modified-Since": response["Last-Modified"]},
            code=304,
        )

    def test_download_args(self) -> None:
        response = self.do_request(
            "api:translation-file",
            kwargs=self.translation_kwargs,
            request={"q": 'source:r".*world.*"'},
            code=400,
        )
        response = self.do_request(
            "api:translation-file",
            kwargs=self.translation_kwargs,
            request={"q": 'source:r".*world.*"', "format": "po"},
            code=200,
        )
        self.assertContains(response, 'msgid ""')
        response = self.do_request(
            "api:translation-file",
            kwargs=self.translation_kwargs,
            request={"q": 'source:r".*world.*"', "format": "invalid"},
            code=400,
        )
        self.assertContains(
            response, "Conversion to invalid is not supported", status_code=400
        )

    def test_download_invalid_format_url(self) -> None:
        args = {"format": "invalid"}
        args.update(self.translation_kwargs)
        response = self.client.get(reverse("api:translation-file", kwargs=args))
        self.assertEqual(response.status_code, 404)

    def test_download_format_url(self) -> None:
        args = {"format": "xliff"}
        args.update(self.translation_kwargs)
        response = self.do_request(
            "api:translation-file",
            kwargs=args,
            code=200,
        )
        self.assertContains(response, "<xliff")

    def test_upload_denied(self) -> None:
        self.authenticate()
        # Remove all permissions
        self.user.groups.clear()
        self.user.clear_cache()

        # Public project should fail with 403
        with open(TEST_PO, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle},
            )
        self.assertEqual(response.status_code, 403)

        # Private one with 404
        self.component.project.access_control = Project.ACCESS_PRIVATE
        self.component.project.save()
        with open(TEST_PO, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle},
            )
        self.assertEqual(response.status_code, 404)

    def test_get_units_no_filter(self) -> None:
        self.authenticate()
        response = self.do_request(
            "api:translation-units",
            kwargs={
                "language__code": "cs",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            code=200,
        )
        response_json = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_json["count"], 4)

    def test_get_units_q_filter(self) -> None:
        self.authenticate()
        response = self.do_request(
            "api:translation-units",
            kwargs={
                "language__code": "cs",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            request={"q": 'source:r".*world.*"'},
            code=200,
        )
        response_json = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_json["count"], 1)
        self.assertEqual(response_json["results"][0]["source"], ["Hello, world!\n"])

    def test_upload_bytes(self) -> None:
        self.authenticate()
        with open(TEST_PO, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": BytesIO(handle.read())},
            )
        self.assertEqual(
            response.data,
            {
                "accepted": 1,
                "count": 4,
                "not_found": 0,
                "result": True,
                "skipped": 0,
                "total": 4,
            },
        )
        translation = self.component.translation_set.get(language_code="cs")
        unit = translation.unit_set.get(source="Hello, world!\n")
        self.assertEqual(unit.target, "Ahoj světe!\n")
        self.assertEqual(unit.state, STATE_TRANSLATED)

        self.assertEqual(self.component.project.stats.suggestions, 0)

    def test_upload(self) -> None:
        self.authenticate()
        with open(TEST_PO, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle},
            )
        self.assertEqual(
            response.data,
            {
                "accepted": 1,
                "count": 4,
                "not_found": 0,
                "result": True,
                "skipped": 0,
                "total": 4,
            },
        )
        translation = self.component.translation_set.get(language_code="cs")
        unit = translation.unit_set.get(source="Hello, world!\n")
        self.assertEqual(unit.target, "Ahoj světe!\n")
        self.assertEqual(unit.state, STATE_TRANSLATED)

        self.assertEqual(self.component.project.stats.suggestions, 0)

    def test_upload_source(self) -> None:
        self.authenticate(True)

        # Upload to translation
        with open(TEST_POT, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle, "method": "source"},
            )
        self.assertEqual(response.status_code, 400)

        source_kwargs = copy(self.translation_kwargs)
        source_kwargs["language__code"] = "en"

        # Upload to source without a method
        with open(TEST_POT, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=source_kwargs),
                {"file": handle, "method": "translate"},
            )
        self.assertEqual(response.status_code, 400)

        # Correct upload
        with open(TEST_POT, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=source_kwargs),
                {"file": handle, "method": "source"},
            )
        self.assertEqual(
            response.data,
            {
                "accepted": 3,
                "count": 3,
                "not_found": 0,
                "result": True,
                "skipped": 0,
                "total": 3,
            },
        )
        translation = self.component.translation_set.get(language_code="cs")
        unit = translation.unit_set.get(source="Hello, world!\n")
        self.assertEqual(unit.target, "")
        self.assertEqual(unit.state, STATE_EMPTY)

        self.assertEqual(self.component.project.stats.suggestions, 0)

    def test_upload_content(self) -> None:
        self.authenticate()
        with open(TEST_PO, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle.read()},
            )
        self.assertEqual(response.status_code, 400)

    def test_upload_conflicts(self) -> None:
        self.authenticate()
        with open(TEST_PO, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle, "conflicts": ""},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "accepted": 1,
                "count": 4,
                "not_found": 0,
                "result": True,
                "skipped": 0,
                "total": 4,
            },
        )
        with open(TEST_PO, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle, "conflicts": "ignore"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "accepted": 0,
                "count": 4,
                "not_found": 0,
                "result": False,
                "skipped": 1,
                "total": 4,
            },
        )

    def test_upload_overwrite(self) -> None:
        self.test_upload()
        with open(TEST_PO, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle, "conflicts": "replace-translated"},
            )
        self.assertEqual(
            response.data,
            {
                "accepted": 0,
                "count": 4,
                "not_found": 0,
                "result": False,
                "skipped": 1,
                "total": 4,
            },
        )

    def test_upload_suggest(self) -> None:
        self.authenticate()
        with open(TEST_PO, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle, "method": "suggest"},
            )
        self.assertEqual(
            response.data,
            {
                "accepted": 1,
                "count": 4,
                "not_found": 0,
                "result": True,
                "skipped": 0,
                "total": 4,
            },
        )
        project = Project.objects.get(id=self.component.project_id)
        self.assertEqual(project.stats.suggestions, 1)
        with open(TEST_PO, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle, "method": "suggest"},
            )
        self.assertEqual(
            response.data,
            {
                "accepted": 0,
                "count": 4,
                "not_found": 0,
                "result": False,
                "skipped": 1,
                "total": 4,
            },
        )

    def test_upload_invalid(self) -> None:
        self.authenticate()
        response = self.client.put(
            reverse("api:translation-file", kwargs=self.translation_kwargs)
        )
        self.assertEqual(response.status_code, 400)

    def test_upload_error(self) -> None:
        self.authenticate()
        with open(TEST_BADPLURALS, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data,
            {
                "errors": [
                    {
                        "attr": "file",
                        "code": "invalid",
                        "detail": "Plural forms do not match the language.",
                    }
                ],
                "type": "validation_error",
            },
        )

    def test_repo_status_denied(self) -> None:
        self.do_request("api:translation-repository", self.translation_kwargs, code=403)

    def test_repo_status(self) -> None:
        self.do_request(
            "api:translation-repository",
            self.translation_kwargs,
            superuser=True,
            data={
                "needs_push": False,
                "needs_merge": False,
                "needs_commit": False,
                "merge_failure": None,
            },
            skip=("remote_commit", "weblate_commit", "status", "url"),
        )

    def test_statistics(self) -> None:
        self.do_request(
            "api:translation-statistics",
            self.translation_kwargs,
            data={
                "name": "Czech",
                "code": "cs",
                "url": "http://example.com/projects/test/test/cs/",
                "translate_url": "http://example.com/translate/test/test/cs/",
                "failing_percent": 0.0,
                "translated_percent": 0.0,
                "total_words": 19,
                "failing": 0,
                "translated_words": 0,
                "fuzzy_percent": 0.0,
                "fuzzy_words_percent": 0.0,
                "fuzzy_chars_percent": 0.0,
                "translated": 0,
                "translated_words_percent": 0.0,
                "translated_chars": 0,
                "translated_chars_percent": 0.0,
                "total_chars": 139,
                "fuzzy": 0,
                "fuzzy_words": 0,
                "fuzzy_chars": 0,
                "total": 4,
                "recent_changes": 0,
                "approved": 0,
                "approved_words": 0,
                "approved_chars": 0,
                "approved_percent": 0.0,
                "approved_words_percent": 0.0,
                "approved_chars_percent": 0.0,
                "comments": 0,
                "suggestions": 0,
                "readonly": 0,
                "readonly_words": 0,
                "readonly_chars": 0,
                "readonly_percent": 0.0,
                "readonly_words_percent": 0.0,
                "readonly_chars_percent": 0.0,
            },
            skip=("last_change",),
        )

    def test_changes(self) -> None:
        request = self.do_request("api:translation-changes", self.translation_kwargs)
        self.assertEqual(request.data["count"], 5)

    def test_units(self) -> None:
        request = self.do_request("api:translation-units", self.translation_kwargs)
        self.assertEqual(request.data["count"], 4)

    def test_autotranslate(self, format: str = "multipart") -> None:  # noqa: A002
        self.do_request(
            "api:translation-autotranslate",
            self.translation_kwargs,
            method="post",
            request={"mode": "invalid"},
            format=format,
            code=403,
        )
        self.do_request(
            "api:translation-autotranslate",
            self.translation_kwargs,
            superuser=True,
            method="post",
            request={"mode": "invalid"},
            format=format,
            code=400,
        )
        response = self.do_request(
            "api:translation-autotranslate",
            self.translation_kwargs,
            superuser=True,
            method="post",
            request={
                "mode": "suggest",
                "filter_type": "todo",
                "auto_source": "others",
                "threshold": "100",
            },
            format=format,
            code=200,
        )
        self.assertContains(response, "Automatic translation completed")
        response = self.do_request(
            "api:translation-autotranslate",
            self.translation_kwargs,
            superuser=True,
            method="post",
            request={
                "mode": "suggest",
                "filter_type": "todo",
                "auto_source": "mt",
                "threshold": "90",
                "engines": ["weblate"],
            },
            format=format,
            code=200,
        )
        self.assertContains(response, "Automatic translation completed")

    def test_autotranslate_json(self) -> None:
        self.test_autotranslate("json")

    def test_add_monolingual(self) -> None:
        component = self.create_acl()
        self.assertEqual(component.source_translation.unit_set.count(), 4)
        self.do_request(
            "api:translation-units",
            {
                "language__code": "cs",
                "component__slug": "test",
                "component__project__slug": "acl",
            },
            method="post",
            superuser=True,
            request={"key": "key", "value": "Source Language"},
            code=403,
        )
        self.assertEqual(component.source_translation.unit_set.count(), 4)
        self.do_request(
            "api:translation-units",
            {
                "language__code": "en",
                "component__slug": "test",
                "component__project__slug": "acl",
            },
            method="post",
            superuser=True,
            request={"key": "key", "value": "Source Language"},
            code=200,
        )
        self.assertEqual(component.source_translation.unit_set.count(), 5)
        unit = Unit.objects.get(
            translation__component=component,
            translation__language_code="cs",
            context="key",
        )
        self.assertEqual(unit.source, "Source Language")
        self.assertEqual(unit.target, "")
        self.do_request(
            "api:translation-units",
            {
                "language__code": "en",
                "component__slug": "test",
                "component__project__slug": "acl",
            },
            method="post",
            superuser=True,
            request={"key": "key", "value": "Source Language"},
            code=400,
        )
        self.assertEqual(component.source_translation.unit_set.count(), 5)
        self.do_request(
            "api:translation-units",
            {
                "language__code": "en",
                "component__slug": "test",
                "component__project__slug": "acl",
            },
            method="post",
            superuser=True,
            format="json",
            request={"key": "plural", "value": ["Source Language", "Source Languages"]},
            code=200,
        )
        self.assertEqual(component.source_translation.unit_set.count(), 6)
        # Duplicate
        self.do_request(
            "api:translation-units",
            {
                "language__code": "en",
                "component__slug": "test",
                "component__project__slug": "acl",
            },
            method="post",
            superuser=True,
            format="json",
            request={"key": "plural", "value": ["Source Language", "Source Languages"]},
            code=400,
        )
        self.assertEqual(component.source_translation.unit_set.count(), 6)
        self.do_request(
            "api:translation-units",
            {
                "language__code": "en",
                "component__slug": "test",
                "component__project__slug": "acl",
            },
            method="post",
            superuser=True,
            format="json",
            request={"key": "invalid-plural", "value": [{}]},
            code=400,
        )
        self.assertEqual(component.source_translation.unit_set.count(), 6)

    def test_add_bilingual(self) -> None:
        self.do_request(
            "api:translation-units",
            {
                "language__code": "cs",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            method="post",
            superuser=True,
            request={"source": "Source", "target": "Target"},
            code=403,
        )
        self.do_request(
            "api:translation-units",
            {
                "language__code": "cs",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            method="post",
            superuser=True,
            request={"source": "Source", "target": "Target"},
            code=403,
        )
        self.component.manage_units = True
        self.component.save()
        self.do_request(
            "api:translation-units",
            {
                "language__code": "cs",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            method="post",
            superuser=True,
            request={"source": "Source", "target": "Target"},
            code=200,
        )
        self.do_request(
            "api:translation-units",
            {
                "language__code": "cs",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            method="post",
            superuser=True,
            request={"source": "Source", "target": "Target"},
            code=400,
        )
        self.do_request(
            "api:translation-units",
            {
                "language__code": "cs",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            method="post",
            superuser=True,
            request={"source": "Source", "target": "Target", "context": "Another"},
            code=200,
        )
        self.do_request(
            "api:translation-units",
            {
                "language__code": "cs",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            method="post",
            superuser=True,
            request={
                "source": "Source",
                "target": "Target",
                "context": "Wrong",
                "state": "0",
            },
            code=400,
        )
        self.do_request(
            "api:translation-units",
            {
                "language__code": "cs",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            method="post",
            superuser=True,
            request={
                "source": "Source",
                "target": "Target",
                "context": "Wrong",
                "state": "30",
            },
            code=400,
        )
        self.do_request(
            "api:translation-units",
            {
                "language__code": "cs",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            method="post",
            superuser=True,
            request={
                "source": "Source",
                "target": "Target",
                "context": "Wrong",
                "state": "100",
            },
            code=400,
        )
        self.do_request(
            "api:translation-units",
            {
                "language__code": "cs",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            method="post",
            superuser=True,
            request={
                "source": "Source",
                "target": "",
                "context": "Wrong",
                "state": "0",
            },
            code=400,
        )
        self.do_request(
            "api:translation-units",
            {
                "language__code": "cs",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            method="post",
            superuser=True,
            request={
                "source": "Source",
                "target": "Target",
                "context": "Fuzzy",
                "state": "10",
            },
            code=200,
        )

    def test_add_bilingual_source(self) -> None:
        self.component.manage_units = True
        self.component.save()
        self.do_request(
            "api:translation-units",
            {
                "language__code": "en",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            method="post",
            superuser=True,
            request={
                "source": "Source",
                "target": "Target",
            },
            code=200,
        )
        self.assertEqual(
            set(Unit.objects.filter(source="Source").values_list("target", flat=True)),
            {"Source", "Target"},
        )
        self.do_request(
            "api:translation-units",
            {
                "language__code": "en",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            method="post",
            superuser=True,
            request={
                "source": "Source2",
                "target": "",
            },
            code=200,
        )
        self.assertEqual(
            set(Unit.objects.filter(source="Source2").values_list("target", flat=True)),
            {"Source2", ""},
        )
        self.do_request(
            "api:translation-units",
            {
                "language__code": "en",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            method="post",
            superuser=True,
            request={
                "source": "Source3",
            },
            code=200,
        )
        self.assertEqual(
            set(Unit.objects.filter(source="Source3").values_list("target", flat=True)),
            {"Source3", ""},
        )

    def test_add_plural(self) -> None:
        # Add to bilingual
        self.component.manage_units = True
        self.component.save()
        self.do_request(
            "api:translation-units",
            {
                "language__code": "cs",
                "component__slug": "test",
                "component__project__slug": "test",
            },
            method="post",
            superuser=True,
            request={
                "source": ["Singular", "Plural"],
                "target": ["Target 0", "Target 1"],
                "state": "20",
            },
            code=200,
        )

        # Add to monolingual
        self.create_acl()
        self.do_request(
            "api:translation-units",
            {
                "language__code": "en",
                "component__slug": "test",
                "component__project__slug": "acl",
            },
            method="post",
            superuser=True,
            request={
                "key": "pluralized",
                "value": ["Singular", "Plural"],
            },
            code=200,
        )

        # Not supported plurals
        self.create_json_mono(name="other", project=self.component.project)
        self.do_request(
            "api:translation-units",
            {
                "language__code": "en",
                "component__slug": "other",
                "component__project__slug": "test",
            },
            method="post",
            superuser=True,
            request={
                "key": "pluralized",
                "value": ["Singular", "Plural"],
                "state": "20",
            },
            code=400,
        )

    def test_delete(self) -> None:
        def _translation_count():
            # exclude glossaries because stale glossaries are also cleaned out
            return Translation.objects.filter(component__is_glossary=False).count()

        start_count = _translation_count()
        self.do_request(
            "api:translation-detail", self.translation_kwargs, method="delete", code=403
        )
        self.do_request(
            "api:translation-detail",
            self.translation_kwargs,
            method="delete",
            superuser=True,
            code=204,
        )

        self.assertEqual(_translation_count(), start_count - 1)


class UnitAPITest(APIBaseTest):
    def test_list_units(self) -> None:
        response = self.client.get(reverse("api:unit-list"))
        self.assertEqual(response.data["count"], 16)

    def test_list_units_filter(self) -> None:
        response = self.client.get(reverse("api:unit-list"), {"q": "is:translated"})
        self.assertEqual(response.data["count"], 6)

    def test_get_unit(self) -> None:
        unit = Unit.objects.get(
            translation__language_code="cs", source="Hello, world!\n"
        )
        response = self.client.get(reverse("api:unit-detail", kwargs={"pk": unit.pk}))
        self.assertIn("translation", response.data)
        self.assertIn("language_code", response.data)
        self.assertEqual(response.data["source"], ["Hello, world!\n"])

    def test_get_plural_unit(self) -> None:
        unit = Unit.objects.get(
            translation__language_code="cs", source__startswith="Orangutan has "
        )
        response = self.client.get(reverse("api:unit-detail", kwargs={"pk": unit.pk}))
        self.assertIn("translation", response.data)
        self.assertIn("language_code", response.data)
        self.assertEqual(
            response.data["source"],
            ["Orangutan has %d banana.\n", "Orangutan has %d bananas.\n"],
        )

    def test_translate_unit(self) -> None:
        unit = Unit.objects.get(
            translation__language_code="cs", source="Hello, world!\n"
        )
        # Changing state only
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=400,
            request={"state": "20"},
        )
        # Changing target only
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=400,
            request={"target": "Test translation"},
        )
        # Performing update
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=200,
            request={"state": "20", "target": "Test translation"},
        )
        # Adding plural where it is not
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=400,
            request={"state": "20", "target": ["Test translation", "Test plural"]},
        )
        # Invalid state changes
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=400,
            request={"state": "100", "target": "Test read-only translation"},
        )
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=400,
            request={"state": "0", "target": "Test read-only translation"},
        )
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=400,
            request={"state": "20", "target": ""},
        )
        unit = Unit.objects.get(pk=unit.pk)
        # The auto fixer adds the trailing newline
        self.assertEqual(unit.target, "Test translation\n")

    def test_translate_unit_whitespace(self) -> None:
        unit = Unit.objects.get(
            translation__language_code="cs", source="Hello, world!\n"
        )
        unit.source = "Hello test "
        # Avoid doing all what .save() does:
        Unit.objects.filter(pk=unit.pk).update(source=unit.source)
        target = "Test translation "
        # Performing update
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=200,
            request={"state": "20", "target": target},
        )
        # Verify string was not stripped
        unit.refresh_from_db()
        self.assertEqual(unit.target, target)

    def test_untranslate_unit(self) -> None:
        unit = Unit.objects.get(
            translation__language_code="cs", source="Hello, world!\n"
        )
        # Performing update
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=200,
            request={"state": "0", "target": ""},
        )

    def test_untranslate_unit_invalid(self) -> None:
        unit = Unit.objects.get(
            translation__language_code="cs", source="Hello, world!\n"
        )
        # JSON payload passed as string
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=400,
            format="json",
            request='{"state": "0", "target": [""]}',
        )

    def test_unit_review(self) -> None:
        self.component.project.translation_review = True
        self.component.project.save()
        unit = Unit.objects.get(
            translation__language_code="cs", source="Hello, world!\n"
        )
        # Changing to approved is not allowed without perms
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=400,
            request={"state": "30", "target": "Test translation"},
        )
        self.assertFalse(Unit.objects.get(pk=unit.pk).approved)

        # Changing state to approved
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=200,
            superuser=True,
            request={"state": "30", "target": "Test translation"},
        )
        self.assertTrue(Unit.objects.get(pk=unit.pk).approved)

        # Changing approved unit is not allowed
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=403,
            request={"state": "20", "target": "Test translation"},
        )
        self.assertTrue(Unit.objects.get(pk=unit.pk).approved)

    def test_translate_source_unit(self) -> None:
        unit = Unit.objects.get(
            translation__language_code="en", source="Hello, world!\n"
        )
        # The params are rejected here
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=403,
            request={"state": "20", "target": "Test translation"},
        )
        unit = Unit.objects.get(pk=unit.pk)
        self.assertEqual(unit.target, "Hello, world!\n")
        # Actual update
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=200,
            superuser=True,
            request={"explanation": "This is good explanation"},
        )
        # No permissions
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=403,
            request={"explanation": "This is wrong explanation"},
        )
        unit = Unit.objects.get(pk=unit.pk)
        self.assertEqual(unit.explanation, "This is good explanation")
        unit = Unit.objects.get(
            translation__language_code="cs", source="Hello, world!\n"
        )
        # Actual update
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=403,
            superuser=True,
            request={"explanation": "This is rejected explanation"},
        )

    def test_unit_flags(self) -> None:
        unit = Unit.objects.get(
            translation__language_code="cs", source="Hello, world!\n"
        )
        unit.translate(self.user, "Hello, world!\n", STATE_TRANSLATED)
        self.assertEqual(unit.all_checks_names, {"same"})

        # Edit on translation will fail
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=403,
            superuser=True,
            request={"extra_flags": "ignore-same"},
        )

        # Edit on source will work
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.source_unit.pk},
            method="patch",
            code=200,
            superuser=True,
            request={"extra_flags": "ignore-same"},
        )

        # Checks and flags should be now updated
        unit = Unit.objects.get(pk=unit.id)
        self.assertEqual(unit.all_flags.format(), "c-format, ignore-same")
        self.assertEqual(unit.all_checks_names, set())

    def test_unit_labels(self) -> None:
        other_project = Project.objects.create(
            name="OtherProject",
            slug="other-project",
            access_control=Project.ACCESS_PRIVATE,
        )

        label1 = self.component.project.label_set.create(name="test", color="navy")
        label2 = other_project.label_set.create(name="test_2", color="navy")

        unit = Unit.objects.get(
            translation__language_code="cs", source="Hello, world!\n"
        )
        unit.translate(self.user, "Hello, world!\n", STATE_TRANSLATED)

        # Edit on translation will fail
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=403,
            superuser=True,
            request={"labels": [label1.id]},
        )

        # Edit on source will fail when label doesn't exist
        # or is not in the same project
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.source_unit.pk},
            method="patch",
            code=400,
            superuser=True,
            request={"labels": [4000]},
        )
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.source_unit.pk},
            method="patch",
            code=400,
            superuser=True,
            request={"labels": ["name"]},
        )
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.source_unit.pk},
            method="patch",
            code=400,
            superuser=True,
            request={"labels": [label2.id]},
        )

        # Edit on source will work when label exists
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.source_unit.pk},
            method="patch",
            code=200,
            superuser=True,
            request={"labels": [label1.id]},
        )

        # Label should be now updated
        unit = Unit.objects.get(pk=unit.id)
        self.assertEqual(len(unit.all_labels), 1)
        self.assertEqual(unit.all_labels[0].name, "test")

        label1.delete()
        label2.delete()
        other_project.delete()

    def test_translate_plural_unit(self) -> None:
        unit = Unit.objects.get(
            translation__language_code="cs", source__startswith="Orangutan has "
        )
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=200,
            format="json",
            request={"state": 20, "target": ["singular", "many", "other"]},
        )
        unit = Unit.objects.get(pk=unit.pk)
        # The auto fixer adds the trailing newline
        self.assertEqual(unit.get_target_plurals(), ["singular\n", "many\n", "other\n"])

    def test_delete_unit(self) -> None:
        component = self._create_component(
            "po-mono",
            "po-mono/*.po",
            "po-mono/en.po",
            project=self.component.project,
            name="mono",
        )
        revision = component.repository.last_revision
        self.assertEqual(component.stats.all, 16)
        unit = Unit.objects.get(
            translation__component=component,
            translation__language_code="cs",
            source="Hello, world!\n",
        )
        # Lack of permissions
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="delete",
            code=403,
        )
        # Deleting of non source unit
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="delete",
            code=403,
            superuser=True,
        )
        # Lack of permissions
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.source_unit.pk},
            method="delete",
            code=403,
        )
        # Deleting of source unit
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.source_unit.pk},
            method="delete",
            code=204,
            superuser=True,
        )
        # Verify units were actually removed
        component = Component.objects.get(pk=component.pk)
        self.assertNotEqual(revision, component.repository.last_revision)
        self.assertEqual(component.stats.all, 12)

    def test_unit_translations(self):
        unit = Unit.objects.get(
            translation__language_code="en", source="Thank you for using Weblate."
        )
        response = self.client.get(
            reverse("api:unit-translations", kwargs={"pk": unit.pk})
        )
        # translations units do not include source unit
        self.assertEqual(len(response.data), 3)

        unit_cs = Unit.objects.get(
            translation__language_code="cs", source="Thank you for using Weblate."
        )
        response = self.client.get(
            reverse("api:unit-translations", kwargs={"pk": unit_cs.pk})
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["errors"][0]["code"], "not-a-source-unit")


class ScreenshotAPITest(APIBaseTest):
    def setUp(self) -> None:
        super().setUp()
        shot = Screenshot.objects.create(
            name="Obrazek", translation=self.component.source_translation
        )
        with open(TEST_SCREENSHOT, "rb") as handle:
            shot.image.save("screenshot.png", File(handle))

    def test_list_screenshots(self) -> None:
        response = self.client.get(reverse("api:screenshot-list"))
        self.assertEqual(response.data["count"], 1)

    def test_get_screenshot(self) -> None:
        response = self.client.get(
            reverse("api:screenshot-detail", kwargs={"pk": Screenshot.objects.get().pk})
        )
        self.assertIn("file_url", response.data)

    def test_download(self) -> None:
        response = self.client.get(
            reverse("api:screenshot-file", kwargs={"pk": Screenshot.objects.get().pk})
        )
        self.assertContains(response, b"PNG")

    def test_upload(self, superuser=True, code=200, filename=TEST_SCREENSHOT) -> None:
        self.authenticate(superuser)
        Screenshot.objects.get().image.delete()

        self.assertEqual(Screenshot.objects.get().image, "")
        with open(filename, "rb") as handle:
            response = self.client.post(
                reverse(
                    "api:screenshot-file", kwargs={"pk": Screenshot.objects.get().pk}
                ),
                {"image": handle},
            )
        self.assertEqual(response.status_code, code)
        if code == 200:
            self.assertTrue(response.data["result"])

            self.assertIn(".png", Screenshot.objects.get().image.path)

    def test_upload_denied(self) -> None:
        self.test_upload(False, 403)

    def test_upload_invalid(self) -> None:
        self.test_upload(True, 400, TEST_PO)

    def test_create(self) -> None:
        with open(TEST_SCREENSHOT, "rb") as handle:
            self.do_request(
                "api:screenshot-list",
                method="post",
                code=403,
                request={
                    "name": "Test create screenshot",
                    "project_slug": "test",
                    "component_slug": "test",
                    "language_code": "en",
                    "image": File(handle),
                },
            )
        with open(TEST_SCREENSHOT, "rb") as handle:
            self.do_request(
                "api:screenshot-list",
                method="post",
                code=400,
                superuser=True,
                data={
                    "errors": [
                        {
                            "attr": "language_code",
                            "code": "invalid",
                            "detail": "This field is required.",
                        }
                    ],
                    "type": "validation_error",
                },
                request={
                    "project_slug": "test",
                    "component_slug": "test",
                    "image": File(handle),
                },
            )
        with open(TEST_SCREENSHOT, "rb") as handle:
            self.do_request(
                "api:screenshot-list",
                method="post",
                code=400,
                superuser=True,
                data={
                    "errors": [
                        {
                            "attr": "project_slug",
                            "code": "invalid",
                            "detail": "Translation matching query does not exist.",
                        },
                        {
                            "attr": "component_slug",
                            "code": "invalid",
                            "detail": "Translation matching query does not exist.",
                        },
                        {
                            "attr": "language_code",
                            "code": "invalid",
                            "detail": "Translation matching query does not exist.",
                        },
                    ],
                    "type": "validation_error",
                },
                request={
                    "name": "Test create screenshot",
                    "project_slug": "aaa",
                    "component_slug": "test",
                    "language_code": "en",
                    "image": File(handle),
                },
            )
        self.do_request(
            "api:screenshot-list",
            method="post",
            code=400,
            data={
                "errors": [
                    {
                        "attr": "name",
                        "code": "required",
                        "detail": "This field is required.",
                    },
                    {
                        "attr": "image",
                        "code": "required",
                        "detail": "No file was submitted.",
                    },
                ],
                "type": "validation_error",
            },
            superuser=True,
            request={
                "project_slug": "test",
                "component_slug": "test",
                "language_code": "en",
            },
        )
        with open(TEST_SCREENSHOT, "rb") as handle:
            self.do_request(
                "api:screenshot-list",
                method="post",
                code=201,
                superuser=True,
                request={
                    "name": "Test create screenshot",
                    "project_slug": "test",
                    "component_slug": "test",
                    "language_code": "en",
                    "image": File(handle),
                },
            )
        self.assertEqual(Screenshot.objects.count(), 2)

    def test_patch_screenshot(self) -> None:
        self.do_request(
            "api:screenshot-detail",
            kwargs={"pk": Screenshot.objects.get().pk},
            method="patch",
            code=403,
            request={"name": "Test New screenshot"},
        )
        self.do_request(
            "api:screenshot-detail",
            kwargs={"pk": Screenshot.objects.get().pk},
            method="patch",
            code=200,
            superuser=True,
            request={"name": "Test New screenshot"},
        )
        self.assertEqual(Screenshot.objects.get().name, "Test New screenshot")

    def test_put_screenshot(self) -> None:
        response = self.client.get(
            reverse("api:screenshot-detail", kwargs={"pk": Screenshot.objects.get().pk})
        )
        request = response.data
        request["name"] = "Test new screenshot"
        self.do_request(
            "api:screenshot-detail",
            kwargs={"pk": Screenshot.objects.get().pk},
            method="put",
            code=403,
            request=request,
        )
        self.do_request(
            "api:screenshot-detail",
            kwargs={"pk": Screenshot.objects.get().pk},
            method="put",
            code=200,
            superuser=True,
            request=request,
        )
        self.assertEqual(Screenshot.objects.get().name, "Test new screenshot")

    def test_delete_screenshot(self) -> None:
        self.do_request(
            "api:screenshot-detail",
            kwargs={"pk": Screenshot.objects.get().pk},
            method="delete",
            code=403,
        )
        self.do_request(
            "api:screenshot-detail",
            kwargs={"pk": Screenshot.objects.get().pk},
            method="delete",
            code=204,
            superuser=True,
        )
        self.assertEqual(Screenshot.objects.count(), 0)

    def test_units_denied(self) -> None:
        unit = self.component.source_translation.unit_set.all()[0]
        response = self.client.post(
            reverse("api:screenshot-units", kwargs={"pk": Screenshot.objects.get().pk}),
            {"unit_id": unit.pk},
        )
        self.assertEqual(response.status_code, 401)

    def test_units_invalid(self) -> None:
        self.authenticate(True)
        response = self.client.post(
            reverse("api:screenshot-units", kwargs={"pk": Screenshot.objects.get().pk}),
            {"unit_id": -1},
        )
        self.assertEqual(response.status_code, 400)

    def test_units(self) -> None:
        self.authenticate(True)
        unit = self.component.source_translation.unit_set.all()[0]
        response = self.client.post(
            reverse("api:screenshot-units", kwargs={"pk": Screenshot.objects.get().pk}),
            {"unit_id": unit.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(unit.pk), response.data["units"][0])

    def test_units_delete(self) -> None:
        self.authenticate(True)
        unit = self.component.source_translation.unit_set.all()[0]
        self.client.post(
            reverse("api:screenshot-units", kwargs={"pk": Screenshot.objects.get().pk}),
            {"unit_id": unit.pk},
        )
        response = self.client.delete(
            reverse(
                "api:screenshot-delete-units",
                kwargs={"pk": Screenshot.objects.get().pk, "unit_id": 100000},
            ),
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.delete(
            reverse(
                "api:screenshot-delete-units",
                kwargs={"pk": Screenshot.objects.get().pk, "unit_id": unit.pk},
            ),
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(Screenshot.objects.get().units.all().count(), 0)


class ChangeAPITest(APIBaseTest):
    def test_list_changes(self) -> None:
        response = self.client.get(reverse("api:change-list"))
        self.assertEqual(response.data["count"], 30)

    def test_filter_changes_after(self) -> None:
        """Filter changes since timestamp."""
        start = Change.objects.order().last().timestamp
        response = self.client.get(
            reverse("api:change-list"), {"timestamp_after": start.isoformat()}
        )
        self.assertEqual(response.data["count"], 30)

    def test_filter_changes_before(self) -> None:
        """Filter changes prior to timestamp."""
        start = Change.objects.order()[0].timestamp - timedelta(seconds=60)
        response = self.client.get(
            reverse("api:change-list"), {"timestamp_before": start.isoformat()}
        )
        self.assertEqual(response.data["count"], 0)

    def test_filter_changes_user(self) -> None:
        """Filter by non existing user."""
        response = self.client.get(reverse("api:change-list"), {"user": "nonexisting"})
        self.assertEqual(response.data["count"], 0)

    def test_get_change(self) -> None:
        response = self.client.get(
            reverse("api:change-detail", kwargs={"pk": Change.objects.all()[0].pk})
        )
        self.assertIn("translation", response.data)


class MetricsAPITest(APIBaseTest):
    def test_metrics(self) -> None:
        self.authenticate()
        response = self.client.get(reverse("api:metrics"))
        self.assertEqual(response.data["projects"], 1)

    def test_metrics_openmetrics(self) -> None:
        self.authenticate()
        response = self.client.get(reverse("api:metrics"), {"format": "openmetrics"})
        self.assertContains(response, "# EOF")

    def test_metrics_csv(self) -> None:
        self.authenticate()
        response = self.client.get(reverse("api:metrics"), {"format": "csv"})
        self.assertContains(response, "units_translated")

    def test_forbidden(self) -> None:
        response = self.client.get(reverse("api:metrics"))
        self.maxDiff = None
        self.assertEqual(
            response.data,
            {
                "type": "client_error",
                "errors": [
                    {
                        "attr": None,
                        "code": "not_authenticated",
                        "detail": "Authentication credentials were not provided.",
                    }
                ],
            },
        )

    def test_ratelimit(self) -> None:
        self.authenticate()
        response = self.client.get(
            reverse("api:metrics"), headers={"remote-addr": "127.0.0.2"}
        )
        current = int(response["X-RateLimit-Remaining"])
        response = self.client.get(
            reverse("api:metrics"), headers={"remote-addr": "127.0.0.2"}
        )
        self.assertEqual(current - 1, int(response["X-RateLimit-Remaining"]))


class SearchAPITest(APIBaseTest):
    def test_blank(self) -> None:
        self.authenticate()
        response = self.client.get(reverse("api:search"))
        self.assertEqual(response.data, [])

    def test_result(self) -> None:
        response = self.client.get(reverse("api:search"), {"q": "test"})
        self.assertEqual(
            [
                {
                    "category": "Project",
                    "name": "Test",
                    "url": "/projects/test/",
                },
                {
                    "category": "Component",
                    "name": "Test/Test",
                    "url": "/projects/test/test/",
                },
                {
                    "category": "User",
                    "name": "apitest",
                    "url": "/user/apitest/",
                },
            ],
            response.data,
        )

    def test_language(self) -> None:
        response = self.client.get(reverse("api:search"), {"q": "czech"})
        self.assertEqual(
            response.data,
            [{"category": "Language", "name": "Czech", "url": "/languages/cs/"}],
        )


class ComponentListAPITest(APIBaseTest):
    def setUp(self) -> None:
        super().setUp()
        clist = ComponentList.objects.create(name="Name", slug="name")
        clist.autocomponentlist_set.create()

    def test_list(self) -> None:
        response = self.client.get(reverse("api:componentlist-list"))
        self.assertEqual(response.data["count"], 1)

    def test_get(self) -> None:
        response = self.client.get(
            reverse(
                "api:componentlist-detail",
                kwargs={"slug": ComponentList.objects.get().slug},
            )
        )
        self.assertIn("components", response.data)

    def test_create(self) -> None:
        self.do_request(
            "api:componentlist-list",
            method="post",
            code=403,
        )
        self.do_request(
            "api:componentlist-list",
            method="post",
            superuser=True,
            code=201,
            request={"name": "List", "slug": "list"},
        )

    def test_delete(self) -> None:
        self.do_request(
            "api:componentlist-detail",
            kwargs={"slug": ComponentList.objects.get().slug},
            method="delete",
            superuser=True,
            code=204,
        )

    def test_add_component(self) -> None:
        self.do_request(
            "api:componentlist-components",
            kwargs={"slug": ComponentList.objects.get().slug},
            method="post",
            code=403,
            request={"component_id": self.component.pk},
        )
        self.do_request(
            "api:componentlist-components",
            kwargs={"slug": ComponentList.objects.get().slug},
            method="post",
            superuser=True,
            code=400,
            request={"component_id": -1},
        )
        self.do_request(
            "api:componentlist-components",
            kwargs={"slug": ComponentList.objects.get().slug},
            method="post",
            superuser=True,
            code=200,
            request={"component_id": self.component.pk},
        )
        response = self.do_request(
            "api:componentlist-components",
            kwargs={"slug": ComponentList.objects.get().slug},
            method="get",
            superuser=True,
            code=200,
        )
        self.assertEqual(response.data["count"], 1)

    def test_remove_component(self) -> None:
        self.do_request(
            "api:componentlist-delete-components",
            kwargs={
                "slug": ComponentList.objects.get().slug,
                "component_slug": self.component.slug,
            },
            method="delete",
            code=403,
        )
        self.do_request(
            "api:componentlist-delete-components",
            kwargs={
                "slug": ComponentList.objects.get().slug,
                "component_slug": "invalid",
            },
            method="delete",
            superuser=True,
            code=404,
        )
        clist = ComponentList.objects.get()
        clist.components.add(self.component)
        self.do_request(
            "api:componentlist-delete-components",
            kwargs={
                "slug": clist.slug,
                "component_slug": self.component.slug,
            },
            method="delete",
            superuser=True,
            code=204,
        )

    def test_put(self) -> None:
        self.do_request(
            "api:componentlist-detail",
            kwargs={"slug": ComponentList.objects.get().slug},
            method="put",
            code=403,
        )
        self.do_request(
            "api:componentlist-detail",
            kwargs={"slug": ComponentList.objects.get().slug},
            method="put",
            superuser=True,
            code=200,
            request={"name": "List", "slug": "list"},
        )
        self.assertEqual(ComponentList.objects.get().name, "List")

    def test_patch(self) -> None:
        self.do_request(
            "api:componentlist-detail",
            kwargs={"slug": ComponentList.objects.get().slug},
            method="patch",
            code=403,
        )
        self.do_request(
            "api:componentlist-detail",
            kwargs={"slug": ComponentList.objects.get().slug},
            method="patch",
            superuser=True,
            code=200,
            request={"name": "other"},
        )
        self.assertEqual(ComponentList.objects.get().name, "other")


class AddonAPITest(APIBaseTest):
    def create_addon(
        self, superuser=True, code=201, name="weblate.gettext.linguas", **request
    ):
        request["name"] = name
        return self.do_request(
            "api:component-addons",
            kwargs=self.component_kwargs,
            method="post",
            code=code,
            superuser=superuser,
            format="json",
            request=request,
        )

    def test_create(self) -> None:
        # Not authenticated user
        response = self.create_addon(code=403, superuser=False)
        self.assertFalse(self.component.addon_set.exists())
        # Non existing addon
        response = self.create_addon(name="invalid.addon", code=400)
        self.assertFalse(self.component.addon_set.exists())
        # Not compatible addon
        response = self.create_addon(name="weblate.resx.update", code=400)
        self.assertFalse(self.component.addon_set.exists())
        # Success
        response = self.create_addon()
        self.assertTrue(
            self.component.addon_set.filter(pk=response.data["id"]).exists()
        )
        # Existing
        response = self.create_addon(code=400)

    def test_delete(self) -> None:
        response = self.create_addon()
        self.do_request(
            "api:addon-detail",
            kwargs={"pk": response.data["id"]},
            method="delete",
            code=403,
        )
        self.do_request(
            "api:addon-detail",
            kwargs={"pk": response.data["id"]},
            method="delete",
            superuser=True,
            code=204,
        )

    def test_configuration(self) -> None:
        self.create_addon(
            name="weblate.gettext.mo", configuration={"path": "{{var}}"}, code=400
        )

    def test_discover(self) -> None:
        initial = {
            "file_format": "po",
            "match": r"(?P<component>[^/]*)/(?P<language>[^/]*)\.po",
            "name_template": "{{ component|title }}",
            "language_regex": "^(?!xx).*$",
        }
        self.assertEqual(Component.objects.all().count(), 2)
        self.create_addon(name="weblate.discovery.discovery", configuration=initial)

        self.assertEqual(self.component.addon_set.get().configuration, initial)
        self.assertEqual(Component.objects.all().count(), 5)

    def test_edit(self) -> None:
        initial = {"path": "{{ filename|stripext }}.mo"}
        expected = {"path": "{{ language_code }}.mo"}
        response = self.create_addon(name="weblate.gettext.mo", configuration=initial)
        self.assertEqual(self.component.addon_set.get().configuration, initial)
        self.do_request(
            "api:addon-detail",
            kwargs={"pk": response.data["id"]},
            method="patch",
            code=403,
            format="json",
            request={"configuration": expected},
        )
        self.assertEqual(self.component.addon_set.get().configuration, initial)
        self.do_request(
            "api:addon-detail",
            kwargs={"pk": response.data["id"]},
            method="patch",
            superuser=True,
            code=200,
            format="json",
            request={"configuration": expected},
        )
        self.assertEqual(self.component.addon_set.get().configuration, expected)

    def create_project_addon(
        self, superuser=True, code=201, name="weblate.consistency.languages", **request
    ):
        request["name"] = name
        return self.do_request(
            "api:project-addons",
            kwargs=self.project_kwargs,
            method="post",
            code=code,
            superuser=superuser,
            format="json",
            request=request,
        )

    def test_create_project_addon(self) -> None:
        # Not authenticated user
        response = self.create_project_addon(code=403, superuser=False)
        self.assertFalse(self.component.project.addon_set.exists())
        # Non existing addon
        response = self.create_project_addon(name="invalid.addon", code=400)
        self.assertFalse(self.component.project.addon_set.exists())
        # Success
        response = self.create_project_addon()
        self.assertTrue(
            self.component.project.addon_set.filter(pk=response.data["id"]).exists()
        )
        # Existing
        response = self.create_project_addon(code=400)

    def test_delete_project_addon(self) -> None:
        response = self.create_project_addon()
        self.do_request(
            "api:addon-detail",
            kwargs={"pk": response.data["id"]},
            method="delete",
            code=403,
        )
        self.do_request(
            "api:addon-detail",
            kwargs={"pk": response.data["id"]},
            method="delete",
            superuser=True,
            code=204,
        )


class CategoryAPITest(APIBaseTest):
    def create_category(self, code: int = 201, **kwargs):
        request = {
            "name": "Category Test",
            "slug": "category-test",
            "project": reverse("api:project-detail", kwargs=self.project_kwargs),
        }
        request.update(kwargs)
        return self.do_request(
            "api:category-list",
            method="post",
            superuser=True,
            request=request,
            code=code,
        )

    def list_categories(self):
        return self.do_request(
            "api:category-list",
            method="get",
            superuser=True,
        )

    def test_create(self) -> None:
        response = self.list_categories()
        self.assertEqual(response.data["count"], 0)
        self.create_category()
        response = self.list_categories()
        self.assertEqual(response.data["count"], 1)
        request = self.do_request("api:project-categories", self.project_kwargs)
        self.assertEqual(request.data["count"], 1)

    def test_create_nested(self) -> None:
        self.create_category()
        self.create_category(
            category=reverse(
                "api:category-detail", kwargs={"pk": Category.objects.all()[0].pk}
            )
        )
        response = self.list_categories()
        self.assertEqual(response.data["count"], 2)
        request = self.do_request("api:project-categories", self.project_kwargs)
        self.assertEqual(request.data["count"], 2)

    def test_create_nested_mismatch(self) -> None:
        component = self.create_acl()
        self.create_category()
        self.create_category(
            category=reverse(
                "api:category-detail", kwargs={"pk": Category.objects.all()[0].pk}
            ),
            project=reverse(
                "api:project-detail", kwargs={"slug": component.project.slug}
            ),
            code=400,
        )
        response = self.list_categories()
        self.assertEqual(response.data["count"], 1)
        request = self.do_request("api:project-categories", self.project_kwargs)
        self.assertEqual(request.data["count"], 1)

    def test_delete(self) -> None:
        response = self.create_category()
        category_url = response.data["url"]
        response = self.do_request(
            category_url,
            method="delete",
            code=403,
        )
        response = self.do_request(
            category_url,
            method="delete",
            superuser=True,
            code=204,
        )
        response = self.list_categories()
        self.assertEqual(response.data["count"], 0)

    def test_rename(self) -> None:
        response = self.create_category()
        category_url = response.data["url"]
        response = self.do_request(
            category_url,
            method="patch",
            code=403,
        )
        response = self.do_request(
            category_url,
            method="patch",
            superuser=True,
            request={"slug": "test"},
            code=400,
        )
        response = self.do_request(
            category_url,
            method="patch",
            superuser=True,
            request={"slug": "test-unused"},
        )

    def test_component(self) -> None:
        response = self.create_category()
        category_url = response.data["url"]
        component_url = reverse("api:component-detail", kwargs=self.component_kwargs)
        response = self.do_request(
            component_url,
            request={"category": category_url},
            method="patch",
            superuser=True,
        )
        # Old URL should no longer work
        self.do_request(component_url, code=404)
        # But new one should
        response = self.do_request(response.data["url"])
        self.assertIn("category-test%252Ftest", response.data["url"])
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.get_url_path(), ("test", "category-test", "test"))

        # Verify that browsing translations works
        response = self.do_request(response.data["url"] + "translations/")
        self.assertEqual(response.data["count"], 4)

        for translation in response.data["results"]:
            self.do_request(translation["url"])

    def test_statistics(self) -> None:
        # Create a category to get the statistics from
        response = self.create_category()
        category_kwargs = {"pk": response.data["id"]}
        # Use the default category kwargs to get the statistics
        request = self.do_request("api:category-statistics", category_kwargs)
        self.assertEqual(request.data["total"], 0)


class LabelAPITest(APIBaseTest):
    def test_get_label(self) -> None:
        label = self.component.project.label_set.create(
            name="test", description="test description", color="navy"
        )

        response = self.do_request(
            "api:project-labels",
            kwargs={"slug": self.component.project.slug},
            method="get",
            code=200,
        )

        self.assertEqual(len(response.data["results"]), 1)

        response_label = response.data["results"][0]

        self.assertEqual(response_label["id"], label.id)
        self.assertEqual(response_label["name"], label.name)
        self.assertEqual(response_label["description"], label.description)
        self.assertEqual(response_label["color"], label.color)

    def test_create_label(self) -> None:
        self.do_request(
            "api:project-labels",
            kwargs={"slug": Project.objects.all()[0].slug},
            method="post",
            superuser=True,
            request={
                "name": "Test Label",
                "description": "Test description for Test Label",
                "color": "green",
            },
            code=201,
        )

        self.do_request(
            "api:project-labels",
            kwargs={"slug": Project.objects.all()[0].slug},
            method="post",
            superuser=False,
            request={
                "name": "Test Label 2",
                "description": "Test description for Test Label 2",
                "color": "red",
            },
            code=403,
        )


class OpenAPITest(APIBaseTest):
    def test_view(self) -> None:
        self.do_request(
            "api-schema",
        )

    def test_redoc(self) -> None:
        self.do_request("redoc")
