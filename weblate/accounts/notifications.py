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

from smtplib import SMTPException
import sys

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils import translation as django_translation
from django.utils.encoding import force_text

from weblate.accounts.models import Profile, AuditLog
from weblate.permissions.helpers import can_access_project
from weblate.utils.site import get_site_url, get_site_domain
from weblate.utils.errors import report_error
from weblate.utils.request import get_ip_address, get_user_agent
from weblate import VERSION
from weblate.logger import LOGGER


def notify_merge_failure(component, error, status):
    """Notification on merge failure."""
    subscriptions = Profile.objects.subscribed_merge_failure(
        component.project,
    )
    users = set()
    mails = []
    for subscription in subscriptions:
        mails.append(
            send_merge_failure(subscription, component, error, status)
        )
        users.add(subscription.user_id)

    for owner in component.project.all_users('@Administration'):
        mails.append(
            send_merge_failure(
                owner.profile, component, error, status
            )
        )

    # Notify admins
    mails.append(
        get_notification_email(
            'en',
            'ADMINS',
            'merge_failure',
            component,
            {
                'component': component,
                'status': status,
                'error': error,
            }
        )
    )
    send_mails(mails)


def notify_parse_error(component, translation, error, filename):
    """Notification on parse error."""
    subscriptions = Profile.objects.subscribed_merge_failure(
        component.project,
    )
    users = set()
    mails = []
    for subscription in subscriptions:
        mails.append(
            send_parse_error(
                subscription,
                component, translation, error, filename
            )
        )
        users.add(subscription.user_id)

    for owner in component.project.all_users('@Administration'):
        mails.append(
            send_parse_error(
                owner.profile,
                component, translation, error, filename
            )
        )

    # Notify admins
    mails.append(
        get_notification_email(
            'en',
            'ADMINS',
            'parse_error',
            translation if translation is not None else component,
            {
                'component': component,
                'translation': translation,
                'error': error,
                'filename': filename,
            }
        )
    )
    send_mails(mails)


def notify_new_string(translation):
    """Notification on new string to translate."""
    mails = []
    subscriptions = Profile.objects.subscribed_new_string(
        translation.component.project, translation.language
    )
    for subscription in subscriptions:
        mails.append(
            send_new_string(subscription, translation)
        )

    send_mails(mails)


def notify_new_language(component, language, user):
    """Notify subscribed users about new language requests"""
    mails = []
    subscriptions = Profile.objects.subscribed_new_language(
        component.project,
        user
    )
    users = set()
    for subscription in subscriptions:
        mails.append(
            send_new_language(subscription, component, language, user)
        )
        users.add(subscription.user_id)

    for owner in component.project.all_users('@Administration'):
        mails.append(
            send_new_language(
                owner.profile, component, language, user
            )
        )

    send_mails(mails)


def notify_new_translation(unit, oldunit, user):
    """Notify subscribed users about new translation"""
    mails = []
    subscriptions = Profile.objects.subscribed_any_translation(
        unit.translation.component.project,
        unit.translation.language,
        user
    )
    for subscription in subscriptions:
        mails.append(
            send_any_translation(subscription, unit, oldunit)
        )

    send_mails(mails)


def notify_new_contributor(unit, user):
    """Notify about new contributor."""
    mails = []
    subscriptions = Profile.objects.subscribed_new_contributor(
        unit.translation.component.project,
        unit.translation.language,
        user
    )
    for subscription in subscriptions:
        mails.append(
            send_new_contributor(
                subscription,
                unit.translation, user
            )
        )

    send_mails(mails)


def notify_new_suggestion(unit, suggestion, user):
    """Notify about new suggestion."""
    mails = []
    subscriptions = Profile.objects.subscribed_new_suggestion(
        unit.translation.component.project,
        unit.translation.language,
        user
    )
    for subscription in subscriptions:
        mails.append(
            send_new_suggestion(
                subscription,
                unit.translation,
                suggestion,
                unit
            )
        )

    send_mails(mails)


def notify_new_comment(unit, comment, user, report_source_bugs):
    """Notify about new comment."""
    mails = []
    subscriptions = Profile.objects.subscribed_new_comment(
        unit.translation.component.project,
        comment.language,
        user
    )
    for subscription in subscriptions:
        mails.append(
            send_new_comment(subscription, unit, comment, user)
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
                'component': unit.translation.component,
            },
            user=user,
        )

    send_mails(mails)


