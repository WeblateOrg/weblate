# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import datetime

from appconf import AppConf
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import get_language, gettext, gettext_lazy, pgettext_lazy
from rest_framework.authtoken.models import Token
from social_django.models import UserSocialAuth

from weblate.accounts.avatar import get_user_display
from weblate.accounts.data import create_default_notifications
from weblate.accounts.notifications import FREQ_CHOICES, NOTIFICATIONS, SCOPE_CHOICES
from weblate.accounts.tasks import notify_auditlog
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.trans.defines import EMAIL_LENGTH
from weblate.trans.models import ComponentList
from weblate.utils import messages
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.fields import EmailField
from weblate.utils.render import validate_editor
from weblate.utils.request import get_ip_address, get_user_agent
from weblate.utils.token import get_token


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

    REGISTRATION_HINTS = {}

    # How long to keep auditlog entries
    AUDITLOG_EXPIRY = 180

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
    )

    class Meta:
        prefix = ""


class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.deletion.CASCADE)
    notification = models.CharField(
        choices=[n.get_choice() for n in NOTIFICATIONS], max_length=100
    )
    scope = models.IntegerField(choices=SCOPE_CHOICES)
    frequency = models.IntegerField(choices=FREQ_CHOICES)
    project = models.ForeignKey(
        "trans.Project", on_delete=models.deletion.CASCADE, null=True
    )
    component = models.ForeignKey(
        "trans.Component", on_delete=models.deletion.CASCADE, null=True
    )
    onetime = models.BooleanField(default=False)

    class Meta:
        unique_together = [("notification", "scope", "project", "component", "user")]
        verbose_name = "Notification subscription"
        verbose_name_plural = "Notification subscriptions"

    def __str__(self):
        return "{}:{},{} ({},{})".format(
            self.user.username,
            self.get_scope_display(),
            self.get_notification_display(),
            self.project,
            self.component,
        )


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
    "removed": gettext_lazy("Account and all private data removed."),
    "removal-request": gettext_lazy("Account removal confirmation sent to {email}."),
    "tos": gettext_lazy("Agreement with Terms of Service {date}."),
    "invited": gettext_lazy("Invited to {site_title} by {username}."),
    "accepted": gettext_lazy("Accepted invitation from {username}."),
    "trial": gettext_lazy("Started trial period."),
    "sent-email": gettext_lazy("Sent confirmation mail to {email}."),
    "autocreated": gettext_lazy(
        "The system created a user to track authorship of "
        "translations uploaded by other user."
    ),
    "blocked": gettext_lazy("Access to project {project} was blocked"),
    "enabled": gettext_lazy("User was enabled by administrator"),
    "disabled": gettext_lazy("User was disabled by administrator"),
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
}


class AuditLogManager(models.Manager):
    def is_new_login(self, user, address, user_agent):
        """
        Checks whether this login is coming from a new device.

        Currently based purely on the IP address.
        """
        logins = self.filter(user=user, activity="login-new")

        # First login
        if not logins.exists():
            return False

        return not logins.filter(Q(address=address) | Q(user_agent=user_agent)).exists()

    def create(self, user, request, activity, **params):
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


