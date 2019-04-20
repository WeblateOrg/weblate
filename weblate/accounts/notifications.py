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

from collections import defaultdict

from dateutil.relativedelta import relativedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import (
    ugettext_lazy as _, get_language, get_language_bidi, override,
)
from django.utils.encoding import force_text

from html2text import html2text

from weblate.celery import app
from weblate.lang.models import Language
from weblate.trans.models import Change
from weblate.utils.site import get_site_url, get_site_domain
from weblate import VERSION
from weblate.logger import LOGGER


FREQ_NONE = 0
FREQ_INSTANT = 1
FREQ_DAILY = 2
FREQ_WEEKLY = 3
FREQ_MONTHLY = 4

FREQ_CHOICES = (
    (FREQ_NONE, _('Do not notify')),
    (FREQ_INSTANT, _('Instant notification')),
    (FREQ_DAILY, _('Daily digest')),
    (FREQ_WEEKLY, _('Weekly digest')),
    (FREQ_MONTHLY, _('Monthly digest')),
)

SCOPE_DEFAULT = 10
SCOPE_ADMIN = 20
SCOPE_PROJECT = 30
SCOPE_COMPONENT = 40

SCOPE_CHOICES = (
    (SCOPE_DEFAULT, 'Defaults'),
    (SCOPE_ADMIN, 'Admin'),
    (SCOPE_PROJECT, 'Project'),
    (SCOPE_COMPONENT, 'Component'),
)

NOTIFICATIONS = []
NOTIFICATIONS_ACTIONS = {}


def register_notification(handler):
    """Register notification handler."""
    NOTIFICATIONS.append(handler)
    for action in handler.actions:
        if action not in NOTIFICATIONS_ACTIONS:
            NOTIFICATIONS_ACTIONS[action] = []
        NOTIFICATIONS_ACTIONS[action].append(handler)
    return handler


