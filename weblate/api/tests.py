# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from copy import copy
from datetime import timedelta
from io import BytesIO

from django.core.files import File
from django.urls import reverse
from rest_framework.exceptions import ErrorDetail
from rest_framework.test import APITestCase
from weblate_language_data.languages import LANGUAGES

from weblate.accounts.models import Subscription
from weblate.auth.models import Group, Role, User
from weblate.lang.models import Language
from weblate.memory.models import Memory
from weblate.screenshots.models import Screenshot
from weblate.trans.models import (
    Change,
    Component,
    ComponentList,
    Project,
    Translation,
    Unit,
)
from weblate.trans.tests.test_models import fixup_languages_seq
from weblate.trans.tests.utils import RepoTestMixin, get_test_file
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
    def setUpClass(cls):
        super().setUpClass()
        immediate_on_commit(cls)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        immediate_on_commit_leave(cls)

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        fixup_languages_seq()

    def setUp(self):
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

    def authenticate(self, superuser: bool = False):
        if self.user.is_superuser != superuser:
            self.user.is_superuser = superuser
            self.user.save()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.user.auth_token.key)

    def do_request(
        self,
        name,
        kwargs=None,
        data=None,
        code=200,
        superuser: bool = False,
        method="get",
        request=None,
        skip=(),
        format: str = "multipart",
    ):
        self.authenticate(superuser)
        url = reverse(name, kwargs=kwargs)
        response = getattr(self.client, method)(url, request, format)
        content = response.content if hasattr(response, "content") else "<stream>"

        self.assertEqual(
            response.status_code,
            code,
            f"Unexpected status code {response.status_code}: {content}",
        )
        if data is not None:
            for item in skip:
                del response.data[item]
            self.assertEqual(response.data, data)
        return response


