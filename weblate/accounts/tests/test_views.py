# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for user handling."""

from __future__ import annotations

from time import sleep
from types import SimpleNamespace
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.signing import TimestampSigner
from django.test.utils import modify_settings, override_settings
from django.urls import reverse
from jsonschema import validate
from requests.exceptions import HTTPError
from rest_framework.authtoken.models import Token
from social_core.exceptions import (
    AuthCanceled,
    AuthFailed,
    AuthForbidden,
    AuthMissingParameter,
    AuthStateMissing,
    AuthTokenError,
    InvalidEmail,
)
from weblate_schemas import load_schema

from weblate.accounts.forms import ProfileForm
from weblate.accounts.models import Profile, Subscription
from weblate.accounts.notifications import NotificationFrequency, NotificationScope
from weblate.accounts.views import log_handled_auth_failure
from weblate.auth.models import User
from weblate.billing.models import Plan
from weblate.lang.models import Language
from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import (
    social_core_modify_settings,
    social_core_override_settings,
)
from weblate.utils.ratelimit import reset_rate_limit
from weblate.utils.state import STATE_TRANSLATED

CONTACT_DATA = {
    "name": "Test",
    "email": "noreply@weblate.org",
    "subject": "Message from dark side",
    "message": "Hi\n\nThis app looks really cool!",
}


