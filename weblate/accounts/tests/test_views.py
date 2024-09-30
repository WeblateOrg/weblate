# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for user handling."""

from __future__ import annotations

from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.signing import TimestampSigner
from django.test.utils import modify_settings, override_settings
from django.urls import reverse
from jsonschema import validate
from weblate_schemas import load_schema

from weblate.accounts.models import Profile, Subscription
from weblate.accounts.notifications import NotificationFrequency, NotificationScope
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import (
    social_core_modify_settings,
    social_core_override_settings,
)
from weblate.utils.ratelimit import reset_rate_limit

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

    @override_settings(
        REGISTRATION_CAPTCHA=False, ADMINS=(("Weblate test", "noreply@weblate.org"),)
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
        self.assertEqual(mail.outbox[0].to, ["noreply@weblate.org"])

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

    @override_settings(RATELIMIT_MESSAGE_ATTEMPTS=1, RATELIMIT_WINDOW=0)
    def test_contact_rate_window(self) -> None:
        """Test for contact form rate limiting."""
        message = "Too many messages sent, please try again later."
        response = self.client.post(reverse("contact"), CONTACT_DATA)
        self.assertNotContains(response, message)
        response = self.client.post(reverse("contact"), CONTACT_DATA)
        self.assertNotContains(response, message)

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
        from weblate.billing.models import Plan

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
        from weblate.billing.models import Plan

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
        self.assertRedirects(response, reverse("contact") + "?t=trial")

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
        self.assertContains(response, "Translations with contribution")

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
        self.get_user()
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
            },
        )

        self.assertRedirects(response, reverse("profile") + "#account")
        self.assertTrue(
            User.objects.get(username="testuser").check_password("1pa$$word!")
        )

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
        self.assertRedirects(response, reverse("profile") + "#api")

        # API key reset without token
        user.auth_token.delete()
        response = self.client.post(reverse("reset-api-key"))
        self.assertRedirects(response, reverse("profile") + "#api")


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
        self.assertRedirects(response, reverse("profile") + "#notifications")

        response = self.client.get(reverse("unsubscribe"), {"i": "x"}, follow=True)
        self.assertRedirects(response, reverse("profile") + "#notifications")
        self.assertContains(response, "notification change link is no longer valid")

        response = self.client.get(
            reverse("unsubscribe"), {"i": TimestampSigner().sign("-1")}, follow=True
        )
        self.assertRedirects(response, reverse("profile") + "#notifications")
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
        self.assertRedirects(response, reverse("profile") + "#notifications")
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
