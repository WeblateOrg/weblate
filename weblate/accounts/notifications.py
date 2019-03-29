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

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils import translation as django_translation
from django.utils.encoding import force_text

from html2text import html2text

from weblate.auth.models import User
from weblate.accounts.models import Profile
from weblate.celery import app
from weblate.lang.models import Language
from weblate.utils.site import get_site_url, get_site_domain
from weblate import VERSION
from weblate.logger import LOGGER


def notify_merge_failure(change):
    """Notification on merge failure."""
    component = change.component
    error = change.details.get('error', '')
    status = change.details.get('status', '')
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

    for owner in User.objects.all_admins(component.project):
        mails.append(
            send_merge_failure(
                owner.profile, component, error, status
            )
        )

    enqueue_mails(mails)


def notify_parse_error(change):
    """Notification on parse error."""
    component = change.component
    translation = change.translation
    error = change.details.get('error', '')
    filename = change.details.get('filename', '')
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

    for owner in User.objects.all_admins(component.project):
        mails.append(
            send_parse_error(
                owner.profile,
                component, translation, error, filename
            )
        )

    enqueue_mails(mails)


def notify_new_string(change):
    """Notification on new string to translate."""
    translation = change.translation
    mails = []
    subscriptions = Profile.objects.subscribed_new_string(
        translation.component.project, translation.language
    )
    for subscription in subscriptions:
        mails.append(
            send_new_string(subscription, translation)
        )

    enqueue_mails(mails)


def notify_new_language(change):
    """Notify subscribed users about new language requests"""
    component = change.component
    language = Language.objects.get(code=change.details['language'])
    user = change.user
    was_added = change.action == change.ACTION_ADDED_LANGUAGE
    mails = []
    subscriptions = Profile.objects.subscribed_new_language(
        component.project,
        user
    )
    users = set()
    for subscription in subscriptions:
        mails.append(
            send_new_language(
                subscription, component, language, user, was_added
            )
        )
        users.add(subscription.user_id)

    for owner in User.objects.all_admins(component.project):
        if owner.id in users:
            continue
        mails.append(
            send_new_language(
                owner.profile, component, language, user, was_added
            )
        )

    enqueue_mails(mails)


def notify_new_translation(change):
    """Notify subscribed users about new translation"""
    unit = change.unit
    user = change.user
    old_target = change.old
    mails = []
    subscriptions = Profile.objects.subscribed_any_translation(
        unit.translation.component.project,
        unit.translation.language,
        user
    )
    for subscription in subscriptions:
        mails.append(
            send_any_translation(subscription, unit, old_target, user)
        )

    enqueue_mails(mails)


def notify_new_contributor(change):
    """Notify about new contributor."""
    unit = change.unit
    user = change.user
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

    enqueue_mails(mails)


def notify_new_suggestion(change):
    """Notify about new suggestion."""
    unit = change.unit
    suggestion = change.suggestion
    if not suggestion:
        return
    user = change.user
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

    enqueue_mails(mails)


def notify_new_comment(change):
    """Notify about new comment."""
    unit = change.unit
    comment = change.comment
    if not comment:
        return
    user = change.user
    report_source_bugs = unit.translation.component.report_source_bugs
    mails = []
    users = {user.pk}
    subscriptions = Profile.objects.subscribed_new_comment(
        unit.translation.component.project,
        comment.language,
        user
    )
    for subscription in subscriptions:
        mails.append(
            send_new_comment(subscription, unit, comment, user)
        )
        users.add(subscription.user.pk)

    # Notify mentioned users
    for mentioned in comment.get_mentions():
        if mentioned.pk in users:
            continue
        mails.append(
            send_new_comment(mentioned.profile, unit, comment, user)
        )
        users.add(mentioned.pk)

    # Notify last author
    last_author = unit.get_last_content_change(None, silent=True)[0]
    if (not last_author.is_anonymous and
            not last_author.is_demo and
            last_author.pk not in users):
        mails.append(
            send_new_comment(last_author.profile, unit, comment, user)
        )
        users.add(last_author.pk)

    # Notify upstream
    if comment.language is None and report_source_bugs:
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

    enqueue_mails(mails)


def get_notification_email(language, email, notification,
                           translation_obj=None, context=None, headers=None,
                           user=None, info=None):
    """Render notification email."""
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

    if info is None:
        info = force_text(translation_obj)

    LOGGER.info(
        'sending notification %s on %s to %s',
        notification,
        info,
        email
    )

    with django_translation.override('en' if language is None else language):
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
        context['user'] = user

        # Render subject
        subject = render_to_string(
            context['subject_template'],
            context
        ).strip()

        # Render body
        html_body = render_to_string(
            'mail/{0}.html'.format(notification),
            context
        )
        body = html2text(html_body)

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

        # Return the mail content
        return {
            'subject': subject,
            'body': body,
            'to': emails,
            'headers': headers,
            'html_body': html_body,
        }


def send_notification_email(language, email, notification,
                            translation_obj=None, context=None, headers=None,
                            user=None, info=None):
    """Render and sends notification email."""
    email = get_notification_email(
        language, email, notification, translation_obj, context, headers,
        user, info
    )
    enqueue_mails([email])


def send_user(profile, notification, component, display_obj,
              context=None, headers=None, user=None):
    """Wrapper for sending notifications to user."""
    if context is None:
        context = {}
    if headers is None:
        headers = {}

    # Check whether user is still allowed to access this project
    if profile.user.can_access_project(component.project):
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


def send_any_translation(profile, unit, old_target, user):
    """Send notification on translation."""
    return send_user(
        profile,
        'changed_translation',
        unit.translation.component,
        unit.translation,
        {
            'unit': unit,
            'old_target': old_target,
        },
        user=user
    )


def send_new_language(profile, component, language, user, was_added):
    """Send notification on new language request."""
    return send_user(
        profile,
        'new_language',
        component,
        component,
        {
            'language': language,
            'was_added': was_added,
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
        },
        user=suggestion.user
    )


def send_new_contributor(profile, translation, user):
    """Send notification on new contributor."""
    return send_user(
        profile,
        'new_contributor',
        translation.component,
        translation,
        user=user,
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


def enqueue_mails(mails):
    mails = [mail for mail in mails if mail is not None]
    if mails:
        send_mails.delay(mails)


@app.task
def send_mails(mails):
    """Send multiple mails in single connection."""
    with get_connection() as connection:
        for mail in mails:
            email = EmailMultiAlternatives(
                settings.EMAIL_SUBJECT_PREFIX + mail['subject'],
                mail['body'],
                to=mail['to'],
                headers=mail['headers'],
                connection=connection,
            )
            email.attach_alternative(
                mail['html_body'],
                'text/html'
            )
            email.send()
