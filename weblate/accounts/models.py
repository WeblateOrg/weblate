# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

import datetime

from appconf import AppConf

from django.db import models
from django.db.models import Q
from django.dispatch import receiver
from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.utils.translation import ugettext_lazy as _, ugettext
from django.utils.encoding import python_2_unicode_compatible
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.translation import LANGUAGE_SESSION_KEY

from rest_framework.authtoken.models import Token

from social_django.models import UserSocialAuth

from weblate.accounts.data import create_default_notifications
from weblate.accounts.notifications import (
    NOTIFICATIONS, FREQ_CHOICES, SCOPE_CHOICES,
)
from weblate.accounts.tasks import notify_auditlog
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.utils import messages
from weblate.accounts.avatar import get_user_display
from weblate.utils.validators import validate_editor
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.fields import JSONField
from weblate.utils.request import get_ip_address, get_user_agent


class Subscription(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.deletion.CASCADE,
    )
    notification = models.CharField(
        choices=[n.get_choice() for n in NOTIFICATIONS],
        max_length=100,
    )
    scope = models.IntegerField(
        choices=SCOPE_CHOICES,
    )
    frequency = models.IntegerField(
        choices=FREQ_CHOICES,
    )
    project = models.ForeignKey(
        'trans.Project',
        on_delete=models.deletion.CASCADE,
        null=True,
    )
    component = models.ForeignKey(
        'trans.Component',
        on_delete=models.deletion.CASCADE,
        null=True,
    )

    class Meta(object):
        unique_together = [
            ('notification', 'scope', 'project', 'component', 'user')
        ]


ACCOUNT_ACTIVITY = {
    'password': _(
        'Password has been changed.'
    ),
    'reset-request': _(
        'Password reset has been requested.'
    ),
    'reset': _(
        'Password reset has been confirmed and password has been disabled.'
    ),
    'auth-connect': _(
        'You can now log in using {method} ({name}).'
    ),
    'auth-disconnect': _(
        'You can no longer log in using {method} ({name}).'
    ),
    'login': _(
        'Logged on using {method} ({name}).'
    ),
    'login-new': _(
        'Logged on using {method} ({name}) from a new device.'
    ),
    'register': _(
        'Somebody has attempted to register with your email.'
    ),
    'connect': _(
        'Somebody has attempted to register using your email address.'
    ),
    'failed-auth': _(
        'Could not log in using {method} ({name}).'
    ),
    'locked': _(
        'Account locked due to many failed logins.'
    ),
    'removed': _(
        'Account and all private data have been removed.'
    ),
    'tos': _(
        'Agreement with Terms of Service {date}.'
    ),
}
# Override activty messages based on method
ACCOUNT_ACTIVITY_METHOD = {
    'password': {
        'auth-connect': _('You can now log in using password.'),
        'login': _('Logged on using password.'),
        'login-new': _('Logged on using password from a new device.'),
        'failed-auth': _('Could not log in using password.'),
    }
}

EXTRA_MESSAGES = {
    'locked': _(
        'To restore access to your account, please reset your password.'
    ),
}

NOTIFY_ACTIVITY = frozenset((
    'password',
    'reset',
    'auth-connect',
    'auth-disconnect',
    'register',
    'connect',
    'locked',
    'removed',
    'login-new',
))


class AuditLogManager(models.Manager):
    def is_new_login(self, user, address, user_agent):
        """Checks whether this login is coming from new device.

        This is currently based purely in IP address.
        """
        logins = self.filter(user=user, activity='login-new')

        # First login
        if not logins.exists():
            return False

        return not logins.filter(
            Q(address=address) | Q(user_agent=user_agent)
        ).exists()

    def create(self, user, request, activity, **params):
        address = get_ip_address(request)
        user_agent = get_user_agent(request)
        if activity == 'login' and self.is_new_login(user, address, user_agent):
            activity = 'login-new'
        return super(AuditLogManager, self).create(
            user=user,
            activity=activity,
            address=address,
            user_agent=user_agent,
            params=params,
        )


