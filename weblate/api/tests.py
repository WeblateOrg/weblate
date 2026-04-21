# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import tempfile
import zipfile
from contextlib import nullcontext
from copy import copy
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import responses
import yaml
from django.conf import settings
from django.core.cache import cache
from django.core.files import File
from django.test.utils import modify_settings, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from weblate_language_data.languages import LANGUAGES

from weblate.accounts.models import Subscription
from weblate.accounts.notifications import (
    NotificationFrequency,
    NotificationScope,
)
from weblate.addons.consistency import LanguageConsistencyAddon
from weblate.addons.gettext import XgettextAddon
from weblate.addons.models import Addon
from weblate.api.serializers import (
    CommentSerializer,
    ComponentSerializer,
    MemoryLookupRequestSerializer,
    RepoOperations,
)
from weblate.api.views import MemoryViewSet
from weblate.auth.data import SELECTION_ALL, SELECTION_MANUAL
from weblate.auth.models import Group, Permission, Role, User
from weblate.lang.models import Language
from weblate.memory.models import Memory
from weblate.screenshots.models import Screenshot
from weblate.trans.actions import ActionEvents
from weblate.trans.autotranslate import AutoTranslate
from weblate.trans.component_copy import (
    normalize_local_copy_branch,
    replace_component_checkout,
)
from weblate.trans.exceptions import FailedCommitError, FileParseError
from weblate.trans.models import (
    Announcement,
    Category,
    Change,
    Component,
    ComponentLink,
    ComponentList,
    Project,
    Translation,
    Unit,
)
from weblate.trans.models.component import ComponentQuerySet
from weblate.trans.tests.utils import (
    RepoTestMixin,
    clear_users_cache,
    create_test_billing,
    fixup_languages_seq,
    get_test_file,
)
from weblate.utils.celery import get_task_metadata_key
from weblate.utils.data import data_dir
from weblate.utils.django_hacks import immediate_on_commit, immediate_on_commit_leave
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.state import (
    STATE_EMPTY,
    STATE_NEEDS_CHECKING,
    STATE_NEEDS_REWRITING,
    STATE_TRANSLATED,
)
from weblate.utils.version import GIT_VERSION
from weblate.utils.version_display import VERSION_DISPLAY_HIDE, VERSION_DISPLAY_SOFT
from weblate.vcs.base import RepositoryError, RepositoryLock

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
        clear_users_cache()

    def setUp(self) -> None:
        Language.objects.flush_object_cache()
        self.clone_test_repos()
        self.component = self.create_component()
        self.project = self.component.project
        self.translation_kwargs = {
            "language__code": "cs",
            "component__slug": "test",
            "component__project__slug": "test",
        }
        self.component_kwargs = {"slug": "test", "project__slug": "test"}
        self.project_kwargs = {"slug": "test"}
        self.tearDown()
        self.user = User.objects.create_user("apitest", "apitest@example.org", "x")
        self.user.profile.languages.add(Language.objects.get(code="cs"))
        self.group = Group.objects.get(name="Users")
        self.user.groups.add(self.group)

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
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.user.auth_token.key}")

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
        skip: set[str] | None = None,
        # pylint: disable-next=redefined-builtin
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
            if skip:
                for item in skip:
                    del response.data[item]
            self.maxDiff = None
            self.assertEqual(response.data, data)
        return response

    def grant_perm_to_user(
        self,
        perm: str,
        group_name: str = "Permission group",
        project: Project | None = None,
    ) -> None:
        permission = Permission.objects.get(codename=perm)
        group = Group.objects.get_or_create(
            name=group_name, language_selection=SELECTION_ALL
        )[0]
        if project:
            group.projects.add(project)
        role = Role.objects.create(name="Permission role")
        role.permissions.add(permission)
        group.roles.add(role)
        self.user.groups.add(group)


