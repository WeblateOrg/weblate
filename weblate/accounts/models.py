# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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
import json
import os
import binascii
import datetime

from django.db import models
from django.dispatch import receiver
from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import python_2_unicode_compatible
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.deprecation import CallableFalse, CallableTrue
from django.utils.translation import LANGUAGE_SESSION_KEY

from rest_framework.authtoken.models import Token

from social_django.models import UserSocialAuth, Code

from weblate.lang.models import Language
from weblate.utils import messages
from weblate.accounts.avatar import get_user_display
from weblate.trans.signals import user_pre_delete
from weblate.utils.validators import validate_editor
from weblate.utils.decorators import disable_for_loaddata


ACCOUNT_ACTIVITY = {
    'password': _(
        'Password has been changed.'
    ),
    'reset-request': _(
        'Password reset has been requested.'
    ),
    'reset': _(
        'Password reset has been confirmed.'
    ),
    'auth-connect': _(
        'Authentication using {method} ({name}) has been added.'
    ),
    'auth-disconnect': _(
        'Authentication using {method} ({name}) has been removed.'
    ),
    'login': _(
        'Successfully authenticated using {method} ({name}).'
    ),
    'register': _(
        'Somebody has attempted to register with your email.'
    ),
    'connect': _(
        'Somebody has attempted to add your email to existing account.'
    ),
    'failed-auth': _(
        'Failed authentication attempt using {method} ({name}).'
    ),
    'locked': _(
        'Account locked due to excessive failed authentication attempts.'
    ),
    'removed': _(
        'Account and all private data have been removed.'
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
))


class WeblateAnonymousUser(User):
    """Proxy model to customize User behavior.

    TODO: Remove Callable* return values and replace them with booleans once
    djangp-rest-framework supports this (changed in Django 1.10).
    """

    class Meta:
        proxy = True

    @property
    def is_authenticated(self):
        return CallableFalse

    @property
    def is_anonymous(self):
        return CallableTrue


def get_anonymous():
    """Return anonymous user"""
    return WeblateAnonymousUser.objects.get(
        username=settings.ANONYMOUS_USER_NAME,
    )


def get_author_name(user, email=True):
    """Return formatted author name with email."""
    # The < > are replace to avoid tricking Git to use
    # name as email

    # Get full name from database
    full_name = user.first_name.replace('<', '').replace('>', '')

    # Use username if full name is empty
    if full_name == '':
        full_name = user.username.replace('<', '').replace('>', '')

    # Add email if we are asked for it
    if not email:
        return full_name
    return '{0} <{1}>'.format(full_name, user.email)


class AuditLogManager(models.Manager):
    def create(self, user, activity, address, **params):
        return super(AuditLogManager, self).create(
            user=user,
            activity=activity,
            address=address,
            params=json.dumps(params)
        )

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

    user = models.ForeignKey(User)
    activity = models.CharField(
        max_length=20,
        choices=[(a, a) for a in sorted(ACCOUNT_ACTIVITY.keys())],
        db_index=True,
    )
    params = models.TextField()
    address = models.GenericIPAddressField()
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditLogManager()

    class Meta(object):
        ordering = ['-timestamp']

    def get_message(self):
        return ACCOUNT_ACTIVITY[self.activity].format(
            **self.get_params()
        )
    get_message.short_description = _('Account activity')

    def get_params(self):
        return json.loads(self.params)

    def should_notify(self):
        return self.activity in NOTIFY_ACTIVITY

    def __str__(self):
        return '{0} for {1} from {2}'.format(
            self.activity,
            self.user.username,
            self.address
        )


@python_2_unicode_compatible
class VerifiedEmail(models.Model):
    """Storage for verified emails from auth backends."""

    social = models.ForeignKey(UserSocialAuth)
    email = models.EmailField(max_length=254)

    def __str__(self):
        return '{0} - {1}'.format(
            self.social.user.username,
            self.email
        )


