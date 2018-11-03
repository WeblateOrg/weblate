# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from django.db import models
from django.dispatch import receiver
from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import python_2_unicode_compatible
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.translation import LANGUAGE_SESSION_KEY

from rest_framework.authtoken.models import Token

from social_django.models import UserSocialAuth

from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.utils import messages
from weblate.accounts.avatar import get_user_display
from weblate.utils.validators import validate_editor
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.fields import JSONField

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
        'Authentication ({method}:{name}) has been added.'
    ),
    'auth-disconnect': _(
        'Authentication ({method}:{name}) has been removed.'
    ),
    'login': _(
        'Authenticated ({method}:{name}).'
    ),
    'login-new': _(
        'Authenticated ({method}:{name}) from new device.'
    ),
    'register': _(
        'Somebody has attempted to register with your email.'
    ),
    'connect': _(
        'Somebody has attempted to add your email to existing account.'
    ),
    'failed-auth': _(
        'Failed authentication attempt ({method}:{name}).'
    ),
    'locked': _(
        'Account locked due to excessive failed authentication attempts.'
    ),
    'removed': _(
        'Account and all private data have been removed.'
    ),
    'tos': _(
        'Agreement with Terms of Service {date}.'
    ),
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
    def create(self, user, activity, address, user_agent, **params):
        return super(AuditLogManager, self).create(
            user=user,
            activity=activity,
            address=address,
            user_agent=user_agent,
            params=params
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

    def get_message(self):
        return ACCOUNT_ACTIVITY[self.activity].format(
            **self.params
        )
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


class ProfileManager(models.Manager):
    """Manager providing shortcuts for subscription queries."""
    # pylint: disable=no-init

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

    subscriptions = models.ManyToManyField(
        'trans.Project',
        verbose_name=_('Watched projects'),
        help_text=_(
            'You can receive notifications for watched projects and '
            'they are shown on the dashboard by default.'
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

    # Ensure user has a profile
    profile = Profile.objects.get_or_create(user=user)[0]

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
    set_lang(request, profile)

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
        Token.objects.create(
            user=instance,
            key=get_random_string(40),
        )
        # Create profile
        Profile.objects.get_or_create(user=instance)
