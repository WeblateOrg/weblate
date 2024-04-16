# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for account removal."""

from django.urls import reverse

from weblate.auth.models import User
from weblate.trans.tests.test_views import RegistrationTestMixin, ViewTestCase


class AccountRemovalTest(ViewTestCase, RegistrationTestMixin):
    def test_page(self) -> None:
        response = self.client.get(reverse("remove"))
        self.assertContains(response, "Account removal deletes all your private data.")

    def verify_removal(self, response) -> None:
        self.assertRedirects(response, reverse("email-sent"))

        # Get confirmation URL
        url = self.assert_registration_mailbox("[Weblate] Account removal on Weblate")
        # Verify confirmation URL
        response = self.client.get(url, follow=True)
        self.assertContains(
            response, "By pressing following button, your will no longer be able to use"
        )
        # Confirm removal
        response = self.client.post(reverse("remove"), follow=True)
        self.assertContains(response, "Your account has been removed.")
        self.assertFalse(User.objects.filter(username="testuser").exists())

    def test_removal(self) -> None:
        response = self.client.post(
            reverse("remove"), {"password": "testpassword"}, follow=True
        )
        self.verify_removal(response)

    def test_removal_failed(self) -> None:
        response = self.client.post(
            reverse("remove"), {"password": "invalidpassword"}, follow=True
        )
        self.assertContains(response, "You have entered an invalid password.")
        self.assertTrue(User.objects.filter(username="testuser").exists())

    def test_removal_nopass(self) -> None:
        # Set unusable password for test user.
        self.user.set_unusable_password()
        self.user.save()
        # Need to force login as user has no password now.
        # In the app he would login by third party auth.
        self.client.force_login(self.user)
        response = self.client.post(reverse("remove"), {"password": ""}, follow=True)
        self.verify_removal(response)

    def test_removal_change(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        # We should have some change to commit
        self.assertTrue(self.component.needs_commit())
        # Remove account
        self.test_removal()
        # Changes should be committed
        self.assertFalse(self.component.needs_commit())
