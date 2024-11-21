# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for ACL management."""

from django.conf import settings
from django.core import mail
from django.test.utils import override_settings
from django.urls import reverse

from weblate.auth.models import Group, Invitation, Role, User, get_anonymous
from weblate.lang.models import Language
from weblate.trans.models import Project
from weblate.trans.tests.test_views import FixtureTestCase, RegistrationTestMixin


class ACLTest(FixtureTestCase, RegistrationTestMixin):
    def setUp(self) -> None:
        super().setUp()
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.access_url = reverse("manage-access", kwargs=self.kw_project)
        self.translate_url = reverse("translate", kwargs=self.kw_translation)
        self.second_user = User.objects.create_user(
            "seconduser", "noreply@example.org", "testpassword"
        )
        self.admin_group = self.project.defined_groups.get(name="Administration")
        self.translate_group = self.project.defined_groups.get(name="Translate")

    def add_acl(self) -> None:
        """Add user to ACL."""
        self.project.add_user(self.user, "Translate")

    def test_acl_denied(self) -> None:
        """No access to the project without ACL."""
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(get_anonymous().can_access_project(self.project))

    def test_acl_disable(self) -> None:
        """Test disabling ACL."""
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 404)
        self.project.access_control = Project.ACCESS_PUBLIC
        self.project.save()
        self.assertTrue(get_anonymous().can_access_project(self.project))
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 403)
        response = self.client.get(self.translate_url)
        self.assertContains(response, ' name="save"')

    def test_acl_protected(self) -> None:
        """Test ACL protected project."""
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 404)
        self.project.access_control = Project.ACCESS_PROTECTED
        self.project.save()
        self.assertTrue(get_anonymous().can_access_project(self.project))
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 403)
        response = self.client.get(self.translate_url)
        self.assertContains(
            response, "Insufficient privileges for saving translations."
        )

    def test_acl(self) -> None:
        """Regular user should not have access to user management."""
        self.add_acl()
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 403)

    def test_edit_acl(self) -> None:
        """Manager should have access to user management."""
        self.add_acl()
        self.make_manager()
        response = self.client.get(self.access_url)
        self.assertContains(response, "Users")

    def test_edit_acl_owner(self) -> None:
        """Owner should have access to user management."""
        self.add_acl()
        self.project.add_user(self.user, "Administration")
        response = self.client.get(self.access_url)
        self.assertContains(response, "Users")

    def add_user(self) -> None:
        self.add_acl()
        self.project.add_user(self.user, "Administration")

        # Add user
        response = self.client.post(
            reverse("add-user", kwargs=self.kw_project),
            {"user": self.second_user.username, "group": self.admin_group.pk},
        )
        self.assertRedirects(response, self.access_url)

        # Ensure user is now listed
        response = self.client.get(self.access_url)
        self.assertContains(response, self.second_user.username)

        # Accept invitation
        invitation = Invitation.objects.get()
        invitation.accept(None, self.second_user)

        # Ensure user is now listed
        response = self.client.get(self.access_url)
        self.assertContains(response, self.second_user.username)

    def test_invite_invalid(self) -> None:
        """Test inviting invalid form."""
        self.project.add_user(self.user, "Administration")
        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {"email": "invalid", "group": self.admin_group.pk},
            follow=True,
        )
        self.assertContains(response, "Enter a valid e-mail address.")

    def test_invite_existing(self) -> None:
        """Test inviting existing user."""
        self.project.add_user(self.user, "Administration")
        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {"email": self.user.email, "group": self.admin_group.pk},
            follow=True,
        )
        self.assertContains(response, "User invitation e-mail was sent.")
        invitation = Invitation.objects.get()
        # Ensure invitation was mapped to existing user
        self.assertEqual(invitation.user, self.user)

    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_invite_user(self) -> None:
        """Test inviting user."""
        self.project.add_user(self.user, "Administration")
        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {"email": "user@example.com", "group": self.admin_group.pk},
            follow=True,
        )
        # Ensure user invitation is now listed
        self.assertContains(response, "user@example.com")
        self.assertNotContains(response, "example-username")
        # Check invitation mail
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "[Weblate] Invitation to Weblate")
        mail.outbox = []

        self.assertEqual(Invitation.objects.count(), 1)

        invitation = Invitation.objects.get()

        # Resend invitation
        response = self.client.post(
            invitation.get_absolute_url(),
            {"action": "resend"},
            follow=True,
        )
        # Check invitation mail
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "[Weblate] Invitation to Weblate")
        mail.outbox = []

        user_client = self.client_class()

        # Follow the invitation list
        response = user_client.get(invitation.get_absolute_url(), follow=True)
        self.assertRedirects(response, reverse("register"))
        self.assertContains(response, "user@example.com")

        # Perform registration
        response = user_client.post(
            reverse("register"),
            {
                "email": "user@example.com",
                "username": "example-username",
                "fullname": "name",
            },
            follow=True,
        )
        url = self.assert_registration_mailbox()
        response = user_client.get(url, follow=True)
        self.assertRedirects(response, reverse("password"))

        # Verify user was added
        response = self.client.get(self.access_url)
        self.assertContains(response, "example-username")

    def remove_user(self) -> None:
        # Remove user
        response = self.client.post(
            reverse("delete-user", kwargs=self.kw_project),
            {"user": self.second_user.username},
        )
        self.assertRedirects(response, self.access_url)

        # Ensure user is now not listed
        response = self.client.get(self.access_url)
        self.assertNotContains(response, self.second_user.username)
        self.assertNotContains(response, self.second_user.email)

    def test_add_acl(self) -> None:
        """Adding and removing users from the ACL project."""
        self.add_user()
        self.remove_user()

    def test_add_owner(self) -> None:
        """Adding and removing owners from the ACL project."""
        self.add_user()
        self.client.post(
            reverse("set-groups", kwargs=self.kw_project),
            {
                "user": self.second_user.username,
                "groups": [self.admin_group.pk],
            },
        )
        self.assertTrue(
            User.objects.all_admins(self.project)
            .filter(username=self.second_user.username)
            .exists()
        )
        self.client.post(
            reverse("set-groups", kwargs=self.kw_project),
            {
                "user": self.second_user.username,
                "groups": [self.translate_group.pk],
            },
        )
        self.assertFalse(
            User.objects.all_admins(self.project)
            .filter(username=self.second_user.username)
            .exists()
        )
        self.remove_user()

    def test_delete_owner(self) -> None:
        """Adding and deleting owners from the ACL project."""
        self.add_user()
        self.client.post(
            reverse("set-groups", kwargs=self.kw_project),
            {
                "user": self.second_user.username,
                "groups": [self.admin_group.pk],
            },
        )
        self.remove_user()
        self.assertFalse(
            User.objects.all_admins(self.project)
            .filter(username=self.second_user.username)
            .exists()
        )

    def test_denied_owner_delete(self) -> None:
        """Test that deleting the last owner does not work."""
        self.project.add_user(self.user, "Administration")
        self.client.post(
            reverse("set-groups", kwargs=self.kw_project),
            {
                "user": self.second_user.username,
                "groups": [self.translate_group.pk],
            },
        )
        self.assertTrue(
            User.objects.all_admins(self.project)
            .filter(username=self.user.username)
            .exists()
        )
        self.client.post(
            reverse("set-groups", kwargs=self.kw_project),
            {
                "user": self.user.username,
                "groups": [self.translate_group.pk],
            },
        )
        self.assertTrue(
            User.objects.all_admins(self.project)
            .filter(username=self.user.username)
            .exists()
        )

    def test_nonexisting_user(self) -> None:
        """Test adding non-existing user."""
        self.project.add_user(self.user, "Administration")
        response = self.client.post(
            reverse("add-user", kwargs=self.kw_project),
            {"user": "nonexisting", "group": self.admin_group.pk},
            follow=True,
        )
        self.assertContains(response, "Could not find any such user")

    def test_acl_groups(self) -> None:
        """Test handling ACL groups."""
        billing_group = 1 if "weblate.billing" in settings.INSTALLED_APPS else 0
        self.project.defined_groups.all().delete()
        self.project.access_control = Project.ACCESS_PUBLIC
        self.project.translation_review = False
        self.project.save()
        self.assertEqual(1, self.project.defined_groups.count())
        self.project.access_control = Project.ACCESS_PROTECTED
        self.project.translation_review = True
        self.project.save()
        self.assertEqual(10 + billing_group, self.project.defined_groups.count())
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.translation_review = True
        self.project.save()
        self.assertEqual(10 + billing_group, self.project.defined_groups.count())
        self.project.access_control = Project.ACCESS_CUSTOM
        self.project.save()
        self.assertEqual(10 + billing_group, self.project.defined_groups.count())
        self.project.access_control = Project.ACCESS_CUSTOM
        self.project.save()
        self.assertEqual(10 + billing_group, self.project.defined_groups.count())
        self.project.defined_groups.all().delete()
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.assertEqual(10 + billing_group, self.project.defined_groups.count())
        self.project.delete()

    def test_restricted_component(self) -> None:
        # Make the project public
        self.project.access_control = Project.ACCESS_PUBLIC
        self.project.save()
        # Add user language to ensure the suggestions are shown
        self.user.profile.languages.add(Language.objects.get(code="cs"))

        project_url = self.project.get_absolute_url()
        url = self.component.get_absolute_url()

        # It is shown on the dashboard and accessible
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get(reverse("home")), url)
        self.assertContains(self.client.get(project_url), url)

        # Make it restricted
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])

        # It is no longer shown on the dashboard and not accessible
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertNotContains(self.client.get(reverse("home")), url)
        self.assertNotContains(self.client.get(project_url), url)

        # Check superuser can access it
        self.user.is_superuser = True
        self.user.save()
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get(reverse("home")), url)
        self.assertContains(self.client.get(project_url), url)

    def test_block_user(self) -> None:
        self.project.add_user(self.user, "Administration")

        # Block user
        response = self.client.post(
            reverse("block-user", kwargs=self.kw_project),
            {"user": self.second_user.username},
        )
        self.assertRedirects(response, self.access_url)
        self.assertEqual(self.project.userblock_set.count(), 1)

        # Block user, for second time
        response = self.client.post(
            reverse("block-user", kwargs=self.kw_project),
            {"user": self.second_user.username},
        )
        self.assertRedirects(response, self.access_url)
        self.assertEqual(self.project.userblock_set.count(), 1)

        # Unblock user
        response = self.client.post(
            reverse("unblock-user", kwargs=self.kw_project),
            {"user": self.second_user.username},
        )
        self.assertRedirects(response, self.access_url)
        self.assertEqual(self.project.userblock_set.count(), 0)

    def test_delete_group(self) -> None:
        self.project.add_user(self.user, "Administration")
        group = self.project.defined_groups.get(name="Memory")
        response = self.client.post(
            group.get_absolute_url(),
            {"delete": group.pk},
        )
        self.assertRedirects(response, self.access_url + "#teams")
        self.assertFalse(Group.objects.filter(pk=group.pk).exists())

    def create_test_group(self):
        self.project.add_user(self.user, "Administration")
        response = self.client.post(
            reverse("create-project-group", kwargs=self.kw_project),
            {
                "name": "Czech team",
                "roles": list(
                    Role.objects.filter(name="Power user").values_list("pk", flat=True)
                ),
                "language_selection": 0,
                "languages": list(
                    Language.objects.filter(code="cs").values_list("pk", flat=True)
                ),
            },
        )
        self.assertRedirects(response, self.access_url + "#teams")
        return Group.objects.get(name="Czech team")

    def test_create_group(self) -> None:
        group = self.create_test_group()
        self.assertEqual(group.defining_project, self.project)
        self.assertEqual(group.language_selection, 0)
        self.assertEqual(list(group.languages.values_list("code", flat=True)), ["cs"])
        self.assertEqual(
            set(group.roles.values_list("name", flat=True)), {"Power user"}
        )

    def test_create_group_all_lang(self) -> None:
        self.project.add_user(self.user, "Administration")
        response = self.client.post(
            reverse("create-project-group", kwargs=self.kw_project),
            {
                "name": "All team",
                "roles": list(
                    Role.objects.filter(name="Power user").values_list("pk", flat=True)
                ),
                "language_selection": 1,
                "languages": list(
                    Language.objects.filter(code="cs").values_list("pk", flat=True)
                ),
            },
        )
        self.assertRedirects(response, self.access_url + "#teams")
        group = Group.objects.get(name="All team")
        self.assertEqual(group.defining_project, self.project)
        self.assertEqual(group.language_selection, 1)
        self.assertNotEqual(
            list(group.languages.values_list("code", flat=True)), ["cs"]
        )
        self.assertEqual(
            set(group.roles.values_list("name", flat=True)), {"Power user"}
        )

    def test_edit_group(self) -> None:
        group = self.create_test_group()

        response = self.client.post(
            group.get_absolute_url(),
            {
                "name": "Global team",
                "roles": list(
                    Role.objects.filter(name="Power user").values_list("pk", flat=True)
                ),
                "language_selection": 1,
                "languages": list(
                    Language.objects.filter(code="cs").values_list("pk", flat=True)
                ),
                "autogroup_set-TOTAL_FORMS": "0",
                "autogroup_set-INITIAL_FORMS": "0",
            },
        )
        self.assertRedirects(response, group.get_absolute_url())
        group = Group.objects.get(name="Global team")
        self.assertEqual(group.defining_project, self.project)
        self.assertEqual(group.language_selection, 1)
        self.assertNotEqual(
            list(group.languages.values_list("code", flat=True)), ["cs"]
        )
