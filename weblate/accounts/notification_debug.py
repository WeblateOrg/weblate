# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Read-only explanations of notification subscription eligibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext

from weblate.accounts.notifications import (
    NOTIFICATIONS,
    Notification,
    NotificationFrequency,
    NotificationScope,
)
from weblate.trans.models import Category, Component, Project, Translation

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise

    from weblate.accounts.models import Subscription
    from weblate.auth.models import User


NOTIFICATION_DETAIL_LIMIT = 5
NOTIFICATION_COMPONENT_LIMIT = 200
NOTIFICATION_PROJECT_LIMIT = 10


@dataclass
class NotificationExplanation:
    notification: type[Notification]
    reason: StrOrPromise
    subscription: Subscription | None = None
    overridden: list[Subscription] = field(default_factory=list)
    conditions: list[StrOrPromise] = field(default_factory=list)
    exceptions: list[NotificationException] = field(default_factory=list)

    @property
    def name(self) -> StrOrPromise:
        return self.notification.verbose

    @property
    def behavior_key(self) -> tuple:
        """Compare effective behavior without splitting equivalent subscriptions."""
        subscription = self.subscription
        return (
            (subscription.scope, subscription.frequency, subscription.onetime)
            if subscription
            else None,
            str(self.reason),
            tuple(str(condition) for condition in self.conditions),
        )


@dataclass
class NotificationException:
    outcome: NotificationExplanation
    count: int = 0
    examples: list[Component] = field(default_factory=list)
    subscription_id: int | None = None
    shared_count: int = 0


@dataclass
class NotificationScopeSummary:
    results: list[NotificationExplanation] = field(default_factory=list)
    component_count: int = 0
    broad: bool = False
    empty: bool = False


