# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Read-only explanations of notification subscription eligibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.core.paginator import Page, Paginator
from django.db.models import F, Value
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
NOTIFICATION_TARGET_PAGE_SIZE = 50


@dataclass
class NotificationExplanation:
    notification: type[Notification]
    reason: StrOrPromise
    subscription: Subscription | None = None
    overridden: list[Subscription] = field(default_factory=list)
    conditions: list[StrOrPromise] = field(default_factory=list)
    targets: list[Project | Component | Translation] = field(default_factory=list)

    @property
    def name(self) -> StrOrPromise:
        return self.notification.verbose


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
        if not self.user.is_active or self.user.is_bot:
            result.reason = gettext(
                "Inactive users and bots do not receive notifications."
            )
            return result

        # Share the delivery matcher, excluding only checks requiring an actual event.
        subscriptions = list(
            handler.get_scope_subscriptions(None, project, component, translation, None)
        )
        if subscriptions:
            result.subscription = subscriptions[0]
            result.overridden = subscriptions[1:]

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
        page_number: str | None,
    ) -> tuple[list[NotificationExplanation], Page]:
        """Group equivalent outcomes over one page of accessible descendants."""
        page = self.get_target_page(target, viewer, page_number)

        groups: dict[tuple, NotificationExplanation] = {}
        for obj in page:
            translation = None
            component = None
            if isinstance(obj, Translation):
                translation = obj
                component = obj.component
                project = component.project
            elif isinstance(obj, Component):
                component = obj
                project = obj.project
            else:
                project = obj
            for handler in self.handlers:
                result = self.explain(handler, project, component, translation)
                key = (
                    handler.get_name(),
                    str(result.reason),
                    result.subscription.pk if result.subscription else None,
                    tuple(subscription.pk for subscription in result.overridden),
                    tuple(str(condition) for condition in result.conditions),
                )
                if key not in groups:
                    groups[key] = result
                groups[key].targets.append(obj)
        return sorted(
            groups.values(), key=lambda result: str(result.notification.verbose)
        ), page

    @staticmethod
    def get_target_page(
        target: Project | Category | Component | Translation,
        viewer: User,
        page_number: str | None,
    ) -> Page:
        """Page identifiers before loading any component or translation objects."""
        if isinstance(target, Translation):
            components = Component.objects.filter(pk=target.component_id)
        elif isinstance(target, Component):
            components = Component.objects.filter(pk=target.pk)
        elif isinstance(target, Category):
            components = Component.objects.filter(
                pk__in=target.get_component_ids_with_links()
            )
        else:
            components = Component.objects.filter(project=target)
        components = components.filter_access(viewer)
        translations = Translation.objects.filter(component__in=components)
        if isinstance(target, Translation):
            translations = translations.filter(pk=target.pk)

        # All branches have the same projection and no implicit model ordering.
        # Ordering keeps each component immediately ahead of its translations.
        translation_ids = (
            translations.order_by()
            .annotate(
                target_component=F("component_id"),
                target_kind=Value("translation"),
                target_id=F("pk"),
            )
            .values_list("target_component", "target_kind", "target_id")
        )
        target_ids = translation_ids
        if not isinstance(target, Translation):
            component_ids = (
                components.order_by()
                .annotate(
                    target_component=F("pk"),
                    target_kind=Value("component"),
                    target_id=F("pk"),
                )
                .values_list("target_component", "target_kind", "target_id")
            )
            target_ids = target_ids.union(component_ids)
        if isinstance(target, Project):
            project_ids = (
                Project.objects.filter(pk=target.pk)
                .order_by()
                .annotate(
                    target_component=Value(0),
                    target_kind=Value("project"),
                    target_id=F("pk"),
                )
                .values_list("target_component", "target_kind", "target_id")
            )
            target_ids = target_ids.union(project_ids)
        target_ids = target_ids.order_by("target_component", "target_kind", "target_id")
        page = Paginator(target_ids, NOTIFICATION_TARGET_PAGE_SIZE).get_page(
            page_number
        )
        identifiers = list(page.object_list)
        objects: dict[tuple[str, int], Project | Component | Translation] = {}
        if isinstance(target, Project):
            objects["project", target.pk] = target
        for component in Component.objects.filter(
            pk__in=[pk for _, kind, pk in identifiers if kind == "component"]
        ).select_related("project", "category"):
            objects["component", component.pk] = component
        for translation in Translation.objects.filter(
            pk__in=[pk for _, kind, pk in identifiers if kind == "translation"]
        ).select_related("language", "component__project", "component__category"):
            objects["translation", translation.pk] = translation
        return Page(
            [objects[kind, pk] for _, kind, pk in identifiers],
            page.number,
            page.paginator,
        )