class ProfileManager(models.Manager):
    """Manager providing shortcuts for subscription queries."""
    # pylint: disable=W0232

    def subscribed_any_translation(self, project, language, user):
        return self.filter(
            subscribe_any_translation=True,
            subscriptions=project,
            languages=language
        ).exclude(
            user=user
        )

    def subscribed_new_language(self, project, user):
        return self.filter(
            subscribe_new_language=True,
            subscriptions=project,
        ).exclude(
            user=user
        )

    def subscribed_new_string(self, project, language):
        return self.filter(
            subscribe_new_string=True,
            subscriptions=project,
            languages=language
        )

    def subscribed_new_suggestion(self, project, language, user):
        ret = self.filter(
            subscribe_new_suggestion=True,
            subscriptions=project,
            languages=language
        )
        # We don't want to filter out anonymous user
        if user is not None and user.is_authenticated:
            ret = ret.exclude(user=user)
        return ret

    def subscribed_new_contributor(self, project, language, user):
        return self.filter(
            subscribe_new_contributor=True,
            subscriptions=project,
            languages=language
        ).exclude(
            user=user
        )

    def subscribed_new_comment(self, project, language, user):
        ret = self.filter(
            subscribe_new_comment=True,
            subscriptions=project
        ).exclude(
            user=user
        )
        # Source comments go to every subscriber
        if language is not None:
            ret = ret.filter(languages=language)
        return ret

    def subscribed_merge_failure(self, project):
        return self.filter(subscribe_merge_failure=True, subscriptions=project)