class NotificationDebugger:
    """Inspect subscriptions without constructing events or invoking delivery."""

    def __init__(self, user: User) -> None:
        self.user = user
        self.handlers = [handler([], user_ids=[user.pk]) for handler in NOTIFICATIONS]
        self.languages = set(user.profile.languages.values_list("pk", flat=True))
        self.watched_projects = set(user.profile.watched.values_list("pk", flat=True))
        self.scopes: dict[str, set[int]] = {}
        for name, scope in user.subscription_set.values_list("notification", "scope"):
            self.scopes.setdefault(name, set()).add(scope)

    def explain(
        self,
        handler: Notification,
        project: Project,
        component: Component | None = None,
        translation: Translation | None = None,
    ) -> NotificationExplanation:
        result = NotificationExplanation(
            type(handler), gettext("No matching subscription.")
        )
        # Share the delivery matcher, excluding only checks requiring an actual event.
        subscriptions = list(
            handler.get_scope_subscriptions(
                None, project, component, translation, None, include_ineligible=True
            )
        )
        if subscriptions:
            result.subscription = subscriptions[0]
            result.overridden = subscriptions[1:]

        if not self.user.is_active or self.user.is_bot:
            result.reason = gettext(
                "Inactive users and bots do not receive notifications."
            )
            return result

        if not handler.can_access_target(self.user, project, component):
            result.reason = gettext("The user cannot access this target.")
        elif (
            language := handler.get_language_filter(None, translation)
        ) is not None and language.pk not in self.languages:
            result.reason = gettext(
                "This language is not among the user’s notification languages."
            )
        elif not subscriptions:
            scopes = self.scopes.get(handler.get_name(), set())
            if NotificationScope.SCOPE_WATCHED in scopes:
                if handler.ignore_watched:
                    result.conditions.append(
                        gettext(
                            "This notification ignores watched-project subscriptions."
                        )
                    )
                elif project.pk not in self.watched_projects:
                    result.conditions.append(
                        gettext("The user is not watching this project.")
                    )
            if NotificationScope.SCOPE_ADMIN in scopes:
                result.conditions.append(
                    gettext("No administered-project subscription matches this target.")
                )
            if scopes & {
                NotificationScope.SCOPE_PROJECT,
                NotificationScope.SCOPE_COMPONENT,
            }:
                result.conditions.append(
                    gettext(
                        "The project or component subscriptions apply to other targets."
                    )
                )
        elif subscriptions[0].frequency == NotificationFrequency.FREQ_NONE:
            result.reason = gettext("Disabled by the effective subscription.")
        else:
            result.reason = gettext(
                "Eligible when the notification’s event conditions are met."
            )
            result.conditions = list(handler.debug_conditions)
            if handler.required_attr:
                result.conditions.append(
                    gettext("Requires a corresponding event on this target.")
                )
            for notification in sorted(
                handler.skip_when_notify, key=lambda item: item.get_name()
            ):
                result.conditions.append(
                    gettext("Instant delivery can be suppressed by: %(notification)s.")
                    % {"notification": notification.verbose}
                )
            if (
                handler.filter_languages
                and translation is None
                and not handler.debug_conditions
            ):
                result.conditions.append(
                    gettext(
                        "Language-specific events require one of the user’s notification languages."
                    )
                )
        return result

    def inspect(
        self,
        target: Project | Category | Component | Translation,
        viewer: User,
    ) -> NotificationScopeSummary:
        """Summarize inherited settings and exceptions across the accessible scope."""
        if isinstance(target, (Component, Translation)):
            component = target.component if isinstance(target, Translation) else target
            if not viewer.can_access_component(component):
                return NotificationScopeSummary(empty=True)
            results = [
                self.explain(
                    handler,
                    component.project,
                    component,
                    target if isinstance(target, Translation) else None,
                )
                for handler in self.handlers
            ]
            results.sort(key=lambda result: str(result.name))
            return NotificationScopeSummary(
                results=[result for result in results if result.subscription],
                component_count=1,
            )

        project = target.project if isinstance(target, Category) else target
        if not viewer.can_access_project(project):
            return NotificationScopeSummary(broad=True, empty=True)
        if isinstance(target, Category):
            components = Component.objects.filter(
                pk__in=target.get_component_ids_with_links()
            )
        else:
            components = Component.objects.filter(
                Q(project=target) | Q(pk__in=target.shared_components.values("pk"))
            )
        components = (
            components.filter_access(viewer)
            .select_related("project", "category")
            .order_by("project_id", "pk")
        )
        # Bound both per-component explanations and per-project subscription
        # queries before loading components or invoking notification handlers.
        scope = list(
            components.values_list("pk", "project_id")[
                : NOTIFICATION_COMPONENT_LIMIT + 1
            ]
        )
        if (
            len(scope) > NOTIFICATION_COMPONENT_LIMIT
            or len({project.pk, *(project_id for _, project_id in scope)})
            > NOTIFICATION_PROJECT_LIMIT
        ):
            raise ValidationError(
                gettext(
                    "This scope is too large to check. Choose a smaller category, "
                    "a component, or a translation."
                ),
                code="notification_scope_too_large",
            )
        results = [self.explain(handler, project) for handler in self.handlers]
        groups: list[dict[tuple, NotificationException]] = [{} for _ in self.handlers]
        summary = NotificationScopeSummary(broad=True)
        for component in components.filter(pk__in=[pk for pk, _ in scope]):
            summary.component_count += 1
            for handler, inherited, exceptions in zip(
                self.handlers, results, groups, strict=True
            ):
                # The matcher uses the component's own project, including linked
                # components whose inherited settings differ from the selected scope.
                outcome = self.explain(handler, component.project, component)
                key = outcome.behavior_key
                if key == inherited.behavior_key:
                    continue
                subscription_id = (
                    outcome.subscription.pk if outcome.subscription else None
                )
                if key not in exceptions:
                    exceptions[key] = NotificationException(
                        outcome, subscription_id=subscription_id
                    )
                exception = exceptions[key]
                if exception.subscription_id != subscription_id:
                    exception.subscription_id = None
                exception.count += 1
                if component.project_id != project.pk:
                    exception.shared_count += 1
                if len(exception.examples) < NOTIFICATION_DETAIL_LIMIT:
                    exception.examples.append(component)
        if isinstance(target, Category) and not summary.component_count:
            summary.empty = True
            return summary
        for result, exceptions in zip(results, groups, strict=True):
            result.exceptions = list(exceptions.values())
            if result.subscription or any(
                item.outcome.subscription for item in result.exceptions
            ):
                summary.results.append(result)
        summary.results.sort(key=lambda result: str(result.name))
        return summary