class Notification(object):
    actions = ()
    verbose = ''
    template_name = None
    digest_template = 'digest'
    filter_languages = False
    ignore_watched = False
    required_attr = None

    def __init__(self, connection):
        self.connection = connection
        self.subscription_cache = {}

    def need_language_filter(self, change):
        return self.filter_languages

    @staticmethod
    def get_freq_choices():
        return FREQ_CHOICES

    @classmethod
    def get_choice(cls):
        return (cls.get_name(), cls.verbose)

    @classmethod
    def get_name(cls):
        return force_text(cls.__name__)

    def filter_subscriptions(self, change, users, lang_filter):
        from weblate.accounts.models import Subscription
        result = Subscription.objects.filter(notification=self.get_name())
        if users is not None:
            result = result.filter(user_id__in=users)
        query = Q(scope=SCOPE_DEFAULT) | Q(scope=SCOPE_ADMIN)
        if change.component:
            query |= Q(component=change.component)
        if change.project:
            query |= Q(project=change.project)
        if lang_filter:
            result = result.filter(
                user__profile__languages=change.translation.language
            )
        return result.filter(
            query
        ).order_by(
            'user', '-scope'
        ).select_related(
            'user__profile'
        )

    def get_subscriptions(self, change, users):
        lang_filter = self.need_language_filter(change)
        cache_key = (
            change.translation.language_id if lang_filter else lang_filter,
            change.component.pk if change.component else None,
            change.project.pk if change.project else None
        )
        if users is not None:
            cache_key += tuple(sorted(users))
        if cache_key in self.subscription_cache:
            return self.subscription_cache[cache_key]
        result = self.filter_subscriptions(change, users, lang_filter)
        self.subscription_cache[cache_key] = result
        return result

    def has_required_attrs(self, change):
        return (
            self.required_attr and
            getattr(change, self.required_attr) is None
        )

    def get_users(self, frequency, change, users=None):
        if self.has_required_attrs(change):
            return
        last_user = None
        subscriptions = self.get_subscriptions(change, users)
        for subscription in subscriptions:
            user = subscription.user
            # Skip lower priority subscription and own changes
            if last_user == user or user == change.user:
                continue
            if (subscription.scope == SCOPE_ADMIN and
                    not user.has_perm('project.edit', change.project)):
                continue
            if (subscription.scope == SCOPE_DEFAULT and
                    not self.ignore_watched and
                    change.project_id is not None and
                    not user.profile.watched.filter(pk=change.project_id).exists()):
                continue
            last_user = user
            if subscription.frequency == frequency:
                yield last_user

    def send(self, address, subject, body, headers):
        email = EmailMultiAlternatives(
            settings.EMAIL_SUBJECT_PREFIX + subject,
            html2text(body),
            to=[address],
            headers=headers,
            connection=self.connection,
        )
        email.attach_alternative(body, 'text/html')
        email.send()

    def render_template(self, suffix, context, digest=False):
        """Render single mail template with given context"""
        template_name = 'mail/{}{}'.format(
            self.digest_template if digest else self.template_name,
            suffix
        )
        return render_to_string(template_name, context).strip()

    def get_context(self, change=None):
        """Return context for rendering mail"""
        result = {
            'LANGUAGE_CODE': get_language(),
            'LANGUAGE_BIDI': get_language_bidi(),
            'current_site_url': get_site_url(),
            'site_title': settings.SITE_TITLE,
            'notification_name': self.verbose,
        }
        if not change:
            return result
        result['change'] = change
        # Extract change attributes
        attribs = (
            'unit', 'translation', 'component', 'project', 'dictionary',
            'comment', 'suggestion', 'whiteboard', 'alert',
            'user',
            'target', 'old', 'details',
        )
        for attrib in attribs:
            result[attrib] = getattr(change, attrib)
        if result['translation']:
            result['translation_url'] = get_site_url(
                result['translation'].get_absolute_url()
            )
        return result

    def get_headers(self, context):
        headers = {
            'Auto-Submitted': 'auto-generated',
            'X-AutoGenerated': 'yes',
            'Precedence': 'bulk',
            'X-Mailer': 'Weblate {0}'.format(VERSION),
            'X-Weblate-Notification': self.get_name()
        }

        # References for unit events
        references = None
        unit = context.get('unit')
        if unit:
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
        return headers

    def send_immediate(self, language, email, change):
        with override('en' if language is None else language):
            context = self.get_context(change)
            subject = self.render_template('_subject.txt', context)
            context['subject'] = subject
            LOGGER.info(
                'sending notification %s on %s to %s',
                self.get_name(), context['component'], email,
            )
            self.send(
                email,
                subject,
                self.render_template('.html', context),
                self.get_headers(context),
            )

    def notify_immediate(self, change):
        for user in self.get_users(FREQ_INSTANT, change):
            if (change.project is None or
                    user.can_access_project(change.project)):
                self.send_immediate(
                    user.profile.language, user.email, change
                )

    def send_digest(self, language, email, changes):
        with override('en' if language is None else language):
            context = self.get_context()
            context['changes'] = changes
            subject = self.render_template(
                '_subject.txt', context, digest=True
            )
            context['subject'] = subject
            LOGGER.info(
                'sending digest notification %s on %d changes to %s',
                self.get_name(), len(changes), email,
            )
            self.send(
                email,
                subject,
                self.render_template('.html', context, digest=True),
                self.get_headers(context),
            )

    def notify_digest(self, frequency, changes):
        notifications = defaultdict(list)
        users = {}
        for change in changes:
            for user in self.get_users(frequency, change):
                if (change.project is None or
                        user.can_access_project(change.project)):
                    notifications[user.pk].append(change)
                    users[user.pk] = user
        for user in users.values():
            self.send_digest(
                user.profile.language, user.email, notifications[user.pk]
            )

    def filter_changes(self, **kwargs):
        return Change.objects.filter(
            action__in=self.actions,
            timestamp__gte=timezone.now() - relativedelta(**kwargs)
        )

    def notify_daily(self):
        self.notify_digest(FREQ_DAILY, self.filter_changes(days=1))

    def notify_weekly(self):
        self.notify_digest(FREQ_WEEKLY, self.filter_changes(weeks=1))

    def notify_monthly(self):
        self.notify_digest(FREQ_MONTHLY, self.filter_changes(months=1))


@register_notification
class MergeFailureNotification(Notification):
    actions = (Change.ACTION_FAILED_MERGE, Change.ACTION_FAILED_REBASE)
    verbose = _('Merge failure')
    template_name = 'merge_failure'


@register_notification
class ParseErrorNotification(Notification):
    actions = (Change.ACTION_PARSE_ERROR,)
    verbose = _('Parse error')
    template_name = 'parse_error'


@register_notification
class NewStringNotificaton(Notification):
    actions = (Change.ACTION_NEW_STRING,)
    verbose = _('New string')
    template_name = 'new_string'
    filter_languages = True