class ViewTest(RepoTestCase):
    """Test for views."""

    def setUp(self) -> None:
        super().setUp()
        reset_rate_limit("login", address="127.0.0.1")
        reset_rate_limit("message", address="127.0.0.1")

    def get_user(self):
        user = User.objects.create_user(
            username="testuser", password="testpassword", full_name="Test User"
        )
        user.full_name = "First Second"
        user.email = "noreply@example.com"
        user.save()
        return user

    @staticmethod
    def get_backend(name: str = "github") -> mock.Mock:
        backend = mock.Mock()
        backend.name = name
        return backend

    def assert_social_complete_result(
        self,
        error: Exception,
        *,
        expected_text: str,
        backend: str = "github",
        session_updates: dict[str, object] | None = None,
        reportable: bool,
    ) -> None:
        session = self.client.session
        if session_updates is not None:
            for key, value in session_updates.items():
                session[key] = value
            session.save()

        with (
            mock.patch("weblate.accounts.views.complete", side_effect=error),
            mock.patch("weblate.accounts.views.report_error") as mocked_report_error,
            mock.patch(
                "weblate.accounts.views.log_handled_auth_failure"
            ) as mocked_handled_error,
        ):
            response = self.client.get(
                reverse("social:complete", args=(backend,)), follow=True
            )

        self.assertRedirects(response, reverse("login"))
        self.assertContains(response, expected_text)
        if reportable:
            mocked_report_error.assert_called_once()
            mocked_handled_error.assert_not_called()
        else:
            mocked_report_error.assert_not_called()
            mocked_handled_error.assert_called_once()

    @override_settings(
        REGISTRATION_CAPTCHA=False, ADMINS=("Weblate test <noreply@weblate.org>",)
    )
    def test_contact(self) -> None:
        """Test for contact form."""
        # Basic get
        response = self.client.get(reverse("contact"))
        self.assertContains(response, 'id="id_message"')

        # Sending message
        response = self.client.post(reverse("contact"), CONTACT_DATA)
        self.assertRedirects(response, reverse("home"))

        # Verify message
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "[Weblate] Message from dark side")
        self.assertEqual(mail.outbox[0].to, list(settings.ADMINS))

    @override_settings(
        REGISTRATION_CAPTCHA=False, ADMINS_CONTACT=["noreply@example.com"]
    )
    def test_contact_separate(self) -> None:
        """Test for contact form."""
        # Sending message
        response = self.client.post(reverse("contact"), CONTACT_DATA)
        self.assertRedirects(response, reverse("home"))

        # Verify message
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "[Weblate] Message from dark side")
        self.assertEqual(mail.outbox[0].to, ["noreply@example.com"])

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_contact_invalid(self) -> None:
        """Test for contact form."""
        # Sending message
        data = CONTACT_DATA.copy()
        data["email"] = "rejected&mail@example.com"
        response = self.client.post(reverse("contact"), data)
        self.assertContains(response, "Enter a valid e-mail address.")

    @override_settings(RATELIMIT_MESSAGE_ATTEMPTS=0)
    def test_contact_rate(self) -> None:
        """Test for contact form rate limiting."""
        response = self.client.post(reverse("contact"), CONTACT_DATA)
        self.assertContains(response, "Too many messages sent, please try again later.")

    @override_settings(RATELIMIT_MESSAGE_ATTEMPTS=1, RATELIMIT_WINDOW=1)
    def test_contact_rate_window(self) -> None:
        """Test for contact form rate limiting."""
        message = "Too many messages sent, please try again later."
        response = self.client.post(reverse("contact"), CONTACT_DATA)
        self.assertNotContains(response, message)
        sleep(1)
        response = self.client.post(reverse("contact"), CONTACT_DATA)
        self.assertNotContains(response, message)

    @override_settings(CONTACT_FORM="disabled")
    def test_contact_disabled(self) -> None:
        """Test for disabled contact form."""
        # Test GET request
        response = self.client.get(reverse("contact"))
        self.assertEqual(response.status_code, 404)

        # Test POST request
        response = self.client.post(reverse("contact"), CONTACT_DATA)
        self.assertEqual(response.status_code, 404)

    @override_settings(OFFER_HOSTING=False)
    def test_hosting_disabled(self) -> None:
        """Test for hosting form with disabled hosting."""
        self.get_user()
        self.client.login(username="testuser", password="testpassword")
        response = self.client.get(reverse("hosting"))
        self.assertRedirects(response, reverse("home"))

    @override_settings(OFFER_HOSTING=True)
    def test_libre(self) -> None:
        """Test for hosting form with enabled hosting."""
        self.get_user()
        self.client.login(username="testuser", password="testpassword")

        Plan.objects.create(price=0, slug="libre", name="Libre")
        self.client.login(username="testuser", password="testpassword")
        response = self.client.get(reverse("hosting"))
        self.assertContains(response, "trial")

        # Creating a trial
        response = self.client.post(reverse("trial"), {"plan": "libre"}, follow=True)
        self.assertContains(response, "Create project")

    @override_settings(OFFER_HOSTING=False)
    def test_trial_disabled(self) -> None:
        """Test for trial form with disabled hosting."""
        self.get_user()
        self.client.login(username="testuser", password="testpassword")
        response = self.client.get(reverse("trial"))
        self.assertRedirects(response, reverse("home"))

    @override_settings(OFFER_HOSTING=True)
    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    def test_trial(self) -> None:
        """Test for trial form with disabled hosting."""
        Plan.objects.create(price=1, slug="640k")
        user = self.get_user()
        self.client.login(username="testuser", password="testpassword")
        response = self.client.get(reverse("trial"))
        self.assertContains(response, "640k")
        response = self.client.post(reverse("trial"), follow=True)
        self.assertContains(response, "Create project")
        billing = user.billing_set.get()
        self.assertTrue(billing.is_trial)

        # Repeated attempt should fail
        response = self.client.get(reverse("trial"))
        self.assertRedirects(response, f"{reverse('contact')}?t=trial")

    def test_contact_subject(self) -> None:
        # With set subject
        response = self.client.get(reverse("contact"), {"t": "reg"})
        self.assertContains(response, "Registration problems")

    def test_contact_user(self) -> None:
        user = self.get_user()
        # Login
        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(reverse("contact"))
        self.assertContains(response, 'value="First Second"')
        self.assertContains(response, user.email)

    def test_user_list(self) -> None:
        """Test user pages."""
        user = self.get_user()
        response = self.client.get(reverse("user_list"), {"q": user.username})
        self.assertEqual(response.status_code, 302)
        self.client.login(username=user.username, password="testpassword")
        user_url = user.get_absolute_url()
        response = self.client.get(reverse("user_list"), {"q": user.username})
        self.assertContains(response, user_url)
        response = self.client.get(reverse("user_list"), {"q": user.full_name})
        self.assertContains(response, user_url)
        response = self.client.get(reverse("user_list"), {"sort_by": "invalid"})
        self.assertContains(response, user_url)

    def test_user(self) -> None:
        """Test user pages."""
        # Setup user
        user = self.get_user()

        # Login as user
        self.client.login(username=user.username, password="testpassword")

        # Get public profile
        response = self.client.get(user.get_absolute_url())
        self.assertContains(response, "table-activity")

    def test_suggestions(self) -> None:
        """Test user pages."""
        # Setup user
        user = self.get_user()

        # Get public profile
        response = self.client.get(
            reverse("user_suggestions", kwargs={"user": user.username})
        )
        self.assertContains(response, "Suggestions")

        response = self.client.get(reverse("user_suggestions", kwargs={"user": "-"}))
        self.assertContains(response, "Suggestions")

    def test_contributions(self) -> None:
        """Test user pages."""
        # Setup user
        user = self.get_user()

        # Get public profile
        response = self.client.get(
            reverse("user_contributions", kwargs={"user": user.username})
        )
        self.assertContains(response, "Translates")

    def test_login(self) -> None:
        user = self.get_user()

        # Login
        response = self.client.post(
            reverse("login"), {"username": user.username, "password": "testpassword"}
        )
        self.assertRedirects(response, reverse("home"))

        # Login redirect
        response = self.client.get(reverse("login"))
        self.assertRedirects(response, reverse("profile"))

        # Logout with GET should fail
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)

        # Logout
        response = self.client.post(reverse("logout"))
        self.assertContains(response, "Thank you for using Weblate")

    def test_login_next_redirect(self) -> None:
        user = self.get_user()

        response = self.client.post(
            reverse("login"),
            {
                "username": user.username,
                "password": "testpassword",
                "next": f"{reverse('profile')}#account",
            },
        )

        self.assertRedirects(response, f"{reverse('profile')}#account")

    def test_login_rejects_unsafe_next(self) -> None:
        user = self.get_user()

        for next_url in ("https://evil.example/", "////evil.example"):
            with self.subTest(next_url=next_url):
                self.client.logout()
                response = self.client.post(
                    reverse("login"),
                    {
                        "username": user.username,
                        "password": "testpassword",
                        "next": next_url,
                    },
                )

                self.assertRedirects(response, reverse("home"))

    @social_core_override_settings(
        AUTHENTICATION_BACKENDS=(
            "social_core.backends.github.GithubOAuth2",
            "weblate.accounts.auth.WeblateUserBackend",
        )
    )
    def test_login_redirect(self) -> None:
        response = self.client.get(reverse("login"))
        self.assertContains(response, "Redirecting you to the authentication provider.")

    def test_login_email(self) -> None:
        user = self.get_user()

        # Login
        response = self.client.post(
            reverse("login"), {"username": user.email, "password": "testpassword"}
        )
        self.assertRedirects(response, reverse("home"))

    def test_login_anonymous(self) -> None:
        # Login
        response = self.client.post(
            reverse("login"),
            {"username": settings.ANONYMOUS_USER_NAME, "password": "testpassword"},
        )
        self.assertContains(
            response, "This username/password combination was not found."
        )

    @social_core_override_settings(
        AUTHENTICATION_BACKENDS=(
            "django.contrib.auth.backends.ModelBackend",
            "weblate.accounts.auth.WeblateUserBackend",
        ),
        REGISTRATION_OPEN=False,
        PASSWORD_RESET_URL="https://id.example.net/password-reset",
    )
    def test_login_password_reset_url(self) -> None:
        response = self.client.get(reverse("login"))
        self.assertContains(response, 'href="https://id.example.net/password-reset"')

    @social_core_override_settings(
        AUTHENTICATION_BACKENDS=(
            "django.contrib.auth.backends.ModelBackend",
            "weblate.accounts.auth.WeblateUserBackend",
        ),
        REGISTRATION_OPEN=False,
        PASSWORD_RESET_URL=None,
    )
    def test_login_without_configured_password_reset_url(self) -> None:
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, reverse("password_reset"))

    @social_core_override_settings(
        AUTHENTICATION_BACKENDS=(
            "social_core.backends.email.EmailAuth",
            "weblate.accounts.auth.WeblateUserBackend",
        ),
        REGISTRATION_OPEN=False,
        PASSWORD_RESET_URL=None,
    )
    def test_login_uses_internal_password_reset_url(self) -> None:
        response = self.client.get(reverse("login"))
        self.assertContains(response, f'href="{reverse("password_reset")}"')

    def test_social_complete_logs_missing_provider_email(self) -> None:
        self.assert_social_complete_result(
            AuthMissingParameter(self.get_backend(), "email"),
            expected_text=(
                "Got no e-mail address from third party authentication service."
            ),
            reportable=False,
        )

    def test_social_complete_logs_disabled_registration(self) -> None:
        self.assert_social_complete_result(
            AuthMissingParameter(self.get_backend(), "disabled"),
            expected_text="New registrations are turned off.",
            reportable=False,
        )

    def test_social_complete_logs_invalid_email_for_reset(self) -> None:
        self.assert_social_complete_result(
            InvalidEmail(self.get_backend("email")),
            expected_text=(
                "Try resetting your password again to verify your identity, "
                "the confirmation link probably expired."
            ),
            backend="email",
            session_updates={"password_reset": True},
            reportable=False,
        )

    def test_social_complete_logs_missing_state(self) -> None:
        self.assert_social_complete_result(
            AuthStateMissing(self.get_backend()),
            expected_text="Could not authenticate due to invalid session state.",
            reportable=False,
        )

    def test_social_complete_logs_expired_provider_code(self) -> None:
        self.assert_social_complete_result(
            AuthFailed(
                self.get_backend(),
                "The code passed is incorrect or expired.",
            ),
            expected_text=(
                "Could not authenticate, probably due to an expired token "
                "or connection error."
            ),
            reportable=False,
        )

    def test_social_complete_reports_token_error(self) -> None:
        self.assert_social_complete_result(
            AuthTokenError(self.get_backend(), "Invalid key/secret, perhaps expired"),
            expected_text=(
                "Authentication failed: Token error: Invalid key/secret, "
                "perhaps expired"
            ),
            reportable=True,
        )

    def test_social_complete_reports_auth_forbidden(self) -> None:
        self.assert_social_complete_result(
            AuthForbidden(self.get_backend()),
            expected_text="The server does not allow authentication.",
            reportable=True,
        )

    def test_social_complete_reports_provider_http_error(self) -> None:
        self.assert_social_complete_result(
            HTTPError(
                "401 Client Error: Unauthorized for url: https://api.github.com/user"
            ),
            expected_text="The authentication provider could not be reached.",
            reportable=True,
        )

    def test_social_complete_logs_auth_canceled(self) -> None:
        self.assert_social_complete_result(
            AuthCanceled(self.get_backend(), "access_denied"),
            expected_text="Authentication cancelled.",
            reportable=False,
        )

    def test_log_handled_auth_failure_uses_string_reason(self) -> None:
        request = self.client.get(reverse("login")).wsgi_request
        request.session["password_reset"] = True

        with mock.patch(
            "weblate.accounts.views.log_handled_exception"
        ) as mocked_log_handled_exception:
            log_handled_auth_failure(
                request,
                "github",
                AuthFailed(
                    self.get_backend(),
                    "The code passed is incorrect or expired.",
                ),
            )

        mocked_log_handled_exception.assert_called_once_with(
            "Handled auth failure",
            extra_log=(
                "backend=github, action=reset, path=/accounts/login/, "
                "reason=The code passed is incorrect or expired."
            ),
        )

    @override_settings(RATELIMIT_ATTEMPTS=20, AUTH_LOCK_ATTEMPTS=5)
    def test_login_ratelimit(self, login=False) -> None:
        if login:
            self.test_login()
        else:
            self.get_user()

        # Use auth attempts
        for _unused in range(5):
            response = self.client.post(
                reverse("login"), {"username": "testuser", "password": "invalid"}
            )
            self.assertContains(response, "Please try again.")

        # Try login with valid password
        response = self.client.post(
            reverse("login"), {"username": "testuser", "password": "testpassword"}
        )
        self.assertContains(response, "Please try again.")

    @override_settings(RATELIMIT_ATTEMPTS=10, AUTH_LOCK_ATTEMPTS=5)
    def test_login_ratelimit_login(self) -> None:
        self.test_login_ratelimit(True)

    def test_password(self) -> None:
        # Create user
        user = self.get_user()
        old_token = user.auth_token.key
        # Login
        self.client.login(username="testuser", password="testpassword")
        # Change without data
        response = self.client.post(reverse("password"))
        self.assertContains(response, "This field is required.")
        response = self.client.get(reverse("password"))
        self.assertContains(response, "Current password")
        # Change with wrong password
        response = self.client.post(
            reverse("password"),
            {
                "password": "123456",
                "new_password1": "123456",
                "new_password2": "123456",
            },
        )
        self.assertContains(response, "You have entered an invalid password.")
        # Change
        response = self.client.post(
            reverse("password"),
            {
                "password": "testpassword",
                "new_password1": "1pa$$word!",
                "new_password2": "1pa$$word!",
                "regenerate_api_key": "on",
            },
        )

        self.assertRedirects(response, f"{reverse('profile')}#account")
        updated_user = User.objects.get(username="testuser")
        self.assertTrue(updated_user.check_password("1pa$$word!"))
        self.assertNotEqual(updated_user.auth_token.key, old_token)
        self.assertFalse(Token.objects.filter(key=old_token).exists())

    def test_password_keeps_api_key(self) -> None:
        user = self.get_user()
        old_token = user.auth_token.key

        self.client.login(username="testuser", password="testpassword")
        response = self.client.post(
            reverse("password"),
            {
                "password": "testpassword",
                "new_password1": "1pa$$word!",
                "new_password2": "1pa$$word!",
            },
        )

        self.assertRedirects(response, f"{reverse('profile')}#account")
        updated_user = User.objects.get(username="testuser")
        self.assertTrue(updated_user.check_password("1pa$$word!"))
        self.assertEqual(updated_user.auth_token.key, old_token)

    def test_api_key(self) -> None:
        # Create user
        user = self.get_user()
        # Login
        self.client.login(username="testuser", password="testpassword")

        # API key reset with GET should fail
        response = self.client.get(reverse("reset-api-key"))
        self.assertEqual(response.status_code, 405)

        # API key reset
        response = self.client.post(reverse("reset-api-key"))
        self.assertRedirects(response, f"{reverse('profile')}#api")

        # API key reset without token
        user.auth_token.delete()
        response = self.client.post(reverse("reset-api-key"))
        self.assertRedirects(response, f"{reverse('profile')}#api")