def get_notification_email(language, email, notification,
                           translation_obj=None, context=None, headers=None,
                           user=None, info=None):
    """Render notification email."""
    cur_language = django_translation.get_language()
    context = context or {}
    headers = headers or {}
    references = None
    if 'unit' in context:
        unit = context['unit']
        references = '{0}/{1}/{2}/{3}'.format(
            unit.translation.component.project.slug,
            unit.translation.component.slug,
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
        context['LANGUAGE_CODE'] = django_translation.get_language()
        context['LANGUAGE_BIDI'] = django_translation.get_language_bidi()

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
    """Render and sends notification email."""
    email = get_notification_email(
        language, email, notification, translation_obj, context, headers,
        user, info
    )
    send_mails([email])


def is_new_login(user, address):
    """Checks whether this login is coming from new device.

    This is currently based purely in IP address.
    """
    logins = AuditLog.objects.filter(user=user, activity='login-new')

    # First login
    if not logins.exists():
        return False

    return not logins.filter(address=address).exists()


def notify_account_activity(user, request, activity, **kwargs):
    """Notification about important activity with account.

    Returns whether the activity should be rate limited."""
    address = get_ip_address(request)
    user_agent = get_user_agent(request)

    if activity == 'login' and is_new_login(user, address):
        activity = 'login-new'

    audit = AuditLog.objects.create(
        user, activity, address, user_agent, **kwargs
    )

    if audit.should_notify():
        profile = Profile.objects.get_or_create(user=user)[0]
        send_notification_email(
            profile.language,
            user.email,
            'account_activity',
            context={
                'message': audit.get_message(),
                'extra_message': audit.get_extra_message(),
                'address': address,
                'user_agent': user_agent,
            },
            info='{0} from {1}'.format(activity, address),
        )

    # Handle rate limiting
    if activity == 'failed-auth' and user.has_usable_password():
        failures = AuditLog.objects.get_after(user, 'login', 'failed-auth')
        if failures.count() >= settings.AUTH_LOCK_ATTEMPTS:
            user.set_unusable_password()
            user.save(update_fields=['password'])
            notify_account_activity(user, request, 'locked')
            return True

    elif activity == 'reset-request':
        failures = AuditLog.objects.get_after(user, 'login', 'reset-request')
        if failures.count() >= settings.AUTH_LOCK_ATTEMPTS:
            return True

    return False


def send_user(profile, notification, component, display_obj,
              context=None, headers=None, user=None):
    """Wrapper for sending notifications to user."""
    if context is None:
        context = {}
    if headers is None:
        headers = {}

    # Check whether user is still allowed to access this project
    if can_access_project(profile.user, component.project):
        # Generate notification
        return get_notification_email(
            profile.language,
            profile.user.email,
            notification,
            display_obj,
            context,
            headers,
            user=user
        )
    return None


def send_any_translation(profile, unit, oldunit):
    """Send notification on translation."""
    if oldunit.translated:
        template = 'changed_translation'
    else:
        template = 'new_translation'
    return send_user(
        profile,
        template,
        unit.translation.component,
        unit.translation,
        {
            'unit': unit,
            'oldunit': oldunit,
        }
    )


def send_new_language(profile, component, language, user):
    """Send notification on new language request."""
    return send_user(
        profile,
        'new_language',
        component,
        component,
        {
            'language': language,
            'user': user,
        },
        user=user
    )


def send_new_string(profile, translation):
    """Send notification on new strings to translate."""
    return send_user(
        profile,
        'new_string',
        translation.component,
        translation,
    )


def send_new_suggestion(profile, translation, suggestion, unit):
    """Send notification on new suggestion."""
    return send_user(
        profile,
        'new_suggestion',
        translation.component,
        translation,
        {
            'suggestion': suggestion,
            'unit': unit,
        }
    )


def send_new_contributor(profile, translation, user):
    """Send notification on new contributor."""
    return send_user(
        profile,
        'new_contributor',
        translation.component,
        translation,
        {
            'user': user,
        }
    )


def send_new_comment(profile, unit, comment, user):
    """Send notification about new comment."""
    return send_user(
        profile,
        'new_comment',
        unit.translation.component,
        unit.translation,
        {
            'unit': unit,
            'comment': comment,
            'component': unit.translation.component,
        },
        user=user,
    )


def send_merge_failure(profile, component, error, status):
    """Send notification on merge failure."""
    return send_user(
        profile,
        'merge_failure',
        component,
        component,
        {
            'component': component,
            'error': error,
            'status': status,
        }
    )


def send_parse_error(profile, component, translation, error, filename):
    """Send notification on parse error."""
    return send_user(
        profile,
        'parse_error',
        component,
        translation if translation is not None else component,
        {
            'component': component,
            'translation': translation,
            'error': error,
            'filename': filename,
        }
    )


def send_mails(mails):
    """Send multiple mails in single connection."""
    try:
        connection = get_connection()
        connection.send_messages(
            [mail for mail in mails if mail is not None]
        )
    except SMTPException as error:
        LOGGER.error('Failed to send email: %s', error)
        report_error(error, sys.exc_info())