class UserAPITest(APIBaseTest):
    def test_list(self):
        response = self.client.get(reverse("api:user-list"))
        self.assertEqual(response.data["count"], 2)
        self.assertNotIn("email", response.data["results"][0])
        self.authenticate(True)
        response = self.client.get(reverse("api:user-list"))
        self.assertEqual(response.data["count"], 2)
        self.assertIsNotNone(response.data["results"][0]["email"])

    def test_get(self):
        response = self.do_request(
            "api:user-detail",
            kwargs={"username": User.objects.filter(is_active=True).first().username},
            method="get",
            superuser=True,
            code=200,
        )
        self.assertEqual(response.data["username"], "apitest")

    def test_filter(self):
        response = self.client.get(reverse("api:user-list"), {"username": "api"})
        self.assertEqual(response.data["count"], 1)

    def test_create(self):
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

    def test_delete(self):
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

    def test_add_group(self):
        group = Group.objects.get(name="Viewers")
        self.do_request(
            "api:user-groups",
            kwargs={"username": User.objects.filter(is_active=True).first().username},
            method="post",
            code=403,
            request={"group_id": group.id},
        )
        self.do_request(
            "api:user-groups",
            kwargs={"username": User.objects.filter(is_active=True).first().username},
            method="post",
            superuser=True,
            code=400,
            request={"group_id": -1},
        )
        self.do_request(
            "api:user-groups",
            kwargs={"username": User.objects.filter(is_active=True).first().username},
            method="post",
            superuser=True,
            code=200,
            request={"group_id": group.id},
        )

    def test_remove_group(self):
        group = Group.objects.get(name="Viewers")
        username = User.objects.filter(is_active=True).first().username
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
        self.assertIn("http://example.com/api/groups/2/", response.data["groups"])
        response = self.do_request(
            "api:user-groups",
            kwargs={"username": username},
            method="delete",
            superuser=True,
            code=200,
            request={"group_id": group.id},
        )
        self.assertNotIn("http://example.com/api/groups/2/", response.data["groups"])

    def test_list_notifications(self):
        response = self.do_request(
            "api:user-notifications",
            kwargs={"username": User.objects.filter(is_active=True).first().username},
            method="get",
            superuser=True,
            code=200,
        )
        self.assertEqual(response.data["count"], 9)

    def test_post_notifications(self):
        self.do_request(
            "api:user-notifications",
            kwargs={"username": User.objects.filter(is_active=True).first().username},
            method="post",
            code=403,
        )
        self.do_request(
            "api:user-notifications",
            kwargs={"username": User.objects.filter(is_active=True).first().username},
            method="post",
            superuser=True,
            code=201,
            request={
                "notification": "RepositoryNotification",
                "scope": 10,
                "frequency": 1,
            },
        )
        self.assertEqual(Subscription.objects.count(), 10)

    def test_get_notifications(self):
        user = User.objects.filter(is_active=True).first()
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
                "subscription_id": Subscription.objects.filter(user=user).first().id,
            },
            method="get",
            code=200,
        )

    def test_put_notifications(self):
        user = User.objects.filter(is_active=True).first()
        response = self.do_request(
            "api:user-notifications-details",
            kwargs={
                "username": user.username,
                "subscription_id": Subscription.objects.filter(
                    user=user, notification="NewAnnouncementNotificaton"
                )
                .first()
                .id,
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

    def test_patch_notifications(self):
        user = User.objects.filter(is_active=True).first()
        response = self.do_request(
            "api:user-notifications-details",
            kwargs={
                "username": user.username,
                "subscription_id": Subscription.objects.filter(
                    user=user, notification="NewAnnouncementNotificaton"
                )
                .first()
                .id,
            },
            method="patch",
            superuser=True,
            code=200,
            request={"notification": "RepositoryNotification"},
        )
        self.assertEqual(response.data["notification"], "RepositoryNotification")

    def test_delete_notifications(self):
        user = User.objects.filter(is_active=True).first()
        self.do_request(
            "api:user-notifications-details",
            kwargs={
                "username": user.username,
                "subscription_id": Subscription.objects.filter(user=user).first().id,
            },
            method="delete",
            superuser=True,
            code=204,
        )
        self.assertEqual(Subscription.objects.count(), 8)

    def test_statistics(self):
        user = User.objects.filter(is_active=True).first()
        request = self.do_request(
            "api:user-statistics",
            kwargs={"username": user.username},
            superuser=True,
        )
        self.assertEqual(request.data["commented"], user.profile.commented)

    def test_put(self):
        self.do_request(
            "api:user-detail",
            kwargs={"username": User.objects.filter(is_active=True).first().username},
            method="put",
            code=403,
        )
        self.do_request(
            "api:user-detail",
            kwargs={"username": User.objects.filter(is_active=True).first().username},
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
        self.assertEqual(User.objects.filter(is_active=True).first().full_name, "Name")

    def test_patch(self):
        self.do_request(
            "api:user-detail",
            kwargs={"username": User.objects.filter(is_active=True).first().username},
            method="patch",
            code=403,
        )
        self.do_request(
            "api:user-detail",
            kwargs={"username": User.objects.filter(is_active=True).first().username},
            method="patch",
            superuser=True,
            code=200,
            request={"full_name": "Other"},
        )
        self.assertEqual(User.objects.filter(is_active=True).first().full_name, "Other")


class GroupAPITest(APIBaseTest):
    def test_list(self):
        response = self.client.get(reverse("api:group-list"))
        self.assertEqual(response.data["count"], 2)
        self.authenticate(True)
        response = self.client.get(reverse("api:group-list"))
        self.assertEqual(response.data["count"], 6)

    def test_get(self):
        response = self.do_request(
            "api:group-detail",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="get",
            superuser=True,
            code=200,
        )
        self.assertEqual(response.data["name"], "Users")

    def test_create(self):
        self.do_request("api:group-list", method="post", code=403)
        self.do_request(
            "api:group-list",
            method="post",
            superuser=True,
            code=201,
            format="json",
            request={"name": "Group", "project_selection": 0, "language_selection": 0},
        )
        self.assertEqual(Group.objects.count(), 7)

    def test_create_project(self):
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
        self.assertEqual(Group.objects.count(), 7)
        group = Group.objects.get(name="Group")
        self.assertEqual(group.defining_project, self.component.project)

    def test_add_role(self):
        role = Role.objects.get(pk=1)
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

    def test_add_component(self):
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

    def test_remove_component(self):
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

    def test_add_project(self):
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

    def test_remove_project(self):
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

    def test_add_language(self):
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

    def test_remove_language(self):
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

    def test_add_componentlist(self):
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

    def test_remove_componentlist(self):
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

    def test_delete(self):
        self.do_request(
            "api:group-detail",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="delete",
            superuser=True,
            code=204,
        )
        self.assertEqual(Group.objects.count(), 5)

    def test_put(self):
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

    def test_patch(self):
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


class RoleAPITest(APIBaseTest):
    def test_list_roles(self):
        response = self.client.get(reverse("api:role-list"))
        self.assertEqual(response.data["count"], 2)
        self.authenticate(True)
        response = self.client.get(reverse("api:role-list"))
        self.assertEqual(response.data["count"], 14)

    def test_get_role(self):
        role = Role.objects.get(name="Access repository")
        response = self.client.get(reverse("api:role-detail", kwargs={"id": role.pk}))
        self.assertEqual(response.data["name"], role.name)

    def test_create(self):
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
        self.assertEqual(Role.objects.count(), 15)
        self.assertEqual(Role.objects.get(name="Role").permissions.count(), 2)

    def test_delete(self):
        self.do_request(
            "api:role-detail",
            kwargs={"id": Role.objects.all()[0].pk},
            method="delete",
            superuser=True,
            code=204,
        )
        self.assertEqual(Role.objects.count(), 13)

    def test_put(self):
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

    def test_patch(self):
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
    def test_list_projects(self):
        response = self.client.get(reverse("api:project-list"))
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["slug"], "test")

    def test_list_projects_acl(self):
        self.create_acl()
        response = self.client.get(reverse("api:project-list"))
        self.assertEqual(response.data["count"], 1)
        self.authenticate(True)
        response = self.client.get(reverse("api:project-list"))
        self.assertEqual(response.data["count"], 2)

    def test_get_project(self):
        response = self.client.get(
            reverse("api:project-detail", kwargs=self.project_kwargs)
        )
        self.assertEqual(response.data["slug"], "test")

    def test_repo_op_denied(self):
        for operation in ("push", "pull", "reset", "cleanup", "commit"):
            self.do_request(
                "api:project-repository",
                self.project_kwargs,
                code=403,
                method="post",
                request={"operation": operation},
            )

    def test_repo_ops(self):
        for operation in ("push", "pull", "reset", "cleanup", "commit"):
            self.do_request(
                "api:project-repository",
                self.project_kwargs,
                method="post",
                superuser=True,
                request={"operation": operation},
            )

    def test_repo_invalid(self):
        self.do_request(
            "api:project-repository",
            self.project_kwargs,
            code=400,
            method="post",
            superuser=True,
            request={"operation": "invalid"},
        )

    def test_repo_status_denied(self):
        self.do_request("api:project-repository", self.project_kwargs, code=403)

    def test_repo_status(self):
        self.do_request(
            "api:project-repository",
            self.project_kwargs,
            superuser=True,
            data={"needs_push": False, "needs_merge": False, "needs_commit": False},
            skip=("url",),
        )

    def test_components(self):
        request = self.do_request("api:project-components", self.project_kwargs)
        self.assertEqual(request.data["count"], 2)

    def test_changes(self):
        request = self.do_request("api:project-changes", self.project_kwargs)
        self.assertEqual(request.data["count"], 33)

    def test_statistics(self):
        request = self.do_request("api:project-statistics", self.project_kwargs)
        self.assertEqual(request.data["total"], 16)

    def test_languages(self):
        request = self.do_request("api:project-languages", self.project_kwargs)
        self.assertEqual(len(request.data), 4)

    def test_delete(self):
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

    def test_create(self):
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

    def test_create_with_source_language(self):
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
            error_response.data["source_language"]["code"][0],
            "Language with this language code was not found.",
        )

    def test_create_with_source_language_string(self, format="json"):
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

    def test_create_with_source_language_string_multipart(self):
        self.test_create_with_source_language_string(format="multipart")

    def test_create_component(self):
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

    def test_create_component_autoshare(self):
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

    def test_create_component_blank_request(self):
        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={},
        )

    def test_create_component_no_format(self):
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
        self.assertIn("file_format", response.data)

    def test_create_component_no_push(self):
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
        # Auto linking in place
        self.assertEqual(
            Component.objects.get(slug="api-project", project__slug="test").repo,
            "weblate://test/test",
        )
        self.assertEqual(response.data["repo"], repo_url)

    def test_create_component_empty_push(self):
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
        # Auto linking in place
        self.assertEqual(
            Component.objects.get(slug="api-project", project__slug="test").repo,
            "weblate://test/test",
        )
        self.assertEqual(response.data["repo"], repo_url)

    def test_create_component_no_match(self):
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
        self.assertIn("filemask", response.data)

    def test_create_component_local(self):
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

    def test_create_component_local_nonexisting(self):
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

    def test_create_component_local_url(self):
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

    def test_patch(self):
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

    def test_create_component_docfile(self):
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
                },
            )
        self.assertEqual(response.data["repo"], "local:")
        self.assertEqual(response.data["filemask"], "local-project/*.html")
        self.assertEqual(Component.objects.count(), 3)

    def test_create_component_docfile_mask(self):
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
                },
            )
        self.assertEqual(response.data["repo"], "local:")
        self.assertEqual(response.data["filemask"], "doc/*.html")
        self.assertEqual(Component.objects.count(), 3)

    def test_create_component_docfile_mask_outside(self):
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

    def test_create_component_docfile_missing(self):
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

    def test_create_component_docfile_json(self):
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
                },
            )

    def test_create_component_docfile_language(self):
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
                },
            )
        self.assertEqual(response.data["repo"], "local:")
        self.assertEqual(response.data["template"], "local-project/cs.html")
        self.assertEqual(Component.objects.count(), 3)

    def test_create_component_zipfile(self):
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

    def test_create_component_zipfile_bad_params(self):
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

    def test_create_component_overwrite(self):
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

    def test_create_component_enforced(self):
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


