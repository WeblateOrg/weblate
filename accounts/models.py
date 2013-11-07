# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

from django.db import models, IntegrityError
from django.dispatch import receiver
from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth.models import Group, User, Permission
from django.db.models.signals import post_syncdb
from django.contrib.sites.models import Site
from django.utils import translation as django_translation
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives

from south.signals import post_migrate
from social.apps.django_app.default.models import UserSocialAuth

from lang.models import Language
from trans.models import Project, Change
from trans.util import (
    get_user_display, get_site_url, get_distinct_translations
)
import weblate
from weblate.appsettings import ANONYMOUS_USER_NAME


def notify_merge_failure(subproject, error, status):
    '''
    Notification on merge failure.
    '''
    subscriptions = Profile.objects.subscribed_merge_failure(
        subproject.project,
    )
    for subscription in subscriptions:
        subscription.notify_merge_failure(subproject, error, status)

    # Notify admins
    send_notification_email(
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


def notify_new_string(translation):
    '''
    Notification on new string to translate.
    '''
    subscriptions = Profile.objects.subscribed_new_string(
        translation.subproject.project, translation.language
    )
    for subscription in subscriptions:
        subscription.notify_new_string(translation)


def notify_new_language(subproject, language, user):
    '''
    Notify subscribed users about new translation
    '''
    subscriptions = Profile.objects.subscribed_new_language(
        subproject.project,
        user
    )
    for subscription in subscriptions:
        subscription.notify_new_language(subproject, language, user)


def notify_new_translation(unit, oldunit, user):
    '''
    Notify subscribed users about new translation
    '''
    subscriptions = Profile.objects.subscribed_any_translation(
        unit.translation.subproject.project,
        unit.translation.language,
        user
    )
    for subscription in subscriptions:
        subscription.notify_any_translation(unit, oldunit)


def notify_new_contributor(unit, user):
    '''
    Notify about new contributor.
    '''
    subscriptions = Profile.objects.subscribed_new_contributor(
        unit.translation.subproject.project,
        unit.translation.language,
        user
    )
    for subscription in subscriptions:
        subscription.notify_new_contributor(
            unit.translation, user
        )


def notify_new_suggestion(unit, suggestion, user):
    '''
    Notify about new suggestion.
    '''
    subscriptions = Profile.objects.subscribed_new_suggestion(
        unit.translation.subproject.project,
        unit.translation.language,
        user
    )
    for subscription in subscriptions:
        subscription.notify_new_suggestion(
            unit.translation,
            suggestion,
            unit
        )


def notify_new_comment(unit, comment, user, report_source_bugs):
    '''
    Notify about new comment.
    '''
    subscriptions = Profile.objects.subscribed_new_comment(
        unit.translation.subproject.project,
        comment.language,
        user
    )
    for subscription in subscriptions:
        subscription.notify_new_comment(unit, comment)

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


def send_notification_email(language, email, notification,
                            translation_obj=None, context=None, headers=None,
                            user=None, info=None):
    '''
    Renders and sends notification email.
    '''
    cur_language = django_translation.get_language()
    if context is None:
        context = {}
    if headers is None:
        headers = {}
    try:
        if info is None:
            info = translation_obj.__unicode__()
        weblate.logger.info(
            'sending notification %s on %s to %s',
            notification,
            info,
            email
        )

        # Load user language
        if language is not None:
            django_translation.activate(language)

        # Template names
        subject_template = 'mail/{}_subject.txt'.format(notification)
        body_template = 'mail/{}.txt'.format(notification)
        html_body_template = 'mail/{}.html'.format(notification)

        # Adjust context
        site = Site.objects.get_current()
        context['current_site'] = site.domain
        context['site'] = site
        if translation_obj is not None:
            context['translation'] = translation_obj
            context['translation_url'] = get_site_url(
                translation_obj.get_absolute_url()
            )
        context['subject_template'] = subject_template

        # Render subject
        subject = render_to_string(subject_template, context).strip()

        # Render body
        body = render_to_string(body_template, context)
        html_body = render_to_string(html_body_template, context)

        # Define headers
        headers['Auto-Submitted'] = 'auto-generated'
        headers['X-AutoGenerated'] = 'yes'
        headers['Precedence'] = 'bulk'
        headers['X-Mailer'] = 'Weblate {}'.format(weblate.VERSION)

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

        # Send it out
        email.send(fail_silently=False)
    finally:
        django_translation.activate(cur_language)


class VerifiedEmail(models.Model):
    '''
    Storage for verified emails from auth backends.
    '''
    social = models.ForeignKey(UserSocialAuth)
    email = models.EmailField()


class ProfileManager(models.Manager):
    '''
    Manager providing shortcuts for subscription queries.
    '''
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


class Profile(models.Model):
    '''
    User profiles storage.
    '''
    user = models.OneToOneField(User, unique=True, editable=False)
    language = models.CharField(
        verbose_name=_(u"Interface Language"),
        max_length=10,
        choices=settings.LANGUAGES
    )
    languages = models.ManyToManyField(
        Language,
        verbose_name=_('Languages'),
        blank=True,
    )
    secondary_languages = models.ManyToManyField(
        Language,
        verbose_name=_('Secondary languages'),
        related_name='secondary_profile_set',
        blank=True,
    )
    suggested = models.IntegerField(default=0, db_index=True)
    translated = models.IntegerField(default=0, db_index=True)

    subscriptions = models.ManyToManyField(
        Project,
        verbose_name=_('Subscribed projects')
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

    objects = ProfileManager()

    def __unicode__(self):
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

    def get_last_change(self):
        '''
        Returns date of last change user has done in Weblate.
        '''
        try:
            change = Change.objects.filter(
                user=self.user
            )
            return change[0].timestamp
        except IndexError:
            return None

    def notify_user(self, notification, translation_obj,
                    context=None, headers=None):
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
        # Actually send notification
        send_notification_email(
            self.language,
            self.user.email,
            notification,
            translation_obj,
            context,
            headers
        )

    def notify_any_translation(self, unit, oldunit):
        '''
        Sends notification on translation.
        '''
        if oldunit.translated:
            template = 'changed_translation'
        else:
            template = 'new_translation'
        self.notify_user(
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
        self.notify_user(
            'new_language',
            subproject,
            {
                'language': language,
            }
        )

    def notify_new_string(self, translation):
        '''
        Sends notification on new strings to translate.
        '''
        self.notify_user(
            'new_string',
            translation,
        )

    def notify_new_suggestion(self, translation, suggestion, unit):
        '''
        Sends notification on new suggestion.
        '''
        self.notify_user(
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
        self.notify_user(
            'new_contributor',
            translation,
            {
                'user': user,
            }
        )

    def notify_new_comment(self, unit, comment):
        '''
        Sends notification about new comment.
        '''
        self.notify_user(
            'new_comment',
            unit.translation,
            {
                'unit': unit,
                'comment': comment,
                'subproject': unit.translation.subproject,
            }
        )

    def notify_merge_failure(self, subproject, error, status):
        '''
        Sends notification on merge failure.
        '''
        self.notify_user(
            'merge_failure',
            subproject,
            {
                'subproject': subproject,
                'error': error,
                'status': status,
            }
        )

    def get_full_name(self):
        '''
        Returns user's full name.
        '''
        return self.user.get_full_name()

    def get_secondary_units(self, unit):
        '''
        Returns list of secondary units.
        '''
        from trans.models.unit import Unit
        secondary_langs = self.secondary_languages.exclude(
            id=unit.translation.language.id
        )
        project = unit.translation.subproject.project
        return get_distinct_translations(
            Unit.objects.filter(
                checksum=unit.checksum,
                translated=True,
                translation__subproject__project=project,
                translation__language__in=secondary_langs,
            )
        )


@receiver(user_logged_in)
def set_lang(sender, **kwargs):
    '''
    Signal handler for setting user language and
    migrating profile if needed.
    '''
    request = kwargs['request']
    user = kwargs['user']

    # Warning about setting password
    if (getattr(user, 'backend', '') == 'social.backends.email.EmailAuth'
            and not user.has_usable_password()):
        request.session['show_set_password'] = True

    # Ensure user has a profile
    profile, dummy = Profile.objects.get_or_create(user=user)

    # Migrate django-registration based verification to python-social-auth
    if (user.has_usable_password()
            and not user.social_auth.filter(provider='email').exists()):
        social = user.social_auth.create(
            provider='email',
            uid=user.email,
        )
        VerifiedEmail.objects.create(
            social=social,
            email=user.email,
        )

    # Set language for session based on preferences
    lang_code = profile.language
    request.session['django_language'] = lang_code


def create_groups(update):
    '''
    Creates standard groups and gives them permissions.
    '''
    guest_group, created = Group.objects.get_or_create(name='Guests')
    if created or update:
        guest_group.permissions.add(
            Permission.objects.get(codename='can_see_git_repository'),
            Permission.objects.get(codename='add_suggestion'),
        )

    group, created = Group.objects.get_or_create(name='Users')
    if created or update:
        group.permissions.add(
            Permission.objects.get(codename='upload_translation'),
            Permission.objects.get(codename='overwrite_translation'),
            Permission.objects.get(codename='save_translation'),
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
        )

    group, created = Group.objects.get_or_create(name='Managers')
    if created or update:
        group.permissions.add(
            Permission.objects.get(codename='author_translation'),
            Permission.objects.get(codename='upload_translation'),
            Permission.objects.get(codename='overwrite_translation'),
            Permission.objects.get(codename='commit_translation'),
            Permission.objects.get(codename='update_translation'),
            Permission.objects.get(codename='push_translation'),
            Permission.objects.get(codename='automatic_translation'),
            Permission.objects.get(codename='save_translation'),
            Permission.objects.get(codename='accept_suggestion'),
            Permission.objects.get(codename='vote_suggestion'),
            Permission.objects.get(codename='override_suggestion'),
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
        )

    try:
        anon_user, created = User.objects.get_or_create(
            username=ANONYMOUS_USER_NAME,
            is_active=False,
        )
        if created or update:
            anon_user.set_unusable_password()
            anon_user.groups.clear()
            anon_user.groups.add(guest_group)
    except IntegrityError as error:
        raise ValueError(
            'Anonymous user ({}) already exists and enabled, '
            'please change ANONYMOUS_USER_NAME setting.\n'
            'Raised error was: {!r}'.format(
                ANONYMOUS_USER_NAME,
                error
            )
        )


def move_users():
    '''
    Moves users to default group.
    '''
    group = Group.objects.get(name='Users')

    for user in User.objects.all():
        user.groups.add(group)


@receiver(post_syncdb)
@receiver(post_migrate)
def sync_create_groups(sender, app, **kwargs):
    '''
    Create groups on syncdb.
    '''
    if (app == 'accounts'
            or getattr(app, '__name__', '') == 'accounts.models'):
        create_groups(False)


@receiver(post_save, sender=User)
def create_profile_callback(sender, **kwargs):
    '''
    Automatically adds user to Users group.
    '''
    if kwargs['created']:
        # Add user to Users group if it exists
        try:
            group = Group.objects.get(name='Users')
            kwargs['instance'].groups.add(group)
        except Group.DoesNotExist:
            pass
