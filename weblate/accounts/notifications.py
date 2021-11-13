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

from collections import defaultdict
from copy import copy
from email.utils import formataddr
from typing import Iterable, Optional

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.signing import TimestampSigner
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import get_language, get_language_bidi
from django.utils.translation import gettext_lazy as _
from django.utils.translation import override

from weblate.accounts.tasks import send_mails
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.logger import LOGGER
from weblate.trans.models import Alert, Change, Translation
from weblate.utils.markdown import get_mention_users
from weblate.utils.site import get_site_domain, get_site_url
from weblate.utils.stats import prefetch_stats
from weblate.utils.version import USER_AGENT

FREQ_NONE = 0
FREQ_INSTANT = 1
FREQ_DAILY = 2
FREQ_WEEKLY = 3
FREQ_MONTHLY = 4

FREQ_CHOICES = (
    (FREQ_NONE, _("Do not notify")),
    (FREQ_INSTANT, _("Instant notification")),
    (FREQ_DAILY, _("Daily digest")),
    (FREQ_WEEKLY, _("Weekly digest")),
    (FREQ_MONTHLY, _("Monthly digest")),
)

SCOPE_ALL = 0
SCOPE_WATCHED = 10
SCOPE_ADMIN = 20
SCOPE_PROJECT = 30
SCOPE_COMPONENT = 40