class ComponentAPITest(APIBaseTest):
    def setUp(self):
        super().setUp()
        shot = Screenshot.objects.create(
            name="Obrazek", translation=self.component.source_translation
        )
        with open(TEST_SCREENSHOT, "rb") as handle:
            shot.image.save("screenshot.png", File(handle))

    def test_list_components(self):
        response = self.client.get(reverse("api:component-list"))
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"][0]["slug"], "test")
        self.assertEqual(response.data["results"][0]["project"]["slug"], "test")
        self.assertEqual(response.data["results"][1]["slug"], "glossary")
        self.assertEqual(response.data["results"][1]["project"]["slug"], "test")

    def test_list_components_acl(self):
        self.create_acl()
        response = self.client.get(reverse("api:component-list"))
        self.assertEqual(response.data["count"], 2)
        self.authenticate(True)
        response = self.client.get(reverse("api:component-list"))
        self.assertEqual(response.data["count"], 4)

    def test_get_component(self):
        response = self.client.get(
            reverse("api:component-detail", kwargs=self.component_kwargs)
        )
        self.assertEqual(response.data["slug"], "test")
        self.assertEqual(response.data["project"]["slug"], "test")

    def test_get_lock(self):
        response = self.client.get(
            reverse("api:component-lock", kwargs=self.component_kwargs)
        )
        self.assertEqual(response.data, {"locked": False})

    def test_set_lock_denied(self):
        self.authenticate()
        url = reverse("api:component-lock", kwargs=self.component_kwargs)
        response = self.client.post(url, {"lock": True})
        self.assertEqual(response.status_code, 403)

    def test_set_lock(self):
        self.authenticate(True)
        url = reverse("api:component-lock", kwargs=self.component_kwargs)
        response = self.client.get(url)
        self.assertEqual(response.data, {"locked": False})
        response = self.client.post(url, {"lock": True})
        self.assertEqual(response.data, {"locked": True})
        response = self.client.post(url, {"lock": False})
        self.assertEqual(response.data, {"locked": False})

    def test_repo_status_denied(self):
        self.do_request("api:component-repository", self.component_kwargs, code=403)

    def test_repo_status(self):
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

    def test_statistics(self):
        self.do_request(
            "api:component-statistics",
            self.component_kwargs,
            data={"count": 4},
            skip=("results", "previous", "next"),
        )

    def test_new_template_404(self):
        self.do_request("api:component-new-template", self.component_kwargs, code=404)

    def test_new_template(self):
        self.component.new_base = "po/cs.po"
        self.component.save()
        self.do_request("api:component-new-template", self.component_kwargs)

    def test_monolingual_404(self):
        self.do_request(
            "api:component-monolingual-base", self.component_kwargs, code=404
        )

    def test_monolingual(self):
        component = self.create_po_mono(name="mono", project=self.component.project)
        self.do_request(
            "api:component-monolingual-base",
            {"project__slug": component.project.slug, "slug": component.slug},
        )

    def test_translations(self):
        request = self.do_request("api:component-translations", self.component_kwargs)
        self.assertEqual(request.data["count"], 4)

    def test_changes(self):
        request = self.do_request("api:component-changes", self.component_kwargs)
        self.assertEqual(request.data["count"], 25)

    def test_screenshots(self):
        request = self.do_request("api:component-screenshots", self.component_kwargs)
        self.assertEqual(request.data["count"], 1)
        self.assertEqual(request.data["results"][0]["name"], "Obrazek")

    def test_patch(self):
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

    def test_put(self):
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

    def test_delete(self):
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

    def test_create_translation(self):
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

    def test_create_translation_existing(self):
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

    def test_create_translation_invalid_language_code(self):
        self.do_request(
            "api:component-translations",
            self.component_kwargs,
            method="post",
            code=400,
            request={"language_code": "invalid"},
        )

    def test_create_translation_prohibited(self):
        self.do_request(
            "api:component-translations",
            self.component_kwargs,
            method="post",
            code=403,
            request={"language_code": "fa"},
        )

    def test_download_translation_zip_ok(self):
        response = self.do_request(
            "api:component-download-archive",
            self.component_kwargs,
            method="get",
            code=200,
            superuser=True,
        )
        self.assertEqual(response.headers["content-type"], "application/zip")

    def test_download_translation_zip_prohibited(self):
        project = self.component.project
        project.access_control = Project.ACCESS_PROTECTED
        project.save(update_fields=["access_control"])
        self.do_request(
            "api:component-download-archive",
            self.component_kwargs,
            method="get",
            code=403,
        )

    def test_links(self):
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