@python_2_unicode_compatible
class Profile(models.Model):
    """User profiles storage."""

    user = models.OneToOneField(User, unique=True, editable=False)
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
        help_text=_('Choose languages to which you can translate.')
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

    hide_completed = models.BooleanField(
        verbose_name=_('Hide completed translations on dashboard'),
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

    DASHBOARD_CHOICES = (
        (DASHBOARD_WATCHED, _('Watched translations')),
        (DASHBOARD_LANGUAGES, _('Your languages')),
        (DASHBOARD_COMPONENT_LIST, _('Component list')),
        (DASHBOARD_SUGGESTIONS, _('Suggested translations')),
    )

    DASHBOARD_SLUGS = {
        DASHBOARD_WATCHED: 'your-subscriptions',
        DASHBOARD_LANGUAGES: 'your-languages',
        DASHBOARD_COMPONENT_LIST: 'list',
        DASHBOARD_SUGGESTIONS: 'suggestions',
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
        blank=True,
        null=True,
    )

    subscriptions = models.ManyToManyField(
        'trans.Project',
        verbose_name=_('Watched projects'),
        help_text=_(
            'You can receive notifications for watched projects and '
            'they are shown on dashboard by default.'
        ),
        blank=True,
    )

    subscribe_any_translation = models.BooleanField(
        verbose_name=_('Notification on any translation'),
        default=False
    )
    subscribe_new_string = models.BooleanField(
        verbose_name=_('Notification on new string to translate'),
        default=False
    )
    subscribe_new_suggestion = models.BooleanField(
        verbose_name=_('Notification on new suggestion'),
        default=False
    )
    subscribe_new_contributor = models.BooleanField(
        verbose_name=_('Notification on new contributor'),
        default=False
    )
    subscribe_new_comment = models.BooleanField(
        verbose_name=_('Notification on new comment'),
        default=False
    )
    subscribe_merge_failure = models.BooleanField(
        verbose_name=_('Notification on merge failure'),
        default=False
    )
    subscribe_new_language = models.BooleanField(
        verbose_name=_('Notification on new language request'),
        default=False
    )

    SUBSCRIPTION_FIELDS = (
        'subscribe_any_translation',
        'subscribe_new_string',
        'subscribe_new_suggestion',
        'subscribe_new_contributor',
        'subscribe_new_comment',
        'subscribe_merge_failure',
        'subscribe_new_language',
    )

    objects = ProfileManager()

    def __str__(self):
        return self.user.username

    def get_user_display(self):
        return get_user_display(self.user)

    def get_user_display_link(self):
        return get_user_display(self.user, True, True)

    def get_user_name(self):
        return get_user_display(self.user, False)

    @models.permalink
    def get_absolute_url(self):
        return ('user_page', (), {
            'user': self.user.username
        })

    @property
    def last_change(self):
        """Return date of last change user has done in Weblate."""
        try:
            return self.user.change_set.values_list('timestamp', flat=True)[0]
        except IndexError:
            return None

    @property
    def full_name(self):
        """Return user's full name."""
        return self.user.first_name

    def clean(self):
        """Check if component list is selected when required."""
        if (self.dashboard_view == Profile.DASHBOARD_COMPONENT_LIST and
                self.dashboard_component_list is None):
            raise ValidationError({
                'dashboard_component_list':
                _("Component list must be selected when used as default.")
            })
        if (self.dashboard_view != Profile.DASHBOARD_COMPONENT_LIST and
                self.dashboard_component_list is not None):
            raise ValidationError({
                'dashboard_component_list':
                _("Component list must not be selected when not used.")
            })


def set_lang(request, profile):
    """Set session language based on user preferences."""
    if profile.language:
        request.session[LANGUAGE_SESSION_KEY] = profile.language


def get_all_user_mails(user):
    """Return all verified mails for user."""
    emails = set(
        VerifiedEmail.objects.filter(
            social__user=user
        ).values_list(
            'email', flat=True
        )
    )
    emails.add(user.email)
    return emails


def remove_user(user, request):
    """Remove user account."""
    from weblate.accounts.notifications import notify_account_activity

    # Send signal (to commit any pending changes)
    user_pre_delete.send(instance=user, sender=user.__class__)

    # Store activity log and notify
    notify_account_activity(user, request, 'removed')

    # Remove any email validation codes
    Code.objects.filter(email__in=get_all_user_mails(user)).delete()

    # Change username
    user.username = 'deleted-{0}'.format(user.pk)
    while User.objects.filter(username=user.username).exists():
        user.username = 'deleted-{0}-{1}'.format(
            user.pk,
            binascii.b2a_hex(os.urandom(5))
        )

    # Remove user information
    user.first_name = 'Deleted User'
    user.last_name = ''
    user.email = 'noreply@weblate.org'

    # Disable the user
    user.is_active = False
    user.set_unusable_password()
    user.save()

    # Remove all social auth associations
    user.social_auth.all().delete()

    # Remove user from all groups
    user.groups.clear()


@receiver(user_logged_in)
def post_login_handler(sender, request, user, **kwargs):
    """Signal handler for post login.

    It sets user language and migrates profile if needed.
    """
    is_email_auth = getattr(user, 'backend', '').endswith('.EmailAuth')

    # Warning about setting password
    if is_email_auth and not user.has_usable_password():
        request.session['show_set_password'] = True

    # Ensure user has a profile
    profile = Profile.objects.get_or_create(user=user)[0]

    # Migrate django-registration based verification to python-social-auth
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
    set_lang(request, profile)

    # Warn about not set email
    if not user.email:
        messages.error(
            request,
            _(
                'You can not submit translations as '
                'you do not have assigned any email address.'
            )
        )


@receiver(user_logged_out)
def post_logout_handler(sender, request, user, **kwargs):
    # Unlock translations on logout
    for translation in user.translation_set.all():
        translation.create_lock(None)


@receiver(post_save, sender=User)
@disable_for_loaddata
def create_profile_callback(sender, instance, created=False, **kwargs):
    """Automatically create token and profile for user."""
    if created:
        # Create API token
        Token.objects.create(
            user=instance,
            key=get_random_string(40),
        )
        # Create profile
        Profile.objects.get_or_create(user=instance)
