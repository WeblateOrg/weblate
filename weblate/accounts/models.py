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


import datetime
from typing import Set

from appconf import AppConf
from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from rest_framework.authtoken.models import Token
from social_django.models import UserSocialAuth

from weblate.accounts.avatar import get_user_display
from weblate.accounts.data import create_default_notifications
from weblate.accounts.notifications import FREQ_CHOICES, NOTIFICATIONS, SCOPE_CHOICES
from weblate.accounts.tasks import notify_auditlog
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.trans.defines import EMAIL_LENGTH
from weblate.utils import messages
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.fields import EmailField, JSONField
from weblate.utils.render import validate_editor
from weblate.utils.request import get_ip_address, get_user_agent


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

    # Registration email filter
    REGISTRATION_EMAIL_MATCH = ".*"

    # Captcha for registrations
    REGISTRATION_CAPTCHA = True

    # How long to keep auditlog entries
    AUDITLOG_EXPIRY = 180

    # Auto-watch setting for new users
    DEFAULT_AUTO_WATCH = True

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

    def __str__(self):
        return "{}:{},{} ({},{})".format(
            self.user.username,
            self.get_scope_display(),
            self.get_notification_display(),
            self.project,
            self.component,
        )


ACCOUNT_ACTIVITY = {
    "password": _("Password changed."),
    "username": _("Username changed from {old} to {new}."),
    "email": _("E-mail changed from {old} to {new}."),
    "full_name": _("Full name changed from {old} to {new}."),
    "reset-request": _("Password reset requested."),
    "reset": _("Password reset confirmed, password turned off."),
    "auth-connect": _("Configured sign in using {method} ({name})."),
    "auth-disconnect": _("Removed sign in using {method} ({name})."),
    "login": _("Signed in using {method} ({name})."),
    "login-new": _("Signed in using {method} ({name}) from a new device."),
    "register": _("Somebody has attempted to register with your e-mail."),
    "connect": _("Somebody has attempted to register using your e-mail address."),
    "failed-auth": _("Could not sign in using {method} ({name})."),
    "locked": _("Account locked due to many failed sign in attempts."),
    "removed": _("Account and all private data removed."),
    "tos": _("Agreement with Terms of Service {date}."),
    "invited": _("Invited to Weblate by {username}."),
    "trial": _("Started trial period."),
    "sent-email": _("Sent confirmation mail to {email}."),
    "autocreated": _(
        "System created user to track authorship of "
        "translations uploaded by other user."
    ),
}
# Override activty messages based on method
ACCOUNT_ACTIVITY_METHOD = {
    "password": {
        "auth-connect": _("Configured password to sign in."),
        "login": _("Signed in using password."),
        "login-new": _("Signed in using password from a new device."),
        "failed-auth": _("Could not sign in using password."),
    }
}

EXTRA_MESSAGES = {
    "locked": _("To restore access to your account, please reset your password.")
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
}