class LanguageAPITest(APIBaseTest):
    def test_list_languages(self):
        response = self.client.get(reverse("api:language-list"))
        self.assertEqual(response.data["count"], 4)

    def test_get_language(self):
        response = self.client.get(
            reverse("api:language-detail", kwargs={"code": "cs"})
        )
        self.assertEqual(response.data["name"], "Czech")
        # Check plural exists
        self.assertEqual(response.data["plural"]["type"], 22)
        self.assertEqual(response.data["plural"]["number"], 3)
        # Check for aliases, with recent language-data there are 3
        self.assertGreaterEqual(len(response.data["aliases"]), 2)

    def test_create(self):
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

    def test_delete(self):
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

    def test_put(self):
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

    def test_patch(self):
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
    def test_get(self):
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

    def test_delete(self):
        self.do_request(
            "api:memory-detail",
            kwargs={"pk": Memory.objects.first().pk},
            method="delete",
            superuser=True,
            code=204,
        )


class TranslationAPITest(APIBaseTest):
    def test_list_translations(self):
        response = self.client.get(reverse("api:translation-list"))
        self.assertEqual(response.data["count"], 8)

    def test_list_translations_acl(self):
        self.create_acl()
        response = self.client.get(reverse("api:translation-list"))
        self.assertEqual(response.data["count"], 8)
        self.authenticate(True)
        response = self.client.get(reverse("api:translation-list"))
        self.assertEqual(response.data["count"], 16)

    def test_get_translation(self):
        response = self.client.get(
            reverse("api:translation-detail", kwargs=self.translation_kwargs)
        )
        self.assertEqual(response.data["language_code"], "cs")

    def test_download(self):
        response = self.do_request(
            "api:translation-file",
            kwargs=self.translation_kwargs,
            code=200,
        )
        self.assertContains(response, "Project-Id-Version: Weblate Hello World 2016")

    def test_download_args(self):
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

    def test_download_invalid_format_url(self):
        args = {"format": "invalid"}
        args.update(self.translation_kwargs)
        response = self.client.get(reverse("api:translation-file", kwargs=args))
        self.assertEqual(response.status_code, 404)

    def test_download_format_url(self):
        args = {"format": "xliff"}
        args.update(self.translation_kwargs)
        response = self.do_request(
            "api:translation-file",
            kwargs=args,
            code=200,
        )
        self.assertContains(response, "<xliff")

    def test_upload_denied(self):
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

    def test_get_units_no_filter(self):
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

    def test_get_units_q_filter(self):
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

    def test_upload_bytes(self):
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

    def test_upload(self):
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

    def test_upload_source(self):
        self.authenticate(True)
        with open(TEST_POT, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle, "method": "source"},
            )
        self.assertEqual(response.status_code, 400)
        with open(TEST_POT, "rb") as handle:
            source_kwargs = copy(self.translation_kwargs)
            source_kwargs["language__code"] = "en"
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

    def test_upload_content(self):
        self.authenticate()
        with open(TEST_PO, "rb") as handle:
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle.read()},
            )
        self.assertEqual(response.status_code, 400)

    def test_upload_conflicts(self):
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

    def test_upload_overwrite(self):
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

    def test_upload_suggest(self):
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
        self.assertEqual(self.component.project.stats.suggestions, 1)
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

    def test_upload_invalid(self):
        self.authenticate()
        response = self.client.put(
            reverse("api:translation-file", kwargs=self.translation_kwargs)
        )
        self.assertEqual(response.status_code, 400)

    def test_upload_error(self):
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
                "file": ErrorDetail(
                    string="Plural forms do not match the language.", code="invalid"
                )
            },
        )

    def test_repo_status_denied(self):
        self.do_request("api:translation-repository", self.translation_kwargs, code=403)

    def test_repo_status(self):
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

    def test_statistics(self):
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
                "translated": 0,
                "translated_words_percent": 0.0,
                "translated_chars": 0,
                "translated_chars_percent": 0.0,
                "total_chars": 139,
                "fuzzy": 0,
                "total": 4,
                "recent_changes": 0,
                "approved": 0,
                "approved_percent": 0.0,
                "comments": 0,
                "suggestions": 0,
                "readonly": 0,
                "readonly_percent": 0.0,
            },
            skip=("last_change",),
        )

    def test_changes(self):
        request = self.do_request("api:translation-changes", self.translation_kwargs)
        self.assertEqual(request.data["count"], 6)

    def test_units(self):
        request = self.do_request("api:translation-units", self.translation_kwargs)
        self.assertEqual(request.data["count"], 4)

    def test_autotranslate(self, format: str = "multipart"):
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

    def test_autotranslate_json(self):
        self.test_autotranslate("json")

    def test_add_monolingual(self):
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

    def test_add_bilingual(self):
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

    def test_delete(self):
        start_count = Translation.objects.count()
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
        self.assertEqual(Translation.objects.count(), start_count - 1)


