# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
import re
import sys
import binascii
from smtplib import SMTPException

from django.db import models
from django.dispatch import receiver
from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import post_save, post_migrate
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import python_2_unicode_compatible, force_text
from django.contrib.auth.models import Group, User, Permission
from django.utils import translation as django_translation
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils.translation import LANGUAGE_SESSION_KEY

from rest_framework.authtoken.models import Token

from social.apps.django_app.default.models import UserSocialAuth

from weblate.lang.models import Language
from weblate.trans import messages
from weblate.trans.site import get_site_url, get_site_domain
from weblate.trans.fields import RegexField
from weblate.accounts.avatar import get_user_display
from weblate.trans.util import report_error
from weblate.trans.signals import user_pre_delete
from weblate import VERSION
from weblate.logger import LOGGER
from weblate.appsettings import ANONYMOUS_USER_NAME, SITE_TITLE


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
    return '%s <%s>' % (full_name, user.email)


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

    for owner in subproject.project.owners.all():
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

    for owner in subproject.project.owners.all():
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

    for owner in subproject.project.owners.all():
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
        context['subject_template'] = 'mail/{}_subject.txt'.format(
            notification
        )

        # Adjust context
        context['current_site_url'] = get_site_url()
        if translation_obj is not None:
            context['translation'] = translation_obj
            context['translation_url'] = get_site_url(
                translation_obj.get_absolute_url()
            )
        context['site_title'] = SITE_TITLE

        # Render subject
        subject = render_to_string(
            context['subject_template'],
            context
        ).strip()

        # Render body
        body = render_to_string(
            'mail/{}.txt'.format(notification),
            context
        )
        html_body = render_to_string(
            'mail/{}.html'.format(notification),
            context
        )

        # Define headers
        headers['Auto-Submitted'] = 'auto-generated'
        headers['X-AutoGenerated'] = 'yes'
        headers['Precedence'] = 'bulk'
        headers['X-Mailer'] = 'Weblate {}'.format(VERSION)

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
        if user is not None and user.is_authenticated():
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

    DASHBOARD_SUBSCRIPTIONS = 1
    DASHBOARD_LANGUAGES = 2
    DASHBOARD_COMPONENT_LIST = 4
    DASHBOARD_SUGGESTIONS = 5

    DASHBOARD_CHOICES = (
        (DASHBOARD_SUBSCRIPTIONS, _('Your subscriptions')),
        (DASHBOARD_LANGUAGES, _('Your languages')),
        (DASHBOARD_COMPONENT_LIST, _('Component list')),
        (DASHBOARD_SUGGESTIONS, _('Suggested translations')),
    )

    DASHBOARD_SLUGS = {
        DASHBOARD_SUBSCRIPTIONS: 'your-subscriptions',
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
        default=DASHBOARD_SUBSCRIPTIONS,
    )

    dashboard_component_list = models.ForeignKey(
        'trans.ComponentList',
        verbose_name=_('Default component list'),
        blank=True,
        null=True,
    )

    subscriptions = models.ManyToManyField(
        'trans.Project',
        verbose_name=_('Subscribed projects'),
        help_text=_(
            'You can receive notifications for subscribed projects and '
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

    def notify_user(self, notification, translation_obj,
                    context=None, headers=None, user=None):
        '''
        Wrapper for sending notifications to user.
        '''
        if context is None:
            context = {}
        if headers is None:
            headers = {}

        # Check whether user is still allowed to access this project
        if not translation_obj.has_acl(self.user):
            return
        # Generate notification
        return get_notification_email(
            self.language,
            self.user.email,
            notification,
            translation_obj,
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
            translation,
        )

    def notify_new_suggestion(self, translation, suggestion, unit):
        '''
        Sends notification on new suggestion.
        '''
        return self.notify_user(
            'new_suggestion',
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


@python_2_unicode_compatible
class AutoGroup(models.Model):
    match = RegexField(
        verbose_name=_('Email regular expression'),
        max_length=200,
        default='^.*$',
        help_text=_(
            'Regular expression which is used to match user email.'
        ),
    )
    group = models.ForeignKey(
        Group,
        verbose_name=_('Group to assign'),
    )

    class Meta(object):
        verbose_name = _('Automatic group assignment')
        verbose_name_plural = _('Automatic group assignments')
        ordering = ('group__name', )

    def __str__(self):
        return 'Automatic rule for {0}'.format(self.group)


def set_lang(request, profile):
    """
    Sets session language based on user preferences.
    """
    request.session[LANGUAGE_SESSION_KEY] = profile.language


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


def create_groups(update):
    '''
    Creates standard groups and gives them permissions.
    '''
    guest_group, created = Group.objects.get_or_create(name='Guests')
    if created or update or guest_group.permissions.count() == 0:
        guest_group.permissions.add(
            Permission.objects.get(codename='can_see_git_repository'),
            Permission.objects.get(codename='add_suggestion'),
        )

    group, created = Group.objects.get_or_create(name='Users')
    if created or update or group.permissions.count() == 0:
        group.permissions.add(
            Permission.objects.get(codename='upload_translation'),
            Permission.objects.get(codename='overwrite_translation'),
            Permission.objects.get(codename='save_translation'),
            Permission.objects.get(codename='save_template'),
            Permission.objects.get(codename='accept_suggestion'),
            Permission.objects.get(codename='delete_suggestion'),
            Permission.objects.get(codename='vote_suggestion'),
            Permission.objects.get(codename='ignore_check'),
            Permission.objects.get(codename='upload_dictionary'),
            Permission.objects.get(codename='add_dictionary'),
            Permission.objects.get(codename='change_dictionary'),
            Permission.objects.get(codename='delete_dictionary'),
            Permission.objects.get(codename='lock_translation'),
            Permission.objects.get(codename='can_see_git_repository'),
            Permission.objects.get(codename='add_comment'),
            Permission.objects.get(codename='add_suggestion'),
            Permission.objects.get(codename='use_mt'),
            Permission.objects.get(codename='add_translation'),
        )

    owner_permissions = (
        Permission.objects.get(codename='author_translation'),
        Permission.objects.get(codename='upload_translation'),
        Permission.objects.get(codename='overwrite_translation'),
        Permission.objects.get(codename='commit_translation'),
        Permission.objects.get(codename='update_translation'),
        Permission.objects.get(codename='push_translation'),
        Permission.objects.get(codename='automatic_translation'),
        Permission.objects.get(codename='save_translation'),
        Permission.objects.get(codename='save_template'),
        Permission.objects.get(codename='accept_suggestion'),
        Permission.objects.get(codename='vote_suggestion'),
        Permission.objects.get(codename='override_suggestion'),
        Permission.objects.get(codename='delete_comment'),
        Permission.objects.get(codename='delete_suggestion'),
        Permission.objects.get(codename='ignore_check'),
        Permission.objects.get(codename='upload_dictionary'),
        Permission.objects.get(codename='add_dictionary'),
        Permission.objects.get(codename='change_dictionary'),
        Permission.objects.get(codename='delete_dictionary'),
        Permission.objects.get(codename='lock_subproject'),
        Permission.objects.get(codename='reset_translation'),
        Permission.objects.get(codename='lock_translation'),
        Permission.objects.get(codename='can_see_git_repository'),
        Permission.objects.get(codename='add_comment'),
        Permission.objects.get(codename='delete_comment'),
        Permission.objects.get(codename='add_suggestion'),
        Permission.objects.get(codename='use_mt'),
        Permission.objects.get(codename='edit_priority'),
        Permission.objects.get(codename='edit_flags'),
        Permission.objects.get(codename='manage_acl'),
        Permission.objects.get(codename='download_changes'),
        Permission.objects.get(codename='view_reports'),
        Permission.objects.get(codename='add_translation'),
    )

    group, created = Group.objects.get_or_create(name='Managers')
    if created or update or group.permissions.count() == 0:
        group.permissions.add(*owner_permissions)

    group, created = Group.objects.get_or_create(name='Owners')
    if created or update or group.permissions.count() == 0:
        group.permissions.add(*owner_permissions)

    created = True
    try:
        anon_user = User.objects.get(
            username=ANONYMOUS_USER_NAME,
        )
        created = False
        if anon_user.is_active:
            raise ValueError(
                'Anonymous user ({}) already exists and enabled, '
                'please change ANONYMOUS_USER_NAME setting.'.format(
                    ANONYMOUS_USER_NAME,
                )
            )
    except User.DoesNotExist:
        anon_user = User.objects.create(
            username=ANONYMOUS_USER_NAME,
            email='noreply@weblate.org',
            is_active=False,
        )

    if created or update:
        anon_user.set_unusable_password()
        anon_user.groups.clear()
        anon_user.groups.add(guest_group)


def move_users():
    '''
    Moves users to default group.
    '''
    group = Group.objects.get(name='Users')

    for user in User.objects.all():
        user.groups.add(group)


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


@receiver(post_migrate)
def sync_create_groups(sender, **kwargs):
    '''
    Create groups on syncdb.
    '''
    if sender.label == 'accounts':
        create_groups(False)


@receiver(post_save, sender=User)
def create_profile_callback(sender, instance, created=False, **kwargs):
    '''
    Automatically adds user to Users group.
    '''
    if created:
        # Add user to automatic groups
        for auto in AutoGroup.objects.all():
            if re.match(auto.match, instance.email):
                instance.groups.add(auto.group)
        # Create API token
        Token.objects.create(user=instance)
        # Create profile
        Profile.objects.get_or_create(user=instance)
