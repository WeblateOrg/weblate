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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals
import os
import sys
import binascii
from smtplib import SMTPException

from django.db import models
from django.dispatch import receiver
from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import python_2_unicode_compatible, force_text
from django.contrib.auth.models import User
from django.utils import translation as django_translation
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils.deprecation import CallableFalse, CallableTrue
from django.utils.translation import LANGUAGE_SESSION_KEY

from rest_framework.authtoken.models import Token

from social_django.models import UserSocialAuth

from weblate.lang.models import Language
from weblate.utils import messages
from weblate.trans.site import get_site_url, get_site_domain
from weblate.accounts.avatar import get_user_display
from weblate.utils.errors import report_error
from weblate.trans.signals import user_pre_delete
from weblate.utils.validators import validate_repoweb
from weblate.utils.decorators import disable_for_loaddata
from weblate import VERSION
from weblate.logger import LOGGER


class WeblateAnonymousUser(User):
    """
    Proxy model to customize User behavior.

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


def send_mails(mails):
    """Sends multiple mails in single connection."""
    try:
        connection = get_connection()
        connection.send_messages(
            [mail for mail in mails if mail is not None]
        )
    except SMTPException as error:
        LOGGER.error('Failed to send email: %s', error)
        report_error(error, sys.exc_info())


def get_author_name(user, email=True):
    """Returns formatted author name with email."""
    # Get full name from database
    full_name = user.first_name

    # Use username if full name is empty
    if full_name == '':
        full_name = user.username

    # Add email if we are asked for it
    if not email:
        return full_name
    return '{0} <{1}>'.format(full_name, user.email)


def notify_merge_failure(subproject, error, status):
    '''
    Notification on merge failure.
    '''
    subscriptions = Profile.objects.subscribed_merge_failure(
        subproject.project,
    )
    users = set()
    mails = []
    for subscription in subscriptions:
        mails.append(
            subscription.notify_merge_failure(subproject, error, status)
        )
        users.add(subscription.user_id)

    for owner in subproject.project.all_users('@Administration'):
        mails.append(
            owner.profile.notify_merge_failure(
                subproject, error, status
            )
        )

    # Notify admins
    mails.append(
        get_notification_email(
            'en',
            'ADMINS',
            'merge_failure',
            subproject,
            {
                'subproject': subproject,
                'status': status,
                'error': error,
            }
        )
    )
    send_mails(mails)


def notify_parse_error(subproject, translation, error, filename):
    '''
    Notification on parse error.
    '''
    subscriptions = Profile.objects.subscribed_merge_failure(
        subproject.project,
    )
    users = set()
    mails = []
    for subscription in subscriptions:
        mails.append(
            subscription.notify_parse_error(
                subproject, translation, error, filename
            )
        )
        users.add(subscription.user_id)

    for owner in subproject.project.all_users('@Administration'):
        mails.append(
            owner.profile.notify_parse_error(
                subproject, translation, error, filename
            )
        )

    # Notify admins
    mails.append(
        get_notification_email(
            'en',
            'ADMINS',
            'parse_error',
            translation if translation is not None else subproject,
            {
                'subproject': subproject,
                'translation': translation,
                'error': error,
                'filename': filename,
            }
        )
    )
    send_mails(mails)


def notify_new_string(translation):
    '''
    Notification on new string to translate.
    '''
    mails = []
    subscriptions = Profile.objects.subscribed_new_string(
        translation.subproject.project, translation.language
    )
    for subscription in subscriptions:
        mails.append(
            subscription.notify_new_string(translation)
        )

    send_mails(mails)


def notify_new_language(subproject, language, user):
    '''
    Notify subscribed users about new language requests
    '''
    mails = []
    subscriptions = Profile.objects.subscribed_new_language(
        subproject.project,
        user
    )
    users = set()
    for subscription in subscriptions:
        mails.append(
            subscription.notify_new_language(subproject, language, user)
        )
        users.add(subscription.user_id)

    for owner in subproject.project.all_users('@Administration'):
        mails.append(
            owner.profile.notify_new_language(
                subproject, language, user
            )
        )

    # Notify admins
    mails.append(
        get_notification_email(
            'en',
            'ADMINS',
            'new_language',
            subproject,
            {
                'language': language,
                'user': user,
            },
            user=user,
        )
    )

    send_mails(mails)


def notify_new_translation(unit, oldunit, user):
    '''
    Notify subscribed users about new translation
    '''
    mails = []
    subscriptions = Profile.objects.subscribed_any_translation(
        unit.translation.subproject.project,
        unit.translation.language,
        user
    )
    for subscription in subscriptions:
        mails.append(
            subscription.notify_any_translation(unit, oldunit)
        )

    send_mails(mails)


def notify_new_contributor(unit, user):
    '''
    Notify about new contributor.
    '''
    mails = []
    subscriptions = Profile.objects.subscribed_new_contributor(
        unit.translation.subproject.project,
        unit.translation.language,
        user
    )
    for subscription in subscriptions:
        mails.append(
            subscription.notify_new_contributor(
                unit.translation, user
            )
        )

    send_mails(mails)


def notify_new_suggestion(unit, suggestion, user):
    '''
    Notify about new suggestion.
    '''
    mails = []
    subscriptions = Profile.objects.subscribed_new_suggestion(
        unit.translation.subproject.project,
        unit.translation.language,
        user
    )
    for subscription in subscriptions:
        mails.append(
            subscription.notify_new_suggestion(
                unit.translation,
                suggestion,
                unit
            )
        )

    send_mails(mails)


def notify_new_comment(unit, comment, user, report_source_bugs):
    '''
    Notify about new comment.
    '''
    mails = []
    subscriptions = Profile.objects.subscribed_new_comment(
        unit.translation.subproject.project,
        comment.language,
        user
    )
    for subscription in subscriptions:
        mails.append(
            subscription.notify_new_comment(unit, comment, user)
        )

    # Notify upstream
    if comment.language is None and report_source_bugs != '':
        send_notification_email(
            'en',
            report_source_bugs,
            'new_comment',
            unit.translation,
            {
                'unit': unit,
                'comment': comment,
                'subproject': unit.translation.subproject,
            },
            user=user,
        )

    send_mails(mails)


def get_notification_email(language, email, notification,
                           translation_obj=None, context=None, headers=None,
                           user=None, info=None):
    '''
    Renders notification email.
    '''
    cur_language = django_translation.get_language()
    context = context or {}
    headers = headers or {}
    references = None
    if 'unit' in context:
        unit = context['unit']
        references = '{0}/{1}/{2}/{3}'.format(
            unit.translation.subproject.project.slug,
            unit.translation.subproject.slug,
            unit.translation.language.code,
            unit.id
        )
    if references is not None:
        references = '<{0}@{1}>'.format(references, get_site_domain())
        headers['In-Reply-To'] = references
        headers['References'] = references
    try:
        if info is None:
            info = force_text(translation_obj)
        LOGGER.info(
            'sending notification %s on %s to %s',
            notification,
            info,
            email
        )

        # Load user language
        if language is not None:
            django_translation.activate(language)

        # Template name
        context['subject_template'] = 'mail/{0}_subject.txt'.format(
            notification
        )

        # Adjust context
        context['current_site_url'] = get_site_url()
        if translation_obj is not None:
            context['translation'] = translation_obj
            context['translation_url'] = get_site_url(
                translation_obj.get_absolute_url()
            )
        context['site_title'] = settings.SITE_TITLE

        # Render subject
        subject = render_to_string(
            context['subject_template'],
            context
        ).strip()

        # Render body
        body = render_to_string(
            'mail/{0}.txt'.format(notification),
            context
        )
        html_body = render_to_string(
            'mail/{0}.html'.format(notification),
            context
        )

        # Define headers
        headers['Auto-Submitted'] = 'auto-generated'
        headers['X-AutoGenerated'] = 'yes'
        headers['Precedence'] = 'bulk'
        headers['X-Mailer'] = 'Weblate {0}'.format(VERSION)

        # Reply to header
        if user is not None:
            headers['Reply-To'] = user.email

        # List of recipients
        if email == 'ADMINS':
            emails = [a[1] for a in settings.ADMINS]
        else:
            emails = [email]

        # Create message
        email = EmailMultiAlternatives(
            settings.EMAIL_SUBJECT_PREFIX + subject,
            body,
            to=emails,
            headers=headers,
        )
        email.attach_alternative(
            html_body,
            'text/html'
        )

        # Return the mail
        return email
    finally:
        django_translation.activate(cur_language)


def send_notification_email(language, email, notification,
                            translation_obj=None, context=None, headers=None,
                            user=None, info=None):
    '''
    Renders and sends notification email.
    '''
    email = get_notification_email(
        language, email, notification, translation_obj, context, headers,
        user, info
    )
    send_mails([email])


@python_2_unicode_compatible
class VerifiedEmail(models.Model):
    '''
    Storage for verified emails from auth backends.
    '''
    social = models.ForeignKey(UserSocialAuth)
    email = models.EmailField(max_length=254)

    def __str__(self):
        return '{0} - {1}'.format(
            self.social.user.username,
            self.email
        )


class ProfileManager(models.Manager):
    '''
    Manager providing shortcuts for subscription queries.
    '''
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
    '''
    User profiles storage.
    '''
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
        validators=[validate_repoweb],
    )
    special_chars = models.CharField(
        default='', blank=True,
        max_length=30,
        verbose_name=_('Special characters'),
        help_text=_(
            'You can specify additional special characters to be show in '
            'visual keyboard while translating. It can be useful for chars '
            'you use frequently but are hard to type on your keyboard.'
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
        '''
        Returns date of last change user has done in Weblate.
        '''
        try:
            return self.user.change_set.values_list(
                'timestamp', flat=True
            )[0]
        except IndexError:
            return None

    def notify_user(self, notification, subproject, display_obj,
                    context=None, headers=None, user=None):
        '''
        Wrapper for sending notifications to user.
        '''
        from weblate.permissions.helpers import can_access_project
        if context is None:
            context = {}
        if headers is None:
            headers = {}

        # Check whether user is still allowed to access this project
        if can_access_project(self.user, subproject.project):
            # Generate notification
            return get_notification_email(
                self.language,
                self.user.email,
                notification,
                display_obj,
                context,
                headers,
                user=user
            )

    def notify_any_translation(self, unit, oldunit):
        '''
        Sends notification on translation.
        '''
        if oldunit.translated:
            template = 'changed_translation'
        else:
            template = 'new_translation'
        return self.notify_user(
            template,
            unit.translation.subproject,
            unit.translation,
            {
                'unit': unit,
                'oldunit': oldunit,
            }
        )

    def notify_new_language(self, subproject, language, user):
        '''
        Sends notification on new language request.
        '''
        return self.notify_user(
            'new_language',
            subproject,
            subproject,
            {
                'language': language,
                'user': user,
            },
            user=user
        )

    def notify_new_string(self, translation):
        '''
        Sends notification on new strings to translate.
        '''
        return self.notify_user(
            'new_string',
            translation.subproject,
            translation,
        )

    def notify_new_suggestion(self, translation, suggestion, unit):
        '''
        Sends notification on new suggestion.
        '''
        return self.notify_user(
            'new_suggestion',
            translation.subproject,
            translation,
            {
                'suggestion': suggestion,
                'unit': unit,
            }
        )

    def notify_new_contributor(self, translation, user):
        '''
        Sends notification on new contributor.
        '''
        return self.notify_user(
            'new_contributor',
            translation.subproject,
            translation,
            {
                'user': user,
            }
        )

    def notify_new_comment(self, unit, comment, user):
        '''
        Sends notification about new comment.
        '''
        return self.notify_user(
            'new_comment',
            unit.translation.subproject,
            unit.translation,
            {
                'unit': unit,
                'comment': comment,
                'subproject': unit.translation.subproject,
            },
            user=user,
        )

    def notify_merge_failure(self, subproject, error, status):
        '''
        Sends notification on merge failure.
        '''
        return self.notify_user(
            'merge_failure',
            subproject,
            subproject,
            {
                'subproject': subproject,
                'error': error,
                'status': status,
            }
        )

    def notify_parse_error(self, subproject, translation, error, filename):
        '''
        Sends notification on parse error.
        '''
        return self.notify_user(
            'parse_error',
            subproject,
            translation if translation is not None else subproject,
            {
                'subproject': subproject,
                'translation': translation,
                'error': error,
                'filename': filename,
            }
        )

    @property
    def full_name(self):
        '''
        Returns user's full name.
        '''
        return self.user.first_name

    def clean(self):
        '''
        Check if component list is selected when required.
        '''
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
    """
    Sets session language based on user preferences.
    """
    if profile.language:
        request.session[LANGUAGE_SESSION_KEY] = profile.language


def remove_user(user):
    '''
    Removes user account.
    '''
    # Send signal (to commit any pending changes)
    user_pre_delete.send(instance=user, sender=user.__class__)

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


@receiver(user_logged_in)
def post_login_handler(sender, request, user, **kwargs):
    '''
    Signal handler for setting user language and
    migrating profile if needed.
    '''

    # Warning about setting password
    if (getattr(user, 'backend', '').endswith('.EmailAuth') and
            not user.has_usable_password()):
        request.session['show_set_password'] = True

    # Ensure user has a profile
    profile = Profile.objects.get_or_create(user=user)[0]

    # Migrate django-registration based verification to python-social-auth
    if (user.has_usable_password() and user.email and
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
    '''
    Automatically adds user to Users group.
    '''
    if created:
        # Create API token
        Token.objects.create(user=instance)
        # Create profile
        Profile.objects.get_or_create(user=instance)