class UnitAPITest(APIBaseTest):
    def test_list_units(self):
        response = self.client.get(reverse("api:unit-list"))
        self.assertEqual(response.data["count"], 16)

    def test_list_units_filter(self):
        response = self.client.get(reverse("api:unit-list"), {"q": "is:translated"})
        self.assertEqual(response.data["count"], 6)

    def test_get_unit(self):
        unit = Unit.objects.get(
            translation__language_code="cs", source="Hello, world!\n"
        )
        response = self.client.get(reverse("api:unit-detail", kwargs={"pk": unit.pk}))
        self.assertIn("translation", response.data)
        self.assertEqual(response.data["source"], ["Hello, world!\n"])

    def test_get_plural_unit(self):
        unit = Unit.objects.get(
            translation__language_code="cs", source__startswith="Orangutan has "
        )
        response = self.client.get(reverse("api:unit-detail", kwargs={"pk": unit.pk}))
        self.assertIn("translation", response.data)
        self.assertEqual(
            response.data["source"],
            ["Orangutan has %d banana.\n", "Orangutan has %d bananas.\n"],
        )

    def test_translate_unit(self):
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
        # Invalid state changes
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=400,
            request={"state": "100", "target": "Test read only translation"},
        )
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=400,
            request={"state": "0", "target": "Test read only translation"},
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

    def test_translate_unit_whitespace(self):
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

    def test_untranslate_unit(self):
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

    def test_untranslate_unit_invalid(self):
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

    def test_unit_review(self):
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

    def test_translate_source_unit(self):
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

    def test_unit_flags(self):
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

    def test_unit_labels(self):
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
            request={"labels": "test"},
        )

        # Edit on source will fail when label doesn't exist
        # or is not in the same project
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=400,
            superuser=True,
            request={"labels": "foo"},
        )
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=400,
            superuser=True,
            request={"labels": "test_2"},
        )

        # Edit on source will work when label exists
        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.source_unit.pk},
            method="patch",
            code=200,
            superuser=True,
            request={"labels": "test"},
        )

        # Label should be now updated
        unit = Unit.objects.get(pk=unit.id)
        self.assertEqual(len(unit.all_labels), 1)
        self.assertEqual(unit.all_labels[0].name, "test")

        label1.delete()
        label2.delete()
        other_project.delete()

    def test_translate_plural_unit(self):
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

    def test_delete_unit(self):
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