class AuditLogQuerySet(models.QuerySet):
    def get_after(self, user, after, activity):
        """Get user activites of given type after another activity.

        This is mostly used for rate limiting as it can return number of failed
        authentication attempts since last login.
        """
        try:
            latest_login = self.filter(
                user=user, activity=after
            )[0]
            kwargs = {'timestamp__gte': latest_login.timestamp}
        except IndexError:
            kwargs = {}
        return self.filter(user=user, activity=activity, **kwargs)

    def get_password(self, user):
        """Get user activities with password change."""
        start = timezone.now() - datetime.timedelta(
            days=settings.AUTH_PASSWORD_DAYS
        )
        return self.filter(
            user=user,
            activity__in=('reset', 'password'),
            timestamp__gt=start,
        )


@python_2_unicode_compatible
class AuditLog(models.Model):
    """User audit log storage."""

    user = models.ForeignKey(
        User,
        on_delete=models.deletion.CASCADE,
    )
    activity = models.CharField(
        max_length=20,
        choices=[(a, a) for a in sorted(ACCOUNT_ACTIVITY.keys())],
        db_index=True,
    )
    params = JSONField()
    address = models.GenericIPAddressField(null=True)
    user_agent = models.CharField(max_length=200, default='')
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditLogManager.from_queryset(AuditLogQuerySet)()

    class Meta(object):
        ordering = ['-timestamp']

    def get_params(self):
        result = {}
        result.update(self.params)
        if 'method' in result:
            result['method'] = ugettext(result['method'])
        return result

    def get_message(self):
        method = self.params.get('method')
        activity = self.activity
        if activity in ACCOUNT_ACTIVITY_METHOD.get(method, {}):
            message = ACCOUNT_ACTIVITY_METHOD[method][activity]
        else:
            message = ACCOUNT_ACTIVITY[activity]
        return message.format(**self.get_params())
    get_message.short_description = _('Account activity')

    def get_extra_message(self):
        if self.activity in EXTRA_MESSAGES:
            return EXTRA_MESSAGES[self.activity].format(
                **self.params
            )
        return None

    def should_notify(self):
        return self.activity in NOTIFY_ACTIVITY and not self.user.is_demo

    def __str__(self):
        return '{0} for {1} from {2}'.format(
            self.activity,
            self.user.username,
            self.address
        )

    def check_rate_limit(self, request):
        """Check whether the activity should be rate limited."""
        if self.activity == 'failed-auth' and self.user.has_usable_password():
            failures = AuditLog.objects.get_after(
                self.user, 'login', 'failed-auth'
            )
            if failures.count() >= settings.AUTH_LOCK_ATTEMPTS:
                self.user.set_unusable_password()
                self.user.save(update_fields=['password'])
                AuditLog.objects.create(self.user, request, 'locked')
                return True

        elif self.activity == 'reset-request':
            failures = AuditLog.objects.get_after(
                self.user, 'login', 'reset-request'
            )
            if failures.count() >= settings.AUTH_LOCK_ATTEMPTS:
                return True

        return False

    def save(self, *args, **kwargs):
        super(AuditLog, self).save(*args, **kwargs)
        if self.should_notify():
            notify_auditlog.delay(self.pk)


@python_2_unicode_compatible
class VerifiedEmail(models.Model):
    """Storage for verified emails from auth backends."""

    social = models.ForeignKey(
        UserSocialAuth,
        on_delete=models.deletion.CASCADE,
    )
    email = models.EmailField(max_length=254)

    def __str__(self):
        return '{0} - {1}'.format(
            self.social.user.username,
            self.email
        )


