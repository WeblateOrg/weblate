# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.auth.models import Group
from weblate.trans.tests.test_views import ViewTestCase


class TeamsTest(ViewTestCase):
    def make_superuser(self, superuser: bool = True) -> None:
        self.user.is_superuser = superuser
        self.user.save()

    def test_sitewide(self) -> None:
        group = Group.objects.create(name="Test group")
        edit_payload = {
            "name": "Other",
            "language_selection": "1",
            "project_selection": "1",
            "autogroup_set-TOTAL_FORMS": "0",
            "autogroup_set-INITIAL_FORMS": "0",
        }
        response = self.client.get(group.get_absolute_url())
        self.assertEqual(response.status_code, 403)

        # Edit not allowed
        response = self.client.post(group.get_absolute_url(), edit_payload)
        group.refresh_from_db()
        self.assertEqual(group.name, "Test group")

        self.make_superuser()
        response = self.client.get(group.get_absolute_url())
        self.assertContains(response, "id_autogroup_set-TOTAL_FORMS")

        response = self.client.post(group.get_absolute_url(), edit_payload)
        self.assertRedirects(response, group.get_absolute_url())
        group.refresh_from_db()
        self.assertEqual(group.name, "Other")

    def test_project(self) -> None:
        group = Group.objects.create(name="Test group", defining_project=self.project)

        edit_payload = {
            "name": "Other",
            "language_selection": "1",
            "autogroup_set-TOTAL_FORMS": "0",
            "autogroup_set-INITIAL_FORMS": "0",
        }
        response = self.client.get(group.get_absolute_url())
        self.assertEqual(response.status_code, 403)

        # Edit not allowed
        response = self.client.post(group.get_absolute_url(), edit_payload)
        group.refresh_from_db()
        self.assertEqual(group.name, "Test group")

        self.make_superuser()
        response = self.client.get(group.get_absolute_url())
        self.assertContains(response, "id_autogroup_set-TOTAL_FORMS")

        response = self.client.post(group.get_absolute_url(), edit_payload)
        self.assertRedirects(response, group.get_absolute_url())
        group.refresh_from_db()
        self.assertEqual(group.name, "Other")

    def test_add_users(self) -> None:
        group = Group.objects.create(name="Test group", defining_project=self.project)

        # Non-privileged
        self.client.post(
            group.get_absolute_url(), {"add_user": "1", "user": self.user.username}
        )
        self.assertEqual(group.user_set.count(), 0)
        self.assertEqual(group.admins.count(), 0)

        # Superuser
        self.make_superuser()
        self.client.post(
            group.get_absolute_url(), {"add_user": "1", "user": "x-invalid"}
        )
        self.assertEqual(group.user_set.count(), 0)
        self.assertEqual(group.admins.count(), 0)
        self.client.post(
            group.get_absolute_url(), {"add_user": "1", "user": self.user.username}
        )
        self.assertEqual(group.user_set.count(), 1)
        self.assertEqual(group.admins.count(), 0)

        self.client.post(
            group.get_absolute_url(),
            {"add_user": "1", "user": self.user.username, "make_admin": "1"},
        )
        self.assertEqual(group.user_set.count(), 1)
        self.assertEqual(group.admins.count(), 1)

        # Team admin
        self.make_superuser(False)
        self.client.post(
            group.get_absolute_url(),
            {"add_user": "1", "user": self.anotheruser.username},
        )
        self.assertEqual(group.user_set.count(), 2)
        self.assertEqual(group.admins.count(), 1)

        self.client.post(
            group.get_absolute_url(),
            {"add_user": "1", "user": self.anotheruser.username, "make_admin": "1"},
        )
        self.assertEqual(group.user_set.count(), 2)
        self.assertEqual(group.admins.count(), 2)

        self.client.post(
            group.get_absolute_url(),
            {"add_user": "1", "user": self.anotheruser.username},
        )
        self.assertEqual(group.user_set.count(), 2)
        self.assertEqual(group.admins.count(), 1)