class ScreenshotAPITest(APIBaseTest):
    def setUp(self):
        super().setUp()
        shot = Screenshot.objects.create(
            name="Obrazek", translation=self.component.source_translation
        )
        with open(TEST_SCREENSHOT, "rb") as handle:
            shot.image.save("screenshot.png", File(handle))

    def test_list_screenshots(self):
        response = self.client.get(reverse("api:screenshot-list"))
        self.assertEqual(response.data["count"], 1)

    def test_get_screenshot(self):
        response = self.client.get(
            reverse("api:screenshot-detail", kwargs={"pk": Screenshot.objects.get().pk})
        )
        self.assertIn("file_url", response.data)

    def test_download(self):
        response = self.client.get(
            reverse("api:screenshot-file", kwargs={"pk": Screenshot.objects.get().pk})
        )
        self.assertContains(response, b"PNG")

    def test_upload(self, superuser=True, code=200, filename=TEST_SCREENSHOT):
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

    def test_upload_denied(self):
        self.test_upload(False, 403)

    def test_upload_invalid(self):
        self.test_upload(True, 400, TEST_PO)

    def test_create(self):
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
                    "language_code": ErrorDetail(
                        string="This field is required.", code="invalid"
                    )
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
                    "project_slug": ErrorDetail(
                        string="Translation matching query does not exist.",
                        code="invalid",
                    ),
                    "component_slug": ErrorDetail(
                        string="Translation matching query does not exist.",
                        code="invalid",
                    ),
                    "language_code": ErrorDetail(
                        string="Translation matching query does not exist.",
                        code="invalid",
                    ),
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
                "name": [
                    ErrorDetail(string="This field is required.", code="required")
                ],
                "image": [
                    ErrorDetail(string="No file was submitted.", code="required")
                ],
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

    def test_patch_screenshot(self):
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

    def test_put_screenshot(self):
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

    def test_delete_screenshot(self):
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

    def test_units_denied(self):
        unit = self.component.source_translation.unit_set.all()[0]
        response = self.client.post(
            reverse("api:screenshot-units", kwargs={"pk": Screenshot.objects.get().pk}),
            {"unit_id": unit.pk},
        )
        self.assertEqual(response.status_code, 401)

    def test_units_invalid(self):
        self.authenticate(True)
        response = self.client.post(
            reverse("api:screenshot-units", kwargs={"pk": Screenshot.objects.get().pk}),
            {"unit_id": -1},
        )
        self.assertEqual(response.status_code, 400)

    def test_units(self):
        self.authenticate(True)
        unit = self.component.source_translation.unit_set.all()[0]
        response = self.client.post(
            reverse("api:screenshot-units", kwargs={"pk": Screenshot.objects.get().pk}),
            {"unit_id": unit.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(unit.pk), response.data["units"][0])

    def test_units_delete(self):
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
    def test_list_changes(self):
        response = self.client.get(reverse("api:change-list"))
        self.assertEqual(response.data["count"], 33)

    def test_filter_changes_after(self):
        """Filter changes since timestamp."""
        start = Change.objects.order().last().timestamp
        response = self.client.get(
            reverse("api:change-list"), {"timestamp_after": start.isoformat()}
        )
        self.assertEqual(response.data["count"], 33)

    def test_filter_changes_before(self):
        """Filter changes prior to timestamp."""
        start = Change.objects.order().first().timestamp - timedelta(seconds=60)
        response = self.client.get(
            reverse("api:change-list"), {"timestamp_before": start.isoformat()}
        )
        self.assertEqual(response.data["count"], 0)

    def test_filter_changes_user(self):
        """Filter by non existing user."""
        response = self.client.get(reverse("api:change-list"), {"user": "nonexisting"})
        self.assertEqual(response.data["count"], 0)

    def test_get_change(self):
        response = self.client.get(
            reverse("api:change-detail", kwargs={"pk": Change.objects.all()[0].pk})
        )
        self.assertIn("translation", response.data)


class MetricsAPITest(APIBaseTest):
    def test_metrics(self):
        self.authenticate()
        response = self.client.get(reverse("api:metrics"))
        self.assertEqual(response.data["projects"], 1)

    def test_forbidden(self):
        response = self.client.get(reverse("api:metrics"))
        self.assertEqual(response.data["detail"].code, "not_authenticated")

    def test_ratelimit(self):
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
    def test_blank(self):
        self.authenticate()
        response = self.client.get(reverse("api:search"))
        self.assertEqual(response.data, [])

    def test_result(self):
        response = self.client.get(reverse("api:search"), {"q": "test"})
        self.assertEqual(
            response.data,
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
        )

    def test_language(self):
        response = self.client.get(reverse("api:search"), {"q": "czech"})
        self.assertEqual(
            response.data,
            [{"category": "Language", "name": "Czech", "url": "/languages/cs/"}],
        )


class ComponentListAPITest(APIBaseTest):
    def setUp(self):
        super().setUp()
        clist = ComponentList.objects.create(name="Name", slug="name")
        clist.autocomponentlist_set.create()

    def test_list(self):
        response = self.client.get(reverse("api:componentlist-list"))
        self.assertEqual(response.data["count"], 1)

    def test_get(self):
        response = self.client.get(
            reverse(
                "api:componentlist-detail",
                kwargs={"slug": ComponentList.objects.get().slug},
            )
        )
        self.assertIn("components", response.data)

    def test_create(self):
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

    def test_delete(self):
        self.do_request(
            "api:componentlist-detail",
            kwargs={"slug": ComponentList.objects.get().slug},
            method="delete",
            superuser=True,
            code=204,
        )

    def test_add_component(self):
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

    def test_remove_component(self):
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

    def test_put(self):
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

    def test_patch(self):
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

    def test_create(self):
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

    def test_delete(self):
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

    def test_configuration(self):
        self.create_addon(
            name="weblate.gettext.mo", configuration={"path": "{{var}}"}, code=400
        )

    def test_discover(self):
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

    def test_edit(self):
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