class UserAPITest(APIBaseTest):
    def test_list(self) -> None:
        response = self.client.get(reverse("api:user-list"))
        self.assertEqual(response.data["count"], 0)

        self.authenticate(False)
        response = self.client.get(reverse("api:user-list"))
        self.assertEqual(response.data["count"], 1)
        self.assertNotIn("email", response.data["results"][0])

        self.authenticate(True)
        response = self.client.get(reverse("api:user-list"))
        self.assertEqual(response.data["count"], 4)
        self.assertIsNotNone(response.data["results"][0]["email"])

        self.authenticate(False)
        self.grant_perm_to_user("user.view")
        response = self.client.get(reverse("api:user-list"))
        self.assertEqual(response.data["count"], 4)
        self.assertIsNotNone(response.data["results"][0]["email"])

    def test_get(self) -> None:
        language = Language.objects.get(code="cs")
        response = self.do_request(
            "api:user-detail",
            kwargs={"username": "apitest"},
            method="get",
            superuser=True,
            code=200,
        )
        self.assertEqual(response.data["username"], "apitest")
        self.assertIn(
            f"http://example.com/api/languages/{language.code}/",
            response.data["languages"],
        )

        # user without permission can only see basic information
        response = self.do_request(
            "api:user-detail",
            kwargs={"username": "apitest"},
            method="get",
            superuser=False,
            code=200,
        )
        self.assertNotIn("languages", response.data)

        # user with right permission can see detailed information
        self.grant_perm_to_user("user.view")
        response = self.do_request(
            "api:user-detail",
            kwargs={"username": "apitest"},
            method="get",
            superuser=False,
            code=200,
        )
        self.assertEqual(response.data["username"], "apitest")
        self.assertIn(
            f"http://example.com/api/languages/{language.code}/",
            response.data["languages"],
        )

    def test_get_anonymous(self) -> None:
        # User info not accessible without auth
        self.do_request(
            "api:user-detail",
            kwargs={"username": settings.ANONYMOUS_USER_NAME},
            method="get",
            authenticated=False,
            code=404,
        )
        # User is able to get another user basic info, but not full details
        self.do_request(
            "api:user-detail",
            kwargs={"username": settings.ANONYMOUS_USER_NAME},
            method="get",
            superuser=False,
            code=200,
            data={"full_name": "Anonymous", "username": settings.ANONYMOUS_USER_NAME},
            skip={"id"},
        )
        # Admin can get full details
        self.do_request(
            "api:user-detail",
            kwargs={"username": settings.ANONYMOUS_USER_NAME},
            method="get",
            superuser=True,
            code=200,
            data={
                "email": "noreply@weblate.org",
                "full_name": "Anonymous",
                "username": settings.ANONYMOUS_USER_NAME,
                "is_superuser": False,
                "is_active": False,
                "is_bot": False,
                "last_login": None,
            },
            skip={
                "id",
                "groups",
                "languages",
                "notifications",
                "date_joined",
                "url",
                "statistics_url",
                "contributions_url",
                "date_expires",
            },
        )

    def test_filter_superuser(self) -> None:
        """Front-end autocompletion interface for superuser."""
        self.authenticate(True)
        # Blank search should return all results for superuser
        response = self.client.get(reverse("api:user-list"), {"username": ""})
        self.assertEqual(response.data["count"], 4)
        # Short search should return results for superuser
        response = self.client.get(reverse("api:user-list"), {"username": "a"})
        self.assertEqual(response.data["count"], 2)
        # Filtering should work
        response = self.client.get(
            reverse("api:user-list"), {"username": settings.ANONYMOUS_USER_NAME}
        )
        self.assertEqual(response.data["count"], 1)

    def test_filter_email(self) -> None:
        """Filtering by email address."""
        self.authenticate(True)
        # Exact match should return the user
        response = self.client.get(
            reverse("api:user-list"), {"email": "apitest@example.org"}
        )
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["username"], "apitest")
        # Case-insensitive match should work
        response = self.client.get(
            reverse("api:user-list"), {"email": "APItest@Example.ORG"}
        )
        self.assertEqual(response.data["count"], 1)
        # Non-matching email should return no results
        response = self.client.get(
            reverse("api:user-list"), {"email": "nonexistent@example.org"}
        )
        self.assertEqual(response.data["count"], 0)
        # Admin can look up another user's email (cross-user lookup)
        response = self.client.get(
            reverse("api:user-list"), {"email": "noreply@weblate.org"}
        )
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["username"], settings.ANONYMOUS_USER_NAME
        )

    def test_filter_email_non_admin(self) -> None:
        """Non-admin users cannot use email filter (prevented by restricted filterset)."""
        self.authenticate(False)
        # Email filter is ignored for non-admins; without username, scoped to self
        response = self.client.get(
            reverse("api:user-list"), {"email": "noreply@weblate.org"}
        )
        # Returns own user because email param is ignored, scoped to self
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["username"], "apitest")
        # Combining username + email should not allow email enumeration
        response = self.client.get(
            reverse("api:user-list"),
            {"username": settings.ANONYMOUS_USER_NAME, "email": "noreply@weblate.org"},
        )
        # Email param is ignored; results are based on username filter only
        self.assertEqual(response.data["count"], 1)
        # Verify the result is the username-matched user, not email-filtered
        self.assertEqual(
            response.data["results"][0]["username"], settings.ANONYMOUS_USER_NAME
        )
        # Non-admin with username + non-matching email: email param ignored
        response = self.client.get(
            reverse("api:user-list"),
            {"username": settings.ANONYMOUS_USER_NAME, "email": "wrong@example.org"},
        )
        # Still returns username match since email is ignored
        self.assertEqual(response.data["count"], 1)

    def test_filter_email_unauthenticated(self) -> None:
        """Unauthenticated users cannot use email filter."""
        # No authentication - email param should be ignored and no results returned
        response = self.client.get(
            reverse("api:user-list"), {"email": "apitest@example.org"}
        )
        self.assertEqual(response.data["count"], 0)
        response = self.client.get(
            reverse("api:user-list"), {"email": "noreply@weblate.org"}
        )
        self.assertEqual(response.data["count"], 0)

    def test_filter_email_with_user_view_permission(self) -> None:
        """Non-superuser with user.view permission can use email filter."""
        # Grant user.view permission to a non-superuser
        self.grant_perm_to_user("user.view")
        self.authenticate(False)
        # User with user.view permission can filter by email
        response = self.client.get(
            reverse("api:user-list"), {"email": "apitest@example.org"}
        )
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["username"], "apitest")
        # Can look up other users by email
        response = self.client.get(
            reverse("api:user-list"), {"email": "noreply@weblate.org"}
        )
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["username"], settings.ANONYMOUS_USER_NAME
        )
        # Case-insensitive search works
        response = self.client.get(
            reverse("api:user-list"), {"email": "APItest@Example.ORG"}
        )
        self.assertEqual(response.data["count"], 1)

    def test_filter_email_with_user_edit_permission(self) -> None:
        """Non-superuser with user.edit permission can use email filter."""
        # Grant user.edit permission to a non-superuser
        self.grant_perm_to_user("user.edit")
        self.authenticate(False)
        # User with user.edit permission can filter by email
        response = self.client.get(
            reverse("api:user-list"), {"email": "apitest@example.org"}
        )
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["username"], "apitest")
        # Can look up other users by email
        response = self.client.get(
            reverse("api:user-list"), {"email": "noreply@weblate.org"}
        )
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["username"], settings.ANONYMOUS_USER_NAME
        )

    def test_filter_user(self) -> None:
        """Front-end autocompletion interface for user."""
        self.authenticate(False)
        # Filtering should work
        response = self.client.get(
            reverse("api:user-list"), {"username": settings.ANONYMOUS_USER_NAME}
        )
        self.assertEqual(response.data["count"], 1)
        # Blank search should return no results
        response = self.client.get(reverse("api:user-list"), {"username": ""})
        self.assertEqual(response.data["count"], 0)
        # Short search should return no results
        response = self.client.get(reverse("api:user-list"), {"username": "a"})
        self.assertEqual(response.data["count"], 0)

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
        self.assertEqual(User.objects.count(), 5)

    def test_create_logs_superuser_grant(self) -> None:
        self.do_request(
            "api:user-list",
            method="post",
            superuser=True,
            code=201,
            request={
                "full_name": "Name",
                "username": "super-name",
                "email": "super-name@example.com",
                "is_active": True,
                "is_superuser": True,
            },
        )
        user = User.objects.get(username="super-name")
        audit = user.auditlog_set.get(activity="superuser-granted")
        self.assertEqual(audit.params["username"], self.user.username)

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
        self.assertEqual(User.objects.count(), 5)
        self.assertEqual(User.objects.filter(is_active=True).count(), 1)

    def test_add_group(self) -> None:
        group = Group.objects.get(name="Viewers")
        target = User.objects.create_user("target-add", "target-add@example.org", "x")
        self.do_request(
            "api:user-groups",
            kwargs={"username": target.username},
            method="post",
            code=403,
            request={"group_id": group.id},
        )
        response = self.do_request(
            "api:user-groups",
            kwargs={"username": target.username},
            method="post",
            superuser=True,
            code=400,
            request={"group_id": -1},
        )
        self.assertContains(response, "Group not found.", status_code=400)
        self.assertNotContains(
            response, "matching query does not exist", status_code=400
        )
        self.do_request(
            "api:user-groups",
            kwargs={"username": target.username},
            method="post",
            superuser=True,
            code=200,
            request={"group_id": group.id},
        )
        target.refresh_from_db()
        audit = target.auditlog_set.get(
            activity="sitewide-team-add",
            params__team=group.name,
            params__username=self.user.username,
        )
        self.assertEqual(audit.params["team"], group.name)
        self.assertEqual(audit.params["username"], self.user.username)

    def test_remove_group(self) -> None:
        group = Group.objects.get(name="Viewers")
        target = User.objects.create_user(
            "target-remove", "target-remove@example.org", "x"
        )
        self.do_request(
            "api:user-groups",
            kwargs={"username": target.username},
            method="post",
            code=403,
            request={"group_id": group.id},
        )
        self.do_request(
            "api:user-groups",
            kwargs={"username": target.username},
            method="post",
            superuser=True,
            code=400,
            request={"group_id": -1},
        )
        response = self.do_request(
            "api:user-groups",
            kwargs={"username": target.username},
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
            kwargs={"username": target.username},
            method="delete",
            superuser=True,
            code=200,
            request={"group_id": group.id},
        )
        self.assertNotIn(
            "http://example.com/api/groups/{group.id}/", response.data["groups"]
        )
        target.refresh_from_db()
        audit = target.auditlog_set.get(
            activity="sitewide-team-remove",
            params__team=group.name,
            params__username=self.user.username,
        )
        self.assertEqual(audit.params["team"], group.name)
        self.assertEqual(audit.params["username"], self.user.username)

    def test_remove_last_group_bot(self) -> None:
        bot = User.objects.create(
            username="bot-test",
            full_name="Test Bot",
            is_bot=True,
            is_active=True,
        )
        group = Group.objects.get(name="Viewers")
        # Clear auto-assigned groups and keep only one
        bot.groups.set([group])
        self.do_request(
            "api:user-groups",
            kwargs={"username": bot.username},
            method="delete",
            superuser=True,
            code=400,
            request={"group_id": group.id},
        )
        # Bot should still have the group
        self.assertTrue(bot.groups.filter(pk=group.pk).exists())

    def test_list_notifications(self) -> None:
        self.do_request(
            "api:user-notifications",
            kwargs={"username": settings.ANONYMOUS_USER_NAME},
            method="get",
            code=403,
        )
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
            kwargs={"username": settings.ANONYMOUS_USER_NAME},
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
        anonymous_user = User.objects.get(username=settings.ANONYMOUS_USER_NAME)
        anonymous_subscription = anonymous_user.subscription_set.create(
            scope=NotificationScope.SCOPE_ALL,
            frequency=NotificationFrequency.FREQ_INSTANT,
        )
        self.do_request(
            "api:user-notifications-details",
            kwargs={"username": user.username, "subscription_id": 1000},
            method="get",
            code=404,
        )
        self.do_request(
            "api:user-notifications-details",
            kwargs={
                "username": settings.ANONYMOUS_USER_NAME,
                "subscription_id": anonymous_subscription.id,
            },
            method="get",
            code=403,
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

    def test_self_notifications(self) -> None:
        """Users should be able to manage their own notifications via the API."""
        # User can list own notifications
        response = self.do_request(
            "api:user-notifications",
            kwargs={"username": self.user.username},
            method="get",
            code=200,
        )
        self.assertEqual(response.data["count"], 10)

        # User can create own notification
        response = self.do_request(
            "api:user-notifications",
            kwargs={"username": self.user.username},
            method="post",
            code=201,
            request={
                "notification": "RepositoryNotification",
                "scope": 10,
                "frequency": 1,
            },
        )
        self.assertEqual(response.data["notification"], "RepositoryNotification")
        subscription_id = response.data["id"]

        # User can read own notification details
        self.do_request(
            "api:user-notifications-details",
            kwargs={"username": self.user.username, "subscription_id": subscription_id},
            method="get",
            code=200,
        )

        # User can update own notification
        response = self.do_request(
            "api:user-notifications-details",
            kwargs={"username": self.user.username, "subscription_id": subscription_id},
            method="patch",
            code=200,
            request={"frequency": 2},
        )
        self.assertEqual(response.data["frequency"], 2)

        # User can delete own notification
        self.do_request(
            "api:user-notifications-details",
            kwargs={"username": self.user.username, "subscription_id": subscription_id},
            method="delete",
            code=204,
        )

        # User cannot manage another user's notifications (create)
        other_user = User.objects.create_user("other_user", "other@example.com")
        self.do_request(
            "api:user-notifications",
            kwargs={"username": other_user.username},
            method="post",
            code=403,
            request={
                "notification": "RepositoryNotification",
                "scope": 10,
                "frequency": 1,
            },
        )

        # User cannot delete another user's notifications
        other_subscription = Subscription.objects.filter(user=other_user)[0]
        self.do_request(
            "api:user-notifications-details",
            kwargs={
                "username": other_user.username,
                "subscription_id": other_subscription.id,
            },
            method="delete",
            code=403,
        )

    def test_statistics(self) -> None:
        user = User.objects.filter(is_active=True)[0]
        request = self.do_request(
            "api:user-statistics",
            kwargs={"username": user.username},
            superuser=True,
        )
        self.assertEqual(request.data["commented"], user.profile.commented)

    def test_contributions(self) -> None:
        user = User.objects.filter(is_active=True)[0]
        request = self.do_request(
            "api:user-contributions",
            kwargs={"username": user.username},
            superuser=True,
        )
        self.assertEqual(request.data["results"], [])

    def test_put(self) -> None:
        self.do_request(
            "api:user-detail",
            kwargs={"username": settings.ANONYMOUS_USER_NAME},
            method="put",
            code=403,
        )
        self.do_request(
            "api:user-detail",
            kwargs={"username": self.user.username},
            method="put",
            code=200,
            request={
                "full_name": "Name",
                "username": "apitest",
                "email": "apitest@example.org",
                "is_active": True,
            },
        )
        self.assertEqual(
            User.objects.get(username=self.user.username).full_name, "Name"
        )
        self.do_request(
            "api:user-detail",
            kwargs={"username": settings.ANONYMOUS_USER_NAME},
            method="put",
            superuser=True,
            code=200,
            request={
                "full_name": "Name",
                "username": "apitest2",
                "email": "apitest2@example.org",
                "is_active": True,
            },
        )
        self.assertFalse(
            User.objects.filter(username=settings.ANONYMOUS_USER_NAME).exists()
        )
        self.assertEqual(User.objects.get(username="apitest2").full_name, "Name")

    def test_put_self_without_user_view_keeps_email(self) -> None:
        self.do_request(
            "api:user-detail",
            kwargs={"username": self.user.username},
            method="put",
            code=200,
            request={
                "full_name": "Renamed",
                "username": self.user.username,
            },
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Renamed")
        self.assertEqual(self.user.email, "apitest@example.org")

    def test_patch(self) -> None:
        self.do_request(
            "api:user-detail",
            kwargs={"username": settings.ANONYMOUS_USER_NAME},
            method="patch",
            code=403,
        )
        # User can edit self
        self.do_request(
            "api:user-detail",
            kwargs={"username": self.user.username},
            method="patch",
            code=200,
            request={"full_name": "Other"},
        )
        self.assertEqual(
            User.objects.get(username=self.user.username).full_name, "Other"
        )
        # User cannot change some self attributes
        self.do_request(
            "api:user-detail",
            kwargs={"username": self.user.username},
            method="patch",
            code=200,
            request={"is_superuser": True},
        )
        self.assertFalse(User.objects.get(username=self.user.username).is_superuser)
        # Superuser can edit anybody
        self.do_request(
            "api:user-detail",
            kwargs={"username": settings.ANONYMOUS_USER_NAME},
            method="patch",
            superuser=True,
            code=200,
            request={"full_name": "Other"},
        )
        self.assertEqual(
            User.objects.get(username=settings.ANONYMOUS_USER_NAME).full_name, "Other"
        )

    def test_patch_logs_superuser_grant(self) -> None:
        target = User.objects.create_user("target", "target@example.org", "x")

        self.do_request(
            "api:user-detail",
            kwargs={"username": target.username},
            method="patch",
            superuser=True,
            code=200,
            request={"is_superuser": True},
        )

        target.refresh_from_db()
        self.assertTrue(target.is_superuser)
        audit = target.auditlog_set.get(activity="superuser-granted")
        self.assertEqual(audit.params["username"], self.user.username)
        self.assertIsNone(audit.address)

    def test_patch_self_with_user_view_permission(self) -> None:
        self.grant_perm_to_user("user.view")
        self.authenticate(False)

        response = self.client.get(
            reverse("api:user-detail", kwargs={"username": self.user.username})
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.data)
        self.assertIn("is_superuser", response.data)

        self.do_request(
            "api:user-detail",
            kwargs={"username": self.user.username},
            method="patch",
            code=200,
            request={"full_name": "Viewed User", "email": "viewed@example.org"},
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Viewed User")
        self.assertEqual(self.user.email, "viewed@example.org")

        self.do_request(
            "api:user-detail",
            kwargs={"username": self.user.username},
            method="patch",
            code=200,
            request={"is_superuser": True, "is_active": False, "is_bot": True},
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_superuser)
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.is_bot)

        self.do_request(
            "api:user-detail",
            kwargs={"username": self.user.username},
            method="patch",
            code=200,
            request={"date_expires": "2030-01-01T00:00:00Z"},
        )
        self.user.refresh_from_db()
        self.assertIsNone(self.user.date_expires)


class GroupAPITest(APIBaseTest):
    def test_list(self) -> None:
        response = self.client.get(reverse("api:group-list"))
        self.assertEqual(response.data["count"], 2)

        self.grant_perm_to_user("group.view", "Viewers")
        self.authenticate(False)
        response = self.client.get(reverse("api:group-list"))
        self.assertEqual(response.data["count"], 7)

    def test_get(self) -> None:
        # user can see details of group they are member of
        response = self.do_request(
            "api:group-detail",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="get",
            code=200,
        )
        self.assertEqual(response.data["name"], "Users")

        # user without view permission can't see other group details
        Group.objects.create(name="Test Group")
        self.do_request(
            "api:group-detail",
            kwargs={"id": Group.objects.get(name="Test Group").id},
            method="get",
            code=404,
        )

        # user with view permission can see other group details
        self.grant_perm_to_user("group.view", "Viewers")
        self.do_request(
            "api:group-detail",
            kwargs={"id": Group.objects.get(name="Test Group").id},
            method="get",
            code=200,
        )

    def test_get_user(self) -> None:
        response = self.do_request(
            "api:group-detail",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="get",
            code=200,
        )
        self.assertEqual(response.data["name"], "Users")

    def test_get_user_admin(self) -> None:
        group = Group.objects.create(name="Test Group")

        # No access to the group
        self.do_request(
            "api:group-detail",
            kwargs={"id": group.id},
            method="get",
            code=404,
        )

        # User access the group
        self.user.groups.add(group)
        response = self.do_request(
            "api:group-detail",
            kwargs={"id": group.id},
            method="get",
            code=200,
        )
        self.assertEqual(response.data["name"], "Test Group")

        # Admin access to the group
        group.admins.add(self.user)
        response = self.do_request(
            "api:group-detail",
            kwargs={"id": group.id},
            method="get",
            code=200,
        )
        self.assertEqual(response.data["name"], "Test Group")

    def test_create(self) -> None:
        self.do_request(
            "api:group-list", method="post", code=403, request={"name": "Group"}
        )
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

        admin = User.objects.create_user("admin", "admin@example.com")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {admin.auth_token.key}")

        # User without group.edit or project.permissions cannot create project team.
        self.do_request(
            "api:group-list",
            method="post",
            code=403,
            authenticated=False,
            format="json",
            request={
                "name": "Group Project",
                "defining_project": reverse(
                    "api:project-detail", kwargs=self.project_kwargs
                ),
            },
        )

        self.component.project.add_user(admin, "Administration")
        self.do_request(
            "api:group-list",
            method="post",
            code=201,
            authenticated=False,
            format="json",
            request={
                "name": "Group Project",
                "defining_project": reverse(
                    "api:project-detail", kwargs=self.project_kwargs
                ),
            },
        )
        self.assertEqual(Group.objects.count(), 9)

        other_component = self.create_acl()
        self.do_request(
            "api:group-list",
            method="post",
            code=403,
            authenticated=False,
            format="json",
            request={
                "name": "Group Project Other",
                "defining_project": reverse(
                    "api:project-detail",
                    kwargs={"slug": other_component.project.slug},
                ),
            },
        )
        self.do_request(
            "api:group-list",
            method="post",
            code=403,
            authenticated=False,
            format="json",
            request={
                "name": "Group Project Missing",
                "defining_project": reverse(
                    "api:project-detail", kwargs={"slug": "missing"}
                ),
            },
        )

        global_admin = User.objects.create_user("groupadmin", "groupadmin@example.com")
        permission = Permission.objects.get(codename="group.edit")
        role = Role.objects.create(name="Global group edit")
        role.permissions.add(permission)
        team = Group.objects.create(name="Global group editors")
        team.roles.add(role)
        global_admin.groups.add(team)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {global_admin.auth_token.key}"
        )
        self.do_request(
            "api:group-list",
            method="post",
            code=201,
            authenticated=False,
            format="json",
            request={
                "name": "Group Project Global",
                "defining_project": reverse(
                    "api:project-detail", kwargs=self.project_kwargs
                ),
            },
        )

    def test_add_role(self) -> None:
        role = Role.objects.get(name="Administration")
        self.do_request(
            "api:group-roles",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            code=403,
            request={"role_id": role.id},
        )
        response = self.do_request(
            "api:group-roles",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=400,
            request={"role_id": -1},
        )
        self.assertContains(response, "Role not found.", status_code=400)
        self.assertNotContains(
            response, "matching query does not exist", status_code=400
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
        response = self.do_request(
            "api:group-components",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=400,
            request={"component_id": -1},
        )
        self.assertContains(response, "Component not found.", status_code=400)
        self.assertNotContains(
            response, "matching query does not exist", status_code=400
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
        response = self.do_request(
            "api:group-projects",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=400,
            request={"project_id": -1},
        )
        self.assertContains(response, "Project not found.", status_code=400)
        self.assertNotContains(
            response, "matching query does not exist", status_code=400
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
        response = self.do_request(
            "api:group-languages",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=400,
            request={"language_code": "invalid"},
        )
        self.assertContains(response, "Language not found.", status_code=400)
        self.assertNotContains(
            response, "matching query does not exist", status_code=400
        )
        response = self.do_request(
            "api:group-languages",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=400,
            request={"language_code": None},
            format="json",
        )
        self.assertContains(response, "Invalid language code.", status_code=400)
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
        response = self.do_request(
            "api:group-componentlists",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="post",
            superuser=True,
            code=400,
            request={"component_list_id": -1},
        )
        self.assertContains(response, "Component list not found.", status_code=400)
        self.assertNotContains(
            response, "matching query does not exist", status_code=400
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
            code=404,
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
        group = Group.objects.create(
            name="Group", project_selection=0, language_selection=0
        )
        self.do_request(
            "api:group-detail",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="patch",
            code=403,
        )
        self.do_request(
            "api:group-detail",
            kwargs={"id": group.id},
            method="patch",
            superuser=True,
            code=200,
            request={"language_selection": 1},
        )
        self.assertEqual(Group.objects.get(name="Group").language_selection, 1)

    def test_patch_internal_group_blocked(self) -> None:
        self.do_request(
            "api:group-detail",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="patch",
            superuser=True,
            code=200,
            format="json",
            request={"language_selection": SELECTION_ALL},
        )
        self.do_request(
            "api:group-detail",
            kwargs={"id": Group.objects.get(name="Users").id},
            method="patch",
            superuser=True,
            code=400,
            format="json",
            request={"project_selection": SELECTION_MANUAL},
        )
        self.assertEqual(Group.objects.get(name="Users").project_selection, 3)

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
        self.assertContains(response, "User not found", status_code=400)
        self.assertNotContains(
            response, "matching query does not exist", status_code=400
        )

        # Missing user ID
        self.do_request(
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

    def test_project_admin_group_visibility(self) -> None:
        """Project admins can manage project-scoped groups but not global-only actions."""
        # Create a non-superuser with project admin rights
        admin = User.objects.create_user("project_admin", "admin@example.com")
        self.component.project.add_user(admin, "Administration")

        # Create a project-scoped group
        group = Group.objects.create(
            name="Project Team",
            project_selection=SELECTION_MANUAL,
            language_selection=SELECTION_ALL,
            defining_project=self.component.project,
        )
        group.projects.add(self.component.project)

        # Switch to project admin credentials
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {admin.auth_token.key}")

        # Project admin can see the group (appears in queryset)
        self.do_request(
            "api:group-detail",
            kwargs={"id": group.id},
            method="get",
            authenticated=False,
            code=200,
        )

        # Project admin can update project-scoped group properties
        self.do_request(
            "api:group-detail",
            kwargs={"id": group.id},
            method="patch",
            authenticated=False,
            code=200,
            request={"language_selection": 1},
        )
        group.refresh_from_db()
        self.assertEqual(group.language_selection, 1)
        self.do_request(
            "api:group-detail",
            kwargs={"id": group.id},
            method="put",
            authenticated=False,
            code=200,
            format="json",
            request={
                "name": group.name,
                "defining_project": reverse(
                    "api:project-detail",
                    kwargs={"slug": self.component.project.slug},
                ),
                "project_selection": group.project_selection,
                "language_selection": group.language_selection,
            },
        )

        # Project admin cannot change project scope fields on a project-scoped group
        self.do_request(
            "api:group-detail",
            kwargs={"id": group.id},
            method="patch",
            authenticated=False,
            code=403,
            format="json",
            request={"project_selection": SELECTION_ALL},
        )
        self.do_request(
            "api:group-detail",
            kwargs={"id": group.id},
            method="patch",
            authenticated=False,
            code=200,
            format="json",
            request={
                "defining_project": reverse(
                    "api:project-detail",
                    kwargs={"slug": self.component.project.slug},
                )
            },
        )
        acl_component = self.create_acl()
        acl_component.project.add_user(admin, "Administration")
        self.do_request(
            "api:group-detail",
            kwargs={"id": group.id},
            method="patch",
            authenticated=False,
            code=400,
            format="json",
            request={
                "defining_project": reverse(
                    "api:project-detail",
                    kwargs={"slug": acl_component.project.slug},
                )
            },
        )
        group.refresh_from_db()
        self.assertEqual(group.project_selection, SELECTION_MANUAL)
        self.assertEqual(group.defining_project, self.component.project)

        internal_group = Group.objects.create(
            name="Project ACL",
            project_selection=SELECTION_MANUAL,
            language_selection=SELECTION_ALL,
            defining_project=self.component.project,
            internal=True,
        )
        internal_group.projects.add(self.component.project)
        self.do_request(
            "api:group-detail",
            kwargs={"id": internal_group.id},
            method="patch",
            authenticated=False,
            code=400,
            request={"language_selection": SELECTION_MANUAL},
        )
        internal_group.refresh_from_db()
        self.assertEqual(internal_group.language_selection, SELECTION_ALL)

        # Project admin cannot add roles to the group (only global admins can)
        role = Role.objects.get(name="Administration")
        self.do_request(
            "api:group-roles",
            kwargs={"id": group.id},
            method="post",
            authenticated=False,
            code=403,
            request={"role_id": role.id},
        )

        # Project admin can delete the project-scoped group
        self.do_request(
            "api:group-detail",
            kwargs={"id": group.id},
            method="delete",
            authenticated=False,
            code=204,
        )
        self.assertFalse(Group.objects.filter(pk=group.pk).exists())

    def test_project_permissions_user_can_put_group_with_unchanged_defining_project(
        self,
    ) -> None:
        admin = User.objects.create_user(
            "project_permissions", "permissions@example.com"
        )
        permission = Permission.objects.get(codename="project.permissions")
        role = Role.objects.create(name="Project permissions only")
        role.permissions.add(permission)
        group = Group.objects.create(
            name="Project Permissions Team",
            project_selection=SELECTION_MANUAL,
            language_selection=SELECTION_ALL,
        )
        group.projects.add(self.component.project)
        group.roles.add(role)
        admin.groups.add(group)

        scoped_group = Group.objects.create(
            name="Project Team",
            project_selection=SELECTION_MANUAL,
            language_selection=SELECTION_ALL,
            defining_project=self.component.project,
        )
        scoped_group.projects.add(self.component.project)

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {admin.auth_token.key}")
        self.do_request(
            "api:group-detail",
            kwargs={"id": scoped_group.id},
            method="put",
            authenticated=False,
            code=200,
            format="json",
            request={
                "name": scoped_group.name,
                "defining_project": reverse(
                    "api:project-detail",
                    kwargs={"slug": self.component.project.slug},
                ),
                "project_selection": scoped_group.project_selection,
                "language_selection": SELECTION_MANUAL,
            },
        )
        scoped_group.refresh_from_db()
        self.assertEqual(scoped_group.language_selection, SELECTION_MANUAL)

    def test_non_project_admin_group_visibility(self) -> None:
        """Users without project admin rights cannot see project-scoped groups."""
        other_user = User.objects.create_user("other_user", "other@example.com")

        # Create a project-scoped group via the API as superuser
        response = self.do_request(
            "api:group-list",
            method="post",
            superuser=True,
            code=201,
            format="json",
            request={
                "name": "Project Team",
                "project_selection": 0,
                "language_selection": 0,
                "defining_project": reverse(
                    "api:project-detail", kwargs=self.project_kwargs
                ),
            },
        )
        group_id = response.data["id"]

        # Switch to a user who has no rights on this project
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {other_user.auth_token.key}")

        # Non-admin cannot see the group (not in queryset)
        self.do_request(
            "api:group-detail",
            kwargs={"id": group_id},
            method="get",
            authenticated=False,
            code=404,
        )


class ComponentCopyTest(APITestCase):
    def test_replace_component_checkout_preserves_local_git_for_non_git_source(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory() as source_dir,
            tempfile.TemporaryDirectory() as target_dir,
        ):
            os.makedirs(os.path.join(source_dir, ".hg"))
            os.makedirs(os.path.join(target_dir, ".git"))
            Path(source_dir, "messages.po").write_text("copied", encoding="utf-8")
            Path(target_dir, "stale.po").write_text("stale", encoding="utf-8")

            source_component = SimpleNamespace(
                full_path=source_dir,
                repository=SimpleNamespace(lock=nullcontext()),
            )
            target_component = SimpleNamespace(
                full_path=target_dir,
                is_repo_local=True,
                repository=SimpleNamespace(lock=nullcontext()),
            )

            self.assertTrue(
                replace_component_checkout(target_component, source_component)
            )
            self.assertTrue(Path(target_dir, ".git").is_dir())
            self.assertFalse(Path(target_dir, ".hg").exists())
            self.assertTrue(Path(target_dir, "messages.po").is_file())
            self.assertFalse(Path(target_dir, "stale.po").exists())

    def test_normalize_local_copy_branch_resets_to_component_branch(self) -> None:
        calls: list[list[str]] = []

        class DummyRepository:
            def __init__(self) -> None:
                self.lock = nullcontext()
                self.branch = "release"

            def has_branch(self, _branch: str) -> bool:
                return False

            def execute(self, args: list[str], *, remote_op: str) -> None:
                if remote_op != "none":
                    raise AssertionError(remote_op)
                calls.append(args)

            def clean_revision_cache(self) -> None:
                calls.append(["clean_revision_cache"])

        repository = DummyRepository()
        component = SimpleNamespace(
            is_repo_local=True,
            branch="main",
            repository=repository,
        )

        normalize_local_copy_branch(component)

        self.assertEqual(calls, [["checkout", "-B", "main"], ["clean_revision_cache"]])
        self.assertEqual(repository.branch, "main")

    def test_collect_other_translations_is_stable_for_selected_components(self) -> None:
        auto = AutoTranslate.__new__(AutoTranslate)
        auto.translation = SimpleNamespace(plural_id=1)
        auto.warnings = []

        class FilteredSources:
            def annotate(self, **_kwargs):
                return self

            def order_by(self, *_args):
                return self

            def values_list(self, *_args):
                return [
                    (1, "Hello", "first", 10, 1),
                    (2, "Hello", "second", 20, 1),
                    (1, "Hello", "later", 30, 1),
                ]

        class EmptyComponents:
            def defer_huge(self):
                return self

            def prefetch(self):
                return self

            def distinct(self):
                return self

            def order_project(self):
                return []

        with patch(
            "weblate.trans.autotranslate.Component.objects.filter",
            return_value=EmptyComponents(),
        ):
            translations = auto.collect_other_translations(FilteredSources(), [1, 2])

        self.assertEqual(translations, {"Hello": ["first"]})


class RoleAPITest(APIBaseTest):
    def test_list_roles(self) -> None:
        response = self.client.get(reverse("api:role-list"))
        self.assertEqual(response.data["count"], 2)

        self.authenticate(True)
        response = self.client.get(reverse("api:role-list"))
        self.assertEqual(response.data["count"], 16)

        self.authenticate(False)
        self.grant_perm_to_user("role.view")  # also creates a new role
        response = self.client.get(reverse("api:role-list"))
        self.assertEqual(response.data["count"], 17)

    def test_get_role(self) -> None:
        # user can view details of a role they have
        role = Role.objects.get(name="Access repository")
        response = self.client.get(reverse("api:role-detail", kwargs={"id": role.pk}))
        self.assertEqual(response.data["name"], role.name)

        # user without view permission can't see other role details
        new_role = Role.objects.create(name="Test Role")
        self.do_request("api:role-detail", kwargs={"id": new_role.pk}, code=404)

        # user with view permission can view other role details
        self.grant_perm_to_user("role.view")
        self.do_request("api:role-detail", kwargs={"id": new_role.pk}, code=200)

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
        self.assertEqual(Role.objects.count(), 17)
        self.assertEqual(Role.objects.get(name="Role").permissions.count(), 2)

    def test_delete(self) -> None:
        self.do_request(
            "api:role-detail",
            kwargs={"id": Role.objects.all()[0].pk},
            method="delete",
            superuser=True,
            code=204,
        )
        self.assertEqual(Role.objects.count(), 15)

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
    def attach_component_template(
        self, component: Component, filename: str = "template.pot"
    ) -> None:
        template_path = Path(component.full_path, filename)
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_bytes(Path(TEST_POT).read_bytes())
        component.template = filename
        component.save(update_fields=["template"])

    def attach_translation_file(
        self,
        component: Component,
        language_code: str = "cs",
        filename: str = "po/cs.po",
    ) -> Translation:
        language = Language.objects.get(code=language_code)
        translation, _ = Translation.objects.get_or_create(
            component=component, language=language
        )
        translation.filename = filename
        translation.save(update_fields=["filename"])

        translation_path = Path(component.full_path, filename)
        translation_path.parent.mkdir(parents=True, exist_ok=True)
        translation_path.write_bytes(Path(TEST_PO).read_bytes())
        return translation

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

    def test_repo_ops(self) -> None:
        for operation in RepoOperations.values:
            # No access for regular user
            self.do_request(
                "api:project-repository",
                self.project_kwargs,
                code=403,
                method="post",
                request={"operation": operation},
            )
            # Admin access
            self.do_request(
                "api:project-repository",
                self.project_kwargs,
                method="post",
                superuser=True,
                request={"operation": operation},
            )

    def test_repo_file_sync_returns_true(self) -> None:
        with patch.object(Component, "queue_background_task", return_value=None):
            response = self.do_request(
                "api:project-repository",
                self.project_kwargs,
                method="post",
                superuser=True,
                request={"operation": "file-sync"},
            )

        self.assertIs(response.data["result"], True)

    def test_project_lock_endpoint(self) -> None:
        """Test the dedicated project lock API endpoint."""
        # Test without authentication
        self.do_request("api:project-lock", self.project_kwargs, data={"locked": False})

        # Test without permissions
        self.do_request(
            "api:project-lock",
            self.project_kwargs,
            method="post",
            request={"lock": True},
            code=403,
        )

        self.authenticate(True)

        # Initially unlocked
        response = self.do_request("api:project-lock", self.project_kwargs)
        self.assertFalse(response.data["locked"])

        # Lock the project
        response = self.do_request(
            "api:project-lock",
            self.project_kwargs,
            method="post",
            request={"lock": True},
            superuser=True,
        )
        self.assertTrue(response.data["locked"])

        # Verify lock status persists
        response = self.do_request("api:project-lock", self.project_kwargs)
        self.assertTrue(response.data["locked"])

        # Unlock the project
        response = self.do_request(
            "api:project-lock",
            self.project_kwargs,
            method="post",
            request={"lock": False},
            superuser=True,
        )
        self.assertFalse(response.data["locked"])

        # Test invalid request
        self.do_request(
            "api:project-lock",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
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
            data={
                "needs_push": False,
                "needs_merge": False,
                "needs_commit": False,
                "weblate_commit": None,
                "status": None,
                "merge_failure": None,
                "outgoing_commits": None,
                "missing_commits": None,
                "remote_commit": None,
                "pending_units": {
                    "total": 0,
                    "errors_skipped": 0,
                    "commit_policy_skipped": 0,
                    "eligible_for_commit": 0,
                },
            },
            skip={"url"},
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

    def test_create_restricted_web(self) -> None:
        with override_settings(PROJECT_WEB_RESTRICT_HOST={"example.com"}):
            self.do_request(
                "api:project-list",
                method="post",
                code=400,
                superuser=True,
                request={
                    "name": "Blocked API project",
                    "slug": "blocked-api-project",
                    "web": "https://example.com/",
                },
            )

    def test_create_with_billing(self) -> None:
        with modify_settings(INSTALLED_APPS={"remove": "weblate.billing"}):
            response = self.do_request(
                "api:project-list",
                method="post",
                code=403,
                request={
                    "name": "API project",
                    "slug": "api-project",
                    "web": "https://weblate.org/",
                },
            )
            self.assertEqual(
                {
                    "errors": [
                        {
                            "attr": None,
                            "code": "permission_denied",
                            "detail": "Can not create projects",
                        }
                    ],
                    "type": "client_error",
                },
                response.data,
            )

        with modify_settings(INSTALLED_APPS={"prepend": "weblate.billing"}):
            response = self.do_request(
                "api:project-list",
                method="post",
                code=403,
                request={
                    "name": "API project",
                    "slug": "api-project",
                    "web": "https://weblate.org/",
                },
            )
            self.assertEqual(
                {
                    "errors": [
                        {
                            "attr": None,
                            "code": "permission_denied",
                            "detail": "No valid billing found or limit exceeded.",
                        }
                    ],
                    "type": "client_error",
                },
                response.data,
            )

            billing = create_test_billing(self.user, invoice=False)

            response = self.do_request(
                "api:project-list",
                method="post",
                code=201,
                request={
                    "name": "API project",
                    "slug": "api-project",
                    "web": "https://weblate.org/",
                },
            )
            project = Project.objects.get(pk=response.data["id"])
            self.assertEqual(project.billing, billing)

            response = self.do_request(
                "api:project-list",
                method="post",
                code=403,
                request={
                    "name": "API project 2",
                    "slug": "api-project-2",
                    "web": "https://weblate.org/",
                },
            )
            self.assertEqual(
                {
                    "errors": [
                        {
                            "attr": None,
                            "code": "permission_denied",
                            "detail": "No valid billing found or limit exceeded.",
                        }
                    ],
                    "type": "client_error",
                },
                response.data,
            )

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

    # pylint: disable-next=redefined-builtin
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

    def test_create_local_component(self) -> None:
        Component.objects.all().delete()
        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={
                "file_format": "tbx",
                "filemask": "*.tbx",
                "name": "Glossary",
                "new_lang": "add",
                "repo": "local:",
                "slug": "glossary",
                "vcs": "local",
            },
        )
        self.assertEqual(Component.objects.count(), 1)

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
        self.do_request(
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
            f"http://example.com{reverse('api:component-detail', kwargs=self.component_kwargs)}",
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
            f"http://example.com{reverse('api:component-detail', kwargs=self.component_kwargs)}",
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
                "file_format": "strings",
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
                "filemask": "*.ts",
                "template": "en.ts",
                "file_format": "ts",
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

    def test_patch_restricted_web(self) -> None:
        with override_settings(PROJECT_WEB_RESTRICT_HOST={"example.com"}):
            self.do_request(
                "api:project-detail",
                self.project_kwargs,
                method="patch",
                superuser=True,
                code=400,
                format="json",
                request={"web": "https://example.com/"},
            )

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

    @override_settings(FILE_UPLOAD_MAX_MEMORY_SIZE=1)
    def test_create_component_docfile_temporary_upload(self) -> None:
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
                    "slug": "local-project-temp",
                    "file_format": "html",
                    "new_lang": "add",
                    "edit_template": "0",
                },
            )
        self.assertEqual(response.data["repo"], "local:")
        self.assertEqual(response.data["filemask"], "local-project-temp/*.html")
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
        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            format="json",
            request={
                "docfile": Path(TEST_DOC).read_bytes(),
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
                "file_format": "strings",
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
                "file_format": "strings",
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
                "file_format": "strings",
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
                "file_format": "strings",
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
                "file_format": "strings",
                "new_lang": "none",
                "enforced_checks": ["same"],
            },
        )
        self.assertEqual(response.data["repo"], "local:")
        self.assertEqual(response.data["enforced_checks"], ["same"])
        self.assertEqual(Component.objects.count(), 3)
        component = Component.objects.get(slug="local-project")
        self.assertEqual(component.enforced_checks, ["same"])

    def test_create_component_with_file_format_params(self) -> None:
        payload = {
            "name": "API project",
            "slug": "api-project",
            "repo": self.format_local_path(self.git_repo_path),
            "filemask": "po/*.po",
            "file_format": "po",
            "push": "https://username:password@github.com/example/push.git",
            "new_lang": "none",
        }

        # attempt create with invalid params
        payload |= {"file_format_params": "not a dict"}
        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request=payload,
            format="json",
        )

        payload |= {"file_format_params": {"po_line_wrap": "invalid"}}
        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request=payload,
            format="json",
        )

        # attempt create with params that don't match format
        payload |= {
            "file_format_params": {"po_line_wrap": -1, "yaml_indent": 8},
        }
        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request=payload,
            format="json",
        )

        # attempt create with non-existing parameter
        payload["file_format_params"] = {"unknown_param_name": 1234}
        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            request=payload,
            format="json",
        )

        # create with valid params
        payload["file_format_params"] = {"po_line_wrap": -1}
        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            request=payload,
            format="json",
        )
        component = Component.objects.get(slug="api-project", project__slug="test")
        self.assertEqual(component.file_format_params["po_line_wrap"], -1)

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

    def test_download_project_translations_language_path(self) -> None:
        response = self.do_request(
            "api:project-language-file",
            {**self.project_kwargs, "language_code": "cs"},
            method="get",
            code=200,
            superuser=True,
            request={"format": "zip"},
        )
        self.assertEqual(response.headers["content-type"], "application/zip")
        # Validate Content-Disposition and that payload is a valid zip
        disp = response.headers.get("content-disposition", "")
        self.assertIn("attachment;", disp)
        self.assertIn("test-cs.zip", disp)
        with zipfile.ZipFile(BytesIO(response.content)) as zf:
            # Ensure archive contains at least one file
            self.assertGreater(len(zf.namelist()), 0)

    def test_download_project_translations_language_path_unsupported_format_suffix(
        self,
    ) -> None:
        self.do_request(
            "api:project-language-file",
            {**self.project_kwargs, "language_code": "cs", "format": "json"},
            method="get",
            code=404,
            superuser=True,
            request={"format": "zip"},
        )

    def test_download_project_translations_language_not_present(self) -> None:
        response = self.do_request(
            "api:project-language-file",
            {**self.project_kwargs, "language_code": "fr"},
            method="get",
            code=200,
            superuser=True,
            request={"format": "zip"},
        )
        self.assertEqual(response.headers["content-type"], "application/zip")
        with zipfile.ZipFile(BytesIO(response.content)) as zf:
            # No entries, since there are no translations for 'fr'
            self.assertEqual(len(zf.namelist()), 0)

    def test_download_project_translations_language_path_converted(self) -> None:
        response = self.do_request(
            "api:project-language-file",
            {**self.project_kwargs, "language_code": "cs"},
            method="get",
            code=200,
            superuser=True,
            request={"format": "zip:csv"},
        )
        self.assertEqual(response.headers["content-type"], "application/zip")

    def test_download_private_project_translations_language_path(self) -> None:
        project = self.component.project
        project.access_control = Project.ACCESS_PRIVATE
        project.save(update_fields=["access_control"])
        self.do_request(
            "api:project-language-file",
            {**self.project_kwargs, "language_code": "cs"},
            method="get",
            code=404,
            request={"format": "zip"},
        )

    def test_download_project_translations_language_path_prohibited(self) -> None:
        self.authenticate()
        self.user.groups.clear()
        self.user.clear_cache()
        self.do_request(
            "api:project-language-file",
            {**self.project_kwargs, "language_code": "cs"},
            method="get",
            code=403,
            request={"format": "zip"},
        )

    def test_project_language_zip_contents(self) -> None:
        self.attach_component_template(self.component)
        translation = self.attach_translation_file(self.component)
        other_component = self.create_po(name="Other", project=self.component.project)
        cs = Language.objects.get(code="cs")
        other_translation, _ = Translation.objects.get_or_create(
            component=other_component,
            language=cs,
        )
        other_translation.filename = ""
        other_translation.save(update_fields=["filename"])
        # Hit the "missing file" path for templates
        self.component.new_base = "missing-new-base.pot"
        self.component.save(update_fields=["new_base"])
        # Inspect actual entries in the zip and they match expectations
        response = self.do_request(
            "api:project-language-file",
            {**self.project_kwargs, "language_code": "cs"},
            method="get",
            code=200,
            superuser=True,
            request={"format": "zip"},
        )
        with zipfile.ZipFile(BytesIO(response.content)) as zf:
            zip_names = set(zf.namelist())

        root = data_dir("vcs")

        # Assert a few key entries
        translation_filename = translation.get_filename()
        self.assertIsNotNone(translation_filename)
        translation_rel = os.path.relpath(translation_filename, root)
        template_rel = os.path.relpath(
            os.path.join(self.component.full_path, self.component.template),
            root,
        )
        missing_new_base_rel = os.path.relpath(
            os.path.join(self.component.full_path, "missing-new-base.pot"),
            root,
        )

        self.assertIn(translation_rel, zip_names)
        self.assertIn(template_rel, zip_names)
        self.assertNotIn(missing_new_base_rel, zip_names)
        self.assertGreater(len(zip_names), 0)

    def test_project_language_zip_skips_symlinked_template(self) -> None:
        self.attach_component_template(self.component)
        template_path = os.path.join(self.component.full_path, self.component.template)

        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(b"outside repository")
        self.addCleanup(os.unlink, handle.name)

        os.unlink(template_path)
        os.symlink(handle.name, template_path)

        response = self.do_request(
            "api:project-language-file",
            {**self.project_kwargs, "language_code": "cs"},
            method="get",
            code=200,
            superuser=True,
            request={"format": "zip"},
        )
        with zipfile.ZipFile(BytesIO(response.content)) as zf:
            zip_names = set(zf.namelist())

        root = data_dir("vcs")
        translation_filename = self.component.translation_set.get(
            language__code="cs"
        ).get_filename()
        self.assertIsNotNone(translation_filename)
        translation_rel = os.path.relpath(translation_filename, root)
        template_rel = os.path.relpath(template_path, root)

        self.assertIn(translation_rel, zip_names)
        self.assertNotIn(template_rel, zip_names)

    def test_download_project_translations_language_path_filter(self) -> None:
        other_component = self.create_po(name="Other", project=self.component.project)
        self.attach_component_template(self.component)
        included_translation = self.attach_translation_file(self.component)
        excluded_translation = self.attach_translation_file(other_component)

        response = self.do_request(
            "api:project-language-file",
            {**self.project_kwargs, "language_code": "cs"},
            method="get",
            code=200,
            superuser=True,
            request={"format": "zip", "filter": "test"},
        )
        with zipfile.ZipFile(BytesIO(response.content)) as zf:
            zip_names = set(zf.namelist())

        root = data_dir("vcs")

        included_translation_filename = included_translation.get_filename()
        self.assertIsNotNone(included_translation_filename)
        included_translation_rel = os.path.relpath(included_translation_filename, root)
        included_template_rel = os.path.relpath(
            os.path.join(self.component.full_path, self.component.template),
            root,
        )
        excluded_translation_filename = excluded_translation.get_filename()
        self.assertIsNotNone(excluded_translation_filename)
        excluded_translation_rel = os.path.relpath(excluded_translation_filename, root)

        self.assertIn(included_translation_rel, zip_names)
        self.assertIn(included_template_rel, zip_names)
        self.assertNotIn(excluded_translation_rel, zip_names)
        self.assertGreater(len(zip_names), 0)

    @patch("weblate.api.views.ComponentSlugFilter")
    def test_download_project_translations_language_path_filter_invalid(
        self, filter_class
    ) -> None:
        filter_instance = filter_class.return_value
        filter_instance.is_valid.return_value = False
        filter_instance.errors = {"filter": ["invalid"]}

        response = self.do_request(
            "api:project-language-file",
            {**self.project_kwargs, "language_code": "cs"},
            method="get",
            code=400,
            superuser=True,
            request={"format": "zip", "filter": "["},
        )

        filter_instance.is_valid.assert_called_once()
        self.assertEqual(response.status_code, 400)

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
        # Deep import to avoid running these as tests
        from weblate.machinery.tests import (  # noqa: PLC0415
            AlibabaTranslationTest,
            DeepLTranslationTest,
        )

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

    def test_install_machinery_blocks_private_project_target(self) -> None:
        self.component.project.add_user(self.user, "Administration")

        response = self.do_request(
            "api:project-machinery-settings",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=False,
            request={
                "service": "deepl",
                "configuration": {"key": "x", "url": "http://127.0.0.1:11434/"},
            },
            format="json",
        )

        self.assertIn("internal or non-public address", str(response.data))


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

    def test_get_component_uses_effective_linked_repository_settings(self) -> None:
        self.component.push_on_commit = True
        self.component.commit_pending_age = 12
        self.component.auto_lock_error = False
        self.component.save(
            update_fields=[
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )
        linked_component = self.create_link_existing(
            name="API linked settings", slug="api-linked-settings"
        )
        linked_component.push_on_commit = False
        linked_component.commit_pending_age = 1
        linked_component.auto_lock_error = True
        linked_component.save(
            update_fields=[
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )

        response = self.client.get(
            reverse(
                "api:component-detail",
                kwargs={
                    "project__slug": linked_component.project.slug,
                    "slug": linked_component.slug,
                },
            )
        )

        self.assertEqual(response.data["push_on_commit"], True)
        self.assertEqual(response.data["commit_pending_age"], 12)
        self.assertEqual(response.data["auto_lock_error"], False)

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
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)

    def test_repo_status_denied(self) -> None:
        self.do_request("api:component-repository", self.component_kwargs, code=403)

    def test_repo_status(self) -> None:
        """Test basic component repository status endpoint."""
        response = self.do_request(
            "api:component-repository",
            self.component_kwargs,
            superuser=True,
        )

        self.assertEqual(response.data["needs_push"], False)
        self.assertEqual(response.data["needs_merge"], False)
        self.assertEqual(response.data["needs_commit"], False)
        self.assertEqual(response.data["merge_failure"], None)

        self.assertIn("url", response.data)
        self.assertIn("status", response.data)
        self.assertIn("remote_commit", response.data)
        self.assertIn("weblate_commit", response.data)
        self.assertIn("pending_units", response.data)
        self.assertIn("outgoing_commits", response.data)
        self.assertIn("missing_commits", response.data)

        self.assertIsNotNone(response.data["url"])
        self.assertIsNotNone(response.data["status"])

        self.assertIsInstance(response.data["outgoing_commits"], int)
        self.assertIsInstance(response.data["missing_commits"], int)

        pending = response.data["pending_units"]
        self.assertIsNotNone(pending)
        self.assertEqual(pending["total"], 0)

    def test_repo_status_detailed(self) -> None:
        """Test component repository status with detailed field verification."""
        response = self.do_request(
            "api:component-repository",
            self.component_kwargs,
            superuser=True,
        )

        self.assertIn("needs_commit", response.data)
        self.assertIn("needs_merge", response.data)
        self.assertIn("needs_push", response.data)
        self.assertIn("url", response.data)
        self.assertIn("status", response.data)
        self.assertIn("merge_failure", response.data)

        self.assertIn("pending_units", response.data)
        self.assertIn("outgoing_commits", response.data)
        self.assertIn("missing_commits", response.data)

        self.assertIn("remote_commit", response.data)
        self.assertIn("weblate_commit", response.data)

        if response.data["remote_commit"]:
            commit = response.data["remote_commit"]
            self.assertIn("revision", commit)
            self.assertIn("shortrevision", commit)
            self.assertIn("author", commit)
            self.assertIn("message", commit)
            self.assertIn("summary", commit)

        self.assertIsInstance(response.data["outgoing_commits"], int)
        self.assertIsInstance(response.data["missing_commits"], int)

    def test_repo_status_with_pending_changes(self) -> None:
        """Test repository status with pending changes and detailed breakdown."""
        component = Component.objects.get(**self.component_kwargs)
        translation = component.translation_set.first()
        unit, unit2 = translation.unit_set.all()[:2]

        unit.translate(self.user, "First change", STATE_TRANSLATED)
        unit2.translate(self.user, "Second change", STATE_TRANSLATED)

        response = self.do_request(
            "api:component-repository",
            self.component_kwargs,
            superuser=True,
        )

        self.assertEqual(response.data["needs_commit"], True)
        self.assertIsNotNone(response.data["pending_units"])

        pending = response.data["pending_units"]
        self.assertIn("total", pending)
        self.assertIn("errors_skipped", pending)
        self.assertIn("commit_policy_skipped", pending)
        self.assertIn("eligible_for_commit", pending)

        self.assertGreaterEqual(pending["total"], 2)
        self.assertGreater(pending["eligible_for_commit"], 0)

    def test_repo_file_sync_returns_true(self) -> None:
        with patch.object(Component, "queue_background_task", return_value=None):
            response = self.do_request(
                "api:component-repository",
                self.component_kwargs,
                superuser=True,
                method="post",
                request={"operation": "file-sync"},
            )

        self.assertIs(response.data["result"], True)

    def test_repo_operation_error_is_sanitized(self) -> None:
        repository_error = RepositoryError(
            128,
            (
                "fatal: unable to access "
                "'ssh://git@internal.example.net/private/repo.git': "
                "Could not resolve host: internal.example.net\n"
                f"{self.component.full_path}/.git/index.lock"
            ),
        )
        with (
            patch.object(Component, "repo_needs_push", return_value=True),
            patch.object(Component, "do_update", return_value=True),
            patch.object(Component, "repo_needs_merge", return_value=False),
            patch.object(
                self.component.repository.__class__,
                "push",
                side_effect=repository_error,
            ),
        ):
            response = self.do_request(
                "api:component-repository",
                self.component_kwargs,
                superuser=True,
                method="post",
                request={"operation": "push"},
            )

        self.assertEqual(response.data["result"], False)
        self.assertIn("Could not push", response.data["detail"])
        self.assertNotIn("internal.example.net", response.data["detail"])
        self.assertNotIn(self.component.full_path, response.data["detail"])
        self.assertIn(".../.git/index.lock", response.data["detail"])

    def test_statistics(self) -> None:
        self.do_request(
            "api:component-statistics",
            self.component_kwargs,
            data={"count": 4},
            skip={"results", "previous", "next"},
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

    def test_patch_locks_component_before_serializer_validation(self) -> None:
        events: list[tuple[str, int]] = []
        original_get_for_update = ComponentQuerySet.get_for_update
        original_is_valid = ComponentSerializer.is_valid

        def record_get_for_update(*args, **kwargs):
            events.append(("lock", kwargs["pk"]))
            return original_get_for_update(*args, **kwargs)

        def record_is_valid(*args, **kwargs):
            events.append(("is_valid", args[0].instance.pk))
            return original_is_valid(*args, **kwargs)

        with (
            patch.object(
                ComponentQuerySet,
                "get_for_update",
                autospec=True,
                side_effect=record_get_for_update,
            ),
            patch.object(
                ComponentSerializer,
                "is_valid",
                autospec=True,
                side_effect=record_is_valid,
            ),
        ):
            response = self.do_request(
                "api:component-detail",
                self.component_kwargs,
                method="patch",
                superuser=True,
                code=200,
                format="json",
                request={"name": "Locked API Name"},
            )

        self.assertEqual(response.data["name"], "Locked API Name")
        lock_index = events.index(("lock", self.component.pk))
        is_valid_index = events.index(("is_valid", self.component.pk))
        self.assertLess(
            lock_index,
            is_valid_index,
            "Component row should be locked before serializer validation runs",
        )

    def test_patch_acquires_repository_lock_before_row_lock(self) -> None:
        events: list[tuple[str, int]] = []
        original_lock_enter = RepositoryLock.__enter__
        original_get_for_update = ComponentQuerySet.get_for_update

        def record_lock_enter(lock):
            component = lock.repository.component
            if component is not None:
                events.append(("repo_lock", component.pk))
            return original_lock_enter(lock)

        def record_get_for_update(*args, **kwargs):
            events.append(("row_lock", kwargs["pk"]))
            return original_get_for_update(*args, **kwargs)

        with (
            patch.object(
                RepositoryLock,
                "__enter__",
                autospec=True,
                side_effect=record_lock_enter,
            ),
            patch.object(
                ComponentQuerySet,
                "get_for_update",
                autospec=True,
                side_effect=record_get_for_update,
            ),
        ):
            response = self.do_request(
                "api:component-detail",
                self.component_kwargs,
                method="patch",
                superuser=True,
                code=200,
                format="json",
                request={"name": "Repo Locked API Name"},
            )

        self.assertEqual(response.data["name"], "Repo Locked API Name")
        self.assertLess(
            events.index(("repo_lock", self.component.pk)),
            events.index(("row_lock", self.component.pk)),
            "Component repository lock should be acquired before the row lock",
        )

    def test_patch_sets_acting_user_before_serializer_validation(self) -> None:
        original_clean = Component.clean

        def record_clean(instance):
            self.assertEqual(instance.acting_user, self.user)
            return original_clean(instance)

        with patch.object(
            Component,
            "clean",
            autospec=True,
            side_effect=record_clean,
        ):
            response = self.do_request(
                "api:component-detail",
                self.component_kwargs,
                method="patch",
                superuser=True,
                code=200,
                format="json",
                request={"name": "Validation User Name"},
            )

        self.assertEqual(response.data["name"], "Validation User Name")

    def test_patch_rejects_linked_repository_setting_override(self) -> None:
        linked_setting_error = (
            "Option is not available for linked repositories. "
            "Setting from linked component will be used."
        )
        self.component.push_on_commit = True
        self.component.commit_pending_age = 12
        self.component.auto_lock_error = False
        self.component.save(
            update_fields=[
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )
        linked_component = self.create_link_existing(
            name="API linked patch", slug="api-linked-patch"
        )
        linked_kwargs = {
            "project__slug": linked_component.project.slug,
            "slug": linked_component.slug,
        }

        response = self.do_request(
            "api:component-detail",
            linked_kwargs,
            method="patch",
            superuser=True,
            code=400,
            format="json",
            request={
                "push_on_commit": False,
                "commit_pending_age": 1,
                "auto_lock_error": True,
            },
        )

        self.assertEqual(
            {(error["attr"], error["detail"]) for error in response.data["errors"]},
            {
                (
                    "push_on_commit",
                    linked_setting_error,
                ),
                (
                    "commit_pending_age",
                    linked_setting_error,
                ),
                (
                    "auto_lock_error",
                    linked_setting_error,
                ),
            },
        )

    def test_put(self) -> None:
        self.do_request(
            "api:component-detail", self.component_kwargs, method="put", code=403
        )
        component = self.client.get(
            reverse("api:component-detail", kwargs=self.component_kwargs), format="json"
        ).json()
        component["name"] = "New Name"

        # put invalid parameter
        component["file_format_params"] = {"yaml_indent": 8}
        response = self.do_request(
            "api:component-detail",
            self.component_kwargs,
            method="put",
            superuser=True,
            code=400,
            format="json",
            request=component,
        )
        self.component.refresh_from_db()
        self.assertNotIn("yaml_indent", self.component.file_format_params)

        # put valid parameter
        component["file_format_params"] = {"po_line_wrap": -1}
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
        self.assertEqual(response.data["file_format_params"]["po_line_wrap"], -1)

    def test_patch_linked_component_keeps_local_repository_setting_drift(self) -> None:
        self.component.push_on_commit = True
        self.component.commit_pending_age = 12
        self.component.auto_lock_error = False
        self.component.save(
            update_fields=[
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )
        linked_component = self.create_link_existing(
            name="API linked put", slug="api-linked-put", filemask="po/*.po"
        )
        linked_component.push_on_commit = False
        linked_component.commit_pending_age = 1
        linked_component.auto_lock_error = True
        linked_component.save(
            update_fields=[
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )
        linked_kwargs = {
            "project__slug": linked_component.project.slug,
            "slug": linked_component.slug,
        }
        response = self.do_request(
            "api:component-detail",
            linked_kwargs,
            method="patch",
            superuser=True,
            code=200,
            format="json",
            request={
                "name": "API linked put renamed",
                "push_on_commit": True,
                "commit_pending_age": 12,
                "auto_lock_error": False,
            },
        )

        linked_component.refresh_from_db()
        self.assertEqual(linked_component.name, "API linked put renamed")
        self.assertFalse(linked_component.push_on_commit)
        self.assertEqual(linked_component.commit_pending_age, 1)
        self.assertTrue(linked_component.auto_lock_error)
        self.assertEqual(response.data["push_on_commit"], True)
        self.assertEqual(response.data["commit_pending_age"], 12)
        self.assertEqual(response.data["auto_lock_error"], False)

    def test_patch_linked_component_can_unlink_with_repository_settings(self) -> None:
        self.component.push_on_commit = True
        self.component.commit_pending_age = 12
        self.component.auto_lock_error = False
        self.component.save(
            update_fields=[
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )
        linked_component = self.create_link_existing(
            name="API linked unlink", slug="api-linked-unlink", filemask="po/*.po"
        )
        linked_kwargs = {
            "project__slug": linked_component.project.slug,
            "slug": linked_component.slug,
        }

        response = self.do_request(
            "api:component-detail",
            linked_kwargs,
            method="patch",
            superuser=True,
            code=200,
            format="json",
            request={
                "repo": self.component.repo,
                "branch": self.component.branch,
                "push": self.component.push,
                "push_on_commit": False,
                "commit_pending_age": 3,
                "auto_lock_error": True,
            },
        )

        linked_component.refresh_from_db()
        self.assertIsNone(linked_component.linked_component_id)
        self.assertEqual(linked_component.repo, self.component.repo)
        self.assertEqual(linked_component.branch, self.component.branch)
        self.assertEqual(linked_component.push, self.component.push)
        self.assertFalse(linked_component.push_on_commit)
        self.assertEqual(linked_component.commit_pending_age, 3)
        self.assertTrue(linked_component.auto_lock_error)
        self.assertEqual(response.data["push_on_commit"], False)
        self.assertEqual(response.data["commit_pending_age"], 3)
        self.assertEqual(response.data["auto_lock_error"], True)

    def test_patch_can_switch_to_link_with_drifting_settings(self) -> None:
        self.component.push_on_commit = True
        self.component.commit_pending_age = 12
        self.component.auto_lock_error = False
        self.component.save(
            update_fields=[
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )
        parent = self.create_po(name="API link target", project=self.project)
        parent.push_on_commit = False
        parent.commit_pending_age = 3
        parent.auto_lock_error = True
        parent.save(
            update_fields=[
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )

        response = self.do_request(
            "api:component-detail",
            self.component_kwargs,
            method="patch",
            superuser=True,
            code=200,
            format="json",
            request={
                "repo": parent.get_repo_link_url(),
                "branch": "",
                "push": "",
                "push_branch": "",
                "push_on_commit": True,
                "commit_pending_age": 12,
                "auto_lock_error": False,
            },
        )

        self.component.refresh_from_db()
        self.assertTrue(self.component.is_repo_link)
        self.assertEqual(self.component.linked_component, parent)
        self.assertEqual(self.component.push_on_commit, True)
        self.assertEqual(self.component.commit_pending_age, 12)
        self.assertEqual(self.component.auto_lock_error, False)
        self.assertEqual(response.data["push_on_commit"], False)
        self.assertEqual(response.data["commit_pending_age"], 3)
        self.assertEqual(response.data["auto_lock_error"], True)

    def test_patch_linked_component_can_switch_parent_with_matching_settings(
        self,
    ) -> None:
        self.component.push_on_commit = True
        self.component.commit_pending_age = 12
        self.component.auto_lock_error = False
        self.component.save(
            update_fields=[
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )
        new_parent = self.create_po(name="api-linked-target", project=self.project)
        new_parent.push_on_commit = False
        new_parent.commit_pending_age = 3
        new_parent.auto_lock_error = True
        new_parent.save(
            update_fields=[
                "push_on_commit",
                "commit_pending_age",
                "auto_lock_error",
            ]
        )
        linked_component = self.create_link_existing(
            name="API linked switch", slug="api-linked-switch", filemask="po/*.po"
        )
        linked_kwargs = {
            "project__slug": linked_component.project.slug,
            "slug": linked_component.slug,
        }

        response = self.do_request(
            "api:component-detail",
            linked_kwargs,
            method="patch",
            superuser=True,
            code=200,
            format="json",
            request={
                "repo": new_parent.get_repo_link_url(),
                "push_on_commit": False,
                "commit_pending_age": 3,
                "auto_lock_error": True,
            },
        )

        linked_component.refresh_from_db()
        self.assertEqual(linked_component.linked_component_id, new_parent.pk)
        self.assertEqual(response.data["push_on_commit"], False)
        self.assertEqual(response.data["commit_pending_age"], 3)
        self.assertEqual(response.data["auto_lock_error"], True)

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

    def test_create_component_from_component_id(self) -> None:
        translation = self.component.translation_set.get(language_code="cs")
        unit = translation.unit_set.get(source="Hello, world!\n")
        unit.translate(self.user, "Duplicated from source!\n", STATE_TRANSLATED)
        self.component.commit_message = "Commit from source"
        self.component.priority = 175
        self.component.save()
        self.component.addon_set.create(name="weblate.gettext.linguas")

        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            format="json",
            request={
                "name": "API copy",
                "slug": "api-copy",
                "priority": 120,
                "from_component": self.component.pk,
            },
        )

        duplicate = Component.objects.get(slug="api-copy", project__slug="test")
        self.assertEqual(duplicate.repo, "local:")
        self.assertEqual(duplicate.vcs, "local")
        self.assertEqual(duplicate.filemask, self.component.filemask)
        self.assertEqual(duplicate.file_format, self.component.file_format)
        self.assertEqual(duplicate.new_lang, self.component.new_lang)
        self.assertEqual(duplicate.commit_message, "Commit from source")
        self.assertEqual(duplicate.priority, 120)
        self.assertTrue(
            duplicate.addon_set.filter(name="weblate.gettext.linguas").exists()
        )
        duplicated_translation = duplicate.translation_set.get(language_code="cs")
        duplicated_unit = duplicated_translation.unit_set.get(source="Hello, world!\n")
        self.assertEqual(duplicated_unit.target, "Duplicated from source!\n")

    def test_create_component_from_component_path(self) -> None:
        category = self.component.project.category_set.create(
            name="Category", slug="category"
        )
        source = self.create_po(
            name="source-category", project=self.component.project, category=category
        )
        source.commit_message = "Path copy commit"
        source.save()

        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            format="json",
            request={
                "name": "API copy path",
                "slug": "api-copy-path",
                "from_component": source.full_slug,
            },
        )

        duplicate = Component.objects.get(slug="api-copy-path", project__slug="test")
        self.assertEqual(duplicate.category, category)
        self.assertEqual(duplicate.repo, "local:")
        self.assertEqual(duplicate.vcs, "local")
        self.assertEqual(duplicate.filemask, source.filemask)
        self.assertEqual(duplicate.file_format, source.file_format)
        self.assertEqual(duplicate.commit_message, "Path copy commit")

    def test_create_component_from_component_cross_project_keeps_current_translations(
        self,
    ) -> None:
        source_project = self.create_project(
            name="Source project",
            slug="source-project",
            contribute_shared_tm=False,
        )
        source = self.create_po(name="source-cross-project", project=source_project)
        translation = source.translation_set.get(language_code="cs")
        unit = translation.unit_set.get(source="Hello, world!\n")
        unit.translate(
            self.user, "Cross-project current translation!\n", STATE_TRANSLATED
        )

        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            format="json",
            request={
                "name": "API copy cross project",
                "slug": "api-copy-cross-project",
                "from_component": source.pk,
            },
        )

        duplicate = Component.objects.get(
            slug="api-copy-cross-project", project__slug=self.component.project.slug
        )
        duplicated_translation = duplicate.translation_set.get(language_code="cs")
        duplicated_unit = duplicated_translation.unit_set.get(source="Hello, world!\n")
        self.assertEqual(duplicated_unit.target, "Cross-project current translation!\n")

    def test_create_component_from_component_rejects_repo_overrides(self) -> None:
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            format="json",
            request={
                "name": "API copy explicit repo",
                "slug": "api-copy-explicit-repo",
                "from_component": self.component.pk,
                "repo": self.component.repo,
                "branch": "release",
            },
        )

        self.assertEqual(
            response.data,
            {
                "type": "validation_error",
                "errors": [
                    {
                        "code": "invalid",
                        "detail": "This field can not be used when using from_component.",
                        "attr": "branch",
                    },
                    {
                        "code": "invalid",
                        "detail": "This field can not be used when using from_component.",
                        "attr": "repo",
                    },
                ],
            },
        )

    def test_create_component_from_component_rejects_layout_override(self) -> None:
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            format="json",
            request={
                "name": "API copy invalid override",
                "slug": "api-copy-invalid-override",
                "from_component": self.component.pk,
                "filemask": "translations/*.po",
            },
        )

        self.assertEqual(
            response.data,
            {
                "type": "validation_error",
                "errors": [
                    {
                        "code": "invalid",
                        "detail": (
                            "This field can not be overridden when using "
                            "from_component."
                        ),
                        "attr": "filemask",
                    }
                ],
            },
        )

    def test_create_component_from_component_rejects_branch_override(self) -> None:
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            format="json",
            request={
                "name": "API copy invalid branch",
                "slug": "api-copy-invalid-branch",
                "from_component": self.component.pk,
                "branch": "release",
            },
        )

        self.assertEqual(
            response.data,
            {
                "type": "validation_error",
                "errors": [
                    {
                        "code": "invalid",
                        "detail": "This field can not be used when using from_component.",
                        "attr": "branch",
                    }
                ],
            },
        )

    def test_create_component_from_component_without_repo_skips_source_repo_validation(
        self,
    ) -> None:
        Component.objects.filter(pk=self.component.pk).update(
            repo="https://example.invalid/missing.git"
        )
        self.component.refresh_from_db()

        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            format="json",
            request={
                "name": "API copy local snapshot",
                "slug": "api-copy-local-snapshot",
                "from_component": self.component.pk,
            },
        )

        duplicate = Component.objects.get(
            slug="api-copy-local-snapshot", project__slug=self.component.project.slug
        )
        self.assertEqual(duplicate.repo, "local:")
        self.assertTrue(duplicate.translation_set.filter(language_code="cs").exists())

    def test_create_component_from_component_requires_available_source_checkout(
        self,
    ) -> None:
        with patch("weblate.api.serializers.os.path.isdir") as isdir:
            isdir.side_effect = lambda path: path != self.component.full_path
            self.do_request(
                "api:project-components",
                self.project_kwargs,
                method="post",
                code=400,
                superuser=True,
                format="json",
                request={
                    "name": "API copy missing checkout",
                    "slug": "api-copy-missing-checkout",
                    "from_component": self.component.pk,
                },
            )

    def test_create_component_from_component_validates_suggestion_settings(
        self,
    ) -> None:
        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            format="json",
            request={
                "name": "API copy invalid suggestions",
                "slug": "api-copy-invalid-suggestions",
                "from_component": self.component.pk,
                "suggestion_voting": False,
                "suggestion_autoaccept": 2,
            },
        )

        self.assertEqual(
            response.data["errors"],
            [
                {
                    "attr": "suggestion_autoaccept",
                    "code": "invalid",
                    "detail": "Accepting suggestions automatically only works with voting turned on.",
                },
                {
                    "attr": "suggestion_voting",
                    "code": "invalid",
                    "detail": "Accepting suggestions automatically only works with voting turned on.",
                },
            ],
        )

    def test_create_component_from_component_validates_new_lang_against_source(
        self,
    ) -> None:
        source = self.create_po(
            name="source-no-new-base", project=self.component.project
        )

        response = self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=400,
            superuser=True,
            format="json",
            request={
                "name": "API copy invalid new lang",
                "slug": "api-copy-invalid-new-lang",
                "from_component": source.pk,
                "new_lang": "add",
            },
        )

        self.assertEqual(
            response.data["errors"],
            [
                {
                    "attr": "new_base",
                    "code": "invalid",
                    "detail": (
                        "You have set up Weblate to add new translation files, "
                        "but did not provide a base file to do that."
                    ),
                },
                {
                    "attr": "new_lang",
                    "code": "invalid",
                    "detail": (
                        "You have set up Weblate to add new translation files, "
                        "but did not provide a base file to do that."
                    ),
                },
            ],
        )

    def test_create_component_from_component_appstore(self) -> None:
        source = self.create_appstore(
            name="source-appstore", project=self.component.project
        )
        source_translation = source.translation_set.get(language_code="cs")
        source_unit = source_translation.unit_set.get(
            source="Weblate - continuous localization"
        )
        source_unit.translate(
            self.user, "Weblate - metadata duplicate", STATE_TRANSLATED
        )

        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            format="json",
            request={
                "name": "API copy appstore",
                "slug": "api-copy-appstore",
                "from_component": source.pk,
            },
        )

        duplicate = Component.objects.get(
            slug="api-copy-appstore", project__slug=self.component.project.slug
        )
        duplicated_translation = duplicate.translation_set.get(language_code="cs")
        duplicated_unit = duplicated_translation.unit_set.get(
            source="Weblate - continuous localization"
        )
        self.assertEqual(duplicated_unit.target, "Weblate - metadata duplicate")
        self.assertGreater(len(source_translation.filenames), 1)
        duplicate_files = {
            os.path.relpath(filename, duplicate.full_path)
            for filename in duplicated_translation.filenames
        }
        self.assertTrue(
            {
                os.path.relpath(filename, source.full_path)
                for filename in source_translation.filenames
            }.issubset(duplicate_files)
        )

    def test_create_component_from_component_does_not_clone_addons_cross_project(
        self,
    ) -> None:
        source_project = self.create_project(name="Source", slug="source")
        source = self.create_po(name="source-copy", project=source_project)
        source.addon_set.create(
            name="weblate.gettext.linguas",
            configuration={"secret": "cross-project"},
        )

        self.do_request(
            "api:project-components",
            self.project_kwargs,
            method="post",
            code=201,
            superuser=True,
            format="json",
            request={
                "name": "API copy no addons",
                "slug": "api-copy-no-addons",
                "from_component": source.pk,
            },
        )

        duplicate = Component.objects.get(
            slug="api-copy-no-addons", project__slug=self.component.project.slug
        )
        self.assertFalse(
            duplicate.addon_set.filter(name="weblate.gettext.linguas").exists()
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_create_component_from_component_queues_seed(self) -> None:
        with (
            patch(
                "weblate.trans.tasks.component_after_save.delay",
                return_value=SimpleNamespace(id="component-task"),
            ) as delay,
            patch(
                "weblate.trans.models.component.AsyncResult",
                return_value=SimpleNamespace(id="component-task", ready=lambda: False),
            ),
        ):
            self.do_request(
                "api:project-components",
                self.project_kwargs,
                method="post",
                code=201,
                superuser=True,
                format="json",
                request={
                    "name": "API copy async",
                    "slug": "api-copy-async",
                    "from_component": self.component.pk,
                },
            )

        self.assertEqual(delay.call_count, 1)
        self.assertEqual(
            delay.call_args.args[0],
            Component.objects.get(slug="api-copy-async").pk,
        )
        self.assertEqual(
            delay.call_args.kwargs["seed_source_component_id"], self.component.pk
        )
        self.assertTrue(delay.call_args.kwargs["copy_seed_addons"])
        self.assertEqual(
            delay.call_args.kwargs["seed_author"], self.user.get_author_name()
        )
        self.assertTrue(delay.call_args.kwargs["skip_push"])

    def test_create_component_from_component_seed_uses_skip_push(self) -> None:
        duplicate = Component.objects.create(
            project=self.component.project,
            name="API copy seeded",
            slug="api-copy-seeded",
            vcs="local",
            repo="local:",
            filemask=self.component.filemask,
            file_format=self.component.file_format,
        )

        with patch(
            "weblate.trans.component_copy.seed_component_from_source"
        ) as seed_component_from_source:
            duplicate.after_save(
                changed_git=False,
                changed_setup=False,
                changed_template=False,
                changed_variant=False,
                changed_enforced_checks=False,
                skip_push=True,
                create=True,
                seed_source_component_id=self.component.pk,
                copy_seed_addons=False,
                seed_author=self.user.get_author_name(),
            )

        seed_component_from_source.assert_called_once_with(
            duplicate,
            self.component,
            author_name=self.user.get_author_name(),
            skip_push=True,
        )

    def test_create_component_from_component_falls_back_to_scan_when_seed_empty(
        self,
    ) -> None:
        duplicate = Component.objects.create(
            project=self.component.project,
            name="API copy empty seed",
            slug="api-copy-empty-seed",
            vcs="local",
            repo="local:",
            filemask=self.component.filemask,
            file_format=self.component.file_format,
        )

        with (
            patch.object(duplicate, "create_translations") as create_translations,
            patch(
                "weblate.trans.component_copy.seed_component_from_source",
                return_value=False,
            ) as seed_component_from_source,
        ):
            duplicate.after_save(
                changed_git=False,
                changed_setup=True,
                changed_template=False,
                changed_variant=False,
                changed_enforced_checks=False,
                skip_push=True,
                create=True,
                seed_source_component_id=self.component.pk,
                copy_seed_addons=False,
                seed_author=self.user.get_author_name(),
            )

        create_translations.assert_called_once_with(force=True, changed_template=False)
        seed_component_from_source.assert_called_once_with(
            duplicate,
            self.component,
            author_name=self.user.get_author_name(),
            skip_push=True,
        )

    def test_create_component_from_component_skips_initial_translation_scan(
        self,
    ) -> None:
        duplicate = Component.objects.create(
            project=self.component.project,
            name="API copy one scan",
            slug="api-copy-one-scan",
            vcs="local",
            repo="local:",
            filemask=self.component.filemask,
            file_format=self.component.file_format,
        )

        with (
            patch.object(duplicate, "create_translations") as create_translations,
            patch(
                "weblate.trans.component_copy.seed_component_from_source"
            ) as seed_component_from_source,
        ):
            duplicate.after_save(
                changed_git=False,
                changed_setup=True,
                changed_template=False,
                changed_variant=False,
                changed_enforced_checks=False,
                skip_push=True,
                create=True,
                seed_source_component_id=self.component.pk,
                copy_seed_addons=False,
                seed_author=self.user.get_author_name(),
            )

        create_translations.assert_not_called()
        seed_component_from_source.assert_called_once_with(
            duplicate,
            self.component,
            author_name=self.user.get_author_name(),
            skip_push=True,
        )

    def test_create_component_from_component_missing_source_falls_back_to_scan(
        self,
    ) -> None:
        duplicate = Component.objects.create(
            project=self.component.project,
            name="API copy missing source",
            slug="api-copy-missing-source",
            vcs="local",
            repo="local:",
            filemask=self.component.filemask,
            file_format=self.component.file_format,
        )

        with (
            patch.object(
                duplicate,
                "create_seed_fallback_translations",
                return_value=True,
            ) as create_seed_fallback_translations,
            patch(
                "weblate.trans.component_copy.seed_component_from_source"
            ) as seed_component_from_source,
            patch(
                "weblate.trans.component_copy.clone_component_addons"
            ) as clone_component_addons,
            patch.object(duplicate, "log_warning") as log_warning,
        ):
            duplicate.after_save(
                changed_git=False,
                changed_setup=True,
                changed_template=False,
                changed_variant=False,
                changed_enforced_checks=False,
                skip_push=True,
                create=True,
                seed_source_component_id=999999,
                copy_seed_addons=True,
                seed_author=self.user.get_author_name(),
            )

        seed_component_from_source.assert_not_called()
        clone_component_addons.assert_not_called()
        create_seed_fallback_translations.assert_called_once_with(
            changed_setup=True,
            changed_git=False,
            changed_template=False,
        )
        log_warning.assert_called_once_with(
            "source component %s is no longer available, falling back to discovery",
            999999,
        )

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

    def test_create_translation_from_component(self) -> None:
        target = self.create_po_new_base(name="target", project=self.component.project)
        source_project_one = self.create_project(
            name="Source one", slug="source-one", contribute_shared_tm=True
        )
        source_project_two = self.create_project(
            name="Source two", slug="source-two", contribute_shared_tm=True
        )
        source_one = self.create_po_new_base(
            name="source-one", project=source_project_one
        )
        source_two = self.create_po_new_base(
            name="source-two", project=source_project_two
        )
        language = Language.objects.get(code="fa")
        fallback_source: str | None = None

        for component, text in (
            (source_one, "First source translation!\n"),
            (source_two, "Second source translation!\n"),
        ):
            translation = component.add_new_language(language, None)
            self.assertIsNotNone(translation)
            if component == source_one:
                unit = translation.unit_set.get(source="Hello, world!\n")
            else:
                unit = next(
                    candidate
                    for candidate in translation.unit_set.exclude(
                        source="Hello, world!\n"
                    )
                    if not candidate.is_plural
                )
            unit.translate(self.user, text, STATE_TRANSLATED)
            if component == source_two:
                fallback_source = unit.source

        self.do_request(
            "api:component-translations",
            {"project__slug": target.project.slug, "slug": target.slug},
            method="post",
            code=201,
            superuser=True,
            format="json",
            request={
                "language_code": "fa",
                "from_component": [source_one.full_slug, str(source_two.pk)],
            },
        )

        self.assertIsNotNone(fallback_source)
        created = target.translation_set.get(language_code="fa")
        first_unit = created.unit_set.get(source="Hello, world!\n")
        second_unit = created.unit_set.get(source=fallback_source)
        self.assertEqual(first_unit.target, "First source translation!\n")
        self.assertEqual(second_unit.target.rstrip("\n"), "Second source translation!")

    def test_create_translation_from_component_duplicates(self) -> None:
        target = self.create_po_new_base(name="target", project=self.component.project)
        source = self.create_po_new_base(name="source", project=self.component.project)
        language = Language.objects.get(code="fa")

        translation = source.add_new_language(language, None)
        self.assertIsNotNone(translation)
        unit = translation.unit_set.get(source="Hello, world!\n")
        unit.translate(self.user, "Duplicated source translation!\n", STATE_TRANSLATED)

        self.do_request(
            "api:component-translations",
            {"project__slug": target.project.slug, "slug": target.slug},
            method="post",
            code=201,
            superuser=True,
            format="json",
            request={
                "language_code": "fa",
                "from_component": [source.full_slug, source.full_slug],
            },
        )

        created = target.translation_set.get(language_code="fa")
        created_unit = created.unit_set.get(source="Hello, world!\n")
        self.assertEqual(created_unit.target, "Duplicated source translation!\n")

    def test_create_translation_from_component_language_code_style(self) -> None:
        target = self.create_po_new_base(name="target", project=self.component.project)
        source = self.create_po_new_base(
            name="source-style",
            project=self.component.project,
            language_code_style="bcp",
        )
        language = Language.objects.get(code="pt_BR")

        translation = source.add_new_language(language, None)
        self.assertIsNotNone(translation)
        self.assertEqual(translation.language.code, "pt_BR")
        self.assertEqual(translation.language_code, "pt-BR")
        unit = translation.unit_set.get(source="Hello, world!\n")
        unit.translate(self.user, "Styled source translation!\n", STATE_TRANSLATED)

        self.do_request(
            "api:component-translations",
            {"project__slug": target.project.slug, "slug": target.slug},
            method="post",
            code=201,
            superuser=True,
            format="json",
            request={
                "language_code": "pt_BR",
                "from_component": [source.full_slug],
            },
        )

        created = target.translation_set.get(language__code="pt_BR")
        created_unit = created.unit_set.get(source="Hello, world!\n")
        self.assertEqual(created_unit.target, "Styled source translation!\n")

    def test_create_translation_from_component_requires_edit_permission(self) -> None:
        target = self.create_po_new_base(name="target", project=self.component.project)
        source = self.create_po_new_base(name="source", project=self.component.project)
        language = Language.objects.get(code="fa")
        source_translation = source.add_new_language(language, None)
        self.assertIsNotNone(source_translation)

        self.do_request(
            "api:component-translations",
            {"project__slug": target.project.slug, "slug": target.slug},
            method="post",
            code=400,
            format="json",
            request={
                "language_code": "fa",
                "from_component": [source.full_slug],
            },
        )

    def test_create_translation_from_component_allows_shared_tm_source_without_edit(
        self,
    ) -> None:
        target = self.create_po_new_base(name="target", project=self.component.project)
        target.project.add_user(self.user, "Administration")
        source_project = self.create_project(
            name="Shared source", slug="shared-source", contribute_shared_tm=True
        )
        source = self.create_po_new_base(name="source", project=source_project)
        language = Language.objects.get(code="fa")
        source_translation = source.add_new_language(language, None)
        self.assertIsNotNone(source_translation)
        unit = source_translation.unit_set.get(source="Hello, world!\n")
        unit.translate(self.user, "Shared TM source translation!\n", STATE_TRANSLATED)

        self.do_request(
            "api:component-translations",
            {"project__slug": target.project.slug, "slug": target.slug},
            method="post",
            code=201,
            format="json",
            request={
                "language_code": "fa",
                "from_component": [source.full_slug],
            },
        )

        created = target.translation_set.get(language_code="fa")
        created_unit = created.unit_set.get(source="Hello, world!\n")
        self.assertEqual(created_unit.target, "Shared TM source translation!\n")

    def test_create_translation_from_component_hides_private_cross_project_source(
        self,
    ) -> None:
        target = self.create_po_new_base(name="target", project=self.component.project)
        target.project.add_user(self.user, "Administration")
        source_project = self.create_project(
            name="Private source", slug="private-source", contribute_shared_tm=False
        )
        source = self.create_po_new_base(name="source", project=source_project)

        response = self.do_request(
            "api:component-translations",
            {"project__slug": target.project.slug, "slug": target.slug},
            method="post",
            code=400,
            format="json",
            request={
                "language_code": "fa",
                "from_component": [source.full_slug],
            },
        )

        self.assertEqual(
            response.data["errors"],
            [
                {
                    "attr": "from_component",
                    "code": "invalid",
                    "detail": "Component not found.",
                }
            ],
        )

    def test_create_translation_from_component_validation_has_no_side_effects(
        self,
    ) -> None:
        target = self.create_po_new_base(name="target", project=self.component.project)
        source_project = self.create_project(
            name="Source", slug="source", contribute_shared_tm=False
        )
        source = self.create_po_new_base(name="source", project=source_project)
        language = Language.objects.get(code="fa")
        source_translation = source.add_new_language(language, None)
        self.assertIsNotNone(source_translation)

        self.do_request(
            "api:component-translations",
            {"project__slug": target.project.slug, "slug": target.slug},
            method="post",
            code=400,
            superuser=True,
            format="json",
            request={
                "language_code": "fa",
                "from_component": [source.full_slug],
            },
        )
        self.assertFalse(target.translation_set.filter(language_code="fa").exists())

    def test_create_translation_from_component_auto_failure_has_no_side_effects(
        self,
    ) -> None:
        target = self.create_po_new_base(name="target", project=self.component.project)
        source = self.create_po_new_base(name="source", project=self.component.project)
        language = Language.objects.get(code="fa")
        source_translation = source.add_new_language(language, None)
        self.assertIsNotNone(source_translation)

        with patch(
            "weblate.trans.autotranslate.AutoTranslate.process_others",
            side_effect=Component.DoesNotExist("Component not found."),
        ):
            response = self.do_request(
                "api:component-translations",
                {"project__slug": target.project.slug, "slug": target.slug},
                method="post",
                code=400,
                superuser=True,
                format="json",
                request={
                    "language_code": "fa",
                    "from_component": [source.full_slug],
                },
            )

        self.assertEqual(
            response.data["errors"],
            [
                {
                    "attr": "from_component",
                    "code": "invalid",
                    "detail": "Automatic translation failed: Component not found.",
                }
            ],
        )
        self.assertFalse(target.translation_set.filter(language_code="fa").exists())

    def test_create_translation_invalid_language_code(self) -> None:
        self.component.new_lang = "add"
        self.component.new_base = "po/hello.pot"
        self.component.save()
        self.do_request(
            "api:component-translations",
            self.component_kwargs,
            method="post",
            code=400,
            superuser=True,
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

    def test_links_with_category(self) -> None:
        self.create_acl()
        category = Category.objects.create(
            name="Test Category",
            slug="test-cat",
            project=Project.objects.get(slug="acl"),
        )
        self.do_request(
            "api:component-links",
            self.component_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={"project_slug": "acl", "category_id": category.pk},
        )
        link = ComponentLink.objects.get(
            component=self.component, project=category.project
        )
        self.assertEqual(link.category, category)

    def test_links_with_wrong_project_category(self) -> None:
        """Category from a different project should be rejected."""
        self.create_acl()
        category = Category.objects.create(
            name="Wrong Category", slug="wrong-cat", project=self.component.project
        )
        self.do_request(
            "api:component-links",
            self.component_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={"project_slug": "acl", "category_id": category.pk},
        )
        self.assertFalse(
            ComponentLink.objects.filter(
                component=self.component, project__slug="acl"
            ).exists()
        )

    def test_links_with_invalid_category(self) -> None:
        """Non-existent category_id should be rejected."""
        self.create_acl()
        self.do_request(
            "api:component-links",
            self.component_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={"project_slug": "acl", "category_id": 99999},
        )

    def test_links_duplicate(self) -> None:
        """Adding a link to an already linked project should return 400."""
        self.create_acl()
        self.do_request(
            "api:component-links",
            self.component_kwargs,
            method="post",
            code=201,
            superuser=True,
            request={"project_slug": "acl"},
        )
        self.do_request(
            "api:component-links",
            self.component_kwargs,
            method="post",
            code=400,
            superuser=True,
            request={"project_slug": "acl"},
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


class TasksAPITest(APIBaseTest):
    task_id = "01234567-89ab-cdef-0123-456789abcdef"

    def tearDown(self) -> None:
        cache.delete(get_task_metadata_key(self.task_id))
        super().tearDown()

    def test_retrieve_uses_cached_component_metadata(self) -> None:
        cache.set(
            get_task_metadata_key(self.task_id),
            {"component_id": self.component.id, "translation_id": None},
            3600,
        )

        class DummyAsyncResult:
            def __init__(self, task_id):
                self.id = task_id
                self.result = None
                self.state = "PENDING"

            def ready(self):
                return False

        with patch("weblate.api.views.AsyncResult", DummyAsyncResult):
            response = self.do_request(
                "api:task-detail",
                kwargs={"pk": self.task_id},
                method="get",
                code=200,
            )

        self.assertEqual(
            response.data,
            {"completed": False, "progress": 0, "result": None, "log": ""},
        )

    def test_retrieve_denies_inaccessible_cached_component(self) -> None:
        other_component = self.create_acl()
        cache.set(
            get_task_metadata_key(self.task_id),
            {"component_id": other_component.id, "translation_id": None},
            3600,
        )

        class DummyAsyncResult:
            def __init__(self, task_id):
                self.id = task_id
                self.result = None
                self.state = "PENDING"

            def ready(self):
                return False

        with patch("weblate.api.views.AsyncResult", DummyAsyncResult):
            self.do_request(
                "api:task-detail",
                kwargs={"pk": self.task_id},
                method="get",
                code=403,
            )

    def test_retrieve_requires_cached_metadata(self) -> None:
        class DummyAsyncResult:
            def __init__(self, task_id):
                self.id = task_id
                self.result = None
                self.state = "PENDING"

            def ready(self):
                return False

        with patch("weblate.api.views.AsyncResult", DummyAsyncResult):
            self.do_request(
                "api:task-detail",
                kwargs={"pk": self.task_id},
                method="get",
                code=404,
            )


class MemoryAPITest(APIBaseTest):
    @staticmethod
    def mock_queryset(*, db: str = "default") -> MagicMock:
        queryset = MagicMock()
        queryset.db = db
        return queryset

    @staticmethod
    def mock_user_with_allowed_projects(
        project_ids: list[int],
        *,
        is_superuser: bool = False,
        has_manage_perm: bool = False,
    ) -> MagicMock:
        user = MagicMock()
        user.is_authenticated = True
        user.is_superuser = is_superuser
        user.has_perm.return_value = has_manage_perm
        user.allowed_projects.values_list.return_value = project_ids
        user.allowed_projects.using.return_value = user.allowed_projects
        return user

    def create_memory(
        self,
        *,
        source: str,
        target: str,
        user: User | None = None,
        project: Project | None = None,
        origin: str = "api-test",
        from_file: bool = False,
        shared: bool = False,
        source_language: str = "en",
        target_language: str = "cs",
    ) -> Memory:
        return Memory.objects.create(
            source=source,
            target=target,
            user=user,
            project=project,
            origin=origin,
            from_file=from_file,
            shared=shared,
            status=Memory.STATUS_ACTIVE,
            source_language=Language.objects.get(code=source_language),
            target_language=Language.objects.get(code=target_language),
        )

    def test_memory_lookup_request_serializer_preserves_whitespace(self) -> None:
        serializer = MemoryLookupRequestSerializer(data={"strings": ["  padded  "]})

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["strings"], ["  padded  "])

    def test_memory_lookup_request_serializer_limits_string_length(self) -> None:
        serializer = MemoryLookupRequestSerializer(data={"strings": ["x" * 2001]})

        self.assertFalse(serializer.is_valid())
        self.assertIn(
            "Ensure this field has no more than 2000 characters.",
            str(serializer.errors),
        )

    def test_get(self) -> None:
        self.authenticate()
        public_entry = self.create_memory(
            source="Visible public project entry",
            target="Viditelny zaznam",
            project=self.component.project,
            origin=self.component.full_slug,
        )
        personal_entry = self.create_memory(
            source="Visible personal entry",
            target="Osobni zaznam",
            user=self.user,
        )
        imported_personal_entry = self.create_memory(
            source="Visible imported personal entry",
            target="Importovany osobni zaznam",
            user=self.user,
            from_file=True,
        )
        imported_project_entry = self.create_memory(
            source="Visible imported project entry",
            target="Importovany projektovy zaznam",
            project=self.component.project,
            origin=self.component.full_slug,
            from_file=True,
        )
        self.create_memory(
            source="Other user entry",
            target="Cizi zaznam",
            user=User.objects.create_user("memory-other", "other@example.org", "x"),
        )
        global_file_entry = self.create_memory(
            source="Visible imported entry",
            target="Importovany zaznam",
            from_file=True,
        )
        hidden_imported_other_user_entry = self.create_memory(
            source="Hidden imported other user entry",
            target="Skryty importovany cizi zaznam",
            user=User.objects.create_user(
                "memory-other-imported", "other-imported@example.org", "x"
            ),
            from_file=True,
        )
        private_component = self.create_acl()
        private_entry = self.create_memory(
            source="Hidden private project entry",
            target="Skryty zaznam",
            project=private_component.project,
            origin=private_component.full_slug,
        )
        hidden_imported_private_entry = self.create_memory(
            source="Hidden imported private project entry",
            target="Skryty importovany projektovy zaznam",
            project=private_component.project,
            origin=private_component.full_slug,
            from_file=True,
        )

        self.do_request(
            "api:memory-list",
            method="get",
            code=200,
        )
        response = self.client.get(reverse("api:memory-list"))
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(public_entry.id, ids)
        self.assertIn(personal_entry.id, ids)
        self.assertIn(imported_personal_entry.id, ids)
        self.assertIn(imported_project_entry.id, ids)
        self.assertIn(global_file_entry.id, ids)
        self.assertNotIn(private_entry.id, ids)
        self.assertNotIn(hidden_imported_other_user_entry.id, ids)
        self.assertNotIn(hidden_imported_private_entry.id, ids)

    def test_get_filters(self) -> None:
        self.authenticate()
        second_component = self.create_po(
            project=self.component.project, name="Second", slug="second"
        )
        source_match = self.create_memory(
            source="Memory filter source needle",
            target="Filtr zdroje",
            project=self.component.project,
            origin=self.component.full_slug,
        )
        component_match = self.create_memory(
            source="Memory filter component",
            target="Filtr komponenty",
            project=self.component.project,
            origin=second_component.full_slug,
        )
        language_match = self.create_memory(
            source="Memory filter language",
            target="Sprachfilter",
            target_language="de",
            from_file=True,
        )

        response = self.client.get(reverse("api:memory-list"), {"source": "needle"})
        ids = {item["id"] for item in response.data["results"]}
        self.assertEqual(ids, {source_match.id})

        response = self.client.get(
            reverse("api:memory-list"),
            {"target_language": "de", "source": "Memory filter language"},
        )
        ids = {item["id"] for item in response.data["results"]}
        self.assertEqual(ids, {language_match.id})

        response = self.client.get(
            reverse("api:memory-list"), {"project": self.component.project.slug}
        )
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(source_match.id, ids)
        self.assertIn(component_match.id, ids)
        self.assertNotIn(language_match.id, ids)

    def test_delete(self) -> None:
        self.authenticate()
        deletable = self.create_memory(
            source="Delete my own entry",
            target="Smazat muj zaznam",
            user=self.user,
        )
        forbidden = self.create_memory(
            source="Delete forbidden entry",
            target="Zakazany zaznam",
            project=self.component.project,
            origin=self.component.full_slug,
        )
        private_component = self.create_acl()
        hidden = self.create_memory(
            source="Delete hidden entry",
            target="Skryty zaznam",
            project=private_component.project,
            origin=private_component.full_slug,
        )

        self.do_request(
            "api:memory-detail",
            kwargs={"pk": deletable.pk},
            method="delete",
            code=204,
        )
        self.assertFalse(Memory.objects.filter(pk=deletable.pk).exists())

        self.do_request(
            "api:memory-detail",
            kwargs={"pk": forbidden.pk},
            method="delete",
            code=403,
        )
        self.do_request(
            "api:memory-detail",
            kwargs={"pk": hidden.pk},
            method="delete",
            code=404,
        )

    def test_superuser_can_access_other_users_personal_memory(self) -> None:
        other_user = User.objects.create_user(
            "memory-admin-target", "memory-admin-target@example.org", "x"
        )
        personal_entry = self.create_memory(
            source="Admin visible personal entry",
            target="Admin vidi osobni zaznam",
            user=other_user,
        )

        self.authenticate(superuser=True)

        response = self.client.get(reverse("api:memory-list"))
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(personal_entry.id, ids)

        response = self.client.delete(
            reverse("api:memory-detail", kwargs={"pk": personal_entry.pk})
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Memory.objects.filter(pk=personal_entry.pk).exists())

    def test_lookup(self) -> None:
        self.authenticate()
        exact = self.create_memory(
            source="Memory API exact",
            target="Pamet API presne",
            project=self.component.project,
            origin=self.component.full_slug,
        )
        self.create_memory(
            source="Scoped lookup",
            target="Prvni komponenta",
            project=self.component.project,
            origin=self.component.full_slug,
        )
        second_component = self.create_po(
            project=self.component.project, name="Lookup", slug="lookup"
        )
        self.create_memory(
            source="Scoped lookup",
            target="Druha komponenta",
            project=self.component.project,
            origin=second_component.full_slug,
        )
        fuzzy = self.create_memory(
            source="Memory API fuzzy entry",
            target="Pamet API priblizne",
            project=self.component.project,
            origin=self.component.full_slug,
        )

        response = self.client.post(
            (
                f"{reverse('api:memory-lookup')}?source_language=en&target_language=cs"
                f"&project={self.component.project.slug}"
            ),
            {
                "strings": [
                    "Memory API exact",
                    "memory API fuzzy entry",
                    "Scoped lookup",
                    "No hit",
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["query"], "Memory API exact")
        self.assertEqual(response.data[0]["match"]["id"], exact.id)
        self.assertTrue(response.data[0]["match"]["exact"])
        self.assertEqual(response.data[1]["match"]["id"], fuzzy.id)
        self.assertFalse(response.data[1]["match"]["exact"])
        self.assertIsNotNone(response.data[2]["match"])
        self.assertIsNone(response.data[3]["match"])

    def test_lookup_with_project_keeps_personal_shared_and_file_entries(self) -> None:
        self.authenticate()
        self.component.project.use_shared_tm = True
        self.component.project.save(update_fields=["use_shared_tm"])

        project_entry = self.create_memory(
            source="Project scoped memory",
            target="Projektova pamet",
            project=self.component.project,
            origin=self.component.full_slug,
            from_file=True,
        )
        personal_entry = self.create_memory(
            source="Personal scoped memory",
            target="Osobni pamet",
            user=self.user,
            from_file=True,
        )
        shared_entry = self.create_memory(
            source="Shared scoped memory",
            target="Sdilena pamet",
            origin=self.component.full_slug,
            shared=True,
        )
        file_entry = self.create_memory(
            source="File scoped memory",
            target="Souborova pamet",
            from_file=True,
        )
        self.create_memory(
            source="Hidden personal file memory",
            target="Skryta osobni souborova pamet",
            user=User.objects.create_user(
                "memory-other-lookup", "memory-other-lookup@example.org", "x"
            ),
            from_file=True,
        )
        private_component = self.create_acl()
        self.create_memory(
            source="Hidden project file memory",
            target="Skryta projektova souborova pamet",
            project=private_component.project,
            origin=private_component.full_slug,
            from_file=True,
        )

        response = self.client.post(
            (
                f"{reverse('api:memory-lookup')}?source_language=en&target_language=cs"
                f"&project={self.component.project.slug}"
            ),
            {
                "strings": [
                    "Project scoped memory",
                    "Personal scoped memory",
                    "Shared scoped memory",
                    "File scoped memory",
                    "Hidden personal file memory",
                    "Hidden project file memory",
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["match"]["id"], project_entry.id)
        self.assertEqual(response.data[1]["match"]["id"], personal_entry.id)
        self.assertEqual(response.data[2]["match"]["id"], shared_entry.id)
        self.assertEqual(response.data[3]["match"]["id"], file_entry.id)
        self.assertIsNone(response.data[4]["match"])
        self.assertIsNone(response.data[5]["match"])

    def test_lookup_batches_exact_matches_before_fuzzy_fallback(self) -> None:
        self.authenticate()
        exact = self.create_memory(
            source="Batch exact match",
            target="Davkova presna shoda",
            project=self.component.project,
            origin=self.component.full_slug,
        )
        fuzzy = self.create_memory(
            source="Batch fuzzy source",
            target="Davkova fuzzy shoda",
            project=self.component.project,
            origin=self.component.full_slug,
        )

        with patch.object(
            MemoryViewSet,
            "get_fuzzy_match",
            autospec=True,
            return_value=fuzzy,
        ) as get_fuzzy_match:
            response = self.client.post(
                (
                    f"{reverse('api:memory-lookup')}?source_language=en&target_language=cs"
                    f"&project={self.component.project.slug}"
                ),
                {
                    "strings": ["Batch exact match", "Batch fuzzy sourca"]
                },  # codespell:ignore sourca
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["match"]["id"], exact.id)
        self.assertEqual(response.data[1]["match"]["id"], fuzzy.id)
        get_fuzzy_match.assert_called_once()
        self.assertEqual(
            get_fuzzy_match.call_args.args[4],
            "Batch fuzzy sourca",  # codespell:ignore sourca
        )

    def test_get_exact_matches_uses_distinct_on_source(self) -> None:
        first = self.create_memory(
            source="Shared exact source",
            target="Prvni shoda",
            project=self.component.project,
            origin=self.component.full_slug,
        )
        second = self.create_memory(
            source="Another exact source",
            target="Druha shoda",
            project=self.component.project,
            origin=self.component.full_slug,
        )
        queryset = self.mock_queryset()
        filtered_queryset = self.mock_queryset()
        ordered_queryset = self.mock_queryset()
        distinct_queryset = self.mock_queryset()
        distinct_queryset.__iter__.return_value = iter([first, second])
        queryset.filter.return_value = filtered_queryset
        filtered_queryset.order_by.return_value = ordered_queryset
        ordered_queryset.distinct.return_value = distinct_queryset

        view = MemoryViewSet()
        matches = view.get_exact_matches(
            queryset, ["Shared exact source", "Another exact source"]
        )

        filtered_queryset.order_by.assert_called_once_with("source", "-status", "id")
        ordered_queryset.distinct.assert_called_once_with("source")
        self.assertEqual(matches, {first.source: first, second.source: second})

    def test_lookup_uses_read_alias_for_similarity_threshold(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        candidate = self.create_memory(
            source="Memory routed fuzzy entry",
            target="Smerovana fuzzy pamet",
            project=self.component.project,
            origin=self.component.full_slug,
        )
        filtered_queryset = self.mock_queryset(db="memory_db")
        annotated_queryset = self.mock_queryset(db="memory_db")
        ordered_queryset = self.mock_queryset(db="memory_db")
        ordered_queryset.__getitem__.return_value = [candidate]
        annotated_queryset.order_by.return_value = ordered_queryset
        filtered_queryset.annotate.return_value = annotated_queryset

        base_queryset = self.mock_queryset(db="memory_db")
        base_queryset.filter.return_value = filtered_queryset

        queryset = self.mock_queryset()
        queryset.filter.return_value = base_queryset

        view = MemoryViewSet()
        with (
            patch("weblate.api.views.adjust_similarity_threshold") as adjust_threshold,
            patch.object(Memory.objects, "threshold_to_similarity", return_value=0.8),
            patch.object(Memory.objects, "minimum_similarity", return_value=0.8),
            patch.object(view.comparer, "similarity", return_value=95),
        ):
            match = view.get_fuzzy_match(
                queryset,
                source_language,
                target_language,
                "Memory routed fuzzy entri",
            )

        self.assertEqual(match, candidate)
        adjust_threshold.assert_called_once_with(0.8, alias="memory_db")

    def test_lookup_retries_lower_similarity_threshold(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        low_quality_candidate = self.create_memory(
            source="Retry fuzzy source",
            target="Nizka fuzzy shoda",
            project=self.component.project,
            origin=self.component.full_slug,
        )
        candidate = self.create_memory(
            source="Retry fuzzy sourca",  # codespell:ignore sourca
            target="Opakovana fuzzy shoda",
            project=self.component.project,
            origin=self.component.full_slug,
        )
        first_filtered_queryset = self.mock_queryset(db="memory_db")
        first_annotated_queryset = self.mock_queryset(db="memory_db")
        first_ordered_queryset = self.mock_queryset(db="memory_db")
        first_ordered_queryset.__getitem__.return_value = [low_quality_candidate]
        first_annotated_queryset.order_by.return_value = first_ordered_queryset
        first_filtered_queryset.annotate.return_value = first_annotated_queryset

        second_filtered_queryset = self.mock_queryset(db="memory_db")
        second_annotated_queryset = self.mock_queryset(db="memory_db")
        second_ordered_queryset = self.mock_queryset(db="memory_db")
        second_ordered_queryset.__getitem__.return_value = [
            low_quality_candidate,
            candidate,
        ]
        second_annotated_queryset.order_by.return_value = second_ordered_queryset
        second_filtered_queryset.annotate.return_value = second_annotated_queryset

        base_queryset = self.mock_queryset(db="memory_db")
        base_queryset.filter.side_effect = [
            first_filtered_queryset,
            second_filtered_queryset,
        ]

        queryset = self.mock_queryset()
        queryset.filter.return_value = base_queryset

        view = MemoryViewSet()
        with (
            patch("weblate.api.views.adjust_similarity_threshold") as adjust_threshold,
            patch.object(Memory.objects, "threshold_to_similarity", return_value=0.95),
            patch.object(Memory.objects, "minimum_similarity", return_value=0.9),
            patch.object(view.comparer, "similarity", side_effect=[60, 95]),
        ):
            match = view.get_fuzzy_match(
                queryset,
                source_language,
                target_language,
                "Retry fuzzy sourc",  # codespell:ignore sourc
            )

        self.assertIsNotNone(match)
        self.assertEqual(
            adjust_threshold.call_args_list,
            [call(0.95, alias="memory_db"), call(0.9, alias="memory_db")],
        )

    def test_lookup_uses_later_fuzzy_candidate_meeting_quality_threshold(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        low_quality_candidate = self.create_memory(
            source="Short source typo",
            target="Nizka kvalita",
            project=self.component.project,
            origin=self.component.full_slug,
        )
        accepted_candidate = self.create_memory(
            source="Short source typa",
            target="Prijata kvalita",
            project=self.component.project,
            origin=self.component.full_slug,
        )
        filtered_queryset = self.mock_queryset(db="memory_db")
        annotated_queryset = self.mock_queryset(db="memory_db")
        ordered_queryset = self.mock_queryset(db="memory_db")
        ordered_queryset.__getitem__.return_value = [
            low_quality_candidate,
            accepted_candidate,
        ]
        annotated_queryset.order_by.return_value = ordered_queryset
        filtered_queryset.annotate.return_value = annotated_queryset

        base_queryset = self.mock_queryset(db="memory_db")
        base_queryset.filter.return_value = filtered_queryset

        queryset = self.mock_queryset()
        queryset.filter.return_value = base_queryset

        view = MemoryViewSet()
        with (
            patch("weblate.api.views.adjust_similarity_threshold"),
            patch.object(Memory.objects, "threshold_to_similarity", return_value=0.85),
            patch.object(Memory.objects, "minimum_similarity", return_value=0.85),
            patch.object(view.comparer, "similarity", side_effect=[60, 95]),
        ):
            match = view.get_fuzzy_match(
                queryset,
                source_language,
                target_language,
                "Short source typi",
            )

        self.assertEqual(match, accepted_candidate)

    def test_get_scoped_queryset_uses_project_subquery_on_memory_db(self) -> None:
        user = self.mock_user_with_allowed_projects([1, 2, 3])
        allowed_projects = MagicMock()
        user.allowed_projects.using.return_value = allowed_projects
        request = MagicMock()
        request.user = user
        using_queryset = self.mock_queryset(db="memory_db")
        filtered_queryset = self.mock_queryset(db="memory_db")
        ordered_queryset = self.mock_queryset(db="memory_db")
        using_queryset.filter.return_value = filtered_queryset
        filtered_queryset.order_by.return_value = ordered_queryset

        view = MemoryViewSet()
        view.request = request

        with patch.object(
            Memory.objects, "using", return_value=using_queryset
        ) as using:
            result = view.get_scoped_queryset(alias="memory_db")

        self.assertIs(result, ordered_queryset)
        using.assert_called_once_with("memory_db")
        user.allowed_projects.using.assert_called_once_with("memory_db")
        query = using_queryset.filter.call_args.args[0]
        self.assertIn(("project__in", allowed_projects), query.children)

    def test_get_scoped_queryset_uses_project_subquery_on_default(self) -> None:
        user = self.mock_user_with_allowed_projects([1, 2, 3])
        allowed_projects = MagicMock()
        user.allowed_projects.using.return_value = allowed_projects
        request = MagicMock()
        request.user = user
        using_queryset = self.mock_queryset(db="default")
        filtered_queryset = self.mock_queryset(db="default")
        ordered_queryset = self.mock_queryset(db="default")
        using_queryset.filter.return_value = filtered_queryset
        filtered_queryset.order_by.return_value = ordered_queryset

        view = MemoryViewSet()
        view.request = request

        with patch.object(
            Memory.objects, "using", return_value=using_queryset
        ) as using:
            result = view.get_scoped_queryset(alias="default")

        self.assertIs(result, ordered_queryset)
        using.assert_called_once_with("default")
        user.allowed_projects.using.assert_called_once_with("default")
        query = using_queryset.filter.call_args.args[0]
        self.assertIn(("project__in", allowed_projects), query.children)

    def test_get_scoped_queryset_superuser_skips_project_materialization(self) -> None:
        user = self.mock_user_with_allowed_projects([1, 2, 3], is_superuser=True)
        request = MagicMock()
        request.user = user
        using_queryset = self.mock_queryset(db="memory_db")
        filtered_queryset = self.mock_queryset(db="memory_db")
        ordered_queryset = self.mock_queryset(db="memory_db")
        using_queryset.filter.return_value = filtered_queryset
        filtered_queryset.order_by.return_value = ordered_queryset

        view = MemoryViewSet()
        view.request = request

        with patch.object(
            Memory.objects, "using", return_value=using_queryset
        ) as using:
            result = view.get_scoped_queryset(alias="memory_db")

        self.assertIs(result, ordered_queryset)
        using.assert_called_once_with("memory_db")
        user.allowed_projects.using.assert_not_called()


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

    def check_upload_changes(self, previous: int, expected: int) -> None:
        changes_end = self.component.change_set.count()
        self.assertEqual(changes_end - previous, expected)
        for change in self.component.change_set.order_by("-timestamp")[:expected]:
            self.assertEqual(change.user, self.user)
            self.assertEqual(change.author, self.user)

    def test_upload_bytes(self) -> None:
        self.authenticate()
        changes_start = self.component.change_set.count()
        response = self.client.put(
            reverse("api:translation-file", kwargs=self.translation_kwargs),
            {"file": BytesIO(Path(TEST_PO).read_bytes())},
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
        self.check_upload_changes(changes_start, 2)

    def test_upload(self) -> None:
        self.authenticate()
        changes_start = self.component.change_set.count()
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
        self.check_upload_changes(changes_start, 2)

    def test_upload_parse_error(self) -> None:
        self.authenticate()
        with (
            patch.object(
                Translation,
                "handle_upload",
                side_effect=FileParseError("Broken PO header"),
            ),
            open(TEST_PO, "rb") as handle,
        ):
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle},
            )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Broken PO header", status_code=400)

    def test_upload_commit_error(self) -> None:
        self.authenticate()
        with (
            patch.object(
                Translation,
                "handle_upload",
                side_effect=FailedCommitError("Commit failed"),
            ),
            open(TEST_PO, "rb") as handle,
        ):
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle},
            )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Commit failed", status_code=400)

    def test_upload_parse_error_is_sanitized(self) -> None:
        self.authenticate()
        with (
            patch.object(
                Translation,
                "handle_upload",
                side_effect=FileParseError(
                    "Broken PO header from "
                    "ssh://git@internal.example.net/private/repo.git "
                    f"in {self.component.full_path}/secret"
                ),
            ),
            open(TEST_PO, "rb") as handle,
        ):
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle},
            )

        self.assertEqual(response.status_code, 400)
        detail = response.data["errors"][0]["detail"]
        self.assertIn("Broken PO header", detail)
        self.assertNotIn("internal.example.net", detail)
        self.assertNotIn("ssh://", detail)
        self.assertNotIn(self.component.full_path, detail)
        self.assertIn(".../secret", detail)

    def test_upload_commit_error_is_sanitized(self) -> None:
        self.authenticate()
        with (
            patch.object(
                Translation,
                "handle_upload",
                side_effect=FailedCommitError(
                    "Commit failed via "
                    "ssh://git@internal.example.net/private/repo.git "
                    f"in {self.component.full_path}/secret"
                ),
            ),
            open(TEST_PO, "rb") as handle,
        ):
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle},
            )

        self.assertEqual(response.status_code, 400)
        detail = response.data["errors"][0]["detail"]
        self.assertIn("Commit failed", detail)
        self.assertNotIn("internal.example.net", detail)
        self.assertNotIn("ssh://", detail)
        self.assertNotIn(self.component.full_path, detail)
        self.assertIn(".../secret", detail)

    def test_upload_internal_error_is_sanitized(self) -> None:
        self.authenticate()
        with (
            patch.object(
                Translation,
                "handle_upload",
                side_effect=Exception(f"Failure in {self.component.full_path}/secret"),
            ),
            open(TEST_PO, "rb") as handle,
        ):
            response = self.client.put(
                reverse("api:translation-file", kwargs=self.translation_kwargs),
                {"file": handle},
            )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "File upload has failed:", status_code=400)
        self.assertNotContains(response, self.component.full_path, status_code=400)
        self.assertContains(response, ".../secret", status_code=400)

    def test_upload_source(self) -> None:
        self.authenticate(True)

        changes_start = self.component.change_set.count()

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

        self.check_upload_changes(changes_start, 1)

        # Non-compatible component
        self.create_po_mono(name="mono", project=self.component.project)

        with open(TEST_POT, "rb") as handle:
            response = self.client.put(
                reverse(
                    "api:translation-file",
                    kwargs={
                        "language__code": "en",
                        "component__slug": "mono",
                        "component__project__slug": "test",
                    },
                ),
                {"file": handle, "method": "source"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual("method", response.data["errors"][0]["attr"])
        self.assertIn(
            "Source upload is only supported for bilingual translations, you might want to use replace upload instead.",
            response.data["errors"][0]["detail"],
        )

    def test_upload_content(self) -> None:
        self.authenticate()
        response = self.client.put(
            reverse("api:translation-file", kwargs=self.translation_kwargs),
            {"file": Path(TEST_PO).read_bytes()},
        )
        self.assertEqual(response.status_code, 400)

    def test_upload_conflicts(self) -> None:
        self.authenticate()
        changes_start = self.component.change_set.count()
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
        self.check_upload_changes(changes_start, 3)

    def test_upload_overwrite(self) -> None:
        self.test_upload()
        changes_start = self.component.change_set.count()
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
        self.check_upload_changes(changes_start, 1)

    def test_upload_suggest(self) -> None:
        self.authenticate()
        changes_start = self.component.change_set.count()
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
        self.check_upload_changes(changes_start, 3)

    def test_upload_replace(self) -> None:
        self.authenticate(superuser=True)
        changes_start = self.component.change_set.count()
        content = Path(TEST_PO).read_text(encoding="utf-8")
        content = f'{content}\n\nmsgid "Testing"\nmsgstr""\n'

        response = self.client.put(
            reverse("api:translation-file", kwargs=self.translation_kwargs),
            {"file": BytesIO(content.encode()), "method": "replace"},
        )
        self.assertEqual(
            response.data,
            {
                "accepted": 5,
                "count": 5,
                "not_found": 0,
                "result": True,
                "skipped": 0,
                "total": 5,
            },
        )
        self.check_upload_changes(changes_start, 7)

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
        response = self.do_request(
            "api:translation-repository",
            self.translation_kwargs,
            superuser=True,
        )

        self.assertIn("needs_commit", response.data)
        self.assertIn("needs_merge", response.data)
        self.assertIn("needs_push", response.data)
        self.assertIn("url", response.data)
        self.assertIn("status", response.data)
        self.assertIn("merge_failure", response.data)

        self.assertIn("pending_units", response.data)
        self.assertIn("outgoing_commits", response.data)
        self.assertIn("missing_commits", response.data)
        self.assertIn("remote_commit", response.data)
        self.assertIn("weblate_commit", response.data)

        self.assertIsInstance(response.data["needs_commit"], bool)
        self.assertIsInstance(response.data["needs_merge"], bool)
        self.assertIsInstance(response.data["needs_push"], bool)

        self.assertEqual(response.data["needs_commit"], False)

        self.assertIsNotNone(response.data["url"])

        self.assertIsNotNone(response.data["status"])

        self.assertIsInstance(response.data["outgoing_commits"], int)
        self.assertIsInstance(response.data["missing_commits"], int)

        pending = response.data["pending_units"]
        self.assertIsNotNone(pending)
        self.assertIn("total", pending)
        self.assertIn("errors_skipped", pending)
        self.assertIn("commit_policy_skipped", pending)
        self.assertIn("eligible_for_commit", pending)

        self.assertEqual(pending["total"], 0)

        if response.data["remote_commit"]:
            commit = response.data["remote_commit"]
            self.assertIn("revision", commit)
            self.assertIn("shortrevision", commit)
            self.assertIn("author", commit)
            self.assertIn("message", commit)
            self.assertIn("summary", commit)

    def test_repo_file_sync_returns_true(self) -> None:
        with patch.object(Component, "queue_background_task", return_value=None):
            response = self.do_request(
                "api:translation-repository",
                self.translation_kwargs,
                superuser=True,
                method="post",
                request={"operation": "file-sync"},
            )

        self.assertIs(response.data["result"], True)

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
            skip={"last_change"},
        )

    def test_changes(self) -> None:
        request = self.do_request("api:translation-changes", self.translation_kwargs)
        self.assertEqual(request.data["count"], 5)

    def test_units(self) -> None:
        request = self.do_request("api:translation-units", self.translation_kwargs)
        self.assertEqual(request.data["count"], 4)

    # pylint: disable-next=redefined-builtin
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
                "q": "state:<translated",
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
                "q": "state:<translated",
                "auto_source": "others",
                "component": self.component.pk,
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
                "q": "state:<translated",
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

    def test_repo_status_with_changes(self) -> None:
        """Test repository status with actual pending changes."""
        translation = Translation.objects.get(**self.translation_kwargs)
        unit = translation.unit_set.first()
        unit.translate(self.user, "Modified translation", STATE_TRANSLATED)

        response = self.do_request(
            "api:translation-repository",
            self.translation_kwargs,
            superuser=True,
        )

        self.assertEqual(response.data["needs_commit"], True)
        self.assertIsNotNone(response.data["pending_units"])

        pending = response.data["pending_units"]
        self.assertGreater(pending["total"], 0)
        self.assertGreaterEqual(pending["eligible_for_commit"], 0)
        self.assertEqual(
            pending["total"],
            pending["errors_skipped"]
            + pending["commit_policy_skipped"]
            + pending["eligible_for_commit"],
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
        response = self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="get",
            code=200,
        )
        data = response.json()
        self.assertEqual(data["pending"], True)
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

    def test_unit_state_rejected(self) -> None:
        """Test that STATE_NEEDS_CHECKING and STATE_NEEDS_REWRITING cannot be set manually via API."""
        unit = Unit.objects.get(
            translation__language_code="cs", source="Hello, world!\n"
        )
        response = self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=400,
            request={"state": str(STATE_NEEDS_CHECKING), "target": "Test translation"},
        )
        self.assertEqual(
            "This state cannot be set manually.", response.json()["errors"][0]["detail"]
        )

        response = self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.pk},
            method="patch",
            code=400,
            request={"state": str(STATE_NEEDS_REWRITING), "target": "Test translation"},
        )
        self.assertEqual(
            "This state cannot be set manually.", response.json()["errors"][0]["detail"]
        )

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

        changes = unit.source_unit.change_set.filter(action=ActionEvents.LABEL_ADD)
        self.assertEqual(changes.count(), 1)
        change = changes.first()
        self.assertEqual(change.target, "Added label test")
        self.assertEqual(change.user, self.user)

        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.source_unit.pk},
            method="patch",
            code=200,
            superuser=True,
            request={"labels": []},
        )

        label1.delete()
        label2.delete()
        other_project.delete()

    def test_unit_labels_multiple_change_events(self) -> None:
        """Test that adding multiple labels creates multiple change events."""
        label1 = self.component.project.label_set.create(name="test1", color="navy")
        label2 = self.component.project.label_set.create(name="test2", color="blue")

        unit = Unit.objects.get(
            translation__language_code="cs", source="Hello, world!\n"
        )
        unit.translate(self.user, "Hello, world!\n", STATE_TRANSLATED)

        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.source_unit.pk},
            method="patch",
            code=200,
            superuser=True,
            request={"labels": [label1.id, label2.id]},
        )

        changes = unit.source_unit.change_set.filter(action=ActionEvents.LABEL_ADD)
        self.assertEqual(changes.count(), 2)

        label_names = {change.target for change in changes}
        self.assertIn(f"Added label {label1.name}", label_names)
        self.assertIn(f"Added label {label2.name}", label_names)

        self.do_request(
            "api:unit-detail",
            kwargs={"pk": unit.source_unit.pk},
            method="patch",
            code=200,
            superuser=True,
            request={"labels": [label1.id]},
        )

        changes = unit.source_unit.change_set.filter(action=ActionEvents.LABEL_REMOVE)
        self.assertEqual(changes.count(), 1)
        self.assertEqual(changes.first().target, f"Removed label {label2.name}")

        label1.delete()
        label2.delete()

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

    def test_delete_unit_locked(self) -> None:
        component = self._create_component(
            "po-mono",
            "po-mono/*.po",
            "po-mono/en.po",
            project=self.component.project,
            name="mono",
        )
        unit = Unit.objects.get(
            translation__component=component,
            translation__language_code="cs",
            source="Hello, world!\n",
        ).source_unit

        with patch(
            "weblate.trans.models.translation.Translation.delete_unit",
            side_effect=WeblateLockTimeoutError(
                "repository locked",
                lock=SimpleNamespace(scope="repository", origin="test/component"),
            ),
        ):
            self.do_request(
                "api:unit-detail",
                kwargs={"pk": unit.pk},
                method="delete",
                code=423,
                superuser=True,
                data={
                    "type": "client_error",
                    "errors": [
                        {
                            "code": "repository-locked",
                            "detail": "Could not remove the string because another background operation is in progress. Please try again later.",
                            "attr": None,
                        }
                    ],
                },
                format="json",
            )

    def test_delete_unit_component_locked(self) -> None:
        component = self._create_component(
            "po-mono",
            "po-mono/*.po",
            "po-mono/en.po",
            project=self.component.project,
            name="mono",
        )
        unit = Unit.objects.get(
            translation__component=component,
            translation__language_code="cs",
            source="Hello, world!\n",
        ).source_unit

        with patch(
            "weblate.trans.models.translation.Translation.delete_unit",
            side_effect=WeblateLockTimeoutError(
                "component locked",
                lock=SimpleNamespace(scope="component:update", origin="test/component"),
            ),
        ):
            self.do_request(
                "api:unit-detail",
                kwargs={"pk": unit.pk},
                method="delete",
                code=423,
                superuser=True,
                data={
                    "type": "client_error",
                    "errors": [
                        {
                            "code": "component-locked",
                            "detail": "Could not obtain the update lock for component test/component to perform the operation.",
                            "attr": None,
                        }
                    ],
                },
                format="json",
            )

    def test_unit_translations(self) -> None:
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

    def test_add_comment(self) -> None:
        unit = Unit.objects.get(
            translation__language_code="en", source="Thank you for using Weblate."
        )

        response = self.do_request(
            reverse("api:unit-comments", kwargs={"pk": unit.pk}),
            request={"scope": "global"},
            method="post",
            code=400,
        )
        self.assertEqual(
            response.data["errors"][0]["detail"], "This field is required."
        )
        self.assertEqual(response.data["errors"][0]["attr"], "comment")

        response = self.do_request(
            reverse("api:unit-comments", kwargs={"pk": unit.pk}),
            request={"scope": "xyz", "comment": "Hello World!"},
            method="post",
            code=400,
        )
        self.assertEqual(
            response.data["errors"][0]["detail"], '"xyz" is not a valid choice.'
        )

        response = self.do_request(
            reverse("api:unit-comments", kwargs={"pk": unit.pk}),
            request={"scope": "translation", "comment": "Hello World!"},
            method="post",
            code=400,
        )
        self.assertEqual(
            response.data["errors"][0]["detail"],
            '"translation" is not a valid choice for source units.',
        )

        response = self.do_request(
            reverse("api:unit-comments", kwargs={"pk": unit.pk}),
            request={"scope": "report", "comment": "Hello World!"},
            method="post",
            code=400,
        )
        self.assertEqual(
            response.data["errors"][0]["detail"],
            '"report" is not a valid choice as source review is disabled.',
        )

        # Enable reviews to test report comments
        project = unit.translation.component.project
        project.source_review = True
        project.save()
        response = self.do_request(
            reverse("api:unit-comments", kwargs={"pk": unit.pk}),
            request={"scope": "report", "comment": "Hello World!"},
            method="post",
            code=201,
        )
        self.assertIn("id", response.data)
        comment = response.data
        self.assertIn("id", comment)
        self.assertEqual(comment["comment"], "Hello World!")
        self.assertIn("timestamp", comment)
        self.assertEqual(comment["user"], "http://example.com/api/users/apitest/")

        unit_cs = Unit.objects.get(
            translation__language_code="cs", source="Thank you for using Weblate."
        )
        response = self.do_request(
            reverse("api:unit-comments", kwargs={"pk": unit_cs.pk}),
            request={"scope": "global", "comment": "Hello World Global!"},
            method="post",
            code=201,
        )
        self.assertIn("id", response.data)

        # Reload the object from database
        unit = Unit.objects.get(
            translation__language_code="en", source="Thank you for using Weblate."
        )
        self.assertCountEqual(
            unit.all_comments.values_list("comment", flat=True).all(),
            ["Hello World!", "Hello World Global!"],
        )

        self.create_acl()
        response = self.do_request(
            "api:translation-units",
            {
                "language__code": "en",
                "component__slug": "test",
                "component__project__slug": "acl",
            },
            method="post",
            superuser=True,
            request={"key": "key", "value": "Foo"},
            code=200,
        )
        new_unit = Unit.objects.get(pk=response.data["id"])
        self.do_request(
            reverse("api:unit-comments", kwargs={"pk": new_unit.pk}),
            request={"scope": "global", "comment": "another test"},
            method="post",
            superuser=True,
            code=201,
        )

        # test user has permission to view project but not edit
        project = unit.translation.component.project
        project.access_control = Project.ACCESS_PROTECTED
        project.save()
        response = self.do_request(
            reverse("api:unit-comments", kwargs={"pk": unit.pk}),
            request={"scope": "global", "comment": "another test"},
            method="post",
            code=403,
        )
        self.assertEqual(
            response.data["errors"][0]["detail"],
            "You do not have permission to perform this action.",
        )

    def test_import_comment(self) -> None:
        unit = Unit.objects.get(
            translation__language_code="en", source="Thank you for using Weblate."
        )
        response = self.do_request(
            reverse("api:unit-comments", kwargs={"pk": unit.pk}),
            request={"scope": "global", "comment": "test comment", "user_email": 1},
            method="post",
            code=400,
        )
        self.assertEqual(
            response.data["errors"][0]["detail"], "Enter a valid email address."
        )
        response = self.do_request(
            reverse("api:unit-comments", kwargs={"pk": unit.pk}),
            request={"scope": "global", "comment": "test comment", "timestamp": 1},
            method="post",
            code=400,
        )
        self.assertIn(
            "Datetime has wrong format.", response.data["errors"][0]["detail"]
        )

        user2 = User.objects.create_user(
            "commentimport", "commentimport@example.org", "x"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {user2.auth_token.key}")
        response = self.do_request(
            reverse("api:unit-comments", kwargs={"pk": unit.pk}),
            request={
                "scope": "global",
                "comment": "test comment",
                "timestamp": "20240101T12:00:00.000Z",
                "user_email": self.user.email,
            },
            method="post",
            authenticated=False,
            code=403,
        )
        self.assertEqual(
            response.data["errors"][0]["detail"],
            "You do not have permission to perform this action.",
        )
        response = self.do_request(
            reverse("api:unit-comments", kwargs={"pk": unit.pk}),
            request={
                "scope": "global",
                "comment": "test comment",
                "user_email": self.user.email,
            },
            method="post",
            authenticated=False,
            code=403,
        )
        self.assertEqual(
            response.data["errors"][0]["detail"],
            "You do not have permission to perform this action.",
        )

        text = "test import comment from different user"
        timestamp = datetime(2024, 1, 1, 12, 45, 0, tzinfo=UTC)
        response = self.do_request(
            reverse("api:unit-comments", kwargs={"pk": unit.pk}),
            request={
                "scope": "global",
                "comment": text,
                "timestamp": timestamp.isoformat(),
                "user_email": user2.email,
            },
            method="post",
            superuser=True,
            code=201,
        )
        comment = response.data
        self.assertIn("id", comment)
        self.assertEqual(comment["comment"], text)
        self.assertEqual(datetime.fromisoformat(comment["timestamp"]), timestamp)
        self.assertEqual(comment["user"], "http://example.com/api/users/commentimport/")

        text = "test import comment with fallback user"
        timestamp += +timedelta(hours=1)
        response = self.do_request(
            reverse("api:unit-comments", kwargs={"pk": unit.pk}),
            request={
                "scope": "global",
                "comment": text,
                "timestamp": timestamp.isoformat(),
                "user_email": "nonexistent@example.org",
            },
            method="post",
            superuser=True,
            code=201,
        )
        comment = response.data
        self.assertIn("id", comment)
        self.assertEqual(comment["comment"], text)
        self.assertEqual(datetime.fromisoformat(comment["timestamp"]), timestamp)
        self.assertEqual(comment["user"], "http://example.com/api/users/apitest/")

        text = "test import default timestamp"
        timestamp = datetime.now(UTC)
        response = self.do_request(
            reverse("api:unit-comments", kwargs={"pk": unit.pk}),
            request={
                "scope": "global",
                "comment": text,
                "user_email": "nonexistent@example.org",
            },
            method="post",
            superuser=True,
            code=201,
        )
        comment = response.data
        self.assertIn("id", comment)
        self.assertEqual(comment["comment"], text)
        self.assertGreaterEqual(datetime.fromisoformat(comment["timestamp"]), timestamp)
        self.assertEqual(comment["user"], "http://example.com/api/users/apitest/")

    def test_comment_serializer(self) -> None:
        # test CommentSerializer works even if unit is not provided in context
        serializer = CommentSerializer(
            data={"scope": "translation", "comment": "note"},
        )
        self.assertTrue(serializer.is_valid())

    def test_list_comments(self) -> None:
        unit = Unit.objects.get(
            translation__language_code="en", source="Thank you for using Weblate."
        )
        url = reverse("api:unit-comments", kwargs={"pk": unit.pk})
        response = self.do_request(url, method="get", code=200)
        self.assertIn("count", response.data)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(len(response.data["results"]), 0)

        self.do_request(
            url,
            request={"scope": "global", "comment": "First comment"},
            method="post",
            code=201,
        )
        self.do_request(
            url,
            request={"scope": "global", "comment": "Second comment"},
            method="post",
            code=201,
        )

        response = self.do_request(url, method="get", code=200)
        self.assertEqual(response.data["count"], 2)

        results = response.data["results"]
        self.assertEqual(len(results), 2)

        comments_text = [c["comment"] for c in results]
        self.assertIn("First comment", comments_text)
        self.assertIn("Second comment", comments_text)

        first_comment = results[0]
        self.assertIn("user", first_comment)
        self.assertIn("timestamp", first_comment)


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

    @override_settings(ALLOWED_ASSET_SIZE=1)
    def test_upload_too_big(self) -> None:
        self.authenticate(True)
        Screenshot.objects.get().image.delete()

        with open(TEST_SCREENSHOT, "rb") as handle:
            self.do_request(
                "api:screenshot-file",
                kwargs={"pk": Screenshot.objects.get().pk},
                method="post",
                code=400,
                superuser=True,
                data={
                    "errors": [
                        {
                            "attr": "image",
                            "code": "invalid",
                            "detail": "Uploaded file is too big.",
                        }
                    ],
                    "type": "validation_error",
                },
                request={"image": handle},
            )

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
                            "detail": "Translation not found.",
                        },
                        {
                            "attr": "component_slug",
                            "code": "invalid",
                            "detail": "Translation not found.",
                        },
                        {
                            "attr": "language_code",
                            "code": "invalid",
                            "detail": "Translation not found.",
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
        self.assertEqual(
            Change.objects.filter(
                action=ActionEvents.SCREENSHOT_UPLOADED,
                screenshot__name="Test create screenshot",
            ).count(),
            1,
        )

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
        self.assertContains(response, "Unit not found.", status_code=400)
        self.assertNotContains(
            response, "matching query does not exist", status_code=400
        )

    def test_units(self) -> None:
        self.authenticate(True)
        screenshot = Screenshot.objects.get()
        unit = self.component.source_translation.unit_set.all()[0]
        response = self.client.post(
            reverse("api:screenshot-units", kwargs={"pk": screenshot.pk}),
            {"unit_id": unit.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(unit.pk), response.data["units"][0])
        added_changes = Change.objects.filter(
            action=ActionEvents.SCREENSHOT_ADDED,
            screenshot=screenshot,
            unit=unit,
        )
        self.assertEqual(added_changes.count(), 1)
        self.assertEqual(added_changes[0].user, self.user)

    def test_units_delete(self) -> None:
        self.authenticate(True)
        screenshot = Screenshot.objects.get()
        unit = self.component.source_translation.unit_set.all()[0]
        self.client.post(
            reverse("api:screenshot-units", kwargs={"pk": screenshot.pk}),
            {"unit_id": unit.pk},
        )
        response = self.client.delete(
            reverse(
                "api:screenshot-delete-units",
                kwargs={"pk": screenshot.pk, "unit_id": 100000},
            ),
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.delete(
            reverse(
                "api:screenshot-delete-units",
                kwargs={"pk": screenshot.pk, "unit_id": unit.pk},
            ),
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(screenshot.units.all().count(), 0)
        removed_changes = Change.objects.filter(
            action=ActionEvents.SCREENSHOT_REMOVED,
            screenshot=screenshot,
            unit=unit,
        )
        self.assertEqual(removed_changes.count(), 1)
        self.assertEqual(removed_changes[0].user, self.user)


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
        self.assertEqual(response.data["version"], GIT_VERSION)

    @override_settings(VERSION_DISPLAY=VERSION_DISPLAY_SOFT, HIDE_VERSION=False)
    def test_metrics_openmetrics(self) -> None:
        self.authenticate()
        response = self.client.get(reverse("api:metrics"), {"format": "openmetrics"})
        self.assertContains(response, f'weblate_info{{version="{GIT_VERSION}"}} 1')
        self.assertContains(response, "# EOF")

    def test_metrics_csv(self) -> None:
        self.authenticate()
        response = self.client.get(reverse("api:metrics"), {"format": "csv"})
        self.assertContains(response, "units_translated")
        self.assertContains(response, GIT_VERSION)

    @override_settings(VERSION_DISPLAY=VERSION_DISPLAY_HIDE, HIDE_VERSION=True)
    def test_metrics_hide_mode_omits_version(self) -> None:
        self.authenticate()
        response = self.client.get(reverse("api:metrics"))
        self.assertNotIn("version", response.data)

        response = self.client.get(reverse("api:metrics"), {"format": "openmetrics"})
        self.assertNotContains(response, "weblate_info{")

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

    def test_result_anonymous(self) -> None:
        self.do_request(
            "api:search",
            request={"q": "test"},
            authenticated=False,
            data=[
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
                # No user search present here
            ],
        )

    def test_result(self) -> None:
        self.do_request(
            "api:search",
            request={"q": "test"},
            data=[
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
        response = self.do_request(
            "api:componentlist-components",
            kwargs={"slug": ComponentList.objects.get().slug},
            method="post",
            superuser=True,
            code=400,
            request={"component_id": -1},
        )
        self.assertContains(response, "Component not found.", status_code=400)
        self.assertNotContains(
            response, "matching query does not exist", status_code=400
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
        change = self.component.change_set.get(action=ActionEvents.ADDON_CREATE)
        self.assertEqual(change.user, self.user)
        # Existing
        self.create_addon(code=400)

    def test_delete(self) -> None:
        response = self.create_addon()
        self.do_request(
            "api:addon-detail",
            kwargs={"pk": response.data["id"]},
            method="delete",
            code=404,
        )
        self.do_request(
            "api:addon-detail",
            kwargs={"pk": response.data["id"]},
            method="delete",
            superuser=True,
            code=204,
        )

    def addon_scope_test(
        self,
        *,
        expect_access: bool,
        authenticated: bool,
        superuser: bool,
        add_user: str = "",
    ) -> None:
        project = self.component.project
        project.access_control = Project.ACCESS_PRIVATE
        project.save(update_fields=["access_control"])
        if add_user:
            project.add_user(self.user, add_user)

        addon_component = self.component.addon_set.create(
            name="weblate.gettext.linguas"
        )
        addon_project = project.addon_set.create(name="weblate.gettext.linguas")
        addon_site = Addon.objects.create(name="weblate.gettext.linguas")
        self.do_request(
            "api:addon-list",
            superuser=superuser,
            authenticated=authenticated,
            data={"count": (3 if superuser else 2) if expect_access else 0},
            skip={"results", "previous", "next"},
        )
        self.do_request(
            "api:addon-detail",
            kwargs={"pk": addon_component.pk},
            superuser=superuser,
            authenticated=authenticated,
            code=200 if expect_access else 404,
        )
        self.do_request(
            "api:addon-detail",
            kwargs={"pk": addon_project.pk},
            superuser=superuser,
            authenticated=authenticated,
            code=200 if expect_access else 404,
        )
        self.do_request(
            "api:addon-detail",
            kwargs={"pk": addon_site.pk},
            superuser=superuser,
            authenticated=authenticated,
            code=200 if expect_access and superuser else 404,
        )

    def test_access_anonymous(self) -> None:
        self.addon_scope_test(expect_access=False, authenticated=False, superuser=False)

    def test_access_superuser(self) -> None:
        self.addon_scope_test(expect_access=True, authenticated=True, superuser=True)

    def test_access_user(self) -> None:
        self.addon_scope_test(expect_access=False, authenticated=True, superuser=False)

    def test_access_user_member(self) -> None:
        self.addon_scope_test(
            expect_access=False,
            authenticated=True,
            superuser=False,
            add_user="Translate",
        )

    def test_access_user_admin(self) -> None:
        self.addon_scope_test(
            expect_access=True,
            authenticated=True,
            superuser=False,
            add_user="Administration",
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
            "language_regex": "^(?!xx).+$",
        }
        self.assertEqual(Component.objects.all().count(), 2)
        self.create_addon(name="weblate.discovery.discovery", configuration=initial)

        self.assertEqual(self.component.addon_set.get().configuration, initial)
        self.assertEqual(Component.objects.all().count(), 6)

    def test_edit(self) -> None:
        initial = {"path": "{{ filename|stripext }}.mo"}
        expected = {"path": "{{ language_code }}.mo"}
        response = self.create_addon(name="weblate.gettext.mo", configuration=initial)
        self.assertEqual(self.component.addon_set.get().configuration, initial)
        self.do_request(
            "api:addon-detail",
            kwargs={"pk": response.data["id"]},
            method="patch",
            code=404,
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
        self.create_project_addon(code=400)

    def test_delete_project_addon(self) -> None:
        response = self.create_project_addon()
        self.do_request(
            "api:addon-detail",
            kwargs={"pk": response.data["id"]},
            method="delete",
            code=404,
        )
        self.do_request(
            "api:addon-detail",
            kwargs={"pk": response.data["id"]},
            method="delete",
            superuser=True,
            code=204,
        )

    @patch("weblate.addons.tasks.run_addon_manually.delay_on_commit")
    def test_trigger_project_addon(self, mocked_delay) -> None:
        self.project.add_user(self.user, "Administration")
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        ).instance

        response = self.do_request(
            "api:addon-trigger",
            kwargs={"pk": addon.pk},
            method="post",
            superuser=False,
            code=202,
        )

        mocked_delay.assert_called_once_with(addon.pk)
        self.assertEqual(response.data["detail"], "Add-on run has been scheduled.")
        self.assertTrue(
            response.data["url"].endswith(
                reverse("api:addon-detail", kwargs={"pk": addon.pk})
            )
        )
        self.assertTrue(
            response.data["logs_url"].endswith(
                reverse("addon-logs", kwargs={"pk": addon.pk})
            )
        )

    def test_trigger_requires_manual_event(self) -> None:
        response = self.create_addon(name="weblate.gettext.authors")

        trigger = self.do_request(
            "api:addon-trigger",
            kwargs={"pk": response.data["id"]},
            method="post",
            superuser=True,
            code=400,
        )

        self.assertEqual(
            trigger.data["errors"][0]["detail"],
            "This add-on cannot be triggered manually.",
        )

    def test_trigger_without_permission(self) -> None:
        addon = LanguageConsistencyAddon.create(
            project=self.project, run=False
        ).instance

        self.do_request(
            "api:addon-trigger",
            kwargs={"pk": addon.pk},
            method="post",
            superuser=False,
            code=404,
        )

    @patch("weblate.addons.tasks.run_addon_manually.delay_on_commit")
    def test_trigger_category_addon(self, mocked_delay) -> None:
        category = Category.objects.create(
            name="API category",
            slug="api-category",
            project=self.project,
        )
        self.component.category = category
        self.component.save(update_fields=["category"])
        self.project.add_user(self.user, "Administration")
        addon = XgettextAddon.create(
            category=category,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        ).instance

        self.do_request(
            "api:addon-trigger",
            kwargs={"pk": addon.pk},
            method="post",
            superuser=False,
            code=202,
        )

        mocked_delay.assert_called_once_with(addon.pk)


class CategoryAPITest(APIBaseTest):
    def api_create_category(self, code: int = 201, **kwargs):
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
        self.api_create_category()
        response = self.list_categories()
        self.assertEqual(response.data["count"], 1)
        request = self.do_request("api:project-categories", self.project_kwargs)
        self.assertEqual(request.data["count"], 1)

    def test_create_nested(self) -> None:
        self.api_create_category()
        self.api_create_category(
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
        self.api_create_category()
        self.api_create_category(
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
        response = self.api_create_category()
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
        response = self.api_create_category()
        category_url = response.data["url"]
        self.do_request(
            category_url,
            method="patch",
            code=403,
        )
        self.do_request(
            category_url,
            method="patch",
            superuser=True,
            request={"slug": "test"},
            code=400,
        )
        self.do_request(
            category_url,
            method="patch",
            superuser=True,
            request={"slug": "test-unused"},
        )

    def test_component(self) -> None:
        response = self.api_create_category()
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
        response = self.do_request(f"{response.data['url']}translations/")
        self.assertEqual(response.data["count"], 4)

        for translation in response.data["results"]:
            self.do_request(translation["url"])

    def test_statistics(self) -> None:
        # Create a category to get the statistics from
        response = self.api_create_category()
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

        found = False
        for response_label in response.data["results"]:
            if response_label["id"] == label.id:
                self.assertEqual(response_label["name"], label.name)
                self.assertEqual(response_label["description"], label.description)
                self.assertEqual(response_label["color"], label.color)
                found = True
        self.assertTrue(found, "Created label not found in response")

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

    def test_delete_label(self) -> None:
        """Test deleting a label from a project."""
        # First create a label
        label = self.component.project.label_set.create(
            name="Test Label to Delete", color="red"
        )

        # Add it to some units
        for unit in self.component.source_translation.unit_set.all():
            unit.labels.add(label)

        # Test successful deletion
        self.do_request(
            "api:project-delete-labels",
            kwargs={"slug": self.component.project.slug, "label_id": label.id},
            method="delete",
            superuser=True,
            code=204,
        )

        # Verify label was deleted
        self.assertFalse(self.component.project.label_set.filter(id=label.id).exists())

    def test_delete_label_permission_denied(self) -> None:
        """Test that non-admin users cannot delete labels."""
        label = self.component.project.label_set.create(
            name="Test Label to Delete", color="red"
        )

        self.do_request(
            "api:project-delete-labels",
            kwargs={"slug": self.component.project.slug, "label_id": label.id},
            method="delete",
            superuser=False,
            code=403,
        )

        # Verify label still exists
        self.assertTrue(self.component.project.label_set.filter(id=label.id).exists())

    def test_delete_nonexistent_label(self) -> None:
        """Test deleting a label that doesn't exist."""
        self.do_request(
            "api:project-delete-labels",
            kwargs={"slug": self.component.project.slug, "label_id": 99999},
            method="delete",
            superuser=True,
            code=404,
        )

    def test_delete_label_wrong_project(self) -> None:
        """Test deleting a label from wrong project returns error."""
        # Create a label in one project
        label = self.component.project.label_set.create(name="Test Label", color="red")

        # Create another project for testing
        project2 = Project.objects.create(
            name="Test Project 2",
            slug="test-project-2",
            access_control=Project.ACCESS_PRIVATE,
        )

        self.do_request(
            "api:project-delete-labels",
            kwargs={"slug": project2.slug, "label_id": label.id},
            method="delete",
            superuser=True,
            code=404,
        )

        # Verify label still exists in original project
        self.assertTrue(self.component.project.label_set.filter(id=label.id).exists())


class AnnouncementAPITest(APIBaseTest):
    def setUp(self) -> None:
        super().setUp()
        # Create announcements for get and delete tests
        self.category = self.component.project.category_set.create(
            name="Category", slug="category"
        )
        self.project_announcement = Announcement.objects.create(
            project=self.component.project, message="Test project announcement"
        )
        self.category_announcement = Announcement.objects.create(
            project=self.component.project,
            category=self.category,
            message="Test category announcement",
        )
        self.component_announcement = Announcement.objects.create(
            project=self.component.project,
            component=self.component,
            message="Test component announcement",
        )
        self.translation_announcement = Announcement.objects.create(
            project=self.component.project,
            component=self.component,
            language=Language.objects.get(code="cs"),
            message="Test translation announcement",
        )

    def test_get_project_announcement(self) -> None:
        response = self.do_request(
            "api:project-announcements",
            kwargs=self.project_kwargs,
            method="get",
            code=200,
        )
        self.assertEqual(response.data["count"], 1)

    def test_project_announcement_options(self) -> None:
        response = self.do_request(
            "api:project-announcements",
            kwargs=self.project_kwargs,
            method="options",
        )
        fields = response.data["actions"]["POST"]
        self.assertLessEqual(
            {"id", "message", "severity", "expiry", "notify"},
            set(fields),
        )
        self.assertTrue(fields["id"]["read_only"])
        self.assertNotIn("name", fields)
        self.assertNotIn("slug", fields)

    def test_create_project_announcement(self) -> None:
        project = self.component.project
        self.authenticate(False)

        self.do_request(
            "api:project-announcements",
            kwargs=self.project_kwargs,
            method="post",
            request={
                "message": "Test message",
                "severity": "info",
                "expiry": date(2026, 1, 1),
                "notify": False,
            },
            code=403,
        )

        self.grant_perm_to_user("announcement.add", "test", project)
        response = self.do_request(
            "api:project-announcements",
            kwargs=self.project_kwargs,
            method="post",
            request={
                "message": "Test message",
                "severity": "info",
                "expiry": date(2026, 1, 1),
                "notify": False,
            },
            code=201,
        )
        announcement = Announcement.objects.filter(project=project).get(
            id=response.data["id"]
        )
        self.assertIsNotNone(announcement)
        self.assertEqual(announcement.project, project)
        self.assertIsNone(announcement.component)
        self.assertIsNone(announcement.language)

    def test_delete_project_announcement(self) -> None:
        """Test deleting an announcement from a project."""
        announcement = self.project_announcement

        # Test successful deletion
        self.do_request(
            "api:project-delete-announcement",
            kwargs={**self.project_kwargs, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=204,
        )

        # Verify announcement was deleted
        self.assertFalse(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_project_announcement_permission_denied(self) -> None:
        """Test that non-admin users cannot delete announcements."""
        announcement: Announcement = self.project_announcement

        self.do_request(
            "api:project-delete-announcement",
            kwargs={**self.project_kwargs, "announcement_id": announcement.id},
            method="delete",
            superuser=False,
            code=403,
        )

        # Verify announcement still exists
        self.assertTrue(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_nonexistent_project_announcement(self) -> None:
        """Test deleting an announcement that doesn't exist."""
        self.do_request(
            "api:project-delete-announcement",
            kwargs={**self.project_kwargs, "announcement_id": 9999},
            method="delete",
            superuser=True,
            code=404,
        )

    def test_delete_project_announcement_wrong_project(self) -> None:
        """Test deleting an announcement from wrong project returns error."""
        # Announcement from one project
        announcement = self.project_announcement

        # Create another project for testing
        project2 = Project.objects.create(
            name="Test Project 2",
            slug="test-project-2",
            access_control=Project.ACCESS_PRIVATE,
        )

        self.do_request(
            "api:project-delete-announcement",
            kwargs={"slug": project2.slug, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=404,
        )

        # Verify announcement still exists
        self.assertTrue(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_project_announcement_wrong_scope(self) -> None:
        """Test deleting a project announcement via the category, component or translation scope returns not found."""
        announcement: Announcement = self.project_announcement

        self.do_request(
            "api:category-delete-announcement",
            kwargs={"pk": self.category.pk, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:component-delete-announcement",
            kwargs={**self.component_kwargs, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:translation-delete-announcement",
            kwargs={**self.translation_kwargs, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=404,
        )

        # Verify announcement still exists
        self.assertTrue(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_project_scope_other_announcements(self) -> None:
        """Test deleting a category, component or translation announcement via the project scope returns not found."""
        self.do_request(
            "api:project-delete-announcement",
            kwargs={
                **self.project_kwargs,
                "announcement_id": self.category_announcement.id,
            },
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:project-delete-announcement",
            kwargs={
                **self.project_kwargs,
                "announcement_id": self.component_announcement.id,
            },
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:project-delete-announcement",
            kwargs={
                **self.project_kwargs,
                "announcement_id": self.translation_announcement.id,
            },
            method="delete",
            superuser=True,
            code=404,
        )

        # Verify announcements still exists
        self.assertTrue(
            Announcement.objects.filter(id=self.category_announcement.id).exists()
        )
        self.assertTrue(
            Announcement.objects.filter(id=self.component_announcement.id).exists()
        )
        self.assertTrue(
            Announcement.objects.filter(id=self.translation_announcement.id).exists()
        )

    def test_get_category_announcement(self) -> None:
        response = self.do_request(
            "api:category-announcements",
            kwargs={"pk": self.category.pk},
            method="get",
            code=200,
        )
        self.assertEqual(response.data["count"], 1)

    def test_create_category_announcement(self) -> None:
        category = self.category
        self.authenticate(False)

        self.do_request(
            "api:category-announcements",
            kwargs={"pk": self.category.pk},
            method="post",
            request={
                "message": "Test message",
                "severity": "info",
                "expiry": date(2026, 1, 1),
                "notify": False,
            },
            code=403,
        )

        self.grant_perm_to_user("announcement.add", "test", category.project)
        response = self.do_request(
            "api:category-announcements",
            kwargs={"pk": self.category.pk},
            method="post",
            request={
                "message": "Test message",
                "severity": "info",
                "expiry": date(2026, 1, 1),
                "notify": False,
            },
            code=201,
        )
        announcement = Announcement.objects.filter(category=category).get(
            id=response.data["id"]
        )
        self.assertIsNotNone(announcement)
        self.assertEqual(announcement.project, category.project)
        self.assertEqual(announcement.category, category)
        self.assertIsNone(announcement.component)
        self.assertIsNone(announcement.language)

    def test_delete_category_announcement(self) -> None:
        """Test deleting an announcement from a category."""
        announcement = self.category_announcement

        # Test successful deletion
        self.do_request(
            "api:category-delete-announcement",
            kwargs={"pk": self.category.pk, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=204,
        )

        # Verify announcement was deleted
        self.assertFalse(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_category_announcement_permission_denied(self) -> None:
        """Test that non-admin users cannot delete announcements."""
        announcement: Announcement = self.category_announcement

        self.do_request(
            "api:category-delete-announcement",
            kwargs={"pk": self.category.pk, "announcement_id": announcement.id},
            method="delete",
            superuser=False,
            code=403,
        )

        # Verify announcement still exists
        self.assertTrue(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_nonexistent_category_announcement(self) -> None:
        """Test deleting an announcement that doesn't exist."""
        self.do_request(
            "api:category-delete-announcement",
            kwargs={"pk": self.category.pk, "announcement_id": 9999},
            method="delete",
            superuser=True,
            code=404,
        )

    def test_delete_category_announcement_wrong_category(self) -> None:
        """Test deleting an announcement from wrong category returns error."""
        # Announcement from one category
        announcement = self.category_announcement

        # Create another category for testing
        category2 = self.component.project.category_set.create(
            name="Test category 2",
            slug="test-category-2",
        )

        self.do_request(
            "api:category-delete-announcement",
            kwargs={
                "pk": category2.pk,
                "announcement_id": announcement.id,
            },
            method="delete",
            superuser=True,
            code=404,
        )

        # Verify announcement still exists
        self.assertTrue(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_category_announcement_wrong_scope(self) -> None:
        """Test deleting a category announcement via the project, component or translation scope returns not found."""
        announcement: Announcement = self.category_announcement

        self.do_request(
            "api:project-delete-announcement",
            kwargs={**self.project_kwargs, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:component-delete-announcement",
            kwargs={**self.component_kwargs, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:translation-delete-announcement",
            kwargs={**self.translation_kwargs, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=404,
        )

        # Verify announcement still exists
        self.assertTrue(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_category_scope_other_announcements(self) -> None:
        """Test deleting a project, component or translation announcement via the category scope returns not found."""
        self.do_request(
            "api:category-delete-announcement",
            kwargs={
                "pk": self.category.pk,
                "announcement_id": self.project_announcement.id,
            },
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:category-delete-announcement",
            kwargs={
                "pk": self.category.pk,
                "announcement_id": self.component_announcement.id,
            },
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:category-delete-announcement",
            kwargs={
                "pk": self.category.pk,
                "announcement_id": self.translation_announcement.id,
            },
            method="delete",
            superuser=True,
            code=404,
        )

        # Verify announcements still exists
        self.assertTrue(
            Announcement.objects.filter(id=self.project_announcement.id).exists()
        )
        self.assertTrue(
            Announcement.objects.filter(id=self.component_announcement.id).exists()
        )
        self.assertTrue(
            Announcement.objects.filter(id=self.translation_announcement.id).exists()
        )

    def test_get_component_announcement(self) -> None:
        response = self.do_request(
            "api:component-announcements",
            kwargs=self.component_kwargs,
            method="get",
            code=200,
        )
        self.assertEqual(response.data["count"], 1)

    def test_create_component_announcement(self) -> None:
        component = self.component
        self.authenticate(False)

        self.do_request(
            "api:component-announcements",
            kwargs=self.component_kwargs,
            method="post",
            request={
                "message": "Test message",
                "severity": "info",
                "expiry": date(2026, 1, 1),
                "notify": False,
            },
            code=403,
        )

        self.grant_perm_to_user("announcement.add", "test", component.project)
        response = self.do_request(
            "api:component-announcements",
            kwargs=self.component_kwargs,
            method="post",
            request={
                "message": "Test message",
                "severity": "info",
                "expiry": date(2026, 1, 1),
                "notify": False,
            },
            code=201,
        )
        announcement = Announcement.objects.filter(component=component).get(
            id=response.data["id"]
        )
        self.assertIsNotNone(announcement)
        self.assertEqual(announcement.project, component.project)
        self.assertEqual(announcement.component, component)
        self.assertIsNone(announcement.language)

    def test_delete_component_announcement(self) -> None:
        """Test deleting an announcement from a component."""
        announcement = self.component_announcement

        # Test successful deletion
        self.do_request(
            "api:component-delete-announcement",
            kwargs={**self.component_kwargs, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=204,
        )

        # Verify announcement was deleted
        self.assertFalse(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_component_announcement_permission_denied(self) -> None:
        """Test that non-admin users cannot delete announcements."""
        announcement: Announcement = self.component_announcement

        self.do_request(
            "api:component-delete-announcement",
            kwargs={**self.component_kwargs, "announcement_id": announcement.id},
            method="delete",
            superuser=False,
            code=403,
        )

        # Verify announcement still exists
        self.assertTrue(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_nonexistent_component_announcement(self) -> None:
        """Test deleting an announcement that doesn't exist."""
        self.do_request(
            "api:component-delete-announcement",
            kwargs={**self.component_kwargs, "announcement_id": 9999},
            method="delete",
            superuser=True,
            code=404,
        )

    def test_delete_component_announcement_wrong_component(self) -> None:
        """Test deleting an announcement from wrong component returns error."""
        # Announcement from one component
        announcement = self.component_announcement

        # Create another component for testing
        component2 = self.create_po(
            project=announcement.project,
            name="Test Component 2",
            slug="test-component-2",
        )

        self.do_request(
            "api:component-delete-announcement",
            kwargs={
                "slug": component2.slug,
                "project__slug": component2.project.slug,
                "announcement_id": announcement.id,
            },
            method="delete",
            superuser=True,
            code=404,
        )

        # Verify announcement still exists
        self.assertTrue(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_component_announcement_wrong_scope(self) -> None:
        """Test deleting a component announcement via the project, category or translation scope returns not found."""
        announcement: Announcement = self.component_announcement

        self.do_request(
            "api:project-delete-announcement",
            kwargs={**self.project_kwargs, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:category-delete-announcement",
            kwargs={"pk": self.category.pk, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:translation-delete-announcement",
            kwargs={**self.translation_kwargs, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=404,
        )

        # Verify announcement still exists
        self.assertTrue(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_component_scope_other_announcements(self) -> None:
        """Test deleting a project, category or translation announcement via the component scope returns not found."""
        self.do_request(
            "api:component-delete-announcement",
            kwargs={
                **self.component_kwargs,
                "announcement_id": self.project_announcement.id,
            },
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:component-delete-announcement",
            kwargs={
                **self.component_kwargs,
                "announcement_id": self.category_announcement.id,
            },
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:component-delete-announcement",
            kwargs={
                **self.component_kwargs,
                "announcement_id": self.translation_announcement.id,
            },
            method="delete",
            superuser=True,
            code=404,
        )

        # Verify announcements still exists
        self.assertTrue(
            Announcement.objects.filter(id=self.project_announcement.id).exists()
        )
        self.assertTrue(
            Announcement.objects.filter(id=self.category_announcement.id).exists()
        )
        self.assertTrue(
            Announcement.objects.filter(id=self.translation_announcement.id).exists()
        )

    def test_get_translation_announcement(self) -> None:
        response = self.do_request(
            "api:translation-announcements",
            kwargs=self.translation_kwargs,
            method="get",
            code=200,
        )
        self.assertEqual(response.data["count"], 1)

    def test_create_translation_announcement(self) -> None:
        component = self.component
        self.authenticate(False)

        self.do_request(
            "api:translation-announcements",
            kwargs=self.translation_kwargs,
            method="post",
            request={
                "message": "Test message",
                "severity": "info",
                "expiry": date(2026, 1, 1),
                "notify": False,
            },
            code=403,
        )

        self.grant_perm_to_user("announcement.add", "test", component.project)
        response = self.do_request(
            "api:translation-announcements",
            kwargs=self.translation_kwargs,
            method="post",
            request={
                "message": "Test message",
                "severity": "info",
                "expiry": date(2026, 1, 1),
                "notify": False,
            },
            code=201,
        )
        announcement = (
            Announcement.objects.filter(component=component)
            .filter(language__code="cs")
            .get(id=response.data["id"])
        )
        self.assertIsNotNone(announcement)
        self.assertEqual(announcement.project, component.project)
        self.assertEqual(announcement.component, component)
        self.assertEqual(
            announcement.language.code, self.translation_kwargs["language__code"]
        )

    def test_delete_translation_announcement(self) -> None:
        """Test deleting an announcement from a translation."""
        announcement = self.translation_announcement

        # Test successful deletion
        self.do_request(
            "api:translation-delete-announcement",
            kwargs={**self.translation_kwargs, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=204,
        )

        # Verify announcement was deleted
        self.assertFalse(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_translation_announcement_permission_denied(self) -> None:
        """Test that non-admin users cannot delete announcements."""
        announcement: Announcement = self.translation_announcement

        self.do_request(
            "api:translation-delete-announcement",
            kwargs={**self.translation_kwargs, "announcement_id": announcement.id},
            method="delete",
            superuser=False,
            code=403,
        )

        # Verify announcement still exists
        self.assertTrue(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_nonexistent_translation_announcement(self) -> None:
        """Test deleting an announcement that doesn't exist."""
        self.do_request(
            "api:translation-delete-announcement",
            kwargs={**self.translation_kwargs, "announcement_id": 9999},
            method="delete",
            superuser=True,
            code=404,
        )

    def test_delete_translation_announcement_wrong_translation(self) -> None:
        """Test deleting an announcement from wrong translation returns error."""
        # Announcement from one translation
        announcement = self.translation_announcement

        # Create another translation for testing
        translation2, _created = Translation.objects.get_or_create(
            component=self.component, language=Language.objects.get(code="en")
        )

        self.do_request(
            "api:translation-delete-announcement",
            kwargs={
                "language__code": translation2.language.code,
                "component__slug": translation2.component.slug,
                "component__project__slug": translation2.component.project.slug,
                "announcement_id": announcement.id,
            },
            method="delete",
            superuser=True,
            code=404,
        )

        # Verify announcement still exists
        self.assertTrue(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_translation_announcement_wrong_scope(self) -> None:
        """Test deleting a translation announcement via the project, category or component scope returns not found."""
        announcement: Announcement = self.translation_announcement

        self.do_request(
            "api:project-delete-announcement",
            kwargs={**self.project_kwargs, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:category-delete-announcement",
            kwargs={"pk": self.category.pk, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:component-delete-announcement",
            kwargs={**self.component_kwargs, "announcement_id": announcement.id},
            method="delete",
            superuser=True,
            code=404,
        )

        # Verify announcement still exists
        self.assertTrue(Announcement.objects.filter(id=announcement.id).exists())

    def test_delete_translation_scope_other_announcements(self) -> None:
        """Test deleting a project, category or component announcement via the translation scope returns not found."""
        self.do_request(
            "api:translation-delete-announcement",
            kwargs={
                **self.translation_kwargs,
                "announcement_id": self.project_announcement.id,
            },
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:translation-delete-announcement",
            kwargs={
                **self.translation_kwargs,
                "announcement_id": self.category_announcement.id,
            },
            method="delete",
            superuser=True,
            code=404,
        )

        self.do_request(
            "api:translation-delete-announcement",
            kwargs={
                **self.translation_kwargs,
                "announcement_id": self.component_announcement.id,
            },
            method="delete",
            superuser=True,
            code=404,
        )

        # Verify announcements still exists
        self.assertTrue(
            Announcement.objects.filter(id=self.project_announcement.id).exists()
        )
        self.assertTrue(
            Announcement.objects.filter(id=self.category_announcement.id).exists()
        )
        self.assertTrue(
            Announcement.objects.filter(id=self.component_announcement.id).exists()
        )


class OpenAPITest(APIBaseTest):
    def get_schema(self) -> dict:
        response = self.do_request("api-schema")
        return yaml.safe_load(response.content)

    def test_view(self) -> None:
        response = self.do_request(
            "api-schema",
        )
        # Ensure schema includes the language-specific project download parameter
        self.assertIn("language_code", response.content.decode())

    def test_metrics_version_is_optional(self) -> None:
        schema = self.get_schema()
        required = schema["components"]["schemas"]["Metrics"]["required"]
        self.assertNotIn("version", required)

    def test_addon_trigger_schema_matches_runtime_behavior(self) -> None:
        schema = self.get_schema()
        operation = schema["paths"]["/api/addons/{id}/trigger/"]["post"]

        self.assertNotIn("requestBody", operation)
        self.assertNotIn("200", operation["responses"])
        self.assertIn("202", operation["responses"])

        response_schema = operation["responses"]["202"]["content"]["application/json"][
            "schema"
        ]
        self.assertEqual(
            response_schema, {"$ref": "#/components/schemas/AddonTriggerResponse"}
        )
        self.assertEqual(
            schema["components"]["schemas"]["AddonTriggerResponse"]["required"],
            ["detail", "logs_url", "url"],
        )

    @patch("weblate.utils.version.VERSION", "5.17.1")
    def test_view_uses_latest_docs_links(self) -> None:
        response = self.do_request("api-schema")
        content = response.content.decode()
        self.assertIn("/latest/contributing/license.html", content)
        self.assertIn("/latest/index.html", content)
        self.assertNotIn("/weblate-5.17.1/index.html", content)

    def test_action_statistics_schema_matches_runtime_behavior(self) -> None:
        schema = self.get_schema()

        self.assertEqual(
            schema["paths"]["/api/projects/{slug}/statistics/"]["get"]["responses"][
                "200"
            ]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/Statistics"},
        )
        self.assertEqual(
            schema["paths"]["/api/projects/{slug}/languages/"]["get"]["responses"][
                "200"
            ]["content"]["application/json"]["schema"],
            {
                "type": "array",
                "items": {"$ref": "#/components/schemas/Statistics"},
            },
        )
        self.assertEqual(
            schema["paths"]["/api/components/{project__slug}/{slug}/statistics/"][
                "get"
            ]["responses"]["200"]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/PaginatedStatisticsList"},
        )
        self.assertEqual(
            schema["components"]["schemas"]["PaginatedStatisticsList"]["properties"][
                "results"
            ],
            {
                "type": "array",
                "items": {"$ref": "#/components/schemas/Statistics"},
            },
        )
        self.assertEqual(
            schema["paths"]["/api/users/{username}/statistics/"]["get"]["responses"][
                "200"
            ]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/UserStatistics"},
        )
        statistics_properties = schema["components"]["schemas"]["Statistics"][
            "properties"
        ]
        self.assertIn("total", statistics_properties)
        self.assertIn("translated", statistics_properties)
        self.assertIn("comments", statistics_properties)
        self.assertIn("readonly_chars_percent", statistics_properties)

    def test_translation_units_create_schema_matches_runtime_behavior(self) -> None:
        schema = self.get_schema()
        operation = schema["paths"][
            "/api/translations/{component__project__slug}/{component__slug}/{language__code}/units/"
        ]["post"]

        request_schema = {"$ref": "#/components/schemas/NewUnitRequest"}
        self.assertEqual(
            operation["requestBody"]["content"],
            {"application/json": {"schema": request_schema}},
        )

        new_unit_request = schema["components"]["schemas"]["NewUnitRequest"]
        self.assertEqual(
            new_unit_request["oneOf"],
            [
                {"$ref": "#/components/schemas/MonolingualUnit"},
                {"$ref": "#/components/schemas/BilingualUnit"},
                {"$ref": "#/components/schemas/BilingualSourceUnit"},
            ],
        )
        self.assertNotEqual(
            request_schema, {"$ref": "#/components/schemas/Translation"}
        )

    def test_string_state_enum_schema_names_are_stable(self) -> None:
        schema = self.get_schema()
        schemas = schema["components"]["schemas"]

        self.assertIn("StringStateEnum", schemas)
        self.assertIn("NewUnitStateEnum", schemas)
        self.assertNotIn("StateFd1Enum", schemas)
        self.assertNotIn("State180Enum", schemas)

        self.assertEqual(
            schemas["MonolingualUnit"]["properties"]["state"],
            {"$ref": "#/components/schemas/NewUnitStateEnum"},
        )
        self.assertEqual(
            schemas["UnitWrite"]["properties"]["state"]["allOf"],
            [{"$ref": "#/components/schemas/StringStateEnum"}],
        )

    def test_error_response_schemas_are_shared(self) -> None:
        schema = self.get_schema()
        schemas = schema["components"]["schemas"]

        self.assertIn("ErrorResponse400", schemas)
        self.assertFalse(
            any(
                name.startswith("Api") and ("Error" in name or "Validation" in name)
                for name in schemas
            )
        )

        response_content = schema["paths"]["/api/projects/"]["post"]["responses"][
            "400"
        ]["content"]
        expected_schema = {"$ref": "#/components/schemas/ErrorResponse400"}
        self.assertEqual(
            response_content["application/json"]["schema"], expected_schema
        )
        self.assertNotIn("text/csv", response_content)

        code_schema = schemas["Error400"]["properties"]["code"]
        self.assertEqual(code_schema["type"], "string")
        self.assertNotIn("enum", code_schema)
        self.assertIn("required", code_schema["examples"])
        self.assertIn("parse_error", code_schema["examples"])

    def test_license_schema_is_plain_string(self) -> None:
        schema = self.get_schema()
        schemas = schema["components"]["schemas"]

        self.assertNotIn("LicenseEnum", schemas)

        for schema_name in ("Component", "ProjectComponent", "PatchedComponent"):
            license_schema = schemas[schema_name]["properties"]["license"]
            self.assertEqual(license_schema["type"], "string")
            self.assertEqual(license_schema["maxLength"], 150)
            self.assertNotIn("enum", license_schema)
            self.assertNotIn("oneOf", license_schema)
            self.assertIn("MIT", license_schema["examples"])
            self.assertIn("GPL-3.0-or-later", license_schema["examples"])
            self.assertIn("proprietary", license_schema["examples"])

    def test_duplicate_small_schemas_are_reused(self) -> None:
        schema = self.get_schema()
        schemas = schema["components"]["schemas"]

        self.assertNotIn("UnitLabels", schemas)
        self.assertNotIn("UnitFlatLabels", schemas)
        self.assertEqual(
            schemas["Unit"]["properties"]["labels"]["items"],
            {"$ref": "#/components/schemas/Label"},
        )
        self.assertEqual(
            schemas["UnitWrite"]["properties"]["labels"]["items"],
            {"type": "integer"},
        )

        self.assertIn("MessageResponse", schemas)
        self.assertNotIn("patch_200_Message_response_serializer", schemas)
        self.assertNotIn("post_201_Message_response_serializer", schemas)
        self.assertNotIn("put_200_Message_response_serializer", schemas)

    def test_schema_media_types_are_trimmed(self) -> None:
        schema = self.get_schema()

        for path, path_item in schema["paths"].items():
            for method, operation in path_item.items():
                if method not in {"delete", "get", "patch", "post", "put"}:
                    continue

                if path != "/api/metrics/":
                    self.assertFalse(
                        any(
                            parameter["name"] == "format" and parameter["in"] == "query"
                            for parameter in operation.get("parameters", ())
                        ),
                        f"{method.upper()} {path} should not expose format query",
                    )

                if "requestBody" not in operation:
                    self.assertNotIn(
                        "415",
                        operation.get("responses", {}),
                        f"{method.upper()} {path} should not expose 415",
                    )

                for status_code, response in operation.get("responses", {}).items():
                    content = response.get("content", {})
                    if (
                        path == "/api/metrics/"
                        and method == "get"
                        and status_code == "200"
                    ):
                        self.assertEqual(
                            content["text/csv"]["schema"], {"type": "string"}
                        )
                        self.assertEqual(
                            content["application/openmetrics-text"]["schema"],
                            {"type": "string"},
                        )
                        continue

                    self.assertNotIn("text/csv", content)
                    self.assertNotIn("application/openmetrics-text", content)

        self.assertEqual(
            schema["paths"]["/api/projects/{slug}/components/"]["post"]["requestBody"][
                "content"
            ].keys(),
            {"application/json", "multipart/form-data"},
        )

    def test_search_and_task_schema_matches_runtime_behavior(self) -> None:
        schema = self.get_schema()

        search = schema["paths"]["/api/search/"]["get"]
        self.assertEqual(search["operationId"], "api_search_retrieve")
        self.assertIn(
            {
                "in": "query",
                "name": "q",
                "schema": {"type": "string"},
                "description": "Search query.",
            },
            search["parameters"],
        )
        self.assertEqual(
            search["responses"]["200"]["content"]["application/json"]["schema"],
            {
                "type": "array",
                "items": {"$ref": "#/components/schemas/SearchResult"},
            },
        )
        self.assertEqual(
            schema["components"]["schemas"]["SearchResult"]["required"],
            ["category", "name", "url"],
        )

        task = schema["paths"]["/api/tasks/{id}/"]["get"]
        self.assertEqual(
            task["responses"]["200"]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/Task"},
        )
        task_schema = schema["components"]["schemas"]["Task"]
        self.assertEqual(
            task_schema["required"], ["completed", "log", "progress", "result"]
        )
        self.assertEqual(
            task_schema["properties"]["completed"],
            {"type": "boolean"},
        )
        self.assertEqual(
            task_schema["properties"]["progress"],
            {"type": "integer", "maximum": 100, "minimum": 0},
        )
        self.assertEqual(task_schema["properties"]["log"], {"type": "string"})
        self.assertEqual(
            task_schema["properties"]["result"]["oneOf"].count({"type": "null"}), 1
        )

    def test_action_nested_list_schema_matches_runtime_behavior(self) -> None:
        schema = self.get_schema()

        self.assertEqual(
            schema["paths"]["/api/projects/{slug}/components/"]["get"]["responses"][
                "200"
            ]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/PaginatedProjectComponentList"},
        )
        self.assertNotIn(
            "project",
            schema["components"]["schemas"]["ProjectComponent"]["properties"],
        )
        self.assertEqual(
            schema["paths"]["/api/components/{project__slug}/{slug}/translations/"][
                "get"
            ]["responses"]["200"]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/PaginatedComponentTranslationList"},
        )
        self.assertNotIn(
            "component",
            schema["components"]["schemas"]["ComponentTranslation"]["properties"],
        )

    def test_action_repository_and_lock_schema_matches_runtime_behavior(self) -> None:
        schema = self.get_schema()

        project_repository = schema["paths"]["/api/projects/{slug}/repository/"]
        self.assertEqual(
            project_repository["get"]["responses"]["200"]["content"][
                "application/json"
            ]["schema"],
            {"$ref": "#/components/schemas/Repository"},
        )
        self.assertEqual(
            project_repository["post"]["requestBody"]["content"]["application/json"][
                "schema"
            ],
            {"$ref": "#/components/schemas/RepoRequest"},
        )
        self.assertEqual(
            project_repository["post"]["responses"]["200"]["content"][
                "application/json"
            ]["schema"],
            {"$ref": "#/components/schemas/RepositoryOperation"},
        )
        component_lock = schema["paths"]["/api/components/{project__slug}/{slug}/lock/"]
        self.assertEqual(
            component_lock["get"]["responses"]["200"]["content"]["application/json"][
                "schema"
            ],
            {"$ref": "#/components/schemas/Lock"},
        )
        self.assertEqual(
            component_lock["post"]["responses"]["200"]["content"]["application/json"][
                "schema"
            ],
            {"$ref": "#/components/schemas/Lock"},
        )
        self.assertEqual(
            schema["paths"]["/api/projects/{slug}/lock/"]["post"]["responses"]["200"][
                "content"
            ]["application/json"]["schema"],
            {"$ref": "#/components/schemas/ProjectLock"},
        )

    def test_file_action_schema_matches_runtime_behavior(self) -> None:
        schema = self.get_schema()

        translation_file = schema["paths"][
            "/api/translations/{component__project__slug}/{component__slug}/{language__code}/file/"
        ]
        self.assertEqual(
            translation_file["get"]["responses"]["200"]["content"][
                "application/octet-stream"
            ]["schema"],
            {"type": "string", "format": "binary"},
        )
        self.assertEqual(
            translation_file["post"]["responses"]["200"]["content"]["application/json"][
                "schema"
            ],
            {"$ref": "#/components/schemas/UploadResult"},
        )
        self.assertEqual(
            translation_file["post"]["requestBody"]["content"]["multipart/form-data"][
                "schema"
            ],
            {"$ref": "#/components/schemas/UploadRequest"},
        )
        self.assertEqual(
            set(translation_file["post"]["requestBody"]["content"]),
            {"multipart/form-data"},
        )

        screenshot_file = schema["paths"]["/api/screenshots/{id}/file/"]
        self.assertEqual(
            screenshot_file["get"]["responses"]["200"]["content"][
                "application/octet-stream"
            ]["schema"],
            {"type": "string", "format": "binary"},
        )
        self.assertEqual(
            screenshot_file["post"]["responses"]["200"]["content"]["application/json"][
                "schema"
            ],
            {"$ref": "#/components/schemas/BooleanResult"},
        )
        self.assertEqual(
            screenshot_file["post"]["requestBody"]["content"],
            {
                "multipart/form-data": {
                    "schema": {"$ref": "#/components/schemas/ScreenshotFile"}
                }
            },
        )

    def test_redoc(self) -> None:
        self.do_request("redoc")
