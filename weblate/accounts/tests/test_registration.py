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

"""Test for user handling."""

from urllib.parse import parse_qs, urlparse

import responses
import social_django.utils
from django.conf import settings
from django.core import mail
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse

from weblate.accounts.models import VerifiedEmail
from weblate.accounts.tasks import cleanup_social_auth
from weblate.auth.models import User
from weblate.trans.tests.test_views import RegistrationTestMixin
from weblate.trans.tests.utils import get_test_file
from weblate.utils.django_hacks import immediate_on_commit, immediate_on_commit_leave
from weblate.utils.ratelimit import reset_rate_limit

REGISTRATION_DATA = {
    "username": "username",
    "email": "noreply-weblate@example.org",
    "fullname": "First Last",
    "captcha": "9999",
}

GH_BACKENDS = (
    "social_core.backends.email.EmailAuth",
    "social_core.backends.github.GithubOAuth2",
    "weblate.accounts.auth.WeblateUserBackend",
)
SAML_BACKENDS = (
    "social_core.backends.email.EmailAuth",
    "social_core.backends.saml.SAMLAuth",
    "weblate.accounts.auth.WeblateUserBackend",
)
with open(get_test_file("saml.crt")) as handle:
    SAML_CERT = handle.read()
with open(get_test_file("saml.key")) as handle:
    SAML_KEY = handle.read()


class BaseRegistrationTest(TestCase, RegistrationTestMixin):
    clear_cookie = False
    social_cleanup = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        immediate_on_commit(cls)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        immediate_on_commit_leave(cls)

    def setUp(self):
        super().setUp()
        reset_rate_limit("registration", address="127.0.0.1")
        reset_rate_limit("login", address="127.0.0.1")

    def assert_registration(self, match=None, reset=False):
        if match is None and reset:
            match = "[Weblate] Password reset on Weblate"

        url = self.assert_registration_mailbox(match)

        if self.clear_cookie and "sessionid" in self.client.cookies:
            del self.client.cookies["sessionid"]

        # Verify that cleanup does not break the workflow
        if self.social_cleanup:
            cleanup_social_auth()

        # Confirm account
        response = self.client.get(url, follow=True)
        if reset:
            # Ensure we can set the password
            self.assertRedirects(response, reverse("password_reset"))
            self.assertContains(response, "You can now set new one")
            # Invalid submission
            response = self.client.post(reverse("password_reset"))
            self.assertContains(response, "You can now set new one")
            # Set password
            response = self.client.post(
                reverse("password_reset"),
                {"new_password1": "2pa$$word!", "new_password2": "2pa$$word!"},
                follow=True,
            )
            self.assertContains(response, "Your password has been changed")
        else:
            self.assertRedirects(response, reverse("password"))
        return url

    def do_register(self, data=None):
        if data is None:
            data = REGISTRATION_DATA
        return self.client.post(reverse("register"), data, follow=True)

    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def perform_registration(self):
        response = self.do_register()
        # Check we did succeed
        self.assertContains(response, "Thank you for registering.")

        # Confirm account
        self.assert_registration()
        mail.outbox.pop()

        # Set password
        response = self.client.post(
            reverse("password"),
            {"new_password1": "1pa$$word!", "new_password2": "1pa$$word!"},
        )
        self.assertRedirects(response, reverse("profile"))
        # Password change notification
        notification = mail.outbox.pop()
        self.assert_notify_mailbox(notification)

        # Check we can access home (was redirected to password change)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "First Last")

        user = User.objects.get(username="username")
        # Verify user is active
        self.assertTrue(user.is_active)
        # Verify stored first/last name
        self.assertEqual(user.full_name, "First Last")

        # Ensure we've picked up all mails
        self.assertEqual(len(mail.outbox), 0)

        # Ensure the audit log matches expectations
        self.assertEqual(
            set(user.auditlog_set.values_list("activity", flat=True)),
            {"sent-email", "password"},
        )