class AuditLogManager(models.Manager):
    def is_new_login(self, user, address, user_agent):
        """Checks whether this login is coming from a new device.

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
        """Get user activites of given type after another activity.

        This is mostly used for rate limiting, as it can return the number of failed
        authentication attempts since last login.
        """
        try:
            latest_login = self.filter(user=user, activity=after).order()[0]
            kwargs = {"timestamp__gte": latest_login.timestamp}
        except IndexError:
            kwargs = {}
        return self.filter(user=user, activity=activity, **kwargs)

    def get_password(self, user):
        """Get user activities with password change."""
        start = timezone.now() - datetime.timedelta(days=settings.AUTH_PASSWORD_DAYS)
        return self.filter(
            user=user, activity__in=("reset", "password"), timestamp__gt=start
        )

    def order(self):
        return self.order_by("-timestamp")


class AuditLog(models.Model):
    """User audit log storage."""

    user = models.ForeignKey(User, on_delete=models.deletion.CASCADE)
    activity = models.CharField(
        max_length=20,
        choices=[(a, a) for a in sorted(ACCOUNT_ACTIVITY.keys())],
        db_index=True,
    )
    params = JSONField()
    address = models.GenericIPAddressField(null=True)
    user_agent = models.CharField(max_length=200, default="")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditLogManager.from_queryset(AuditLogQuerySet)()

    def __str__(self):
        return f"{self.activity} for {self.user.username} from {self.address}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.should_notify():
            email = self.user.email
            transaction.on_commit(lambda: notify_auditlog.delay(self.pk, email))

    def get_params(self):
        from weblate.accounts.templatetags.authnames import get_auth_name

        result = {}
        result.update(self.params)
        if "method" in result:
            # The gettext is here for legacy entries which contained method name
            result["method"] = gettext(get_auth_name(result["method"]))
        return result

    def get_message(self):
        method = self.params.get("method")
        activity = self.activity
        if activity in ACCOUNT_ACTIVITY_METHOD.get(method, {}):
            message = ACCOUNT_ACTIVITY_METHOD[method][activity]
        else:
            message = ACCOUNT_ACTIVITY[activity]
        return message.format(**self.get_params())

    get_message.short_description = _("Account activity")

    def get_extra_message(self):
        if self.activity in EXTRA_MESSAGES:
            return EXTRA_MESSAGES[self.activity].format(**self.params)
        return None

    def should_notify(self):
        return self.user.is_active and self.activity in NOTIFY_ACTIVITY

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

    social = models.ForeignKey(UserSocialAuth, on_delete=models.deletion.CASCADE)
    email = models.EmailField(max_length=EMAIL_LENGTH)

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
        verbose_name=_("Interface Language"),
        max_length=10,
        blank=True,
        choices=settings.LANGUAGES,
    )
    languages = models.ManyToManyField(
        Language,
        verbose_name=_("Translated languages"),
        blank=True,
        help_text=_(
            "Choose the languages you can translate to. "
            "These will be offered to you on the dashboard "
            "for easier access to your chosen translations."
        ),
    )
    secondary_languages = models.ManyToManyField(
        Language,
        verbose_name=_("Secondary languages"),
        help_text=_(
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

    hide_completed = models.BooleanField(
        verbose_name=_("Hide completed translations on the dashboard"), default=False
    )
    secondary_in_zen = models.BooleanField(
        verbose_name=_("Show secondary translations in the Zen mode"), default=True
    )
    hide_source_secondary = models.BooleanField(
        verbose_name=_("Hide source if a secondary translation exists"), default=False
    )
    editor_link = models.CharField(
        default="",
        blank=True,
        max_length=200,
        verbose_name=_("Editor link"),
        help_text=_(
            "Enter a custom URL to be used as link to the source code. "
            "You can use {{branch}} for branch, "
            "{{filename}} and {{line}} as filename and line placeholders."
        ),
        validators=[validate_editor],
    )
    TRANSLATE_FULL = 0
    TRANSLATE_ZEN = 1
    translate_mode = models.IntegerField(
        verbose_name=_("Translation editor mode"),
        choices=((TRANSLATE_FULL, _("Full editor")), (TRANSLATE_ZEN, _("Zen mode"))),
        default=TRANSLATE_FULL,
    )
    ZEN_VERTICAL = 0
    ZEN_HORIZONTAL = 1
    zen_mode = models.IntegerField(
        verbose_name=_("Zen editor mode"),
        choices=(
            (ZEN_VERTICAL, _("Top to bottom")),
            (ZEN_HORIZONTAL, _("Side by side")),
        ),
        default=ZEN_VERTICAL,
    )
    special_chars = models.CharField(
        default="",
        blank=True,
        max_length=30,
        verbose_name=_("Special characters"),
        help_text=_(
            "You can specify additional special visual keyboard characters "
            "to be shown while translating. It can be useful for "
            "characters you use frequently, but are hard to type on your keyboard."
        ),
    )
    nearby_strings = models.SmallIntegerField(
        verbose_name=_("Number of nearby strings"),
        default=settings.NEARBY_MESSAGES,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text=_(
            "Number of nearby strings to show in each direction in the full editor."
        ),
    )
    auto_watch = models.BooleanField(
        verbose_name=_("Automatically watch projects on contribution"),
        default=settings.DEFAULT_AUTO_WATCH,
        help_text=_(
            "Whenever you translate a string in a project, you will start watching it."
        ),
    )

    DASHBOARD_WATCHED = 1
    DASHBOARD_COMPONENT_LIST = 4
    DASHBOARD_SUGGESTIONS = 5
    DASHBOARD_COMPONENT_LISTS = 6

    DASHBOARD_CHOICES = (
        (DASHBOARD_WATCHED, _("Watched translations")),
        (DASHBOARD_COMPONENT_LISTS, _("Component lists")),
        (DASHBOARD_COMPONENT_LIST, _("Component list")),
        (DASHBOARD_SUGGESTIONS, _("Suggested translations")),
    )

    DASHBOARD_SLUGS = {
        DASHBOARD_WATCHED: "your-subscriptions",
        DASHBOARD_COMPONENT_LIST: "list",
        DASHBOARD_SUGGESTIONS: "suggestions",
        DASHBOARD_COMPONENT_LISTS: "componentlists",
    }

    dashboard_view = models.IntegerField(
        choices=DASHBOARD_CHOICES,
        verbose_name=_("Default dashboard view"),
        default=DASHBOARD_WATCHED,
    )

    dashboard_component_list = models.ForeignKey(
        "trans.ComponentList",
        verbose_name=_("Default component list"),
        on_delete=models.deletion.SET_NULL,
        blank=True,
        null=True,
    )

    watched = models.ManyToManyField(
        "trans.Project",
        verbose_name=_("Watched projects"),
        help_text=_(
            "You can receive notifications for watched projects and "
            "they are shown on the dashboard by default."
        ),
        blank=True,
    )

    # Public profile fields
    website = models.URLField(
        verbose_name=_("Website URL"),
        blank=True,
    )
    liberapay = models.SlugField(
        verbose_name=_("Liberapay username"),
        blank=True,
        help_text=_(
            "Liberapay is a platform to donate money to teams, "
            "organizations and individuals."
        ),
    )
    fediverse = models.URLField(
        verbose_name=_("Fediverse URL"),
        blank=True,
        help_text=_(
            "Link to your Fediverse profile for federated services "
            "like Mastodon or diaspora*."
        ),
    )
    codesite = models.URLField(
        verbose_name=_("Code site URL"),
        blank=True,
        help_text=_("Link to your code profile for services like Codeberg or GitLab."),
    )
    github = models.SlugField(
        verbose_name=_("GitHub username"),
        blank=True,
    )
    twitter = models.SlugField(
        verbose_name=_("Twitter username"),
        blank=True,
    )
    linkedin = models.SlugField(
        verbose_name=_("LinkedIn profile name"),
        help_text=_("Your LinkedIn profile name from linkedin.com/in/profilename"),
        blank=True,
    )
    location = models.CharField(
        verbose_name=_("Location"),
        max_length=100,
        blank=True,
    )
    company = models.CharField(
        verbose_name=_("Company"),
        max_length=100,
        blank=True,
    )
    public_email = EmailField(
        verbose_name=_("Public e-mail"),
        blank=True,
        max_length=EMAIL_LENGTH,
    )

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
            message = _(
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
            message = _(
                "Selecting component list has no effect when not shown on "
                "the dashboard."
            )
            raise ValidationError(
                {"dashboard_component_list": message, "dashboard_view": message}
            )

    def dump_data(self):
        def dump_object(obj, *attrs):
            return {attr: getattr(obj, attr) for attr in attrs}

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
                "secondary_in_zen",
                "hide_source_secondary",
                "editor_link",
                "translate_mode",
                "zen_mode",
                "special_chars",
                "dashboard_view",
                "dashboard_component_list",
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
    def primary_language_ids(self) -> Set[int]:
        return set(self.languages.values_list("pk", flat=True))

    @cached_property
    def secondary_language_ids(self) -> Set[int]:
        return set(self.secondary_languages.values_list("pk", flat=True))

    def get_language_order(self, language: Language) -> int:
        """Returns key suitable for ordering languages based on user preferences."""
        if language.pk in self.primary_language_ids:
            return 0
        if language.pk in self.secondary_language_ids:
            return 1
        return 2

    @cached_property
    def watched_project_ids(self):
        # We do not use values_list, because we prefetch this
        return {watched.id for watched in self.watched.all()}

    def watches_project(self, project):
        return project.id in self.watched_project_ids


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
    """Signal handler for post login.

    It sets user language and migrates profile if needed.
    """
    backend_name = getattr(user, "backend", "")
    is_email_auth = backend_name.endswith(".EmailAuth") or backend_name.endswith(
        ".WeblateUserBackend"
    )

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
            _(
                "You can not submit translations as "
                "you do not have assigned any e-mail address."
            ),
        )


@receiver(post_save, sender=User)
@disable_for_loaddata
def create_profile_callback(sender, instance, created=False, **kwargs):
    """Automatically create token and profile for user."""
    if created:
        # Create API token
        Token.objects.create(user=instance, key=get_random_string(40))
        # Create profile
        Profile.objects.create(user=instance)
        # Create subscriptions
        if not instance.is_anonymous:
            create_default_notifications(instance)
