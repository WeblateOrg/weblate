# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import datetime
import re
from datetime import timedelta
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlparse

from appconf import AppConf
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Upper
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.timezone import now
from django.utils.translation import get_language, gettext, gettext_lazy, pgettext_lazy
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp_webauthn.models import WebAuthnCredential
from rest_framework.authtoken.models import Token
from social_django.models import UserSocialAuth
from unidecode import unidecode

from weblate.accounts.avatar import get_user_display
from weblate.accounts.data import create_default_notifications
from weblate.accounts.notifications import (
    NOTIFICATIONS,
    NotificationFrequency,
    NotificationScope,
)
from weblate.accounts.tasks import notify_auditlog
from weblate.auth.models import AuthenticatedHttpRequest, User
from weblate.lang.models import Language
from weblate.trans.defines import EMAIL_LENGTH
from weblate.trans.models import Change, ComponentList, Translation, Unit
from weblate.trans.models.translation import GhostTranslation
from weblate.utils import messages
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.fields import EmailField
from weblate.utils.html import mail_quote_value
from weblate.utils.render import validate_editor
from weblate.utils.request import get_ip_address, get_user_agent
from weblate.utils.stats import (
    CategoryLanguageStats,
    GhostProjectLanguageStats,
    ProjectLanguageStats,
)
from weblate.utils.token import get_token
from weblate.utils.validators import EMAIL_BLACKLIST, WeblateURLValidator
from weblate.wladmin.models import get_support_status

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from django_otp.models import Device


class WeblateAccountsConf(AppConf):
    """Accounts settings."""

    # Disable avatars
    ENABLE_AVATARS = True

    # Avatar URL prefix
    AVATAR_URL_PREFIX = "https://www.gravatar.com/"

    # Avatar fallback image
    # See http://en.gravatar.com/site/implement/images/ for available choices
    AVATAR_DEFAULT_IMAGE = "identicon"

    # Enable registrations
    REGISTRATION_OPEN = True

    # Allow registration from certain backends
    REGISTRATION_ALLOW_BACKENDS = []

    # Allow rebinding to existing accounts
    REGISTRATION_REBIND = False

    # Registration email filter
    REGISTRATION_EMAIL_MATCH = ".*"

    # Captcha for registrations
    REGISTRATION_CAPTCHA = True

    ALTCHA_MAX_NUMBER = 1_000_000

    REGISTRATION_HINTS = {}

    # How long to keep auditlog entries
    AUDITLOG_EXPIRY = 180

    # Disable login support status check for superusers
    SUPPORT_STATUS_CHECK = True

    # Auto-watch setting for new users
    DEFAULT_AUTO_WATCH = True

    CONTACT_FORM = "reply-to"

    PRIVATE_COMMIT_EMAIL_TEMPLATE = "{username}@users.noreply.{site_domain}"
    PRIVATE_COMMIT_EMAIL_OPT_IN = True

    # Auth0 provider default image & title on login page
    SOCIAL_AUTH_AUTH0_IMAGE = "auth0.svg"
    SOCIAL_AUTH_AUTH0_TITLE = "Auth0"
    SOCIAL_AUTH_SAML_IMAGE = "saml.svg"
    SOCIAL_AUTH_SAML_TITLE = "SAML"

    MAXIMAL_PASSWORD_LENGTH = 72

    # Login required URLs
    LOGIN_REQUIRED_URLS = []
    LOGIN_REQUIRED_URLS_EXCEPTIONS = (
        r"{URL_PREFIX}/accounts/(.*)$",  # Required for login
        r"{URL_PREFIX}/admin/login/(.*)$",  # Required for admin login
        r"{URL_PREFIX}/static/(.*)$",  # Required for development mode
        r"{URL_PREFIX}/widgets/(.*)$",  # Allowing public access to widgets
        r"{URL_PREFIX}/data/(.*)$",  # Allowing public access to data exports
        r"{URL_PREFIX}/hooks/(.*)$",  # Allowing public access to notification hooks
        r"{URL_PREFIX}/healthz/$",  # Allowing public access to health check
        r"{URL_PREFIX}/api/(.*)$",  # Allowing access to API
        r"{URL_PREFIX}/js/i18n/$",  # JavaScript localization
        r"{URL_PREFIX}/contact/$",  # Optional for contact form
        r"{URL_PREFIX}/legal/(.*)$",  # Optional for legal app
        r"{URL_PREFIX}/avatar/(.*)$",  # Optional for avatars
        r"{URL_PREFIX}/site.webmanifest$",  # The request for the manifest is made without credentials
    )

    class Meta:
        prefix = ""


