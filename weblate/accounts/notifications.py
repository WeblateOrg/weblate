# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections import defaultdict
from copy import copy
from email.utils import formataddr
from typing import TYPE_CHECKING, Any

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.signing import TimestampSigner
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import (
    get_language,
    get_language_bidi,
    gettext_lazy,
    override,
    pgettext_lazy,
)
from siphashc import siphash

from weblate.accounts.tasks import send_mails
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.logger import LOGGER
from weblate.trans.models import Alert, Change, Translation
from weblate.utils.markdown import get_mention_users
from weblate.utils.ratelimit import rate_limit
from weblate.utils.site import get_site_domain, get_site_url
from weblate.utils.stats import prefetch_stats
from weblate.utils.version import USER_AGENT

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django_stubs_ext import StrOrPromise

FREQ_NONE = 0
FREQ_INSTANT = 1
FREQ_DAILY = 2
FREQ_WEEKLY = 3
FREQ_MONTHLY = 4

FREQ_CHOICES = (
    (FREQ_NONE, gettext_lazy("No notification")),
    (FREQ_INSTANT, gettext_lazy("Instant notification")),
    (FREQ_DAILY, gettext_lazy("Daily digest")),
    (FREQ_WEEKLY, gettext_lazy("Weekly digest")),
    (FREQ_MONTHLY, gettext_lazy("Monthly digest")),
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

NOTIFICATIONS: list[type[Notification]] = []
NOTIFICATIONS_ACTIONS: dict[int, list[type[Notification]]] = {}


def get_email_headers(notification: str) -> dict[str, str]:
    return {
        "X-Mailer": "Weblate" if settings.HIDE_VERSION else USER_AGENT,
        "X-Weblate-Notification": notification,
    }


def register_notification(handler: type[Notification]):
    """Register notification handler."""
    NOTIFICATIONS.append(handler)
    for action in handler.actions:
        if action not in NOTIFICATIONS_ACTIONS:
            NOTIFICATIONS_ACTIONS[action] = []
        NOTIFICATIONS_ACTIONS[action].append(handler)
    return handler


def is_notificable_action(action: int) -> bool:
    return action in NOTIFICATIONS_ACTIONS


class Notification:
    actions: Iterable[int] = ()
    verbose: StrOrPromise = ""
    template_name: str = ""
    digest_template: str = "digest"
    filter_languages: bool = False
    ignore_watched: bool = False
    any_watched: bool = False
    required_attr: str | None = None
    skip_when_notify: list[Any] = []

    def __init__(self, outgoing, perm_cache=None) -> None:
        self.outgoing = outgoing
        self.subscription_cache = {}
        self.child_notify: list[Notification] | None = None
        if perm_cache is not None:
            self.perm_cache = perm_cache
        else:
            self.perm_cache = {}

    def get_language_filter(self, change, translation):
        if self.filter_languages:
            return translation.language
        return None

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
        query = Q(scope__in=(SCOPE_ADMIN, SCOPE_ALL))
        # Special case for site-wide announcements
        if self.any_watched and not project and not component:
            query |= Q(scope=SCOPE_WATCHED)
        if component:
            if not self.ignore_watched:
                query |= Q(scope=SCOPE_WATCHED) & Q(
                    user__profile__watched=component.project
                )
            query |= Q(component=component)
        if project:
            if not self.ignore_watched:
                query |= Q(scope=SCOPE_WATCHED) & Q(user__profile__watched=project)
            query |= Q(project=project)
        if lang_filter:
            result = result.filter(user__profile__languages=lang_filter)
        return (
            result.filter(query)
            .order_by("user", "-scope")
            .prefetch_related("user", "user__profile", "user__profile__watched")
        )

    def get_subscriptions(self, change, project, component, translation, users):
        lang_filter = self.get_language_filter(change, translation)
        cache_key = (
            lang_filter.id if lang_filter else None,
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

    def is_admin(self, user: User, project):
        if project is None:
            return False

        if project.pk not in self.perm_cache:
            self.perm_cache[project.pk] = set(
                User.objects.all_admins(project).values_list("pk", flat=True)
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
                or user.is_bot
                # Admin for not admin projects
                or (
                    subscription.scope == SCOPE_ADMIN
                    and not self.is_admin(user, project)
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

    def send(self, address, subject, body, headers) -> None:
        encoded_email = siphash("Weblate notifier", address)
        if rate_limit(f"notify:rate:{encoded_email}", 1000, 86400):
            LOGGER.info(
                "discarding notification %s to %s after sending too many",
                self.get_name(),
                address,
            )
        else:
            self.outgoing.append(
                {
                    "address": address,
                    "subject": subject,
                    "body": body,
                    "headers": headers,
                }
            )

    def render_template(self, suffix, context, digest=False):
        """Render single mail template with given context."""
        base_name = self.digest_template if digest else self.template_name
        template_name = f"mail/{base_name}{suffix}"
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
            result["unsubscribe_url"] = "{}?i={}".format(
                reverse("unsubscribe"), TimestampSigner().sign(f"{subscription.pk}")
            )
            result["subscription_user"] = subscription.user
        else:
            result["subscription_user"] = None
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
        headers = get_email_headers(self.get_name())

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
            references = f"{component.project.slug}/{component.slug}/{translation.language.code}/{unit.id}"
        if references is not None:
            references = f"<{references}@{get_site_domain()}>"
            headers["In-Reply-To"] = references
            headers["References"] = references
        if unsubscribe_url := context.get("unsubscribe_url"):
            headers["List-Unsubscribe"] = unsubscribe_url
        return headers

    def send_immediate(
        self, language, email, change, extracontext=None, subscription=None
    ) -> None:
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

    def _convert_change_skip(self, change):
        return change

    def should_skip(self, user: User, change):
        if not self.skip_when_notify:
            return False
        if self.child_notify is None:
            self.child_notify = [
                notify_class(None, self.perm_cache)
                for notify_class in self.skip_when_notify
            ]
        converted_change = self._convert_change_skip(change)
        return any(
            list(
                child_notify.get_users(FREQ_INSTANT, converted_change, users=[user.pk])
            )
            for child_notify in self.child_notify
        )

    def notify_immediate(self, change) -> None:
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

    def send_digest(self, language, email, changes, subscription=None) -> None:
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

    def notify_digest(self, frequency, changes) -> None:
        notifications = defaultdict(list)
        users = {}
        for change in changes:
            for user in self.get_users(frequency, change):
                if change.project is None or user.can_access_project(change.project):
                    notifications[user.pk].append(change)
                    users[user.pk] = user
        for user in users.values():
            changes = notifications[user.pk]
            parts = []
            while len(changes) > 120:
                parts.append(changes[:100])
                changes = changes[100:]
            if changes:
                parts.append(changes)

            for part in parts:
                self.send_digest(
                    user.profile.language,
                    user.email,
                    part,
                    subscription=user.current_subscription,
                )

    def filter_changes(self, **kwargs):
        return Change.objects.filter(
            action__in=self.actions,
            timestamp__gte=timezone.now() - relativedelta(**kwargs),
        )

    def notify_daily(self) -> None:
        self.notify_digest(FREQ_DAILY, self.filter_changes(days=1))

    def notify_weekly(self) -> None:
        self.notify_digest(FREQ_WEEKLY, self.filter_changes(weeks=1))

    def notify_monthly(self) -> None:
        self.notify_digest(FREQ_MONTHLY, self.filter_changes(months=1))


@register_notification
class RepositoryNotification(Notification):
    actions = (
        Change.ACTION_COMMIT,
        Change.ACTION_PUSH,
        Change.ACTION_RESET,
        Change.ACTION_REBASE,
        Change.ACTION_MERGE,
    )
    verbose = pgettext_lazy(
        "Notification name", "Operation was performed in the repository"
    )
    template_name = "repository_operation"


@register_notification
class LockNotification(Notification):
    actions = (
        Change.ACTION_LOCK,
        Change.ACTION_UNLOCK,
    )
    verbose = pgettext_lazy("Notification name", "Component was locked or unlocked")
    template_name = "component_lock"


@register_notification
class LicenseNotification(Notification):
    actions = (Change.ACTION_LICENSE_CHANGE, Change.ACTION_AGREEMENT_CHANGE)
    verbose = pgettext_lazy("Notification name", "License was changed")
    template_name = "component_license"


@register_notification
class ParseErrorNotification(Notification):
    actions = (Change.ACTION_PARSE_ERROR,)
    verbose = pgettext_lazy("Notification name", "Parse error occurred")
    template_name = "parse_error"

    def get_context(
        self, change=None, subscription=None, extracontext=None, changes=None
    ):
        context = super().get_context(change, subscription, extracontext, changes)
        if change:
            context["details"]["filelink"] = change.component.get_repoweb_link(
                change.details.get("filename"), "1", user=context["user"]
            )
        return context


@register_notification
class NewStringNotificaton(Notification):
    actions = (
        Change.ACTION_NEW_UNIT,
        Change.ACTION_NEW_UNIT_REPO,
        Change.ACTION_NEW_UNIT_UPLOAD,
        Change.ACTION_MARKED_EDIT,
        Change.ACTION_SOURCE_CHANGE,
    )
    verbose = pgettext_lazy("Notification name", "String is available for translation")
    template_name = "new_string"
    filter_languages = True
    required_attr = "unit"


@register_notification
class NewContributorNotificaton(Notification):
    actions = (Change.ACTION_NEW_CONTRIBUTOR,)
    verbose = pgettext_lazy(
        "Notification name", "Contributor made their first translation"
    )
    template_name = "new_contributor"
    filter_languages = True


@register_notification
class NewSuggestionNotificaton(Notification):
    actions = (Change.ACTION_SUGGESTION,)
    verbose = pgettext_lazy("Notification name", "Suggestion was added")
    template_name = "new_suggestion"
    filter_languages = True
    required_attr = "suggestion"


@register_notification
class LanguageTranslatedNotificaton(Notification):
    actions = (Change.ACTION_COMPLETE,)
    verbose = pgettext_lazy("Notification name", "Language was translated")
    template_name = "translated_language"
    required_attr = "translation"


@register_notification
class ComponentTranslatedNotificaton(Notification):
    actions = (Change.ACTION_COMPLETED_COMPONENT,)
    verbose = pgettext_lazy("Notification name", "Component was translated")
    template_name = "translated_component"
    required_attr = "component"


@register_notification
class NewCommentNotificaton(Notification):
    actions = (Change.ACTION_COMMENT,)
    verbose = pgettext_lazy("Notification name", "Comment was added")
    template_name = "new_comment"
    filter_languages = True
    required_attr = "comment"

    def get_language_filter(self, change, translation):
        if not change.comment.unit.is_source:
            return translation.language
        return None

    def notify_immediate(self, change) -> None:
        super().notify_immediate(change)

        # Notify upstream
        report_source_bugs = change.component.report_source_bugs
        if change.comment and change.comment.unit.is_source and report_source_bugs:
            self.send_immediate("en", report_source_bugs, change)


@register_notification
class MentionCommentNotificaton(Notification):
    actions = (Change.ACTION_COMMENT,)
    verbose = pgettext_lazy("Notification name", "You were mentioned in a comment")
    template_name = "new_comment"
    ignore_watched = True
    required_attr = "comment"
    skip_when_notify = [NewCommentNotificaton]

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
class LastAuthorCommentNotificaton(Notification):
    actions = (Change.ACTION_COMMENT,)
    verbose = pgettext_lazy("Notification name", "Your translation received a comment")
    template_name = "new_comment"
    ignore_watched = True
    required_attr = "comment"
    skip_when_notify = [MentionCommentNotificaton]

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
        users = [] if last_author.is_anonymous else [last_author.pk]
        return super().get_users(
            frequency, change, project, component, translation, users
        )


@register_notification
class TranslatedStringNotificaton(Notification):
    actions = (Change.ACTION_CHANGE, Change.ACTION_NEW, Change.ACTION_ACCEPT)
    verbose = pgettext_lazy("Notification name", "String was edited by user")
    template_name = "translated_string"
    filter_languages = True


@register_notification
class ApprovedStringNotificaton(Notification):
    actions = (Change.ACTION_APPROVE,)
    verbose = pgettext_lazy("Notification name", "String was approved")
    template_name = "approved_string"
    filter_languages = True


@register_notification
class ChangedStringNotificaton(Notification):
    actions = Change.ACTIONS_CONTENT
    verbose = pgettext_lazy("Notification name", "String was changed")
    template_name = "changed_translation"
    filter_languages = True
    skip_when_notify = [TranslatedStringNotificaton, ApprovedStringNotificaton]


@register_notification
class NewTranslationNotificaton(Notification):
    actions = (Change.ACTION_ADDED_LANGUAGE, Change.ACTION_REQUESTED_LANGUAGE)
    verbose = pgettext_lazy("Notification name", "New language was added or requested")
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
    verbose = pgettext_lazy(
        "Notification name", "New translation component was created"
    )
    template_name = "new_component"


@register_notification
class NewAnnouncementNotificaton(Notification):
    actions = (Change.ACTION_ANNOUNCEMENT,)
    verbose = pgettext_lazy("Notification name", "Announcement was published")
    template_name = "new_announcement"
    required_attr = "announcement"
    any_watched: bool = True

    def should_skip(self, user: User, change) -> bool:
        return not change.announcement.notify

    def get_language_filter(self, change, translation):
        return change.announcement.language


@register_notification
class NewAlertNotificaton(Notification):
    actions = (Change.ACTION_ALERT,)
    verbose = pgettext_lazy("Notification name", "New alert emerged in a component")
    template_name = "new_alert"
    required_attr = "alert"

    def should_skip(self, user: User, change):
        if change.alert.obj.link_wide:
            # Notify for main component
            if not change.component.linked_component:
                return False
            # Notify only for others only when user will not get main.
            # This handles component level subscriptions.
            fake = copy(change)
            fake.component = change.component.linked_component
            fake.project = fake.component.project
            return bool(list(self.get_users(FREQ_INSTANT, fake, users=[user.pk])))
        if change.alert.obj.project_wide:
            first_component = change.component.project.component_set.order_by("id")[0]
            # Notify for the first component
            if change.component.id == first_component.id:
                return True
            # Notify only for others only when user will not get first.
            # This handles component level subscriptions.
            fake = copy(change)
            fake.component = first_component
            fake.project = fake.component.project
            return bool(list(self.get_users(FREQ_INSTANT, fake, users=[user.pk])))
        return False


@register_notification
class MergeFailureNotification(Notification):
    actions = (
        Change.ACTION_FAILED_MERGE,
        Change.ACTION_FAILED_REBASE,
        Change.ACTION_FAILED_PUSH,
    )
    verbose = pgettext_lazy("Notification name", "Repository operation failed")
    template_name = "repository_error"
    skip_when_notify = [NewAlertNotificaton]

    def _convert_change_skip(self, change):
        fake = copy(change)
        fake.action = Change.ACTION_ALERT
        fake.alert = Alert(name="MergeFailure", details={"error": ""})
        return fake


class SummaryNotification(Notification):
    filter_languages = True

    @staticmethod
    def get_freq_choices():
        return [x for x in FREQ_CHOICES if x[0] != FREQ_INSTANT]

    def notify_daily(self) -> None:
        self.notify_summary(FREQ_DAILY)

    def notify_weekly(self) -> None:
        self.notify_summary(FREQ_WEEKLY)

    def notify_monthly(self) -> None:
        self.notify_summary(FREQ_MONTHLY)

    def notify_summary(self, frequency) -> None:
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
    def get_count(translation) -> int:
        raise NotImplementedError

    def get_context(
        self, change=None, subscription=None, extracontext=None, changes=None
    ):
        context = super().get_context(change, subscription, extracontext, changes)
        context["total_count"] = sum(change["count"] for change in changes)
        return context


@register_notification
class PendingSuggestionsNotification(SummaryNotification):
    verbose = pgettext_lazy("Notification name", "Pending suggestions exist")
    digest_template = "pending_suggestions"

    @staticmethod
    def get_count(translation) -> int:
        return translation.stats.suggestions


@register_notification
class ToDoStringsNotification(SummaryNotification):
    verbose = pgettext_lazy("Notification name", "Unfinished strings exist")
    digest_template = "todo_strings"

    @staticmethod
    def get_count(translation) -> int:
        return translation.stats.todo


def get_notification_emails(
    language, recipients, notification, context=None, info=None
):
    """Render notification email."""
    context = context or {}

    # Define headers
    headers = get_email_headers(notification)

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

        # Return the mail content
        return [
            {"subject": subject, "body": body, "address": address, "headers": headers}
            for address in recipients
        ]


def send_notification_email(
    language, recipients, notification, context=None, info=None
) -> None:
    """Render and sends notification email."""
    send_mails.delay(
        get_notification_emails(language, recipients, notification, context, info)
    )