@python_2_unicode_compatible
class Profile(models.Model):
    """User profiles storage."""

    user = models.OneToOneField(
        User, unique=True, editable=False, on_delete=models.deletion.CASCADE
    )
    language = models.CharField(
        verbose_name=_('Interface Language'),
        max_length=10,
        blank=True,
        choices=settings.LANGUAGES
    )
    languages = models.ManyToManyField(
        Language,
        verbose_name=_('Translated languages'),
        blank=True,
        help_text=_(
            'Choose which languages you prefer to translate. '
            'These will be offered to you on the dashboard to '
            'have easier access to chosen translations.'
        )
    )
    secondary_languages = models.ManyToManyField(
        Language,
        verbose_name=_('Secondary languages'),
        help_text=_(
            'Choose languages you can understand, strings in those languages '
            'will be shown in addition to the source string.'
        ),
        related_name='secondary_profile_set',
        blank=True,
    )
    suggested = models.IntegerField(default=0, db_index=True)
    translated = models.IntegerField(default=0, db_index=True)
    uploaded = models.IntegerField(default=0, db_index=True)

    hide_completed = models.BooleanField(
        verbose_name=_('Hide completed translations on the dashboard'),
        default=False
    )
    secondary_in_zen = models.BooleanField(
        verbose_name=_('Show secondary translations in zen mode'),
        default=True
    )
    hide_source_secondary = models.BooleanField(
        verbose_name=_('Hide source if there is secondary language'),
        default=False
    )
    editor_link = models.CharField(
        default='', blank=True,
        max_length=200,
        verbose_name=_('Editor link'),
        help_text=_(
            'Enter custom URL to be used as link to open source code. '
            'You can use %(branch)s for branch, '
            '%(file)s and %(line)s as filename and line placeholders. '
            'Usually something like editor://open/?file=%(file)s&line=%(line)s'
            ' is good option.'
        ),
        validators=[validate_editor],
    )
    TRANSLATE_FULL = 0
    TRANSLATE_ZEN = 1
    translate_mode = models.IntegerField(
        verbose_name=_('Translation editor mode'),
        choices=(
            (TRANSLATE_FULL, _('Full editor')),
            (TRANSLATE_ZEN, _('Zen mode')),
        ),
        default=TRANSLATE_FULL,
    )
    special_chars = models.CharField(
        default='', blank=True,
        max_length=30,
        verbose_name=_('Special characters'),
        help_text=_(
            'You can specify additional special characters to be shown in '
            'the visual keyboard while translating. It can be useful for '
            'chars you use frequently but are hard to type on your keyboard.'
        )
    )

    DASHBOARD_WATCHED = 1
    DASHBOARD_LANGUAGES = 2
    DASHBOARD_COMPONENT_LIST = 4
    DASHBOARD_SUGGESTIONS = 5
    DASHBOARD_COMPONENT_LISTS = 6

    DASHBOARD_CHOICES = (
        (DASHBOARD_WATCHED, _('Watched translations')),
        (DASHBOARD_LANGUAGES, _('Your languages')),
        (DASHBOARD_COMPONENT_LISTS, _('Component lists')),
        (DASHBOARD_COMPONENT_LIST, _('Component list')),
        (DASHBOARD_SUGGESTIONS, _('Suggested translations')),
    )

    DASHBOARD_SLUGS = {
        DASHBOARD_WATCHED: 'your-subscriptions',
        DASHBOARD_LANGUAGES: 'your-languages',
        DASHBOARD_COMPONENT_LIST: 'list',
        DASHBOARD_SUGGESTIONS: 'suggestions',
        DASHBOARD_COMPONENT_LISTS: 'componentlists'
    }

    DASHBOARD_SLUGMAP = {
        d[1]: d[0] for d in DASHBOARD_SLUGS.items()
    }

    dashboard_view = models.IntegerField(
        choices=DASHBOARD_CHOICES,
        verbose_name=_('Default dashboard view'),
        default=DASHBOARD_WATCHED,
    )

    dashboard_component_list = models.ForeignKey(
        'trans.ComponentList',
        verbose_name=_('Default component list'),
        on_delete=models.deletion.CASCADE,
        blank=True,
        null=True,
    )

    watched = models.ManyToManyField(
        'trans.Project',
        verbose_name=_('Watched projects'),
        help_text=_(
            'You can receive notifications for watched projects and '
            'they are shown on the dashboard by default.'
        ),
        blank=True,
    )

    def __str__(self):
        return self.user.username

    def get_user_display(self):
        return get_user_display(self.user)

    def get_user_display_link(self):
        return get_user_display(self.user, True, True)

    def get_user_name(self):
        return get_user_display(self.user, False)

    def get_absolute_url(self):
        return reverse('user_page', kwargs={'user': self.user.username})

    @property
    def full_name(self):
        """Return user's full name."""
        return self.user.full_name

    def clean(self):
        """Check if component list is chosen when required."""
        # This is used for form validation as well, but those
        # will not contain all fields
        if not hasattr(self, 'dashboard_component_list'):
            return
        if (self.dashboard_view == Profile.DASHBOARD_COMPONENT_LIST and
                self.dashboard_component_list is None):
            raise ValidationError({
                'dashboard_component_list':
                _("Component list must be chosen when used as default.")
            })
        if (self.dashboard_view != Profile.DASHBOARD_COMPONENT_LIST and
                self.dashboard_component_list is not None):
            raise ValidationError({
                'dashboard_component_list':
                _("Component list can not be chosen when unused.")
            })

    def dump_data(self):
        def dump_object(obj, *attrs):
            return {attr: getattr(obj, attr) for attr in attrs}

        result = {
            'basic': dump_object(
                self.user,
                'username', 'full_name', 'email', 'date_joined'
            ),
            'profile': dump_object(
                self,
                'language',
                'suggested', 'translated', 'uploaded',
                'hide_completed', 'secondary_in_zen', 'hide_source_secondary',
                'editor_link', 'translate_mode', 'special_chars',
                'dashboard_view', 'dashboard_component_list',
            ),
            'auditlog': [
                dump_object(log, 'address', 'user_agent', 'timestamp', 'activity')
                for log in self.user.auditlog_set.iterator()
            ]
        }
        result['profile']['languages'] = [
            lang.code for lang in self.languages.iterator()
        ]
        result['profile']['secondary_languages'] = [
            lang.code for lang in self.secondary_languages.iterator()
        ]
        result['profile']['watched'] = [
            project.slug for project in self.watched.iterator()
        ]
        return result


