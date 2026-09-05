# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections import OrderedDict, defaultdict
from copy import copy
from datetime import timedelta
from email.utils import formataddr
from heapq import heappush, heapreplace
from itertools import batched
from operator import itemgetter
from typing import TYPE_CHECKING, Any, ClassVar, cast
from urllib.parse import urlencode
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, IntegerChoices, Q
from django.db.models.functions import Coalesce
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import (
    get_language,
    get_language_bidi,
    gettext_lazy,
    override,
    pgettext_lazy,
)

from weblate.accounts.tasks import EMAIL_BATCH_SIZE, queue_mails
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.logger import LOGGER
from weblate.trans.actions import ActionEvents
from weblate.trans.alerts.base import AlertSeverity
from weblate.trans.models import (
    Alert,
    Change,
    Comment,
    Suggestion,
    Translation,
)
from weblate.utils.errors import report_error
from weblate.utils.markdown import get_mention_users
from weblate.utils.ratelimit import rate_limit_notify
from weblate.utils.site import get_site_domain, get_site_url
from weblate.utils.stats import iter_prefetch_stats, prefetch_stats
from weblate.utils.version import USER_AGENT
from weblate.utils.version_display import VERSION_DISPLAY_HIDE

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from django.db.models import QuerySet
    from django_stubs_ext import StrOrPromise

    from weblate.accounts.models import Subscription
    from weblate.accounts.tasks import OutgoingEmail
    from weblate.trans.models import (
        Announcement,
        Component,
        Project,
        Unit,
    )


class NotificationFrequency(IntegerChoices):
    FREQ_NONE = 0, gettext_lazy("No notification")
    FREQ_INSTANT = 1, gettext_lazy("Instant notification")
    FREQ_DAILY = 2, gettext_lazy("Daily digest")
    FREQ_WEEKLY = 3, gettext_lazy("Weekly digest")
    FREQ_MONTHLY = 4, gettext_lazy("Monthly digest")


class NotificationScope(IntegerChoices):
    SCOPE_ALL = 0, gettext_lazy("All")
    SCOPE_WATCHED = 10, gettext_lazy("Watched")
    SCOPE_ADMIN = 20, gettext_lazy("Administered")
    SCOPE_PROJECT = 30, gettext_lazy("Project")
    SCOPE_COMPONENT = 40, gettext_lazy("Component")


NOTIFICATIONS: list[type[Notification]] = []
NOTIFICATIONS_ACTIONS: dict[int, list[type[Notification]]] = {}
RECIPIENT_USERNAME_HEADER = "X-Weblate-Recipient-Username"
DIGEST_MAX_ITEMS = 100
DIGEST_USER_BATCH_SIZE = 50
NOTIFICATION_QUERY_CHUNK_SIZE = 200
SUBSCRIPTION_CACHE_SIZE = 16
_UNSCOPED = object()


def get_email_headers(notification: str) -> dict[str, str]:
    return {
        "X-Mailer": "Weblate"
        if settings.VERSION_DISPLAY == VERSION_DISPLAY_HIDE
        else USER_AGENT,
        "X-Weblate-Notification": notification,
        "Message-ID": f"{uuid4()}@{get_site_domain()}",
    }


def add_recipient_headers(headers: dict[str, str], user: User | None) -> None:
    if user is not None:
        headers[RECIPIENT_USERNAME_HEADER] = user.username


def register_notification(handler: type[Notification]) -> type[Notification]:
    """Register notification handler."""
    NOTIFICATIONS.append(handler)
    for action in handler.actions:
        if action not in NOTIFICATIONS_ACTIONS:
            NOTIFICATIONS_ACTIONS[action] = []
        NOTIFICATIONS_ACTIONS[action].append(handler)
    return handler


def is_notificable_action(action: int) -> bool:
    return action in NOTIFICATIONS_ACTIONS


def dispatch_changes_notifications(changes: Iterable[Change]) -> None:
    # ruff: ignore[import-outside-top-level]
    from weblate.accounts.tasks import notify_changes

    notifiable: list[int] = [
        change.pk for change in changes if is_notificable_action(change.action)
    ]
    if notifiable:
        notify_changes.delay_on_commit(notifiable)