class AuditLogQuerySet(models.QuerySet):
    def get_after(self, user, after, activity):
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

    def get_past_passwords(self, user):
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

    def __str__(self):
        return f"{self.activity} for {self.user.username} from {self.address}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.should_notify():
            email = self.user.email
            transaction.on_commit(lambda: notify_auditlog.delay(self.pk, email))

    def get_params(self):
        from weblate.accounts.templatetags.authnames import get_auth_name

        result = {
            "site_title": settings.SITE_TITLE,
        }
        result.update(self.params)
        if "method" in result:
            # The gettext is here for legacy entries which contained method name
            result["method"] = gettext(get_auth_name(result["method"]))
        return result

    @admin.display(description=gettext_lazy("Account activity"))
    def get_message(self):
        method = self.params.get("method")
        activity = self.activity
        if activity in ACCOUNT_ACTIVITY_METHOD.get(method, {}):
            message = ACCOUNT_ACTIVITY_METHOD[method][activity]
        else:
            message = ACCOUNT_ACTIVITY[activity]
        return message.format(**self.get_params())

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

    def check_rate_limit(self, request):
        """Check whether the activity should be rate limited."""
        if self.activity == "failed-auth" and self.user.has_usable_password():
            failures = AuditLog.objects.get_after(self.user, "login", "failed-auth")
            if failures.count() >= settings.AUTH_LOCK_ATTEMPTS:
                self.user.set_unusable_password()
                self.user.save(update_fields=["password"])
                AuditLog.objects.create(self.user, request, "locked")
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

    def __str__(self):
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

    DASHBOARD_CHOICES = (
        (DASHBOARD_WATCHED, gettext_lazy("Watched translations")),
        (DASHBOARD_COMPONENT_LISTS, gettext_lazy("Component lists")),
        (DASHBOARD_COMPONENT_LIST, gettext_lazy("Component list")),
        (DASHBOARD_SUGGESTIONS, gettext_lazy("Suggested translations")),
    )

    DASHBOARD_SLUGS = {
        DASHBOARD_WATCHED: "your-subscriptions",
        DASHBOARD_COMPONENT_LIST: "list",
        DASHBOARD_SUGGESTIONS: "suggestions",
        DASHBOARD_COMPONENT_LISTS: "componentlists",
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
    )
    codesite = models.URLField(
        verbose_name=gettext_lazy("Code site URL"),
        blank=True,
        help_text=gettext_lazy(
            "Link to your code profile for services like Codeberg or GitLab."
        ),
    )
    github = models.SlugField(
        verbose_name=gettext_lazy("GitHub username"),
        blank=True,
        db_index=False,
    )
    twitter = models.SlugField(
        verbose_name=gettext_lazy("Twitter username"),
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

    class Meta:
        verbose_name = "User profile"
        verbose_name_plural = "User profiles"

    def __str__(self):
        return self.user.username

    def get_absolute_url(self):
        return self.user.get_absolute_url()

    def get_user_display(self):
        return get_user_display(self.user)

    def get_user_display_link(self):
        return get_user_display(self.user, True, True)

    def get_user_name(self):
        return get_user_display(self.user, False)

    def increase_count(self, item: str, increase: int = 1):
        """Updates user actions counter."""
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

    def clean(self):
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

    def get_translation_order(self, translation) -> str:
        """Returns key suitable for ordering languages based on user preferences."""
        from weblate.trans.models import Unit

        if isinstance(translation, Unit):
            translation = translation.translation
        language = translation.language

        if language.pk in self.primary_language_ids:
            priority = 0
        elif language.pk in self.secondary_language_ids:
            priority = 1
        elif translation.is_source:
            priority = 2
        else:
            priority = 3

        return f"{priority}-{language}"

    def fixup_profile(self, request):
        fields = set()
        if not self.language:
            self.language = get_language()
            fields.add("language")

        allowed = {clist.pk for clist in self.allowed_dashboard_component_lists}

        if not allowed and self.dashboard_view in (
            Profile.DASHBOARD_COMPONENT_LIST,
            Profile.DASHBOARD_COMPONENT_LISTS,
        ):
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
        if not email and not settings.PRIVATE_COMMIT_EMAIL_OPT_IN:
            email = self.get_site_commit_email()
        if not email:
            email = self.user.email
        return email

    def get_site_commit_email(self) -> str:
        if not settings.PRIVATE_COMMIT_EMAIL_TEMPLATE:
            return ""
        return settings.PRIVATE_COMMIT_EMAIL_TEMPLATE.format(
            username=self.user.username,
            site_domain=settings.SITE_DOMAIN,
        )


def set_lang_cookie(response, profile):
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
def post_login_handler(sender, request, user, **kwargs):
    """
    Signal handler for post login.

    It sets user language and migrates profile if needed.
    """
    backend_name = getattr(user, "backend", "")
    is_email_auth = backend_name.endswith((".EmailAuth", ".WeblateUserBackend"))

    # Warning about setting password
    if is_email_auth and not user.has_usable_password():
        request.session["show_set_password"] = True

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
            gettext(
                "You can not submit translations as "
                "you do not have assigned any e-mail address."
            ),
        )

    # Sanitize profile
    user.profile.fixup_profile(request)


@receiver(post_save, sender=User)
@disable_for_loaddata
def create_profile_callback(sender, instance, created=False, **kwargs):
    """Automatically create token and profile for user."""
    if created:
        # Create API token
        instance.auth_token = Token.objects.create(
            user=instance, key=get_token("wlp" if instance.is_bot else "wlu")
        )
        # Create profile
        instance.profile = Profile.objects.create(user=instance)
        # Create subscriptions
        if not instance.is_anonymous:
            create_default_notifications(instance)