class RegistrationTest(BaseRegistrationTest):
    @override_settings(REGISTRATION_CAPTCHA=True)
    def test_register_captcha_fail(self):
        response = self.do_register()
        self.assertContains(response, "That was not correct, please try again.")

    @override_settings(REGISTRATION_CAPTCHA=True)
    def test_register_captcha(self):
        """Test registration with captcha enabled."""
        response = self.client.get(reverse("register"))
        form = response.context["captcha_form"]
        data = REGISTRATION_DATA.copy()
        data["captcha"] = form.captcha.result
        response = self.do_register(data)
        self.assertContains(response, "Thank you for registering.")

        # Second registration should fail
        response = self.do_register(data)
        self.assertNotContains(response, "Thank you for registering.")

    @override_settings(REGISTRATION_OPEN=False)
    def test_register_closed(self):
        # Disable registration
        response = self.do_register()
        self.assertContains(
            response, "Sorry, new registrations are turned off on this site."
        )

    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_double_register_logout(self, logout=True):
        """Test double registration from single browser with logout."""
        # First registration
        response = self.do_register()
        first_url = self.assert_registration_mailbox()
        mail.outbox.pop()

        # Second registration
        data = REGISTRATION_DATA.copy()
        data["email"] = "noreply@example.net"
        data["username"] = "second"
        response = self.do_register(data)
        second_url = self.assert_registration_mailbox()
        mail.outbox.pop()

        # Confirm first account
        response = self.client.get(first_url, follow=True)
        self.assertTrue(
            User.objects.filter(email="noreply-weblate@example.org").exists()
        )
        self.assertRedirects(response, reverse("password"))
        if logout:
            self.client.post(reverse("logout"))

        # Confirm second account
        response = self.client.get(second_url, follow=True)
        self.assertEqual(
            User.objects.filter(email="noreply@example.net").exists(), logout
        )
        self.assertEqual(
            VerifiedEmail.objects.filter(email="noreply@example.net").exists(), logout
        )

    def test_double_register(self):
        """Test double registration from single browser without logout."""
        self.test_double_register_logout(False)

    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_register_missing(self):
        """Test handling of incomplete registration URL."""
        # Disable captcha
        response = self.do_register()
        # Check we did succeed
        self.assertContains(response, "Thank you for registering.")

        # Confirm account
        url = self.assert_registration_mailbox()

        # Remove partial_token from URL
        url = url.split("?")[0]

        # Confirm account
        response = self.client.get(url, follow=True)
        self.assertRedirects(response, reverse("login"))
        self.assertContains(response, "the verification token probably expired")

    @override_settings(REGISTRATION_CAPTCHA=False, AUTH_LOCK_ATTEMPTS=5)
    def test_reset_ratelimit(self):
        """Test for password reset ratelimiting."""
        User.objects.create_user("testuser", "test@example.com", "x")
        self.assertEqual(len(mail.outbox), 0)

        for _unused in range(10):
            response = self.client.post(
                reverse("password_reset"), {"email": "test@example.com"}, follow=True
            )
            self.assertContains(response, "Password reset almost complete")

        # Even though we've asked 10 times for reset, user should get only
        # e-mails until rate limit is applied
        self.assertEqual(len(mail.outbox), 4)

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_reset_nonexisting(self):
        """Test for password reset of nonexisting e-mail."""
        response = self.client.get(reverse("password_reset"))
        self.assertContains(response, "Reset my password")
        response = self.client.post(
            reverse("password_reset"), {"email": "test@example.com"}, follow=True
        )
        self.assertContains(response, "Password reset almost complete")
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_reset_invalid(self):
        """Test for password reset of invalid e-mail."""
        response = self.client.get(reverse("password_reset"))
        self.assertContains(response, "Reset my password")
        response = self.client.post(
            reverse("password_reset"), {"email": "@example.com"}
        )
        self.assertContains(response, "Enter a valid e-mail address.")
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(REGISTRATION_CAPTCHA=True)
    def test_reset_captcha(self):
        """Test for password reset of invalid captcha."""
        response = self.client.get(reverse("password_reset"))
        self.assertContains(response, "Reset my password")
        response = self.client.post(
            reverse("password_reset"), {"email": "test@example.com", "captcha": 9999}
        )
        self.assertContains(response, "That was not correct, please try again.")
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_reset_anonymous(self):
        """Test for password reset of anonymous user."""
        response = self.client.get(reverse("password_reset"))
        self.assertContains(response, "Reset my password")
        response = self.client.post(
            reverse("password_reset"), {"email": "noreply@weblate.org"}
        )
        self.assertContains(
            response, "No password reset for deleted or anonymous user."
        )
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_reset_twice(self):
        """Test for password reset."""
        User.objects.create_user("testuser", "test@example.com", "x")
        User.objects.create_user("testuser2", "test2@example.com", "x")

        response = self.client.post(
            reverse("password_reset"), {"email": "test@example.com"}
        )
        self.assertRedirects(response, reverse("email-sent"))
        self.assert_registration(reset=True)
        # Pop notifications (new association + reset + password change)
        sent_mail = mail.outbox.pop()
        sent_mail = mail.outbox.pop()
        sent_mail = mail.outbox.pop()
        self.assertEqual(["test@example.com"], sent_mail.to)
        self.assert_notify_mailbox(sent_mail)
        # Pop password change
        sent_mail = mail.outbox.pop()

        response = self.client.post(
            reverse("password_reset"), {"email": "test2@example.com"}
        )
        self.assertRedirects(response, reverse("email-sent"))
        self.assert_registration(reset=True)
        # Pop notifications (new association + reset + password change)
        sent_mail = mail.outbox.pop()
        sent_mail = mail.outbox.pop()
        sent_mail = mail.outbox.pop()
        self.assertEqual(["test2@example.com"], sent_mail.to)
        # Pop password change
        sent_mail = mail.outbox.pop()

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_reset_paralel(self):
        """Test for password reset from two browsers."""
        User.objects.create_user("testuser", "test@example.com", "x")
        match = "[Weblate] Password reset on Weblate"

        client2 = Client()

        # First reset
        response = self.client.post(
            reverse("password_reset"), {"email": "test@example.com"}
        )
        self.assertRedirects(response, reverse("email-sent"))

        response = self.client.get(self.assert_registration_mailbox(match), follow=True)
        self.assertRedirects(response, reverse("password_reset"))
        self.assertContains(response, "You can now set new one")

        mail.outbox = []

        # Second reset
        response = client2.post(
            reverse("password_reset"), {"email": "test@example.com"}
        )
        self.assertRedirects(response, reverse("email-sent"))

        response = client2.get(self.assert_registration_mailbox(match), follow=True)
        self.assertRedirects(response, reverse("password_reset"))
        self.assertContains(response, "You can now set new one")

        # Set first password
        response = self.client.post(
            reverse("password_reset"),
            {"new_password1": "2pa$$word!", "new_password2": "2pa$$word!"},
            follow=True,
        )
        self.assertContains(response, "Your password has been changed")

        # Set second password
        response = client2.post(
            reverse("password_reset"),
            {"new_password1": "3pa$$word!", "new_password2": "3pa$$word!"},
            follow=True,
        )
        self.assertContains(response, "Password reset has been already completed.")

    def test_wrong_username(self):
        data = REGISTRATION_DATA.copy()
        data["username"] = ""
        response = self.do_register(data)
        self.assertContains(response, "This field is required.")

    def test_wrong_mail(self):
        data = REGISTRATION_DATA.copy()
        data["email"] = "x"
        response = self.do_register(data)
        self.assertContains(response, "Enter a valid e-mail address.")

    @override_settings(REGISTRATION_EMAIL_MATCH="^.*@weblate.org$")
    def test_filtered_mail(self):
        data = REGISTRATION_DATA.copy()
        data["email"] = "noreply@example.com"
        response = self.do_register(data)
        self.assertContains(response, "This e-mail address is disallowed.")
        data["email"] = "noreply@weblate.org"
        response = self.client.post(reverse("register"), data, follow=True)
        self.assertNotContains(response, "This e-mail address is disallowed.")

    def test_spam(self):
        data = REGISTRATION_DATA.copy()
        data["content"] = "x"
        response = self.do_register(data)
        self.assertContains(response, "Invalid value")

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_add_mail(self, fails=False):
        """Adding mail to existing account."""
        # Create user
        self.perform_registration()

        # Check adding e-mail page
        response = self.client.post(
            reverse("social:begin", args=("email",)), follow=True
        )
        self.assertContains(response, "Register e-mail")

        # Try invalid address first
        response = self.client.post(reverse("email_login"), {"email": "invalid"})
        self.assertContains(response, "has-error")

        # Add e-mail account
        response = self.client.post(
            reverse("email_login"), {"email": "second@example.net"}, follow=True
        )
        self.assertRedirects(response, reverse("email-sent"))

        if fails:
            self.assertEqual(len(mail.outbox), 1)
            self.assert_notify_mailbox(mail.outbox[0])
            return

        # Verify confirmation mail
        url = self.assert_registration_mailbox()
        response = self.client.get(url, follow=True)
        self.assertRedirects(response, reverse("confirm"))

        # Enter wrong password
        user = User.objects.get(username="username")
        reset_rate_limit("confirm", user=user)
        response = self.client.post(reverse("confirm"), {"password": "invalid"})
        self.assertContains(response, "You have entered an invalid password.")

        # Correct password
        response = self.client.post(
            reverse("confirm"), {"password": "1pa$$word!"}, follow=True
        )
        self.assertRedirects(response, "{}#account".format(reverse("profile")))

        # Check database models
        user = User.objects.get(username="username")
        self.assertEqual(VerifiedEmail.objects.filter(social__user=user).count(), 2)
        self.assertTrue(
            VerifiedEmail.objects.filter(
                social__user=user, email="second@example.net"
            ).exists()
        )

        # Check notification
        notification = mail.outbox.pop()
        self.assert_notify_mailbox(notification)

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_add_existing(self):
        """Adding existing mail to existing account should fail."""
        User.objects.create_user("testuser", "second@example.net", "x")
        self.test_add_mail(True)

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_remove_mail(self):
        # Register user with two mails
        self.test_add_mail()
        mail.outbox = []

        user = User.objects.get(username="username")
        social = user.social_auth.get(uid="noreply-weblate@example.org")

        response = self.client.post(
            reverse(
                "social:disconnect_individual",
                kwargs={"backend": social.provider, "association_id": social.pk},
            ),
            follow=True,
        )
        self.assertContains(
            response, "Your e-mail no longer belongs to verified account"
        )
        notification = mail.outbox.pop()
        self.assert_notify_mailbox(notification)

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_remove_mail_verified(self):
        """Test rejected removal of association in case no verified e-mail left."""
        # Register user with two mails
        self.test_add_mail()
        mail.outbox = []

        user = User.objects.get(username="username")
        social = user.social_auth.get(uid="noreply-weblate@example.org")

        # Remove other verified emails
        VerifiedEmail.objects.exclude(social=social).delete()

        response = self.client.post(
            reverse(
                "social:disconnect_individual",
                kwargs={"backend": social.provider, "association_id": social.pk},
            ),
            follow=True,
        )
        self.assertContains(
            response, "Add another identity by confirming your e-mail address first."
        )

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_pipeline_redirect(self):
        """Test pipeline redirect using next parameter."""
        # Create user
        self.perform_registration()

        # Valid next URL
        response = self.client.post(
            reverse("social:begin", args=("email",)), {"next": "/#valid"}
        )
        response = self.client.post(
            reverse("email_login"), {"email": "second@example.net"}, follow=True
        )
        self.assertRedirects(response, reverse("email-sent"))

        # Verify confirmation mail
        url = self.assert_registration_mailbox()
        # Confirmation
        mail.outbox.pop()
        response = self.client.get(url, follow=True)
        self.assertRedirects(response, reverse("confirm"))
        response = self.client.post(
            reverse("confirm"), {"password": "1pa$$word!"}, follow=True
        )
        self.assertRedirects(response, "/#valid")
        # Activity
        mail.outbox.pop()

        # Invalid next URL
        response = self.client.post(
            reverse("social:begin", args=("email",)), {"next": "////example.com"}
        )
        response = self.client.post(
            reverse("email_login"), {"email": "third@example.net"}, follow=True
        )
        self.assertRedirects(response, reverse("email-sent"))

        # Verify confirmation mail
        url = self.assert_registration_mailbox()
        response = self.client.get(url, follow=True)
        self.assertRedirects(response, reverse("confirm"))
        response = self.client.post(
            reverse("confirm"), {"password": "1pa$$word!"}, follow=True
        )
        # We should fallback to default URL
        self.assertRedirects(response, "/accounts/profile/#account")

    @responses.activate
    @override_settings(AUTHENTICATION_BACKENDS=GH_BACKENDS)
    def test_github(self, confirm=None, fail=False):
        """Test GitHub integration."""
        try:
            # psa creates copy of settings...
            orig_backends = social_django.utils.BACKENDS
            social_django.utils.BACKENDS = GH_BACKENDS

            responses.add(
                responses.POST,
                "https://github.com/login/oauth/access_token",
                json={"access_token": "123", "token_type": "bearer"},
            )
            responses.add(
                responses.GET,
                "https://api.github.com/user",
                json={
                    "email": "foo@example.net",
                    "login": "weblate",
                    "id": 1,
                    "name": "Test Weblate Name",
                },
            )
            responses.add(
                responses.GET,
                "https://api.github.com/user/emails",
                json=[
                    {
                        "email": "noreply2@example.org",
                        "verified": False,
                        "primary": False,
                    },
                    {
                        "email": "noreply-weblate@example.org",
                        "verified": True,
                        "primary": True,
                    },
                ],
            )
            response = self.client.post(reverse("social:begin", args=("github",)))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(
                response["Location"].startswith(
                    "https://github.com/login/oauth/authorize"
                )
            )
            query = parse_qs(urlparse(response["Location"]).query)
            return_query = parse_qs(urlparse(query["redirect_uri"][0]).query)
            response = self.client.get(
                reverse("social:complete", args=("github",)),
                {"state": query["state"][0] or return_query["state"][0], "code": "XXX"},
                follow=True,
            )
            if fail:
                self.assertContains(response, "is already in use for another account")
                return
            if confirm:
                self.assertContains(response, "Confirm new association")
                response = self.client.post(
                    reverse("confirm"), {"password": confirm}, follow=True
                )
            self.assertContains(response, "Test Weblate Name")
            user = User.objects.get(username="weblate")
            self.assertEqual(user.full_name, "Test Weblate Name")
            self.assertEqual(user.email, "noreply-weblate@example.org")
        finally:
            social_django.utils.BACKENDS = orig_backends

    def test_github_existing(self):
        """Adding GitHub association to existing account."""
        User.objects.create_user("weblate", "noreply-weblate@example.org", "x")
        self.test_github(confirm="x")

    def test_github_loggedin(self):
        """Adding GitHub association to existing account."""
        User.objects.create_user("weblate", "noreply-weblate@example.org", "x")
        self.client.login(username="weblate", password="x")
        user = User.objects.get(username="weblate")
        # Name should now contain username (as that is only info we have)
        self.assertEqual(user.full_name, "weblate")
        # Reset name
        user.full_name = ""
        user.save(update_fields=["full_name"])
        self.test_github(confirm="x")

    def test_github_add_other(self):
        """Adding authentication from another account."""
        User.objects.create_user("weblate", "noreply-weblate@example.org", "x")
        # Login so that verified mail objects are created
        self.client.login(username="weblate", password="x")
        # Switch to second user
        User.objects.create_user("second", "noreply-second@example.org", "x")
        # Try to add GitHub auth with other e-mail
        self.client.login(username="second", password="x")
        self.test_github(fail=True)
        # User should get an notification
        self.assertEqual(len(mail.outbox), 1)
        self.assert_notify_mailbox(mail.outbox[0])
        self.assertEqual(mail.outbox[0].to, ["noreply-weblate@example.org"])

    def test_saml_disabled(self):
        url = reverse("social:saml-metadata")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    @override_settings(
        AUTHENTICATION_BACKENDS=SAML_BACKENDS,
        SOCIAL_AUTH_SAML_SP_PUBLIC_CERT=SAML_CERT,
        SOCIAL_AUTH_SAML_SP_PRIVATE_KEY=SAML_KEY,
    )
    def test_saml(self):
        try:
            # psa creates copy of settings...
            orig_backends = social_django.utils.BACKENDS
            social_django.utils.BACKENDS = SAML_BACKENDS

            url = reverse("social:saml-metadata")
            response = self.client.get(url)
            self.assertContains(response, url)
        finally:
            social_django.utils.BACKENDS = orig_backends