@register_notification
class NewContributorNotificaton(Notification):
    actions = (Change.ACTION_NEW_CONTRIBUTOR,)
    verbose = _('New contributor')
    template_name = 'new_contributor'
    filter_languages = True


@register_notification
class NewSuggestionNotificaton(Notification):
    actions = (Change.ACTION_SUGGESTION,)
    verbose = _('New suggestion')
    template_name = 'new_suggestion'
    filter_languages = True
    required_attr = 'suggestion'


@register_notification
class LastAuthorCommentNotificaton(Notification):
    actions = (Change.ACTION_COMMENT,)
    verbose = _('Comment on authored translation')
    template_name = 'new_comment'
    ignore_watched = True
    required_attr = 'comment'

    def get_users(self, frequency, change, users=None):
        last_author = change.unit.get_last_content_change(None, silent=True)[0]
        if last_author.is_anonymous or last_author.is_demo:
            users = []
        else:
            users = [last_author.pk]
        return super(LastAuthorCommentNotificaton, self).get_users(
            frequency, change, users
        )


@register_notification
class MentionCommentNotificaton(Notification):
    actions = (Change.ACTION_COMMENT,)
    verbose = _('Mentioned in comment')
    template_name = 'new_comment'
    ignore_watched = True
    required_attr = 'comment'

    def get_users(self, frequency, change, users=None):
        if self.has_required_attrs(change):
            return
        users = [user.pk for user in change.comment.get_mentions()]
        return super(MentionCommentNotificaton, self).get_users(
            frequency, change, users
        )


@register_notification
class NewCommentNotificaton(Notification):
    actions = (Change.ACTION_COMMENT,)
    verbose = _('New comment')
    template_name = 'new_comment'
    filter_languages = True
    required_attr = 'comment'

    def need_language_filter(self, change):
        return bool(change.comment.language)

    def notify_immediate(self, change):
        super(NewCommentNotificaton, self).notify_immediate(change)

        # Notify upstream
        report_source_bugs = change.component.report_source_bugs
        if change.comment.language is None and report_source_bugs:
            self.send_immediate('en', report_source_bugs, change)


@register_notification
class ChangedStringNotificaton(Notification):
    actions = Change.ACTIONS_CONTENT
    verbose = _('Changed string')
    template_name = 'changed_translation'
    filter_languages = True


@register_notification
class NewTranslationNotificaton(Notification):
    actions = (Change.ACTION_ADDED_LANGUAGE, Change.ACTION_REQUESTED_LANGUAGE)
    verbose = _('New language')
    template_name = 'new_language'

    def get_context(self, change=None):
        context = super(NewTranslationNotificaton, self).get_context(change)
        if change:
            context['language'] = Language.objects.get(
                code=change.details['language']
            )
            context['was_added'] = (
                change.action == Change.ACTION_ADDED_LANGUAGE
            )
        return context


@register_notification
class NewComponentNotificaton(Notification):
    actions = (Change.ACTION_CREATE_COMPONENT,)
    verbose = _('New translation component')
    template_name = 'new_component'


@register_notification
class NewWhiteboardMessageNotificaton(Notification):
    actions = (Change.ACTION_MESSAGE,)
    verbose = _('New whiteboard message')
    template_name = 'new_whiteboard'
    required_attr = 'whiteboard'


@register_notification
class NewAlertNotificaton(Notification):
    actions = (Change.ACTION_ALERT,)
    verbose = _('New component alert')
    template_name = 'new_alert'
    required_attr = 'alert'


def get_notification_email(language, email, notification,
                           context=None, info=None):
    """Render notification email."""
    context = context or {}
    headers = {}

    LOGGER.info(
        'sending notification %s on %s to %s',
        notification,
        info,
        email
    )

    with override('en' if language is None else language):
        # Template name
        context['subject_template'] = 'mail/{0}_subject.txt'.format(
            notification
        )
        context['LANGUAGE_CODE'] = get_language()
        context['LANGUAGE_BIDI'] = get_language_bidi()

        # Adjust context
        context['current_site_url'] = get_site_url()
        context['site_title'] = settings.SITE_TITLE

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


def send_notification_email(language, email, notification, context=None,
                            info=None):
    """Render and sends notification email."""
    email = get_notification_email(
        language, email, notification, context, info
    )
    send_mails.delay([email])


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