def set_lang(request, profile):
    """Set session language based on user preferences."""
    if profile.language:
        request.session[LANGUAGE_SESSION_KEY] = profile.language


@receiver(user_logged_in)
def post_login_handler(sender, request, user, **kwargs):
    """Signal handler for post login.

    It sets user language and migrates profile if needed.
    """
    backend_name = getattr(user, 'backend', '')
    is_email_auth = (
        backend_name.endswith('.EmailAuth') or
        backend_name.endswith('.WeblateUserBackend')
    )

    # Warning about setting password
    if is_email_auth and not user.has_usable_password():
        request.session['show_set_password'] = True

    # Migrate django-registration based verification to python-social-auth
    # and handle external authentication such as LDAP
    if (is_email_auth and user.has_usable_password() and user.email and
            not user.social_auth.filter(provider='email').exists()):
        social = user.social_auth.create(
            provider='email',
            uid=user.email,
        )
        VerifiedEmail.objects.create(
            social=social,
            email=user.email,
        )

    # Set language for session based on preferences
    set_lang(request, user.profile)

    # Fixup accounts with empty name
    if not user.full_name:
        user.full_name = user.username
        user.save(update_fields=['full_name'])

    # Warn about not set email
    if not user.email:
        messages.error(
            request,
            _(
                'You can not submit translations as '
                'you do not have assigned any email address.'
            )
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
        if not instance.is_anonymous and not instance.is_demo:
            create_default_notifications(instance)


class WeblateAccountsConf(AppConf):
    """Accounts settings."""
    # Disable avatars
    ENABLE_AVATARS = True

    # Avatar URL prefix
    AVATAR_URL_PREFIX = 'https://www.gravatar.com/'

    # Avatar fallback image
    # See http://en.gravatar.com/site/implement/images/ for available choices
    AVATAR_DEFAULT_IMAGE = 'identicon'

    # Enable registrations
    REGISTRATION_OPEN = True

    # Registration email filter
    REGISTRATION_EMAIL_MATCH = '.*'

    # Captcha for registrations
    REGISTRATION_CAPTCHA = True

    # How long to keep auditlog entries
    AUDITLOG_EXPIRY = 180

    # Auth0 provider default image & title on login page
    SOCIAL_AUTH_AUTH0_IMAGE = 'btn_auth0_badge.png'
    SOCIAL_AUTH_AUTH0_TITLE = 'Auth0'

    class Meta(object):
        prefix = ''