class CookieRegistrationTest(BaseRegistrationTest):
    def test_register(self):
        self.perform_registration()

    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_double_link(self):
        """Test that verification link works just once."""
        response = self.do_register()
        # Check we did succeed
        self.assertContains(response, "Thank you for registering.")
        url = self.assert_registration()

        # Clear cookies
        if self.clear_cookie and "sessionid" in self.client.cookies:
            del self.client.cookies["sessionid"]

        response = self.client.get(url, follow=True)
        self.assertContains(response, "the verification token probably expired")

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_reset(self):
        """Test for password reset."""
        User.objects.create_user("testuser", "test@example.com", "x")

        response = self.client.get(reverse("password_reset"))
        self.assertContains(response, "Reset my password")
        response = self.client.post(
            reverse("password_reset"), {"email": "test@example.com"}, follow=True
        )
        self.assertContains(response, "Password reset almost complete")

        self.assert_registration(reset=True)


class NoCookieRegistrationTest(CookieRegistrationTest):
    clear_cookie = True


class NoCookieCleanupRegistrationTest(CookieRegistrationTest):
    clear_cookie = True
    social_cleanup = True


@override_settings(
    AUTHENTICATION_BACKENDS=[
        "social_core.backends.email.EmailAuth",
        "social_core.backends.username.UsernameAuth",
        "weblate.accounts.auth.WeblateUserBackend",
    ],
    SOCIAL_AUTH_USERNAME_FORM_URL="/accounts/login/",
)
class RegistrationLimitTest(TestCase):
    """
    Registration limiting tests.

    This uses social_core.backends.username.UsernameAuth which does not validation
    at all.
    """

    EMAIL = "username@example.com"
    USERNAME = "user-name"

    def do_register(self, success: bool):
        # Check that login page contains username login
        response = self.client.get(reverse("register"))
        if success:
            self.assertContains(response, "/accounts/login/username/")
        else:
            self.assertNotContains(response, "/accounts/login/username/")

        # Begin authentication
        response = self.client.post(reverse("social:begin", args=("username",)))
        self.assertRedirects(response, settings.SOCIAL_AUTH_USERNAME_FORM_URL)

        # Complete authentication
        response = self.client.post(
            reverse("social:complete", args=("username",)),
            {"username": self.USERNAME, "email": self.EMAIL},
            follow=True,
        )
        if success:
            user = User.objects.get(username=self.USERNAME)
            self.assertTrue(user.is_active)
            self.assertEqual(user.email, self.EMAIL)
        else:
            self.assertContains(response, "New registrations are turned off.")
            self.assertFalse(User.objects.filter(username=self.USERNAME).exists())

    def setUp(self):
        super().setUp()
        self.orig_backends = social_django.utils.BACKENDS
        social_django.utils.BACKENDS = settings.AUTHENTICATION_BACKENDS

    def tearDown(self):
        super().tearDown()
        social_django.utils.BACKENDS = self.orig_backends

    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_open(self):
        """Registration fully open."""
        self.do_register(True)

    @override_settings(REGISTRATION_OPEN=False, REGISTRATION_CAPTCHA=False)
    def test_closed(self):
        """Registration fully closed."""
        self.do_register(False)

    @override_settings(
        REGISTRATION_OPEN=False,
        REGISTRATION_CAPTCHA=False,
        REGISTRATION_ALLOW_BACKENDS=["username"],
    )
    def test_open_partial(self):
        """Registration open for certain backend with auto redirect."""
        self.do_register(True)

    @override_settings(
        REGISTRATION_OPEN=False,
        REGISTRATION_CAPTCHA=False,
        REGISTRATION_ALLOW_BACKENDS=["username", "email"],
    )
    def test_open_partial_two(self):
        """Registration open for certain backend with registration form."""
        self.do_register(True)

    @override_settings(
        REGISTRATION_OPEN=False,
        REGISTRATION_CAPTCHA=False,
        REGISTRATION_ALLOW_BACKENDS=["email"],
    )
    def test_closed_partial(self):
        """Registration closed for certain backend with registration form."""
        self.do_register(False)

    @override_settings(
        REGISTRATION_OPEN=True,
        REGISTRATION_CAPTCHA=False,
        REGISTRATION_ALLOW_BACKENDS=["username"],
    )
    def test_open_partial_open(self):
        """Registration open for certain backend."""
        self.do_register(True)

    @override_settings(
        REGISTRATION_OPEN=True,
        REGISTRATION_CAPTCHA=False,
        REGISTRATION_ALLOW_BACKENDS=["email"],
    )
    def test_closed_partial_open(self):
        """Registration closed for certain backend."""
        self.do_register(False)