class ProfileTest(FixtureTestCase):
    def test_profile(self) -> None:
        # Get profile page
        response = self.client.get(reverse("profile"))
        self.assertContains(response, 'action="/accounts/profile/"')
        self.assertContains(response, 'name="secondary_languages"')
        self.assertContains(response, reverse("userdata"))

        # Save profile
        response = self.client.post(
            reverse("profile"),
            {
                "language": "en",
                "languages": Language.objects.get(code="cs").id,
                "secondary_languages": Language.objects.get(code="cs").id,
                "full_name": "First Last",
                "email": "weblate@example.org",
                "username": "testik",
                "dashboard_view": Profile.DASHBOARD_WATCHED,
                "translate_mode": Profile.TRANSLATE_FULL,
                "zen_mode": Profile.ZEN_VERTICAL,
                "nearby_strings": 10,
                "theme": "auto",
                "notifications__0-scope": 0,
                "notifications__0-project": "",
                "notifications__0-component": "",
                "notifications__1-scope": 10,
                "notifications__1-project": "",
                "notifications__1-component": "",
                "notifications__2-scope": 20,
                "notifications__2-project": "",
                "notifications__2-component": "",
            },
        )
        self.assertRedirects(response, reverse("profile"))

    def test_profile_contact_rejects_direct_download(self) -> None:
        form = ProfileForm(
            {"contact": "https://example.org/file.zip"},
            instance=self.user.profile,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("not directly to a file download", form.errors["contact"][0])

    def test_profile_contact_rejects_userinfo(self) -> None:
        form = ProfileForm(
            {"contact": "https://user@example.org/contact"},
            instance=self.user.profile,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("username or password credentials", form.errors["contact"][0])

    def test_profile_contact_rejects_private_target(self) -> None:
        form = ProfileForm(
            {"contact": "https://127.0.0.1/contact"},
            instance=self.user.profile,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("internal or non-public address", form.errors["contact"][0])

    def test_user_contact_warning(self) -> None:
        profile = self.anotheruser.profile
        profile.contact = "https://example.org/contact"
        profile.save(update_fields=["contact"])

        contact_url = reverse(
            "user_contact", kwargs={"user": self.anotheruser.username}
        )
        response = self.client.get(
            reverse("user_page", kwargs={"user": self.anotheruser.username})
        )

        self.assertContains(response, f'href="{contact_url}"')
        self.assertNotContains(response, 'href="https://example.org/contact"')

        response = self.client.get(contact_url)
        self.assertContains(response, "External contact link")
        self.assertContains(response, "example.org/contact")
        self.assertContains(response, 'href="https://example.org/contact"')

    def test_user_contact_missing(self) -> None:
        response = self.client.get(
            reverse("user_contact", kwargs={"user": self.anotheruser.username})
        )

        self.assertEqual(response.status_code, 404)

    def test_user_contact_redirects_legacy_invalid_values(self) -> None:
        contact_url = reverse(
            "user_contact", kwargs={"user": self.anotheruser.username}
        )
        profile_url = reverse("user_page", kwargs={"user": self.anotheruser.username})

        for url in (
            "https://example.org/file.zip",
            "https://user@example.org/contact",
            "https://127.0.0.1/contact",
        ):
            Profile.objects.filter(pk=self.anotheruser.profile.pk).update(contact=url)

            response = self.client.get(contact_url, follow=True)

            self.assertRedirects(response, profile_url)
            self.assertContains(response, "This contact link is no longer available.")

    def test_profile_dashboard(self) -> None:
        # Save profile with invalid settings
        response = self.client.post(
            reverse("profile"),
            {
                "language": "en",
                "languages": Language.objects.get(code="cs").id,
                "secondary_languages": Language.objects.get(code="cs").id,
                "full_name": "First Last",
                "email": "weblate@example.org",
                "username": "testik",
                "dashboard_view": Profile.DASHBOARD_COMPONENT_LIST,
                "translate_mode": Profile.TRANSLATE_FULL,
                "zen_mode": Profile.ZEN_VERTICAL,
                "nearby_strings": 10,
                "theme": "auto",
                "notifications__0-scope": 0,
                "notifications__0-project": "",
                "notifications__0-component": "",
                "notifications__1-scope": 10,
                "notifications__1-project": "",
                "notifications__1-component": "",
                "notifications__2-scope": 20,
                "notifications__2-project": "",
                "notifications__2-component": "",
            },
        )
        self.assertContains(response, "Select a valid choice.")

    def test_userdata(self) -> None:
        response = self.client.post(reverse("userdata"))
        self.assertContains(response, "basic")

        # Add more languages
        self.user.profile.languages.add(Language.objects.get(code="pl"))
        self.user.profile.secondary_languages.add(Language.objects.get(code="de"))
        self.user.profile.secondary_languages.add(Language.objects.get(code="uk"))
        response = self.client.post(reverse("userdata"))
        self.assertContains(response, '"pl"')
        self.assertContains(response, '"de"')
        validate(response.json(), load_schema("weblate-userdata.schema.json"))

    def test_subscription(self) -> None:
        # Get profile page
        response = self.client.get(reverse("profile"))
        self.assertEqual(self.user.subscription_set.count(), 10)

        # Extract current form data
        data: dict[str, str | list[str]] = {}
        for form in response.context["all_forms"]:
            for field in form:
                value = field.value()
                name = field.html_name
                if value is None:
                    data[name] = ""
                elif isinstance(value, list):
                    data[name] = value
                else:
                    data[name] = str(value)

        # Save unchanged data
        response = self.client.post(reverse("profile"), data, follow=True)
        self.assertContains(response, "Your profile has been updated.")
        self.assertEqual(self.user.subscription_set.count(), 10)

        # Remove some subscriptions
        data["notifications__1-notify-LastAuthorCommentNotificaton"] = "0"
        data["notifications__1-notify-MentionCommentNotificaton"] = "0"
        response = self.client.post(reverse("profile"), data, follow=True)
        self.assertContains(response, "Your profile has been updated.")
        self.assertEqual(self.user.subscription_set.count(), 8)

        # Add some subscriptions
        data["notifications__2-notify-ChangedStringNotificaton"] = "1"
        response = self.client.post(reverse("profile"), data, follow=True)
        self.assertContains(response, "Your profile has been updated.")
        self.assertEqual(self.user.subscription_set.count(), 9)

    def test_subscription_customize(self) -> None:
        # Initial view
        response = self.client.get(reverse("profile"))
        self.assertNotContains(response, "Project: Test")
        self.assertNotContains(response, "Component: Test/Test")
        # Configure project
        response = self.client.get(
            reverse("profile"), {"notify_project": self.project.pk}
        )
        self.assertContains(response, "Project: Test")
        self.assertNotContains(response, "Component: Test/Test")
        # Configure component
        response = self.client.get(
            reverse("profile"), {"notify_component": self.component.pk}
        )
        self.assertNotContains(response, "Project: Test")
        self.assertContains(response, "Component: Test/Test")
        # Configure invalid
        response = self.client.get(reverse("profile"), {"notify_component": "a"})
        self.assertNotContains(response, "Project: Test")
        self.assertNotContains(response, "Component: Test/Test")
        # Configure invalid
        response = self.client.get(reverse("profile"), {"notify_project": "a"})
        self.assertNotContains(response, "Project: Test")
        self.assertNotContains(response, "Component: Test/Test")

    def test_subscription_additional_form_defaults_to_active_scope(self) -> None:
        initial_response = self.client.get(
            f"{reverse('profile')}?notify_project={self.project.pk}"
        )
        existing_indexes = [
            int(form.prefix.split("__", 1)[1])
            for form in initial_response.context["all_forms"]
            if form.prefix and form.prefix.startswith("notifications__")
        ]
        extra_index = max(existing_indexes) + 5

        response = self.client.post(
            f"{reverse('profile')}?notify_project={self.project.pk}",
            {
                "username": "",
                f"notifications__{extra_index}-scope": "",
            },
        )
        self.assertEqual(response.status_code, 200)

        form = next(
            (
                item
                for item in response.context["all_forms"]
                if item.prefix == f"notifications__{extra_index}"
            ),
            None,
        )
        if form is None:
            self.fail(f"Expected extra notification form notifications__{extra_index}")
        self.assertEqual(form.initial["scope"], NotificationScope.SCOPE_PROJECT)
        self.assertEqual(form.initial["project"], self.project)

    def test_watch(self) -> None:
        self.assertEqual(self.user.profile.watched.count(), 0)
        self.assertEqual(self.user.subscription_set.count(), 10)

        # Watch project
        self.client.post(reverse("watch", kwargs={"path": self.project.get_url_path()}))
        self.assertEqual(self.user.profile.watched.count(), 1)
        self.assertEqual(
            self.user.subscription_set.filter(project=self.project).count(), 0
        )

        # Mute notifications for component
        self.client.post(reverse("mute", kwargs=self.kw_component))
        self.assertEqual(
            self.user.subscription_set.filter(component=self.component).count(), 20
        )

        # Mute notifications for project
        self.client.post(reverse("mute", kwargs={"path": self.project.get_url_path()}))
        self.assertEqual(
            self.user.subscription_set.filter(project=self.project).count(), 20
        )

        # Unwatch project
        self.client.post(
            reverse("unwatch", kwargs={"path": self.project.get_url_path()})
        )
        self.assertEqual(self.user.profile.watched.count(), 0)
        self.assertEqual(
            self.user.subscription_set.filter(project=self.project).count(), 0
        )
        self.assertEqual(
            self.user.subscription_set.filter(component=self.component).count(), 0
        )
        self.assertEqual(self.user.subscription_set.count(), 10)

    def test_watch_component(self) -> None:
        self.assertEqual(self.user.profile.watched.count(), 0)
        self.assertEqual(self.user.subscription_set.count(), 10)

        # Watch component
        self.client.post(reverse("watch", kwargs=self.kw_component))
        self.assertEqual(self.user.profile.watched.count(), 1)
        # All project notifications should be muted
        self.assertEqual(
            self.user.subscription_set.filter(project=self.project).count(), 20
        )
        # Only default notifications should be enabled
        self.assertEqual(
            self.user.subscription_set.filter(component=self.component).count(), 4
        )

    def test_unsubscribe(self) -> None:
        response = self.client.get(reverse("unsubscribe"), follow=True)
        self.assertRedirects(response, f"{reverse('profile')}#notifications")

        response = self.client.get(reverse("unsubscribe"), {"i": "x"}, follow=True)
        self.assertRedirects(response, f"{reverse('profile')}#notifications")
        self.assertContains(response, "notification change link is no longer valid")

        response = self.client.get(
            reverse("unsubscribe"), {"i": TimestampSigner().sign("-1")}, follow=True
        )
        self.assertRedirects(response, f"{reverse('profile')}#notifications")
        self.assertContains(response, "notification change link is no longer valid")

        subscription = Subscription.objects.create(
            user=self.user,
            notification="x",
            frequency=NotificationFrequency.FREQ_DAILY,
            scope=NotificationScope.SCOPE_WATCHED,
        )
        response = self.client.get(
            reverse("unsubscribe"),
            {"i": TimestampSigner().sign(f"{subscription.pk}")},
            follow=True,
        )
        self.assertRedirects(response, f"{reverse('profile')}#notifications")
        self.assertContains(response, "Notification settings adjusted")
        subscription.refresh_from_db()
        self.assertEqual(subscription.frequency, NotificationFrequency.FREQ_NONE)

    def test_profile_password_warning(self) -> None:
        with mock.patch.object(User, "has_usable_password", return_value=False):
            response = self.client.get(reverse("profile"))
            self.assertContains(response, "Please enable the password authentication")
            with social_core_modify_settings(
                AUTHENTICATION_BACKENDS={
                    "remove": "social_core.backends.email.EmailAuth"
                }
            ):
                response = self.client.get(reverse("profile"))
                self.assertNotContains(
                    response, "Please enable the password authentication"
                )
        self.assertTrue(self.user.has_usable_password())
        response = self.client.get(reverse("profile"))
        self.assertNotContains(response, "Please enable the password authentication")

    def test_language(self) -> None:
        self.user.profile.languages.clear()

        # English is not saved
        self.client.get(reverse("profile"), headers={"accept-language": "en"})
        self.assertFalse(self.user.profile.languages.exists())

        # Other language is saved
        self.client.get(reverse("profile"), headers={"accept-language": "cs"})
        self.assertEqual(
            set(self.user.profile.languages.values_list("code", flat=True)), {"cs"}
        )


class EditUserTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user.is_superuser = True
        self.user.save()

    def test_edit(self) -> None:
        # Change user as superuser
        response = self.client.post(
            self.user.get_absolute_url(),
            {
                "username": "us",
                "full_name": "Full name",
                "email": "noreply@example.com",
                "is_active": "1",
            },
        )
        user = User.objects.get(pk=self.user.pk)
        self.assertRedirects(response, user.get_absolute_url())
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_superuser)
        audit = user.auditlog_set.get(activity="superuser-revoked")
        self.assertEqual(audit.params["username"], self.user.username)
        # No permissions now
        response = self.client.post(
            self.user.get_absolute_url(),
            {
                "username": "us",
                "full_name": "Full name",
                "email": "noreply@example.com",
                "is_active": "1",
            },
        )
        self.assertEqual(response.status_code, 403)


class AdminUserRevertTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user.is_superuser = True
        self.user.save()
        self.target_user = User.objects.create_user(
            username="sitewide-target", password="testpassword"
        )

    def test_revert_user_edits(self) -> None:
        unit = self.get_unit()
        self.change_unit("Nazdar svete!\n", user=self.target_user)

        with mock.patch(
            "weblate.accounts.views.revert_user_edits_task.delay",
            return_value=SimpleNamespace(id="task-1"),
        ) as mocked_delay:
            response = self.client.post(
                self.target_user.get_absolute_url(),
                {"revert_user_edits": "1"},
                follow=True,
            )

        mocked_delay.assert_called_once_with(
            target_user_id=self.target_user.id,
            acting_user_id=self.user.id,
            sitewide=True,
        )
        self.assertContains(
            response, "Reverting edits by sitewide-target site-wide was scheduled."
        )
        unit.refresh_from_db()
        self.assertEqual(unit.target, "Nazdar svete!\n")
        self.assertEqual(unit.state, STATE_TRANSLATED)