SCOPE_CHOICES = (
    (SCOPE_ALL, "All"),
    (SCOPE_WATCHED, "Watched"),
    (SCOPE_ADMIN, "Administered"),
    (SCOPE_PROJECT, "Project"),
    (SCOPE_COMPONENT, "Component"),
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


class Notification:
    actions: Iterable[int] = ()
    verbose: str = ""
    template_name: str = ""
    digest_template: str = "digest"
    filter_languages: bool = False
    ignore_watched: bool = False
    required_attr: Optional[str] = None

    def __init__(self, outgoing, perm_cache=None):
        self.outgoing = outgoing
        self.subscription_cache = {}
        if perm_cache is not None:
            self.perm_cache = perm_cache
        else:
            self.perm_cache = {}

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
        return cls.__name__

    def filter_subscriptions(self, project, component, translation, users, lang_filter):
        from weblate.accounts.models import Subscription

        result = Subscription.objects.filter(notification=self.get_name())
        if users is not None:
            result = result.filter(user_id__in=users)
        query = Q(scope__in=(SCOPE_WATCHED, SCOPE_ADMIN, SCOPE_ALL))
        if component:
            query |= Q(component=component)
        if project:
            query |= Q(project=project)
        if lang_filter:
            result = result.filter(user__profile__languages=translation.language)
        return (
            result.filter(query)
            .order_by("user", "-scope")
            .prefetch_related("user__profile__watched")
        )

    def get_subscriptions(self, change, project, component, translation, users):
        lang_filter = self.need_language_filter(change)
        cache_key = (
            translation.language_id if lang_filter else lang_filter,
            component.pk if component else None,
            project.pk if project else None,
        )
        if users is not None:
            users.sort()
            cache_key += tuple(users)
        if cache_key not in self.subscription_cache:
            self.subscription_cache[cache_key] = self.filter_subscriptions(
                project, component, translation, users, lang_filter
            )
        return self.subscription_cache[cache_key]

    def has_required_attrs(self, change):
        try:
            return self.required_attr and getattr(change, self.required_attr) is None
        except ObjectDoesNotExist:
            return False

    def is_admin(self, user, project):
        if project is None:
            return False

        if project.pk not in self.perm_cache:
            self.perm_cache[project.pk] = User.objects.all_admins(project).values_list(
                "pk", flat=True
            )

        return user.pk in self.perm_cache[project.pk]

    def get_users(
        self,
        frequency,
        change=None,
        project=None,
        component=None,
        translation=None,
        users=None,
    ):
        if self.has_required_attrs(change):
            return
        if change is not None:
            project = change.project
            component = change.component
            translation = change.translation
        last_user = None
        subscriptions = self.get_subscriptions(
            change, project, component, translation, users
        )
        for subscription in subscriptions:
            user = subscription.user
            # Skip notification in some cases
            if (
                # Lower priority subscription for user
                (user == last_user)
                # Own change
                or (change is not None and user == change.user)
                # Inactive users
                or (not user.is_active)
                # Admin for not admin projects
                or (
                    subscription.scope == SCOPE_ADMIN
                    and not self.is_admin(user, project)
                )
                # Watched scope for not watched
                or (
                    subscription.scope == SCOPE_WATCHED
                    and not self.ignore_watched
                    and project is not None
                    and not user.profile.watches_project(project)
                )
            ):
                continue

            last_user = user
            if subscription.frequency != frequency:
                continue
            if frequency == FREQ_INSTANT and self.should_skip(user, change):
                continue
            last_user.current_subscription = subscription
            yield last_user

    def send(self, address, subject, body, headers):
        self.outgoing.append(
            {"address": address, "subject": subject, "body": body, "headers": headers}
        )

    def render_template(self, suffix, context, digest=False):
        """Render single mail template with given context."""
        template_name = "mail/{}{}".format(
            self.digest_template if digest else self.template_name, suffix
        )
        return render_to_string(template_name, context).strip()

    def get_context(
        self, change=None, subscription=None, extracontext=None, changes=None
    ):
        """Return context for rendering mail."""
        result = {
            "LANGUAGE_CODE": get_language(),
            "LANGUAGE_BIDI": get_language_bidi(),
            "current_site_url": get_site_url(),
            "site_title": settings.SITE_TITLE,
            "notification_name": self.verbose,
        }
        if changes is not None:
            result["changes"] = changes
        if subscription is not None:
            result["unsubscribe_nonce"] = TimestampSigner().sign(subscription.pk)
            result["user"] = subscription.user
        if extracontext:
            result.update(extracontext)
        if change:
            result["change"] = change
            # Extract change attributes
            attribs = (
                "unit",
                "translation",
                "component",
                "project",
                "comment",
                "suggestion",
                "announcement",
                "alert",
                "user",
                "target",
                "old",
                "details",
            )
            for attrib in attribs:
                result[attrib] = getattr(change, attrib)
        if result.get("translation"):
            result["translation_url"] = get_site_url(
                result["translation"].get_absolute_url()
            )
        return result

    def get_headers(self, context):
        headers = {
            "Auto-Submitted": "auto-generated",
            "X-AutoGenerated": "yes",
            "Precedence": "bulk",
            "X-Mailer": "Weblate" if settings.HIDE_VERSION else USER_AGENT,
            "X-Weblate-Notification": self.get_name(),
        }

        # Set From header to contain user full name
        user = context.get("user")
        if user:
            headers["From"] = formataddr(
                (context["user"].get_visible_name(), settings.DEFAULT_FROM_EMAIL)
            )

        # References for unit events
        references = None
        unit = context.get("unit")
        if unit:
            translation = unit.translation
            component = translation.component
            references = "{}/{}/{}/{}".format(
                component.project.slug,
                component.slug,
                translation.language.code,
                unit.id,
            )
        if references is not None:
            references = f"<{references}@{get_site_domain()}>"
            headers["In-Reply-To"] = references
            headers["References"] = references
        return headers

    def send_immediate(
        self, language, email, change, extracontext=None, subscription=None
    ):
        with override("en" if language is None else language):
            context = self.get_context(change, subscription, extracontext)
            subject = self.render_template("_subject.txt", context)
            context["subject"] = subject
            LOGGER.info(
                "sending notification %s on %s to %s",
                self.get_name(),
                context["component"],
                email,
            )
            self.send(
                email,
                subject,
                self.render_template(".html", context),
                self.get_headers(context),
            )

    def should_skip(self, user, change):
        return False

    def notify_immediate(self, change):
        for user in self.get_users(FREQ_INSTANT, change):
            if change.project is None or user.can_access_project(change.project):
                self.send_immediate(
                    user.profile.language,
                    user.email,
                    change,
                    subscription=user.current_subscription,
                )
                # Delete onetime subscription
                if user.current_subscription.onetime:
                    user.current_subscription.delete()

    def send_digest(self, language, email, changes, subscription=None):
        with override("en" if language is None else language):
            context = self.get_context(subscription=subscription, changes=changes)
            subject = self.render_template("_subject.txt", context, digest=True)
            context["subject"] = subject
            LOGGER.info(
                "sending digest notification %s on %d changes to %s",
                self.get_name(),
                len(changes),
                email,
            )
            self.send(
                email,
                subject,
                self.render_template(".html", context, digest=True),
                self.get_headers(context),
            )

    def notify_digest(self, frequency, changes):
        notifications = defaultdict(list)
        users = {}
        for change in changes:
            for user in self.get_users(frequency, change):
                if change.project is None or user.can_access_project(change.project):
                    notifications[user.pk].append(change)
                    users[user.pk] = user
        for user in users.values():
            self.send_digest(
                user.profile.language,
                user.email,
                notifications[user.pk],
                subscription=user.current_subscription,
            )

    def filter_changes(self, **kwargs):
        return Change.objects.filter(
            action__in=self.actions,
            timestamp__gte=timezone.now() - relativedelta(**kwargs),
        )

    def notify_daily(self):
        self.notify_digest(FREQ_DAILY, self.filter_changes(days=1))

    def notify_weekly(self):
        self.notify_digest(FREQ_WEEKLY, self.filter_changes(weeks=1))

    def notify_monthly(self):
        self.notify_digest(FREQ_MONTHLY, self.filter_changes(months=1))


@register_notification
class MergeFailureNotification(Notification):
    actions = (
        Change.ACTION_FAILED_MERGE,
        Change.ACTION_FAILED_REBASE,
        Change.ACTION_FAILED_PUSH,
    )
    # Translators: Notification name
    verbose = _("Repository failure")
    template_name = "repository_error"

    def __init__(self, outgoing, perm_cache=None):
        super().__init__(outgoing, perm_cache)
        self.fake_notify = None

    def should_skip(self, user, change):
        fake = copy(change)
        fake.action = Change.ACTION_ALERT
        fake.alert = Alert()
        if self.fake_notify is None:
            self.fake_notify = NewAlertNotificaton(None, self.perm_cache)
        return bool(
            list(self.fake_notify.get_users(FREQ_INSTANT, fake, users=[user.pk]))
        )


@register_notification
class RepositoryNotification(Notification):
    actions = (
        Change.ACTION_COMMIT,
        Change.ACTION_PUSH,
        Change.ACTION_RESET,
        Change.ACTION_REBASE,
        Change.ACTION_MERGE,
    )
    # Translators: Notification name
    verbose = _("Repository operation")
    template_name = "repository_operation"


@register_notification
class LockNotification(Notification):
    actions = (
        Change.ACTION_LOCK,
        Change.ACTION_UNLOCK,
    )
    # Translators: Notification name
    verbose = _("Component locking")
    template_name = "component_lock"


@register_notification
class LicenseNotification(Notification):
    actions = (Change.ACTION_LICENSE_CHANGE, Change.ACTION_AGREEMENT_CHANGE)
    # Translators: Notification name
    verbose = _("Changed license")
    template_name = "component_license"


@register_notification
class ParseErrorNotification(Notification):
    actions = (Change.ACTION_PARSE_ERROR,)
    # Translators: Notification name
    verbose = _("Parse error")
    template_name = "parse_error"


@register_notification
class NewStringNotificaton(Notification):
    actions = (Change.ACTION_NEW_STRING,)
    # Translators: Notification name
    verbose = _("New string")
    template_name = "new_string"
    filter_languages = True


@register_notification
class NewContributorNotificaton(Notification):
    actions = (Change.ACTION_NEW_CONTRIBUTOR,)
    # Translators: Notification name
    verbose = _("New contributor")
    template_name = "new_contributor"
    filter_languages = True


@register_notification
class NewSuggestionNotificaton(Notification):
    actions = (Change.ACTION_SUGGESTION,)
    # Translators: Notification name
    verbose = _("New suggestion")
    template_name = "new_suggestion"
    filter_languages = True
    required_attr = "suggestion"


@register_notification
class LastAuthorCommentNotificaton(Notification):
    actions = (Change.ACTION_COMMENT,)
    # Translators: Notification name
    verbose = _("Comment on own translation")
    template_name = "new_comment"
    ignore_watched = True
    required_attr = "comment"

    def __init__(self, outgoing, perm_cache=None):
        super().__init__(outgoing, perm_cache)
        self.fake_notify = None

    def should_skip(self, user, change):
        if self.fake_notify is None:
            self.fake_notify = MentionCommentNotificaton(None, self.perm_cache)
        return bool(
            list(self.fake_notify.get_users(FREQ_INSTANT, change, users=[user.pk]))
        )

    def get_users(
        self,
        frequency,
        change=None,
        project=None,
        component=None,
        translation=None,
        users=None,
    ):
        last_author = change.unit.get_last_content_change()[0]
        if last_author.is_anonymous:
            users = []
        else:
            users = [last_author.pk]
        return super().get_users(
            frequency, change, project, component, translation, users
        )


@register_notification
class MentionCommentNotificaton(Notification):
    actions = (Change.ACTION_COMMENT,)
    # Translators: Notification name
    verbose = _("Mentioned in comment")
    template_name = "new_comment"
    ignore_watched = True
    required_attr = "comment"

    def __init__(self, outgoing, perm_cache=None):
        super().__init__(outgoing, perm_cache)
        self.fake_notify = None

    def should_skip(self, user, change):
        if self.fake_notify is None:
            self.fake_notify = NewCommentNotificaton(None, self.perm_cache)
        return bool(
            list(self.fake_notify.get_users(FREQ_INSTANT, change, users=[user.pk]))
        )

    def get_users(
        self,
        frequency,
        change=None,
        project=None,
        component=None,
        translation=None,
        users=None,
    ):
        if self.has_required_attrs(change):
            return []
        return super().get_users(
            frequency,
            change,
            project,
            component,
            translation,
            list(
                get_mention_users(change.comment.comment).values_list("id", flat=True)
            ),
        )


@register_notification
class NewCommentNotificaton(Notification):
    actions = (Change.ACTION_COMMENT,)
    # Translators: Notification name
    verbose = _("New comment")
    template_name = "new_comment"
    filter_languages = True
    required_attr = "comment"

    def need_language_filter(self, change):
        return not change.comment.unit.is_source

    def notify_immediate(self, change):
        super().notify_immediate(change)

        # Notify upstream
        report_source_bugs = change.component.report_source_bugs
        if change.comment and change.comment.unit.is_source and report_source_bugs:
            self.send_immediate("en", report_source_bugs, change)


@register_notification
class ChangedStringNotificaton(Notification):
    actions = Change.ACTIONS_CONTENT
    # Translators: Notification name
    verbose = _("Changed string")
    template_name = "changed_translation"
    filter_languages = True


@register_notification
class TranslatedStringNotificaton(Notification):
    actions = (Change.ACTION_CHANGE, Change.ACTION_NEW)
    # Translators: Notification name
    verbose = _("Translated string")
    template_name = "translated_string"
    filter_languages = True


@register_notification
class ApprovedStringNotificaton(Notification):
    actions = (Change.ACTION_APPROVE,)
    # Translators: Notification name
    verbose = _("Approved string")
    template_name = "approved_string"
    filter_languages = True


@register_notification
class NewTranslationNotificaton(Notification):
    actions = (Change.ACTION_ADDED_LANGUAGE, Change.ACTION_REQUESTED_LANGUAGE)
    # Translators: Notification name
    verbose = _("New language")
    template_name = "new_language"

    def get_context(
        self, change=None, subscription=None, extracontext=None, changes=None
    ):
        context = super().get_context(change, subscription, extracontext, changes)
        if change:
            context["language"] = Language.objects.get(code=change.details["language"])
            context["was_added"] = change.action == Change.ACTION_ADDED_LANGUAGE
        return context


@register_notification
class NewComponentNotificaton(Notification):
    actions = (Change.ACTION_CREATE_COMPONENT,)
    # Translators: Notification name
    verbose = _("New translation component")
    template_name = "new_component"


@register_notification
class NewAnnouncementNotificaton(Notification):
    actions = (Change.ACTION_ANNOUNCEMENT,)
    # Translators: Notification name
    verbose = _("New announcement")
    template_name = "new_announcement"
    required_attr = "announcement"

    def should_skip(self, user, change):
        return not change.announcement.notify


@register_notification
class NewAlertNotificaton(Notification):
    actions = (Change.ACTION_ALERT,)
    # Translators: Notification name
    verbose = _("New alert")
    template_name = "new_alert"
    required_attr = "alert"

    def should_skip(self, user, change):
        if not change.component.linked_component or not change.alert.obj.link_wide:
            return False
        fake = copy(change)
        fake.component = change.component.linked_component
        fake.project = fake.component.project
        return bool(list(self.get_users(FREQ_INSTANT, fake, users=[user.pk])))


class SummaryNotification(Notification):
    filter_languages = True

    @staticmethod
    def get_freq_choices():
        return [x for x in FREQ_CHOICES if x[0] != FREQ_INSTANT]

    def notify_daily(self):
        self.notify_summary(FREQ_DAILY)

    def notify_weekly(self):
        self.notify_summary(FREQ_WEEKLY)

    def notify_monthly(self):
        self.notify_summary(FREQ_MONTHLY)

    def notify_summary(self, frequency):
        users = {}
        notifications = defaultdict(list)
        for translation in prefetch_stats(Translation.objects.prefetch()):
            count = self.get_count(translation)
            if not count:
                continue
            context = {
                "project": translation.component.project,
                "component": translation.component,
                "translation": translation,
            }
            current_users = self.get_users(frequency, **context)
            context["count"] = count
            for user in current_users:
                users[user.pk] = user
                notifications[user.pk].append(context)
        for userid, changes in notifications.items():
            user = users[userid]
            self.send_digest(
                user.profile.language,
                user.email,
                changes,
                subscription=user.current_subscription,
            )

    @staticmethod
    def get_count(translation):
        raise NotImplementedError()

    def get_context(
        self, change=None, subscription=None, extracontext=None, changes=None
    ):
        context = super().get_context(change, subscription, extracontext, changes)
        context["total_count"] = sum(change["count"] for change in changes)
        return context


@register_notification
class PendingSuggestionsNotification(SummaryNotification):
    # Translators: Notification name
    verbose = _("Pending suggestions")
    digest_template = "pending_suggestions"

    @staticmethod
    def get_count(translation):
        return translation.stats.suggestions


@register_notification
class ToDoStringsNotification(SummaryNotification):
    # Translators: Notification name
    verbose = _("Strings needing action")
    digest_template = "todo_strings"

    @staticmethod
    def get_count(translation):
        return translation.stats.todo


def get_notification_emails(
    language, recipients, notification, context=None, info=None
):
    """Render notification email."""
    context = context or {}
    headers = {}

    LOGGER.info(
        "sending notification %s on %s to %s", notification, info, ", ".join(recipients)
    )

    with override("en" if language is None else language):
        # Template name
        context["subject_template"] = f"mail/{notification}_subject.txt"
        context["LANGUAGE_CODE"] = get_language()
        context["LANGUAGE_BIDI"] = get_language_bidi()

        # Adjust context
        context["current_site_url"] = get_site_url()
        context["site_title"] = settings.SITE_TITLE

        # Render subject
        subject = render_to_string(context["subject_template"], context).strip()
        context["subject"] = subject

        # Render body
        body = render_to_string(f"mail/{notification}.html", context)

        # Define headers
        headers["Auto-Submitted"] = "auto-generated"
        headers["X-AutoGenerated"] = "yes"
        headers["Precedence"] = "bulk"
        headers["X-Mailer"] = "Weblate" if settings.HIDE_VERSION else USER_AGENT

        # Return the mail content
        return [
            {"subject": subject, "body": body, "address": address, "headers": headers}
            for address in recipients
        ]


def send_notification_email(
    language, recipients, notification, context=None, info=None
):
    """Render and sends notification email."""
    send_mails.delay(
        get_notification_emails(language, recipients, notification, context, info)
    )