class Notification:
    actions: Iterable[int] = ()
    verbose: StrOrPromise = ""
    verbose_plural: StrOrPromise = ""
    template_name: str = ""
    digest_template: str = "digest"
    filter_languages: bool = False
    ignore_watched: bool = False
    any_watched: bool = False
    required_attr: str | None = None
    batch_recipients = True
    debug_conditions: ClassVar[tuple[StrOrPromise, ...]] = ()
    skip_when_notify: ClassVar[set[type[Notification]]] = set()

    def __init__(
        self,
        outgoing: list[OutgoingEmail],
        *,
        user_ids: list[int] | None = None,
    ) -> None:
        self.outgoing: list[OutgoingEmail] = outgoing
        self.user_ids = user_ids
        self.subscription_cache: OrderedDict[int | None, list[Subscription]] = (
            OrderedDict()
        )
        self.child_notify: list[Notification] | None = None

    def get_language_filter(
        self, change: Change | None, translation: Translation | None
    ) -> Language | None:
        if self.filter_languages and translation is not None:
            return translation.language
        return None

    @classmethod
    def get_freq_choices(cls) -> list[tuple[int, StrOrPromise]]:
        return NotificationFrequency.choices

    @classmethod
    def get_choice(cls) -> tuple[str, StrOrPromise]:
        return (cls.get_name(), cls.verbose)

    @classmethod
    def get_name(cls) -> str:
        return cls.__name__

    @classmethod
    def get_periodic_actions(cls) -> Iterable[int]:
        return cls.actions

    def filter_subscriptions(self, project: Project | None) -> list[Subscription]:
        # ruff: ignore[import-outside-top-level]
        from weblate.accounts.models import Subscription

        result = Subscription.objects.filter(notification=self.get_name())
        if self.user_ids is not None:
            result = result.filter(user_id__in=self.user_ids)
        scopes: set[NotificationScope] = {NotificationScope.SCOPE_ALL}
        # special case for site-wide announcements
        if self.any_watched and not project:
            scopes.add(NotificationScope.SCOPE_WATCHED)

        query = Q(scope__in=scopes)

        if project:
            if not self.ignore_watched:
                query |= Q(scope=NotificationScope.SCOPE_WATCHED) & Q(
                    user__profile__watched=project
                )
            # Direct subscriptions
            query |= Q(project=project) | Q(component__project=project)
            # Admins for current project
            query |= Q(scope=NotificationScope.SCOPE_ADMIN) & Q(
                user__in=User.objects.all_admins(project)
            )
        return list(
            result.filter(query)
            # Inactive users and bots
            .filter(Q(user__is_bot=False) & Q(user__is_active=True))
            .order_by("user", "-scope")
            .select_related("user", "user__profile")
            .prefetch_related("user__profile__languages")
        )

    def get_scope_subscriptions(
        self,
        change: Change | None,
        project: Project | None,
        component: Component | None,
        translation: Translation | None,
        users: list[int] | None,
    ) -> Iterable[Subscription]:
        """Match account, scope, and language in descending subscription priority."""
        lang_filter: Language | None = self.get_language_filter(change, translation)
        cache_key: int | None = project.pk if project else None
        try:
            subscriptions = self.subscription_cache.pop(cache_key)
        except KeyError:
            subscriptions = self.filter_subscriptions(project)
            if len(self.subscription_cache) >= SUBSCRIPTION_CACHE_SIZE:
                self.subscription_cache.popitem(last=False)
        self.subscription_cache[cache_key] = subscriptions
        for subscription in subscriptions:
            # Users filter
            if users is not None and subscription.user_id not in users:
                continue

            # Languages filter
            if (
                lang_filter
                and lang_filter not in subscription.user.profile.languages.all()
            ):
                continue

            # Component filter
            if subscription.component_id is not None and (
                component is None or subscription.component_id != component.id
            ):
                continue

            yield subscription

    def get_subscriptions(
        self,
        change: Change | None,
        project: Project | None,
        component: Component | None,
        translation: Translation | None,
        users: list[int] | None,
    ) -> Iterable[Subscription]:
        return self.get_scope_subscriptions(
            change, project, component, translation, users
        )

    def missing_required_attrs(self, change: Change | None) -> bool:
        if not self.required_attr:
            return False
        if change is None:
            return True
        try:
            return getattr(change, self.required_attr) is None
        except ObjectDoesNotExist:
            return False

    def can_access_target(
        self,
        user: User,
        project: Project | None,
        component: Component | None,
    ) -> bool:
        if component is not None:
            return user.can_access_component(component)
        return project is None or user.can_access_project(project)

    def get_users(
        self,
        frequency: NotificationFrequency,
        change: Change | None = None,
        project: Project | None = None,
        component: Component | None = None,
        translation: Translation | None = None,
        users: list[int] | None = None,
    ) -> Iterable[User]:
        if self.missing_required_attrs(change):
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
            ):
                continue

            last_user = user
            if subscription.frequency != frequency:
                continue
            if not self.can_access_target(user, project, component):
                continue
            if frequency == NotificationFrequency.FREQ_INSTANT and (
                change is None or self.should_skip(user, change)
            ):
                continue
            last_user.current_subscription = subscription
            yield last_user

    def send(
        self, address: str, subject: str, body: str, headers: dict[str, str]
    ) -> None:
        is_blocked, reason = rate_limit_notify(address)

        if is_blocked:
            LOGGER.info(
                "discarding notification %s to %s due to rate limit: %s",
                self.get_name(),
                address,
                reason,
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
            # Avoid building huge queue of notifications in memory
            if len(self.outgoing) >= EMAIL_BATCH_SIZE:
                queue_mails(self.outgoing)
                self.outgoing.clear()

    def render_template(self, suffix: str, context: dict, digest: bool = False) -> str:
        """Render single mail template with given context."""
        base_name = self.digest_template if digest else self.template_name
        template_name = f"mail/{base_name}{suffix}"
        return render_to_string(template_name, context).strip()

    def get_notification_name(self, num_changes: int) -> StrOrPromise:
        # We don't use proper ngettext here to simplify the code and
        # in most languages the specific plural rules won't apply for
        # subject rendering.
        if num_changes > 1:
            return self.verbose_plural
        return self.verbose

    def get_context(
        self,
        change: Change | None = None,
        subscription: Subscription | None = None,
        extracontext: dict | None = None,
        *,
        changes: QuerySet[Change] | list[Change] | list[dict[str, Any]] | None = None,
        summaries: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return context for rendering mail."""
        result = {
            "LANGUAGE_CODE": get_language(),
            "LANGUAGE_BIDI": get_language_bidi(),
            "current_site_url": get_site_url(),
            "site_title": settings.SITE_TITLE,
            "notification_name": self.get_notification_name(
                len(changes) if changes is not None else 0
            ),
        }
        if changes is not None:
            result["changes"] = changes
        elif summaries is not None:
            result["changes"] = summaries
        if subscription is not None:
            result["unsubscribe_url"] = get_site_url(subscription.get_unsubscribe_url())
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
            if change.translation:
                result["translation_url"] = get_site_url(
                    change.translation.get_absolute_url()
                )
        return result

    def get_headers(self, context: dict[str, Any]) -> dict[str, str]:
        headers = get_email_headers(self.get_name())
        add_recipient_headers(headers, context.get("subscription_user"))

        # Set From header to contain user full name
        if user := context.get("user"):
            from_name = user.get_visible_name()
        else:
            from_name = settings.SITE_TITLE
        headers["From"] = formataddr((from_name, settings.DEFAULT_FROM_EMAIL))

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
        self,
        language: str | None,
        email: str,
        change: Change,
        extracontext: dict | None = None,
        subscription: Subscription | None = None,
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

    def _convert_change_skip(self, change: Change) -> Change:
        return change

    def should_skip(self, user: User, change: Change) -> bool:
        if not self.skip_when_notify:
            return False
        if self.child_notify is None:
            self.child_notify = [
                notify_class([]) for notify_class in self.skip_when_notify
            ]
        converted_change = self._convert_change_skip(change)
        return any(
            list(
                child_notify.get_users(
                    NotificationFrequency.FREQ_INSTANT,
                    converted_change,
                    users=[user.pk],
                )
            )
            for child_notify in self.child_notify
        )

    def notify_immediate(self, change: Change) -> None:
        for user in self.get_users(NotificationFrequency.FREQ_INSTANT, change):
            if change.project is None or user.can_access_project(change.project):
                self.send_immediate(
                    user.profile.language,
                    user.email,
                    change,
                    subscription=user.current_subscription,
                )
                # Delete onetime subscription
                current_subscription = cast("Subscription", user.current_subscription)
                if current_subscription.onetime:
                    current_subscription.delete()

    def send_digest(
        self,
        language: str,
        email: str,
        *,
        changes: QuerySet[Change] | list[Change] | list[dict[str, Any]] | None = None,
        summaries: list[dict[str, Any]] | None = None,
        subscription: Subscription | None = None,
        overlimit: bool = False,
        extracontext: dict[str, Any] | None = None,
    ) -> None:
        with override("en" if language is None else language):
            digest_context = extracontext.copy() if extracontext else {}
            digest_context["overlimit"] = overlimit
            context = self.get_context(
                subscription=subscription,
                changes=changes,
                summaries=summaries,
                extracontext=digest_context,
            )
            subject = self.render_template("_subject.txt", context, digest=True)
            context["subject"] = subject
            length = 0
            if changes:
                length = len(changes)
            elif summaries:
                length = len(summaries)
            try:
                body = self.render_template(".html", context, digest=True)
            except Exception:
                report_error("Could not render changes", level="critical")
                LOGGER.exception(
                    "sending digest notification %s on %d changes to %s failed",
                    self.get_name(),
                    length,
                    email,
                )
            else:
                LOGGER.info(
                    "sending digest notification %s on %d changes to %s",
                    self.get_name(),
                    length,
                    email,
                )
                self.send(email, subject, body, self.get_headers(context))

    def notify_digest(
        self,
        frequency: NotificationFrequency,
        changes: QuerySet[Change],
    ) -> None:
        notifications: dict[int, list[tuple[datetime, int, Change]]] = defaultdict(list)
        users = {}
        overlimit: set[int] = set()
        last_project_id: int | object | None = _UNSCOPED
        ordered_changes = changes.order_by("project_id", "-timestamp", "-pk")
        for change in ordered_changes.iterator(
            chunk_size=NOTIFICATION_QUERY_CHUNK_SIZE
        ):
            if change.project_id != last_project_id:
                self.subscription_cache.clear()
                last_project_id = change.project_id
            change.fill_in_prefetched()
            for user in self.get_users(frequency, change):
                if change.project is None or user.can_access_project(change.project):
                    users[user.pk] = user
                    user_notifications = notifications[user.pk]
                    entry = (change.timestamp, change.pk, change)
                    if len(user_notifications) < DIGEST_MAX_ITEMS:
                        heappush(user_notifications, entry)
                    else:
                        overlimit.add(user.pk)
                        if (entry[0], entry[1]) > (
                            user_notifications[0][0],
                            user_notifications[0][1],
                        ):
                            heapreplace(user_notifications, entry)
        for user in users.values():
            user_changes = [
                entry[2]
                for entry in sorted(
                    notifications[user.pk],
                    key=itemgetter(0, 1),
                    reverse=True,
                )
            ]
            self.send_digest(
                user.profile.language,
                user.email,
                changes=user_changes,
                subscription=user.current_subscription,
                overlimit=user.pk in overlimit,
            )

    def filter_changes(
        self,
        *,
        since: datetime,
        until: datetime,
        project: Project | object | None = _UNSCOPED,
    ) -> QuerySet[Change]:
        changes = Change.objects.filter(
            action__in=self.actions,
            timestamp__gte=since,
            timestamp__lt=until,
        )
        if project is not _UNSCOPED:
            changes = changes.filter(project=cast("Project | None", project))
        return changes.order_by("-timestamp", "-pk").prefetch_for_render()

    def notify_periodic(
        self,
        frequency: NotificationFrequency,
        *,
        since: datetime,
        until: datetime,
        project: Project | None,
    ) -> None:
        self.notify_digest(
            frequency,
            self.filter_changes(since=since, until=until, project=project),
        )

    def get_periodic_projects(
        self,
        frequency: NotificationFrequency,
        *,
        since: datetime,
        until: datetime,
    ) -> QuerySet[Project]:
        # ruff: ignore[import-outside-top-level]
        from weblate.accounts.tasks import get_digest_projects

        return get_digest_projects(
            type(self),
            frequency,
            since=since,
            until=until,
            user_ids=self.user_ids,
        )

    def notify_periodic_batch(
        self,
        frequency: NotificationFrequency,
        *,
        since: datetime,
        until: datetime,
    ) -> None:
        projects = self.get_periodic_projects(frequency, since=since, until=until)
        changes = self.filter_changes(since=since, until=until).filter(
            Q(project__in=projects) | Q(project__isnull=True)
        )
        self.notify_digest(frequency, changes)

    def notify_for_period(
        self,
        frequency: NotificationFrequency,
        period: relativedelta,
    ) -> None:
        from weblate.accounts.models import (  # ruff: ignore[import-outside-top-level]
            Subscription,
        )

        until = timezone.now()
        since = until - period
        if not self.batch_recipients:
            self.user_ids = None
            self.notify_periodic_batch(frequency, since=since, until=until)
            return

        user_ids = (
            Subscription.objects.filter(
                notification=self.get_name(),
                frequency=frequency,
                user__is_active=True,
                user__is_bot=False,
            )
            .order_by("user_id")
            .values_list("user_id", flat=True)
            .distinct()
        )
        for user_batch in batched(
            user_ids.iterator(chunk_size=NOTIFICATION_QUERY_CHUNK_SIZE),
            DIGEST_USER_BATCH_SIZE,
        ):
            self.user_ids = list(user_batch)
            self.subscription_cache.clear()
            self.notify_periodic_batch(frequency, since=since, until=until)

    def notify_daily(self) -> None:
        self.notify_for_period(NotificationFrequency.FREQ_DAILY, relativedelta(days=1))

    def notify_weekly(self) -> None:
        self.notify_for_period(
            NotificationFrequency.FREQ_WEEKLY, relativedelta(weeks=1)
        )

    def notify_monthly(self) -> None:
        self.notify_for_period(
            NotificationFrequency.FREQ_MONTHLY, relativedelta(months=1)
        )


@register_notification
class RepositoryNotification(Notification):
    actions = (
        ActionEvents.COMMIT,
        ActionEvents.PUSH,
        ActionEvents.RESET,
        ActionEvents.REBASE,
        ActionEvents.MERGE,
    )
    verbose = pgettext_lazy(
        "Notification name", "Operation was performed in the repository"
    )
    verbose_plural = pgettext_lazy(
        "Notification name", "Operations were performed in the repository"
    )
    template_name = "repository_operation"


@register_notification
class LockNotification(Notification):
    actions = (
        ActionEvents.LOCK,
        ActionEvents.UNLOCK,
    )
    verbose = pgettext_lazy("Notification name", "Component was locked or unlocked")
    verbose_plural = pgettext_lazy(
        "Notification name", "Components were locked or unlocked"
    )
    template_name = "component_lock"


@register_notification
class LicenseNotification(Notification):
    actions = (
        ActionEvents.LICENSE_CHANGE,
        ActionEvents.AGREEMENT_CHANGE,
    )
    verbose = pgettext_lazy("Notification name", "License was changed")
    template_name = "component_license"


@register_notification
class ParseErrorNotification(Notification):
    actions = (ActionEvents.PARSE_ERROR,)
    verbose = pgettext_lazy("Notification name", "Parse error occurred")
    verbose_plural = pgettext_lazy("Notification name", "Parse errors occurred")
    template_name = "parse_error"

    def get_context(
        self,
        change: Change | None = None,
        subscription: Subscription | None = None,
        extracontext: dict | None = None,
        *,
        changes: QuerySet[Change] | list[Change] | list[dict[str, Any]] | None = None,
        summaries: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        context = super().get_context(
            change, subscription, extracontext, changes=changes, summaries=summaries
        )
        if change and change.component:
            context["details"]["filelink"] = change.component.get_repoweb_link(
                change.details.get("filename"), "1", user=context["user"]
            )
        return context


@register_notification
class NewStringNotificaton(Notification):
    actions = (
        ActionEvents.NEW_UNIT,
        ActionEvents.NEW_UNIT_REPO,
        ActionEvents.NEW_UNIT_UPLOAD,
        ActionEvents.MARKED_EDIT,
        ActionEvents.SOURCE_CHANGE,
    )
    verbose = pgettext_lazy("Notification name", "String is available for translation")
    verbose_plural = pgettext_lazy(
        "Notification name", "Strings are available for translation"
    )
    template_name = "new_string"
    filter_languages = True
    required_attr = "unit"


@register_notification
class TranslationActivitySummaryNotification(Notification):
    verbose_plural = verbose = pgettext_lazy(
        "Notification name", "Translation activity summary"
    )
    filter_languages = True

    activity_fields: ClassVar[tuple[str, ...]] = (
        "added",
        "updated",
        "translated",
        "approved",
        "needs_editing",
    )
    activity_actions: ClassVar[dict[str, tuple[ActionEvents, ...]]] = {
        "added": (
            ActionEvents.NEW_UNIT,
            ActionEvents.NEW_UNIT_REPO,
            ActionEvents.NEW_UNIT_UPLOAD,
        ),
        "updated": (
            ActionEvents.SOURCE_CHANGE,
            ActionEvents.STRING_REPO_UPDATE,
            ActionEvents.STRING_UPLOAD_UPDATE,
        ),
        "translated": (
            ActionEvents.CHANGE,
            ActionEvents.NEW,
            ActionEvents.ACCEPT,
        ),
        "approved": (ActionEvents.APPROVE,),
        "needs_editing": (ActionEvents.MARKED_EDIT,),
    }
    digest_template = "translation_activity_summary"
    since: datetime | None = None
    until: datetime | None = None

    @classmethod
    def get_freq_choices(cls) -> list[tuple[int, StrOrPromise]]:
        return [
            x
            for x in super().get_freq_choices()
            if x[0] != NotificationFrequency.FREQ_INSTANT
        ]

    @classmethod
    def get_activity_actions(cls) -> tuple[ActionEvents, ...]:
        return tuple(
            action for actions in cls.activity_actions.values() for action in actions
        )

    @classmethod
    def get_periodic_actions(cls) -> Iterable[int]:
        return cls.get_activity_actions()

    @classmethod
    def get_activity_field(cls, action: int) -> str | None:
        for field, actions in cls.activity_actions.items():
            if action in actions:
                return field
        return None

    @staticmethod
    def get_action_query(action: ActionEvents) -> str:
        with override("en"):
            action_name = str(action.label).lower().replace(" ", "-")
        return f"change_action:{action_name}"

    def get_activity_query(self, actions: tuple[ActionEvents, ...]) -> str:
        if self.since is None or self.until is None:
            msg = "Activity summary period is not set"
            raise ValueError(msg)
        action_query = " OR ".join(self.get_action_query(action) for action in actions)
        if len(actions) > 1:
            action_query = f"({action_query})"
        return (
            f"change_time:>={self.since.isoformat()} AND "
            f"change_time:<{self.until.isoformat()} AND {action_query}"
        )

    @staticmethod
    def get_search_url(translation: Translation, query: str) -> str:
        return f"{translation.get_translate_url()}?{urlencode({'q': query})}"

    def notify_periodic(
        self,
        frequency: NotificationFrequency,
        *,
        since: datetime,
        until: datetime,
        project: Project | None,
    ) -> None:
        if project is None:
            return
        self.notify_activity_summary(
            frequency,
            since=since,
            until=until,
            project=project,
        )

    def notify_periodic_batch(
        self,
        frequency: NotificationFrequency,
        *,
        since: datetime,
        until: datetime,
    ) -> None:
        self.notify_activity_summary(
            frequency,
            since=since,
            until=until,
            projects=self.get_periodic_projects(frequency, since=since, until=until),
        )

    def get_activity_change_filter(self, frequency: NotificationFrequency) -> Q:
        # ruff: ignore[import-outside-top-level]
        from weblate.accounts.models import Subscription

        subscriptions = Subscription.objects.filter(
            notification=self.get_name(),
            frequency=frequency,
            user__is_active=True,
            user__is_bot=False,
        )
        if self.user_ids is not None:
            subscriptions = subscriptions.filter(user_id__in=self.user_ids)
        if not subscriptions.exists():
            return Q(pk__in=())

        if subscriptions.filter(
            scope__in=(NotificationScope.SCOPE_ALL, NotificationScope.SCOPE_ADMIN)
        ).exists():
            return Q()

        project_ids = set(
            subscriptions.filter(
                scope=NotificationScope.SCOPE_PROJECT, project__isnull=False
            ).values_list("project_id", flat=True)
        )
        project_ids.update(
            subscriptions.filter(
                scope=NotificationScope.SCOPE_WATCHED,
                user__profile__watched__isnull=False,
            ).values_list("user__profile__watched", flat=True)
        )
        component_ids = set(
            subscriptions.filter(
                scope=NotificationScope.SCOPE_COMPONENT, component__isnull=False
            ).values_list("component_id", flat=True)
        )

        query = Q()
        if project_ids:
            query |= Q(project_id__in=project_ids)
        if component_ids:
            query |= Q(component_id__in=component_ids)
        return query or Q(pk__in=())

    def get_activity_change_rows(
        self,
        frequency: NotificationFrequency,
        project: Project | object | None = _UNSCOPED,
        projects: QuerySet[Project] | None = None,
    ):
        if projects is not None:
            change_filter = Q(project__in=projects)
        elif project is _UNSCOPED:
            change_filter = self.get_activity_change_filter(frequency)
        else:
            change_filter = Q(project=project)
        return (
            Change.objects.filter(
                change_filter,
                action__in=self.get_activity_actions(),
                timestamp__gte=self.since,
                timestamp__lt=self.until,
                translation__isnull=False,
            )
            .annotate(summary_unit_id=Coalesce("unit_id", "id"))
            .values("project_id", "translation_id", "action", "user_id")
            .annotate(count=Count("summary_unit_id", distinct=True))
            .order_by("project_id", "translation_id", "action", "user_id")
        )

    def get_activity_summary_users(
        self,
        frequency: NotificationFrequency,
        translation: Translation,
        actor_user_id: int | None,
    ) -> Iterable[User]:
        component = translation.component
        project = component.project
        last_user = None
        for subscription in self.get_subscriptions(
            None, project, component, translation, None
        ):
            user = subscription.user
            if user == last_user or (
                actor_user_id is not None and user.pk == actor_user_id
            ):
                continue

            last_user = user
            if subscription.frequency != frequency:
                continue
            if not user.can_access_component(component):
                continue

            user.current_subscription = subscription
            yield user

    def notify_activity_summary(
        self,
        frequency: NotificationFrequency,
        *,
        since: datetime,
        until: datetime,
        project: Project | object | None = _UNSCOPED,
        projects: QuerySet[Project] | None = None,
    ) -> None:
        self.since = since
        self.until = until
        users = {}
        notifications: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)
        totals: dict[int, int] = defaultdict(int)
        overlimit: set[int] = set()
        activity_rows = self.get_activity_change_rows(
            frequency, project, projects
        ).iterator(chunk_size=NOTIFICATION_QUERY_CHUNK_SIZE)
        last_project_id: int | object | None = _UNSCOPED
        for activity_batch in batched(activity_rows, NOTIFICATION_QUERY_CHUNK_SIZE):
            translation_ids = {row["translation_id"] for row in activity_batch}
            translations = {
                translation.pk: translation
                for translation in prefetch_stats(
                    Translation.objects.filter(pk__in=translation_ids).prefetch()
                )
            }
            for row in activity_batch:
                if row["project_id"] != last_project_id:
                    self.subscription_cache.clear()
                    last_project_id = row["project_id"]
                field = self.get_activity_field(row["action"])
                translation = translations.get(row["translation_id"])
                if field is None or translation is None:
                    continue

                for user in self.get_activity_summary_users(
                    frequency, translation, row["user_id"]
                ):
                    users[user.pk] = user
                    totals[user.pk] += row["count"]
                    user_notifications = notifications[user.pk]
                    try:
                        summary = user_notifications[translation.pk]
                    except KeyError:
                        if len(user_notifications) >= DIGEST_MAX_ITEMS:
                            overlimit.add(user.pk)
                            continue
                        summary = user_notifications[translation.pk] = {
                            "translation": translation,
                            **dict.fromkeys(self.activity_fields, 0),
                        }
                    summary[field] += row["count"]

        for userid, user_notifications in notifications.items():
            summaries = self.get_summary_rows(user_notifications)
            if not summaries:
                continue
            user = users[userid]
            self.send_digest(
                user.profile.language,
                user.email,
                summaries=summaries,
                subscription=user.current_subscription,
                overlimit=userid in overlimit,
                extracontext={"total_count": totals[userid]},
            )

    def get_summary_rows(
        self,
        summaries: dict[int, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = []
        for summary in summaries.values():
            translation = summary["translation"]
            total = 0
            row = {"translation": translation}
            for field in self.activity_fields:
                count = summary[field]
                total += count
                row[field] = {
                    "count": count,
                    "url": self.get_search_url(
                        translation,
                        self.get_activity_query(self.activity_actions[field]),
                    ),
                }
            row["unfinished"] = {
                "count": translation.stats.todo,
                "url": self.get_search_url(translation, "state:<translated"),
            }
            row["total"] = total
            result.append(row)
        return sorted(result, key=lambda item: str(item["translation"]))

    def get_context(
        self,
        change: Change | None = None,
        subscription: Subscription | None = None,
        extracontext: dict | None = None,
        *,
        changes: QuerySet[Change] | list[Change] | list[dict[str, Any]] | None = None,
        summaries: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        context = super().get_context(
            change, subscription, extracontext, changes=changes, summaries=summaries
        )
        if summaries:
            context.setdefault("total_count", sum(item["total"] for item in summaries))
        return context


@register_notification
class NewContributorNotificaton(Notification):
    actions = (ActionEvents.NEW_CONTRIBUTOR,)
    verbose = pgettext_lazy(
        "Notification name", "Contributor made their first translation"
    )
    verbose_plural = pgettext_lazy(
        "Notification name", "Contributors made their first translation"
    )
    template_name = "new_contributor"
    filter_languages = True


@register_notification
class NewSuggestionNotificaton(Notification):
    actions = (ActionEvents.SUGGESTION,)
    verbose = pgettext_lazy("Notification name", "Suggestion was added")
    verbose_plural = pgettext_lazy("Notification name", "Suggestions were added")
    template_name = "new_suggestion"
    filter_languages = True
    required_attr = "suggestion"


@register_notification
class LanguageTranslatedNotificaton(Notification):
    actions = (ActionEvents.COMPLETE,)
    verbose = pgettext_lazy("Notification name", "Language was translated")
    verbose_plural = pgettext_lazy("Notification name", "Languages were translated")
    template_name = "translated_language"
    required_attr = "translation"


@register_notification
class ComponentTranslatedNotificaton(Notification):
    actions = (ActionEvents.COMPLETED_COMPONENT,)
    verbose = pgettext_lazy("Notification name", "Component was translated")
    verbose_plural = pgettext_lazy("Notification name", "Components were translated")
    template_name = "translated_component"
    required_attr = "component"


@register_notification
class NewCommentNotificaton(Notification):
    debug_conditions = (
        gettext_lazy(
            "Source-string comments ignore notification languages; other comments require a matching language."
        ),
    )
    actions = (ActionEvents.COMMENT,)
    verbose = pgettext_lazy("Notification name", "Comment was added")
    verbose_plural = pgettext_lazy("Notification name", "Comments were added")
    template_name = "new_comment"
    filter_languages = True
    required_attr = "comment"

    def get_language_filter(
        self, change: Change | None, translation: Translation | None
    ) -> Language | None:
        if translation is None:
            return None
        is_source = (
            cast("Unit", change.unit).is_source
            if change is not None
            else translation.is_source
        )
        return None if is_source else translation.language

    def notify_immediate(self, change: Change) -> None:
        super().notify_immediate(change)

        # Notify upstream
        report_source_bugs = cast("Component", change.component).report_source_bugs
        if change.comment and change.comment.unit.is_source and report_source_bugs:
            self.send_immediate("en", report_source_bugs, change)


@register_notification
class MentionCommentNotificaton(Notification):
    debug_conditions = (gettext_lazy("The comment must mention this user."),)
    actions = (ActionEvents.COMMENT,)
    verbose = pgettext_lazy("Notification name", "You were mentioned in a comment")
    verbose_plural = pgettext_lazy(
        "Notification name", "You were mentioned in some comments"
    )
    template_name = "new_comment"
    ignore_watched = True
    required_attr = "comment"
    skip_when_notify: ClassVar[set[type[Notification]]] = {NewCommentNotificaton}

    def get_users(
        self,
        frequency: NotificationFrequency,
        change: Change | None = None,
        project: Project | None = None,
        component: Component | None = None,
        translation: Translation | None = None,
        users: list[int] | None = None,
    ) -> Iterable[User]:
        if change is None or self.missing_required_attrs(change):
            return []
        return super().get_users(
            frequency,
            change,
            project,
            component,
            translation,
            list(
                get_mention_users(cast("Comment", change.comment).comment).values_list(
                    "id", flat=True
                )
            ),
        )


@register_notification
class LastAuthorCommentNotificaton(Notification):
    debug_conditions = (
        gettext_lazy(
            "The user must have contributed to the string or previously participated in its discussion."
        ),
    )
    actions = (ActionEvents.COMMENT,)
    verbose = pgettext_lazy(
        "Notification name",
        "String you contributed to received a comment",
    )
    verbose_plural = pgettext_lazy(
        "Notification name",
        "Strings you contributed to received comments",
    )
    template_name = "new_comment"
    required_attr = "comment"
    skip_when_notify: ClassVar[set[type[Notification]]] = {
        MentionCommentNotificaton,
        NewCommentNotificaton,
    }

    def get_change_users(self, change: Change) -> list[int]:
        change_users: list[int] = []
        seen: set[int] = set()

        def add_user_id(user_id: int | None) -> None:
            if user_id is not None and user_id not in seen:
                seen.add(user_id)
                change_users.append(user_id)

        unit = cast("Unit", change.unit)
        last_author = unit.get_last_content_change()[0]
        if not last_author.is_anonymous:
            add_user_id(last_author.pk)

        comment = cast("Comment", change.comment)
        unit_ids: list[int | None] = [unit.pk]
        if not unit.is_source:
            unit_ids.append(unit.source_unit_id)

        comment_unit_ids = {unit_id for unit_id in unit_ids if unit_id is not None}
        previous_comments = Q(timestamp__lt=comment.timestamp)
        if comment.pk is not None:
            previous_comments |= Q(timestamp=comment.timestamp, pk__lt=comment.pk)
        commenter_ids = (
            Comment.objects.filter(unit_id__in=comment_unit_ids)
            .filter(previous_comments)
            .exclude(user__isnull=True)
            .values_list("user_id", flat=True)
            .distinct()
        )
        for user_id in commenter_ids:
            add_user_id(user_id)

        if not unit.is_source:
            suggestion_user_ids = (
                Suggestion.objects.filter(unit=unit, timestamp__lt=comment.timestamp)
                .exclude(user__isnull=True)
                .values_list("user_id", flat=True)
                .distinct()
            )
            for user_id in suggestion_user_ids:
                add_user_id(user_id)

        return change_users

    def get_users(
        self,
        frequency: NotificationFrequency,
        change: Change | None = None,
        project: Project | None = None,
        component: Component | None = None,
        translation: Translation | None = None,
        users: list[int] | None = None,
    ) -> Iterable[User]:
        if change is None or self.missing_required_attrs(change):
            return []
        return super().get_users(
            frequency,
            change,
            project,
            component,
            translation,
            self.get_change_users(change),
        )


@register_notification
class TranslatedStringNotificaton(Notification):
    actions = (
        ActionEvents.CHANGE,
        ActionEvents.NEW,
        ActionEvents.ACCEPT,
    )
    verbose = pgettext_lazy("Notification name", "String was edited by user")
    verbose_plural = pgettext_lazy("Notification name", "Strings were edited by user")
    template_name = "translated_string"
    filter_languages = True


@register_notification
class ApprovedStringNotificaton(Notification):
    actions = (ActionEvents.APPROVE,)
    verbose = pgettext_lazy("Notification name", "String was approved")
    verbose_plural = pgettext_lazy("Notification name", "Strings were approved")
    template_name = "approved_string"
    filter_languages = True


@register_notification
class ChangedStringNotificaton(Notification):
    actions = Change.ACTIONS_CONTENT
    verbose = pgettext_lazy("Notification name", "String was changed")
    verbose_plural = pgettext_lazy("Notification name", "Strings were changed")
    template_name = "changed_translation"
    filter_languages = True
    skip_when_notify: ClassVar[set[type[Notification]]] = {
        TranslatedStringNotificaton,
        ApprovedStringNotificaton,
    }


@register_notification
class NewTranslationNotificaton(Notification):
    actions = (
        ActionEvents.ADDED_LANGUAGE,
        ActionEvents.REQUESTED_LANGUAGE,
    )
    verbose = pgettext_lazy("Notification name", "New language was added or requested")
    verbose_plural = pgettext_lazy(
        "Notification name", "New languages were added or requested"
    )
    template_name = "new_language"

    def get_context(
        self,
        change: Change | None = None,
        subscription: Subscription | None = None,
        extracontext: dict | None = None,
        *,
        changes: QuerySet[Change] | list[Change] | list[dict[str, Any]] | None = None,
        summaries: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        context = super().get_context(
            change, subscription, extracontext, changes=changes, summaries=summaries
        )
        if change:
            context["language"] = Language.objects.get(code=change.details["language"])
            context["was_added"] = change.action == ActionEvents.ADDED_LANGUAGE
        return context


@register_notification
class NewComponentNotificaton(Notification):
    actions = (ActionEvents.CREATE_COMPONENT,)
    verbose = pgettext_lazy(
        "Notification name", "New translation component was created"
    )
    verbose_plural = pgettext_lazy(
        "Notification name", "New translation components were created"
    )
    template_name = "new_component"


@register_notification
class NewAnnouncementNotificaton(Notification):
    debug_conditions = (
        gettext_lazy(
            "The announcement must enable notifications. If it specifies a language, that language must match the user’s notification languages."
        ),
    )
    actions = (ActionEvents.ANNOUNCEMENT,)
    verbose = pgettext_lazy("Notification name", "Announcement was published")
    verbose_plural = pgettext_lazy("Notification name", "Announcements were published")
    template_name = "new_announcement"
    required_attr = "announcement"
    any_watched: bool = True

    def should_skip(self, user: User, change: Change) -> bool:
        return not cast("Announcement", change.announcement).notify

    def get_language_filter(
        self, change: Change | None, translation: Translation | None
    ) -> Language | None:
        if change is None:
            return None
        return cast("Announcement", change.announcement).language


@register_notification
class NewAlertNotificaton(Notification):
    debug_conditions = (
        gettext_lazy(
            "The alert must be at least a warning and the user must be able to act on it. Linked-component and project-wide alerts can be deduplicated."
        ),
    )
    actions = (ActionEvents.ALERT, ActionEvents.ALERT_REOPENED)
    verbose = pgettext_lazy("Notification name", "New alert emerged in a component")
    verbose_plural = pgettext_lazy(
        "Notification name", "New alerts emerged in a component"
    )
    template_name = "new_alert"
    required_attr = "alert"
    wide_alert_deduplication_window = timedelta(minutes=5)

    def has_canonical_event(self, change: Change, component: Component) -> bool:
        return Change.objects.filter(
            action=change.action,
            alert__name=change.alert.name,
            component=component,
            details__fingerprint=change.details.get("fingerprint"),
            timestamp__gte=change.timestamp - self.wide_alert_deduplication_window,
            timestamp__lte=change.timestamp,
        ).exists()

    def get_subscriptions(
        self, change, project, component, translation, users
    ) -> Iterable[Subscription]:
        for subscription in super().get_subscriptions(
            change, project, component, translation, users
        ):
            if change is None:
                continue
            try:
                alert = cast("Alert", change.alert)
            except Alert.DoesNotExist:
                continue
            target = cast("Component", change.component)
            user = subscription.user
            if alert.severity >= AlertSeverity.WARNING and alert.obj.can_user_act(
                user, target
            ):
                yield subscription

    def should_skip(self, user: User, change: Change) -> bool:
        try:
            alert = cast("Alert", change.alert)
        except Alert.DoesNotExist:
            # Alert was removed meanwhile
            return False
        component = cast("Component", change.component)
        if alert.severity < AlertSeverity.WARNING or not alert.obj.can_user_act(
            user, component
        ):
            return True
        if alert.obj.link_wide:
            # Notify for main component
            if not component.linked_component:
                return False
            if not self.has_canonical_event(change, component.linked_component):
                return False
            # Notify only for others only when user will not get main.
            # This handles component level subscriptions.
            fake = copy(change)
            fake.component = component.linked_component
            fake.project = fake.component.project
            return bool(
                list(
                    self.get_users(
                        NotificationFrequency.FREQ_INSTANT, fake, users=[user.pk]
                    )
                )
            )
        if alert.obj.project_wide:
            first_component = component.project.component_set.order_by("id")[0]
            # Notify for the first component
            if component.id == first_component.id:
                return False
            if not self.has_canonical_event(change, first_component):
                return False
            # Notify only for others only when user will not get first.
            # This handles component level subscriptions.
            fake = copy(change)
            fake.component = first_component
            fake.project = fake.component.project
            return bool(
                list(
                    self.get_users(
                        NotificationFrequency.FREQ_INSTANT, fake, users=[user.pk]
                    )
                )
            )
        return False


@register_notification
class MergeFailureNotification(Notification):
    actions = (
        ActionEvents.FAILED_MERGE,
        ActionEvents.FAILED_REBASE,
        ActionEvents.FAILED_PUSH,
    )
    verbose = pgettext_lazy("Notification name", "Repository operation failed")
    verbose_plural = pgettext_lazy("Notification name", "Repository operations failed")
    template_name = "repository_error"
    skip_when_notify: ClassVar[set[type[Notification]]] = {NewAlertNotificaton}

    def _convert_change_skip(self, change: Change) -> Change:
        fake = copy(change)
        fake.action = ActionEvents.ALERT
        alert_name = (
            "PushFailure"
            if change.action == ActionEvents.FAILED_PUSH
            else "MergeFailure"
        )
        fake.alert = Alert(name=alert_name, details={"error": ""})
        return fake


class SummaryNotification(Notification):
    filter_languages = True
    # Computing snapshot counts requires one pass over all matching translations.
    # Splitting recipients would repeat that database and statistics-cache scan.
    batch_recipients = False

    @classmethod
    def get_freq_choices(cls) -> list[tuple[int, StrOrPromise]]:
        return [
            x
            for x in super().get_freq_choices()
            if x[0] != NotificationFrequency.FREQ_INSTANT
        ]

    def notify_periodic(
        self,
        frequency: NotificationFrequency,
        *,
        since: datetime,
        until: datetime,
        project: Project | None,
    ) -> None:
        if project is None:
            return
        self.notify_summary(frequency, project=project)

    def notify_periodic_batch(
        self,
        frequency: NotificationFrequency,
        *,
        since: datetime,
        until: datetime,
    ) -> None:
        self.notify_summary(
            frequency,
            projects=self.get_periodic_projects(frequency, since=since, until=until),
        )

    def notify_summary(
        self,
        frequency: NotificationFrequency,
        *,
        project: Project | object = _UNSCOPED,
        projects: QuerySet[Project] | None = None,
    ) -> None:
        users = {}
        notifications: dict[int, list[dict[str, Any]]] = defaultdict(list)
        totals: dict[int, int] = defaultdict(int)
        overlimit: set[int] = set()
        translations = Translation.objects.prefetch().order_by(
            "component__project_id", "pk"
        )
        if projects is not None:
            translations = translations.filter(component__project__in=projects)
        elif project is not _UNSCOPED:
            translations = translations.filter(component__project=project)
        last_project_id: int | object = _UNSCOPED
        for translation in iter_prefetch_stats(translations):
            if translation.component.project_id != last_project_id:
                self.subscription_cache.clear()
                last_project_id = translation.component.project_id
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
                totals[user.pk] += count
                user_notifications = notifications[user.pk]
                if len(user_notifications) < DIGEST_MAX_ITEMS:
                    user_notifications.append(context)
                else:
                    overlimit.add(user.pk)
        for userid, summaries in notifications.items():
            user = users[userid]
            self.send_digest(
                user.profile.language,
                user.email,
                summaries=summaries,
                subscription=user.current_subscription,
                overlimit=userid in overlimit,
                extracontext={"total_count": totals[userid]},
            )

    @staticmethod
    def get_count(translation: Translation) -> int:
        raise NotImplementedError

    def get_context(
        self,
        change: Change | None = None,
        subscription: Subscription | None = None,
        extracontext: dict | None = None,
        *,
        changes: QuerySet[Change] | list[Change] | list[dict[str, Any]] | None = None,
        summaries: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        context = super().get_context(
            change, subscription, extracontext, changes=changes, summaries=summaries
        )
        if summaries:
            context.setdefault("total_count", sum(item["count"] for item in summaries))
        return context


@register_notification
class PendingSuggestionsNotification(SummaryNotification):
    verbose_plural = verbose = pgettext_lazy(
        "Notification name", "Pending suggestions exist"
    )
    digest_template = "pending_suggestions"

    @staticmethod
    def get_count(translation: Translation) -> int:
        return translation.stats.suggestions


@register_notification
class ToDoStringsNotification(SummaryNotification):
    verbose_plural = verbose = pgettext_lazy(
        "Notification name", "Unfinished strings exist"
    )
    digest_template = "todo_strings"

    @staticmethod
    def get_count(translation: Translation) -> int:
        return translation.stats.todo


def get_notification_emails(
    language: str | None,
    recipients: list[str],
    notification: str,
    context: dict[str, Any] | None = None,
    info: str | None = None,
    *,
    user: User | None = None,
) -> list[OutgoingEmail]:
    """Render notification email."""
    context = context or {}

    # Define headers
    headers = get_email_headers(notification)
    add_recipient_headers(headers, user)

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
    language: str | None,
    recipients: list[str],
    notification: str,
    context: dict[str, Any] | None = None,
    info: str | None = None,
    *,
    user: User | None = None,
) -> None:
    """Render and sends notification email."""
    queue_mails(
        get_notification_emails(
            language, recipients, notification, context, info, user=user
        )
    )