# This is essentially a part for django.core.validators.EmailValidator
DOT_ATOM_RE = re.compile(
    r"^[-!#$%&'*+/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+/=?^_`{}|~0-9A-Z]+)*\Z", re.IGNORECASE
)


def format_private_email(username: str, user_id: int) -> str:
    if not settings.PRIVATE_COMMIT_EMAIL_TEMPLATE:
        return ""
    if username:
        if username.endswith(".") or ".." in username:
            # Remove problematic docs
            username = username.replace(".", "_")
        if not DOT_ATOM_RE.match(username):
            # Remove unicode
            username = unidecode(username)
        if not DOT_ATOM_RE.match(username) or EMAIL_BLACKLIST.match(username):
            username = ""
    if not username:
        username = f"user-{user_id}"
    return settings.PRIVATE_COMMIT_EMAIL_TEMPLATE.format(
        username=username.lower(),
        site_domain=settings.SITE_DOMAIN.rsplit(":", 1)[0],
    )


class SubscriptionQuerySet(models.QuerySet["Subscription"]):
    def order(self):
        """Ordering in project scope by priority."""
        return self.order_by("user", "scope")

    def prefetch(self):
        return self.prefetch_related("component", "project")


class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.deletion.CASCADE)
    notification = models.CharField(
        choices=[n.get_choice() for n in NOTIFICATIONS], max_length=100
    )
    scope = models.IntegerField(choices=NotificationScope.choices)
    frequency = models.IntegerField(choices=NotificationFrequency.choices)
    project = models.ForeignKey(
        "trans.Project", on_delete=models.deletion.CASCADE, null=True
    )
    component = models.ForeignKey(
        "trans.Component", on_delete=models.deletion.CASCADE, null=True
    )
    onetime = models.BooleanField(default=False)

    objects = SubscriptionQuerySet.as_manager()

    class Meta:
        verbose_name = "Notification subscription"
        verbose_name_plural = "Notification subscriptions"
        constraints = [
            models.UniqueConstraint(
                name="accounts_subscription_notification_unique",
                fields=("notification", "scope", "project", "component", "user"),
                nulls_distinct=False,
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user.username}:{self.get_scope_display()},{self.get_notification_display()} ({self.project},{self.component})"


ACCOUNT_ACTIVITY = {
    "password": gettext_lazy("Password changed."),
    "username": gettext_lazy("Username changed from {old} to {new}."),
    "email": gettext_lazy("E-mail changed from {old} to {new}."),
    "full_name": gettext_lazy("Full name changed from {old} to {new}."),
    "reset-request": gettext_lazy("Password reset requested."),
    "reset": gettext_lazy("Password reset confirmed, password turned off."),
    "auth-connect": gettext_lazy("Configured sign in using {method} ({name})."),
    "auth-disconnect": gettext_lazy("Removed sign in using {method} ({name})."),
    "login": gettext_lazy("Signed in using {method} ({name})."),
    "login-new": gettext_lazy("Signed in using {method} ({name}) from a new device."),
    "register": gettext_lazy("Somebody attempted to register with your e-mail."),
    "connect": gettext_lazy(
        "Somebody attempted to register using your e-mail address."
    ),
    "failed-auth": gettext_lazy("Could not sign in using {method} ({name})."),
    "locked": gettext_lazy("Account locked due to many failed sign in attempts."),
    "admin-locked": gettext_lazy("Account locked by the site administrator."),
    "removed": gettext_lazy("Account and all private data removed."),
    "removal-request": gettext_lazy("Account removal confirmation sent to {email}."),
    "tos": gettext_lazy("Agreement with General Terms and Conditions {date}."),
    "invited": gettext_lazy("Invited to {site_title} by {username}."),
    "accepted": gettext_lazy("Accepted invitation from {username}."),
    "trial": gettext_lazy("Started trial period."),
    "sent-email": gettext_lazy("Sent confirmation mail to {email}."),
    "autocreated": gettext_lazy(
        "The system created a user to track authorship of "
        "translations uploaded by other user."
    ),
    "blocked": gettext_lazy("Access to project {project} was blocked."),
    "enabled": gettext_lazy("User was enabled by administrator."),
    "disabled": gettext_lazy("User was disabled by administrator."),
    "donate": gettext_lazy("Semiannual support status review was displayed."),
    "team-add": gettext_lazy("User was added to the {team} team by {username}."),
    "team-remove": gettext_lazy("User was removed from the {team} team by {username}."),
    "recovery-generate": gettext_lazy(
        "Two-factor authentication recovery codes were generated"
    ),
    "recovery-show": gettext_lazy(
        "Two-factor authentication recovery codes were viewed"
    ),
    "twofactor-add": gettext_lazy("Two-factor authentication added: {device}"),
    "twofactor-remove": gettext_lazy("Two-factor authentication removed: {device}"),
    "twofactor-login": gettext_lazy("Two-factor authentication sign in using {device}"),
}
# Override activity messages based on method
ACCOUNT_ACTIVITY_METHOD = {
    "password": {
        "auth-connect": gettext_lazy("Configured password to sign in."),
        "login": gettext_lazy("Signed in using password."),
        "login-new": gettext_lazy("Signed in using password from a new device."),
        "failed-auth": gettext_lazy("Could not sign in using password."),
    },
    "project": {
        "invited": gettext_lazy("Invited to {project} by {username}."),
    },
    "configured": {
        "password": gettext_lazy("Password configured."),
    },
}

EXTRA_MESSAGES = {
    "locked": gettext_lazy(
        "To restore access to your account, please reset your password."
    ),
    "blocked": gettext_lazy(
        "Please contact project maintainers if you feel this is inappropriate."
    ),
    "register": gettext_lazy(
        "If it was you, please use a password reset to regain access to your account."
    ),
    "connect": gettext_lazy(
        "If it was you, please use a password reset to regain access to your account."
    ),
}

NOTIFY_ACTIVITY = {
    "password",
    "reset",
    "auth-connect",
    "auth-disconnect",
    "register",
    "connect",
    "locked",
    "removed",
    "login-new",
    "email",
    "username",
    "full_name",
    "blocked",
    "recovery-generate",
    "recovery-show",
    "twofactor-add",
    "twofactor-remove",
}


class AuditLogManager(models.Manager):
    def is_new_login(self, user: User, address, user_agent) -> bool:
        """
        Check whether this login is coming from a new device.

        Currently based purely on the IP address.
        """
        logins = self.filter(user=user, activity="login-new")

        # First login
        if not logins.exists():
            return False

        return not logins.filter(Q(address=address) | Q(user_agent=user_agent)).exists()

    def create(
        self, user: User, request: AuthenticatedHttpRequest | None, activity, **params
    ):
        address = get_ip_address(request)
        user_agent = get_user_agent(request)
        if activity == "login" and self.is_new_login(user, address, user_agent):
            activity = "login-new"
        return super().create(
            user=user,
            activity=activity,
            address=address,
            user_agent=user_agent,
            params=params,
        )


class AuditLogQuerySet(models.QuerySet["AuditLog"]):
    def get_after(self, user: User, after, activity):
        """
        Get user activities of given type after another activity.

        This is mostly used for rate limiting, as it can return the number of failed
        authentication attempts since last login.
        """
        try:
            latest_login = self.filter(user=user, activity=after).order()[0]
            kwargs = {"timestamp__gte": latest_login.timestamp}
        except IndexError:
            kwargs = {}
        return self.filter(user=user, activity=activity, **kwargs)

    def get_past_passwords(self, user: User):
        """Get user activities with password change."""
        start = timezone.now() - datetime.timedelta(days=settings.AUTH_PASSWORD_DAYS)
        return self.filter(
            user=user, activity__in=("reset", "password"), timestamp__gt=start
        )

    def order(self):
        return self.order_by("-timestamp")


class AuditLog(models.Model):
    """User audit log storage."""

    user = models.ForeignKey(User, on_delete=models.deletion.CASCADE, null=True)
    activity = models.CharField(
        max_length=20,
        choices=[(a, a) for a in sorted(ACCOUNT_ACTIVITY.keys())],
        db_index=True,
    )
    params = models.JSONField(default=dict)
    address = models.GenericIPAddressField(null=True)
    user_agent = models.CharField(max_length=200, default="")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditLogManager.from_queryset(AuditLogQuerySet)()

    class Meta:
        verbose_name = "Audit log entry"
        verbose_name_plural = "Audit log entries"

    def __str__(self) -> str:
        return f"{self.activity} for {self.user.username} from {self.address}"

    def save(self, *args, **kwargs) -> None:
        super().save(*args, **kwargs)
        if self.should_notify():
            email = self.user.email
            notify_auditlog.delay_on_commit(self.pk, email)

    def get_params(self):
        from weblate.accounts.templatetags.authnames import get_auth_name

        result = {
            "site_title": settings.SITE_TITLE,
        }
        for name, value in self.params.items():
            if value is None:
                value = format_html("<em>{}</em>", value)
            elif name in {"old", "new", "name", "email", "username"}:
                value = format_html("<code>{}</code>", mail_quote_value(value))
            elif name == "method":
                value = format_html("<strong>{}</strong>", get_auth_name(value))
            elif name in {"device", "project", "site_title"}:
                value = format_html("<strong>{}</strong>", mail_quote_value(value))

            result[name] = value

        return result

    @admin.display(description=gettext_lazy("Account activity"))
    def get_message(self):
        method = self.params.get("method")
        activity = self.activity
        if activity in ACCOUNT_ACTIVITY_METHOD.get(method, {}):
            message = ACCOUNT_ACTIVITY_METHOD[method][activity]
        else:
            message = ACCOUNT_ACTIVITY[activity]
        return format_html(message, **self.get_params())

    def get_extra_message(self):
        if self.activity in EXTRA_MESSAGES:
            return EXTRA_MESSAGES[self.activity].format(**self.params)
        return None

    def should_notify(self):
        return (
            self.user is not None
            and not self.user.is_bot
            and self.user.is_active
            and self.user.email
            and self.activity in NOTIFY_ACTIVITY
            and not self.params.get("skip_notify")
        )

    def check_rate_limit(self, request: AuthenticatedHttpRequest) -> bool:
        """Check whether the activity should be rate limited."""
        from weblate.accounts.utils import lock_user

        if self.activity == "failed-auth" and self.user.has_usable_password():
            failures = AuditLog.objects.get_after(self.user, "login", "failed-auth")
            if failures.count() >= settings.AUTH_LOCK_ATTEMPTS:
                lock_user(self.user, "locked", request)
                return True

        elif self.activity == "reset-request":
            failures = AuditLog.objects.filter(
                user=self.user,
                timestamp__gte=timezone.now() - datetime.timedelta(days=1),
                activity="reset-request",
            )
            if failures.count() >= settings.AUTH_LOCK_ATTEMPTS:
                return True

        return False


class VerifiedEmail(models.Model):
    """Storage for verified e-mails from auth backends."""

    is_deliverable = models.BooleanField(default=True)
    social = models.ForeignKey(UserSocialAuth, on_delete=models.deletion.CASCADE)
    email = EmailField()

    class Meta:
        verbose_name = "Verified e-mail"
        verbose_name_plural = "Verified e-mails"
        indexes = [
            models.Index(
                Upper("email"),
                name="accounts_verifiedemail_email",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.social.user.username} - {self.email}"

    @property
    def provider(self):
        return self.social.provider


class Profile(models.Model):
    """User profiles storage."""

    user = models.OneToOneField(
        User, unique=True, editable=False, on_delete=models.deletion.CASCADE
    )
    language = models.CharField(
        verbose_name=gettext_lazy("Interface Language"),
        max_length=10,
        choices=settings.LANGUAGES,
    )
    languages = models.ManyToManyField(
        Language,
        verbose_name=gettext_lazy("Translated languages"),
        blank=True,
        help_text=gettext_lazy(
            "Choose the languages you can translate to. "
            "These will be offered to you on the dashboard "
            "for easier access to your chosen translations."
        ),
    )
    secondary_languages = models.ManyToManyField(
        Language,
        verbose_name=gettext_lazy("Secondary languages"),
        help_text=gettext_lazy(
            "Choose languages you can understand, strings in those languages "
            "will be shown in addition to the source string."
        ),
        related_name="secondary_profile_set",
        blank=True,
    )
    suggested = models.IntegerField(default=0, db_index=True)
    translated = models.IntegerField(default=0, db_index=True)
    uploaded = models.IntegerField(default=0, db_index=True)
    commented = models.IntegerField(default=0, db_index=True)
    theme = models.CharField(
        max_length=10,
        verbose_name=gettext_lazy("Theme"),
        default="auto",
        choices=(
            ("auto", pgettext_lazy("Theme selection", "Sync with system")),
            ("light", pgettext_lazy("Theme selection", "Light")),
            ("dark", pgettext_lazy("Theme selection", "Dark")),
        ),
    )
    hide_completed = models.BooleanField(
        verbose_name=gettext_lazy("Hide completed translations on the dashboard"),
        default=False,
    )
    secondary_in_zen = models.BooleanField(
        verbose_name=gettext_lazy("Show secondary translations in the Zen mode"),
        default=True,
    )
    hide_source_secondary = models.BooleanField(
        verbose_name=gettext_lazy("Hide source if a secondary translation exists"),
        default=False,
    )
    editor_link = models.CharField(
        default="",
        blank=True,
        max_length=200,
        verbose_name=gettext_lazy("Editor link"),
        help_text=gettext_lazy(
            "Enter a custom URL to be used as link to the source code. "
            "You can use {{branch}} for branch, "
            "{{filename}} and {{line}} as filename and line placeholders."
        ),
        validators=[validate_editor],
    )
    TRANSLATE_FULL = 0
    TRANSLATE_ZEN = 1
    translate_mode = models.IntegerField(
        verbose_name=gettext_lazy("Translation editor mode"),
        choices=(
            (TRANSLATE_FULL, gettext_lazy("Full editor")),
            (TRANSLATE_ZEN, gettext_lazy("Zen mode")),
        ),
        default=TRANSLATE_FULL,
    )
    ZEN_VERTICAL = 0
    ZEN_HORIZONTAL = 1
    zen_mode = models.IntegerField(
        verbose_name=gettext_lazy("Zen editor mode"),
        choices=(
            (ZEN_VERTICAL, gettext_lazy("Top to bottom")),
            (ZEN_HORIZONTAL, gettext_lazy("Side by side")),
        ),
        default=ZEN_VERTICAL,
    )
    special_chars = models.CharField(
        default="",
        blank=True,
        max_length=30,
        verbose_name=gettext_lazy("Special characters"),
        help_text=gettext_lazy(
            "You can specify additional special visual keyboard characters "
            "to be shown while translating. It can be useful for "
            "characters you use frequently, but are hard to type on your keyboard."
        ),
    )
    nearby_strings = models.SmallIntegerField(
        verbose_name=gettext_lazy("Number of nearby strings"),
        default=settings.NEARBY_MESSAGES,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text=gettext_lazy(
            "Number of nearby strings to show in each direction in the full editor."
        ),
    )
    auto_watch = models.BooleanField(
        verbose_name=gettext_lazy("Automatically watch projects on contribution"),
        default=settings.DEFAULT_AUTO_WATCH,
        help_text=gettext_lazy(
            "Whenever you translate a string in a project, you will start watching it."
        ),
    )

    DASHBOARD_WATCHED = 1
    DASHBOARD_COMPONENT_LIST = 4
    DASHBOARD_SUGGESTIONS = 5
    DASHBOARD_COMPONENT_LISTS = 6
    DASHBOARD_MANAGED = 7

    DASHBOARD_CHOICES = (
        (DASHBOARD_WATCHED, gettext_lazy("Watched translations")),
        (DASHBOARD_COMPONENT_LISTS, gettext_lazy("Component lists")),
        (DASHBOARD_COMPONENT_LIST, gettext_lazy("Component list")),
        (DASHBOARD_SUGGESTIONS, gettext_lazy("Suggested translations")),
        (DASHBOARD_MANAGED, gettext_lazy("Managed projects")),
    )

    DASHBOARD_SLUGS = {
        DASHBOARD_WATCHED: "your-subscriptions",
        DASHBOARD_COMPONENT_LIST: "list",
        DASHBOARD_SUGGESTIONS: "suggestions",
        DASHBOARD_COMPONENT_LISTS: "componentlists",
        DASHBOARD_MANAGED: "managed",
    }

    dashboard_view = models.IntegerField(
        choices=DASHBOARD_CHOICES,
        verbose_name=gettext_lazy("Default dashboard view"),
        default=DASHBOARD_WATCHED,
    )

    dashboard_component_list = models.ForeignKey(
        "trans.ComponentList",
        verbose_name=gettext_lazy("Default component list"),
        on_delete=models.deletion.SET_NULL,
        blank=True,
        null=True,
    )

    watched = models.ManyToManyField(
        "trans.Project",
        verbose_name=gettext_lazy("Watched projects"),
        help_text=gettext_lazy(
            "You can receive notifications for watched projects and "
            "they are shown on the dashboard by default."
        ),
        blank=True,
    )

    # Public profile fields
    website = models.URLField(
        verbose_name=gettext_lazy("Website URL"),
        blank=True,
        validators=[WeblateURLValidator()],
    )
    liberapay = models.SlugField(
        verbose_name=gettext_lazy("Liberapay username"),
        blank=True,
        help_text=gettext_lazy(
            "Liberapay is a platform to donate money to teams, "
            "organizations and individuals."
        ),
        db_index=False,
    )
    fediverse = models.URLField(
        verbose_name=gettext_lazy("Fediverse URL"),
        blank=True,
        help_text=gettext_lazy(
            "Link to your Fediverse profile for federated services "
            "like Mastodon or diaspora*."
        ),
        validators=[WeblateURLValidator()],
    )
    codesite = models.URLField(
        verbose_name=gettext_lazy("Code site URL"),
        blank=True,
        help_text=gettext_lazy(
            "Link to your code profile for services like Codeberg or GitLab."
        ),
        validators=[WeblateURLValidator()],
    )
    github = models.SlugField(
        verbose_name=gettext_lazy("GitHub username"),
        blank=True,
        db_index=False,
    )
    twitter = models.SlugField(
        verbose_name=gettext_lazy("X username"),
        blank=True,
        db_index=False,
    )
    linkedin = models.SlugField(
        verbose_name=gettext_lazy("LinkedIn profile name"),
        help_text=gettext_lazy(
            "Your LinkedIn profile name from linkedin.com/in/profilename"
        ),
        blank=True,
        db_index=False,
        allow_unicode=True,
    )
    location = models.CharField(
        verbose_name=gettext_lazy("Location"),
        max_length=100,
        blank=True,
    )
    company = models.CharField(
        verbose_name=gettext_lazy("Company"),
        max_length=100,
        blank=True,
    )
    public_email = EmailField(
        verbose_name=gettext_lazy("Public e-mail"),
        blank=True,
        max_length=EMAIL_LENGTH,
    )

    commit_email = EmailField(
        verbose_name=gettext_lazy("Commit e-mail"),
        blank=True,
        max_length=EMAIL_LENGTH,
    )

    last_2fa = models.CharField(
        choices=(
            ("", "None"),
            ("totp", "TOTP"),
            ("webauthn", "WebAuthn"),
        ),
        blank=True,
        default="",
        max_length=15,
    )

    class Meta:
        verbose_name = "User profile"
        verbose_name_plural = "User profiles"

    def __str__(self) -> str:
        return self.user.username

    def get_absolute_url(self) -> str:
        return self.user.get_absolute_url()

    def get_user_display(self):
        return get_user_display(self.user)

    def get_user_display_link(self):
        return get_user_display(self.user, True, True)

    def get_user_name(self):
        return get_user_display(self.user, False)

    def get_fediverse_share(self):
        if not self.fediverse:
            return None
        parsed = urlparse(self.fediverse)
        if not parsed.hostname:
            return None
        return parsed._replace(path="/share", query="text=", fragment="").geturl()

    def increase_count(self, item: str, increase: int = 1) -> None:
        """Update user actions counter."""
        # Update our copy
        setattr(self, item, getattr(self, item) + increase)
        # Update database
        update = {item: F(item) + increase}
        Profile.objects.filter(pk=self.pk).update(**update)

    @cached_property
    def all_languages(self):
        return self.languages.all()

    @property
    def full_name(self):
        """Return user's full name."""
        return self.user.full_name

    def clean(self) -> None:
        """Check if component list is chosen when required."""
        # There is matching logic in ProfileBaseForm.add_error to ignore this
        # validation on partial forms
        if (
            self.dashboard_view == Profile.DASHBOARD_COMPONENT_LIST
            and self.dashboard_component_list is None
        ):
            message = gettext(
                "Please choose which component list you want to display on "
                "the dashboard."
            )
            raise ValidationError(
                {"dashboard_component_list": message, "dashboard_view": message}
            )
        if (
            self.dashboard_view != Profile.DASHBOARD_COMPONENT_LIST
            and self.dashboard_component_list is not None
        ):
            message = gettext(
                "Selecting component list has no effect when not shown on "
                "the dashboard."
            )
            raise ValidationError(
                {"dashboard_component_list": message, "dashboard_view": message}
            )

    def dump_data(self):
        def map_attr(attr):
            if attr.endswith("_id"):
                return attr[:-3]
            return attr

        def dump_object(obj, *attrs):
            return {map_attr(attr): getattr(obj, attr) for attr in attrs}

        result = {
            "basic": dump_object(
                self.user, "username", "full_name", "email", "date_joined"
            ),
            "profile": dump_object(
                self,
                "language",
                "suggested",
                "translated",
                "uploaded",
                "hide_completed",
                "theme",
                "secondary_in_zen",
                "hide_source_secondary",
                "editor_link",
                "translate_mode",
                "zen_mode",
                "special_chars",
                "dashboard_view",
                "dashboard_component_list_id",
            ),
            "auditlog": [
                dump_object(log, "address", "user_agent", "timestamp", "activity")
                for log in self.user.auditlog_set.iterator()
            ],
        }
        result["profile"]["languages"] = [
            lang.code for lang in self.languages.iterator()
        ]
        result["profile"]["secondary_languages"] = [
            lang.code for lang in self.secondary_languages.iterator()
        ]
        result["profile"]["watched"] = [
            project.slug for project in self.watched.iterator()
        ]
        return result

    @cached_property
    def primary_language_ids(self) -> set[int]:
        return {language.pk for language in self.all_languages}

    @cached_property
    def allowed_dashboard_component_lists(self):
        return ComponentList.objects.filter(
            show_dashboard=True,
            components__project__in=self.user.allowed_projects,
        ).distinct()

    @cached_property
    def secondary_language_ids(self) -> set[int]:
        return set(self.secondary_languages.values_list("pk", flat=True))

    def get_translation_orderer(
        self, request: AuthenticatedHttpRequest | None
    ) -> Callable[
        [
            Iterable[
                Unit
                | Translation
                | Language
                | ProjectLanguageStats
                | CategoryLanguageStats
                | GhostProjectLanguageStats
                | GhostTranslation
            ]
        ],
        str,
    ]:
        """Create a function suitable for ordering languages based on user preferences."""

        def get_translation_order(
            obj: Unit
            | Translation
            | Language
            | ProjectLanguageStats
            | CategoryLanguageStats
            | GhostProjectLanguageStats
            | GhostTranslation,
        ) -> str:
            from weblate.trans.models import Unit

            language: Language
            is_source = False
            if isinstance(obj, Language):
                language = obj
            elif isinstance(obj, Unit):
                translation = obj.translation
                language = translation.language
                is_source = translation.is_source
            elif isinstance(
                obj,
                (
                    Translation,
                    ProjectLanguageStats,
                    CategoryLanguageStats,
                    GhostProjectLanguageStats,
                    GhostTranslation,
                ),
            ):
                language = obj.language
                is_source = obj.is_source
            else:
                message = f"{obj.__class__.__name__} is not supported"
                raise TypeError(message)

            if language.pk in self.primary_language_ids:
                priority = 0
            elif language.pk in self.secondary_language_ids:
                priority = 1
            elif (
                not self.primary_language_ids
                and request is not None
                and language == request.accepted_language
            ):
                priority = 2
            elif is_source:
                priority = 3
            else:
                priority = 4

            return f"{priority}-{language}"

        return get_translation_order

    def fixup_profile(self, request: AuthenticatedHttpRequest) -> None:
        fields = set()
        if not self.language:
            self.language = get_language()
            fields.add("language")

        allowed = {clist.pk for clist in self.allowed_dashboard_component_lists}

        if not allowed and self.dashboard_view in {
            Profile.DASHBOARD_COMPONENT_LIST,
            Profile.DASHBOARD_COMPONENT_LISTS,
        }:
            self.dashboard_view = Profile.DASHBOARD_WATCHED
            fields.add("dashboard_view")

        if self.dashboard_component_list_id and (
            self.dashboard_component_list_id not in allowed
            or self.dashboard_view != Profile.DASHBOARD_COMPONENT_LIST
        ):
            self.dashboard_component_list = None
            self.dashboard_view = Profile.DASHBOARD_WATCHED
            fields.add("dashboard_view")
            fields.add("dashboard_component_list")

        if (
            not self.dashboard_component_list_id
            and self.dashboard_view == Profile.DASHBOARD_COMPONENT_LIST
        ):
            self.dashboard_view = Profile.DASHBOARD_WATCHED
            fields.add("dashboard_view")

        if not self.languages.exists():
            language = Language.objects.get_request_language(request)
            if language:
                self.languages.add(language)
                messages.info(
                    request,
                    gettext(
                        "Added %(language)s to your translated languages. "
                        "You can adjust them in the settings."
                    )
                    % {"language": language},
                )

        if fields:
            self.save(update_fields=fields)

    def get_commit_email(self) -> str:
        email = self.commit_email
        if (
            not email
            and not settings.PRIVATE_COMMIT_EMAIL_OPT_IN
            and not self.user.is_bot
        ):
            email = self.get_site_commit_email()
        if not email:
            email = self.user.email
        return email

    def get_site_commit_email(self) -> str:
        return format_private_email(self.user.username, self.user.pk)

    def _get_second_factors(self) -> Iterable[Device]:
        backend: type[Device]
        for backend in (StaticDevice, TOTPDevice, WebAuthnCredential):
            yield from backend.objects.filter(user=self.user)

    @cached_property
    def second_factors(self) -> list[Device]:
        return list(self._get_second_factors())

    @cached_property
    def second_factor_types(self) -> set[Literal["totp", "webauthn", "recovery"]]:
        from weblate.accounts.utils import get_key_type

        return {get_key_type(device) for device in self.second_factors}

    @property
    def has_2fa(self) -> bool:
        return any(
            isinstance(device, TOTPDevice | WebAuthnCredential)
            for device in self.second_factors
        )

    def log_2fa(self, request: AuthenticatedHttpRequest, device: Device) -> None:
        from weblate.accounts.utils import get_key_name, get_key_type

        # Audit log entry
        AuditLog.objects.create(
            self.user, request, "twofactor-login", device=get_key_name(device)
        )
        # Store preferred method (skipping recovery codes)
        device_type = get_key_type(device)
        if device_type not in {self.last_2fa, "recovery"}:
            self.last_2fa = device_type
            self.save(update_fields=["last_2fa"])

    def get_second_factor_type(self) -> Literal["totp", "webauthn"]:
        if self.last_2fa in self.second_factor_types:
            return self.last_2fa
        for tested in ("webauthn", "totp"):
            if tested in self.second_factor_types:
                return tested
        msg = "No second factor available!"
        raise ValueError(msg)


def set_lang_cookie(response, profile) -> None:
    """Set session language based on user preferences."""
    if profile.language:
        response.set_cookie(
            settings.LANGUAGE_COOKIE_NAME,
            profile.language,
            max_age=settings.LANGUAGE_COOKIE_AGE,
            path=settings.LANGUAGE_COOKIE_PATH,
            domain=settings.LANGUAGE_COOKIE_DOMAIN,
            secure=settings.LANGUAGE_COOKIE_SECURE,
            httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
            samesite=settings.LANGUAGE_COOKIE_SAMESITE,
        )


@receiver(user_logged_in)
def post_login_handler(
    sender, request: AuthenticatedHttpRequest, user: User, **kwargs
) -> None:
    """
    Signal handler for post login.

    It sets user language and migrates profile if needed.
    """
    backend_name = getattr(user, "backend", "")
    is_email_auth = backend_name.endswith((".EmailAuth", ".WeblateUserBackend"))

    # Warning about setting password
    if is_email_auth and not user.has_usable_password():
        request.session["show_set_password"] = True

    # Redirect superuser to donate page twice a year
    if (
        settings.SUPPORT_STATUS_CHECK
        and user.is_superuser
        and not get_support_status(request)["has_support"]
        and not user.auditlog_set.filter(
            timestamp__gt=now() - timedelta(days=180), activity="donate"
        ).exists()
        and Change.objects.filter(timestamp__lt=now() - timedelta(days=14)).exists()
    ):
        request.session["redirect_to_donate"] = True

    # Migrate django-registration based verification to python-social-auth
    # and handle external authentication such as LDAP
    if (
        is_email_auth
        and user.has_usable_password()
        and user.email
        and not user.social_auth.filter(provider="email").exists()
    ):
        social = user.social_auth.create(provider="email", uid=user.email)
        VerifiedEmail.objects.create(social=social, email=user.email)

    # Fixup accounts with empty name
    if not user.full_name:
        user.full_name = user.username
        user.save(update_fields=["full_name"])

    # Warn about not set e-mail
    if not user.email:
        messages.error(
            request,
            gettext("Please provide an e-mail address for submitting translations."),
        )

    # Sanitize profile
    user.profile.fixup_profile(request)


@receiver(post_save, sender=User)
@disable_for_loaddata
def create_profile_callback(sender, instance, created=False, **kwargs) -> None:
    """Automatically create token and profile for user."""
    if created:
        # Create API token
        instance.auth_token = Token.objects.create(
            user=instance, key=get_token("wlp" if instance.is_bot else "wlu")
        )
        # Create profile
        instance.profile = Profile.objects.create(user=instance)
        # Create subscriptions
        if not instance.is_anonymous and not instance.is_bot:
            create_default_notifications(instance)
