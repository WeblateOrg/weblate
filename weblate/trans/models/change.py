# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar, TypedDict, cast, overload
from uuid import uuid5

import sentry_sdk
from django.conf import settings
from django.core.cache import cache
from django.db import models, transaction
from django.db.models import Count, F, OuterRef, Q, Subquery
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy
from rapidfuzz.distance import DamerauLevenshtein

from weblate.trans.actions import (
    ACTIONS_ADDON,
    ACTIONS_CONTENT,
    ACTIONS_LOG,
    ACTIONS_MERGE_FAILURE,
    ACTIONS_REPOSITORY,
    ACTIONS_REVERTABLE,
    ACTIONS_SHOW_CONTENT,
    ActionEvents,
)
from weblate.trans.mixins import UserDisplayMixin
from weblate.trans.models.project import Project
from weblate.trans.signals import change_bulk_create
from weblate.trans.util import split_plural
from weblate.utils.const import WEBLATE_UUID_NAMESPACE
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.state import StringState

if TYPE_CHECKING:
    from collections.abc import Iterable
    from uuid import UUID

    from django_stubs_ext import StrOrPromise

    from weblate.auth.models import User
    from weblate.lang.models import Language
    from weblate.trans.models import Category, Component, Translation, Unit

LOGGER = logging.getLogger("weblate.change")

CHANGE_PROJECT_LOOKUP_KEY = "change:project-lookup"

PREFETCH_FIELDS = (
    "user",
    "author",
    "translation",
    "language",
    "component",
    "category",
    "project",
    "component__source_language",
    "component__secondary_language",
    "project__secondary_language",
    "unit",
    "unit__source_unit",
    "translation__plural",
)

COMPONENT_ORIGINS = {
    "scratch": gettext_lazy("Component created from scratch"),
    "branch": gettext_lazy("Component created as a branch"),
    "api": gettext_lazy("Component created via API"),
    "vcs": gettext_lazy("Component created from version control"),
    "zip": gettext_lazy("Component created via ZIP upload"),
    "document": gettext_lazy("Component created via document upload"),
}


class RevertUserEditsResult(TypedDict):
    reverted: int
    skipped: int
    skipped_newer: int
    skipped_failed: int


def dt_as_day_range(dt: datetime | date) -> tuple[datetime, datetime]:
    """
    Convert given datetime/date to a range for that day.

    The resulting tuple contains the start of the day (00:00:00) and end of the
    day (23:59:59.999999).
    """
    if isinstance(dt, date):
        dt = timezone.make_aware(datetime.combine(dt, datetime.min.time()))
    return (
        dt.replace(hour=0, minute=0, second=0, microsecond=0),
        dt.replace(hour=23, minute=59, second=59, microsecond=999999),
    )


class ChangeQuerySet(models.QuerySet["Change"]):
    def content(self, prefetch: bool = False) -> ChangeQuerySet:
        """Return queryset with content changes."""
        base = self
        if prefetch:
            base = base.prefetch()
        return base.filter(action__in=ACTIONS_CONTENT)

    def for_category(self, category: Category) -> ChangeQuerySet:
        return self.filter(
            Q(component_id__in=category.all_component_ids) | Q(category=category)
        )

    def filter_announcements(self) -> ChangeQuerySet:
        return self.filter(action=ActionEvents.ANNOUNCEMENT)

    def count_stats(
        self, days: int, step: int, dtstart: datetime
    ) -> list[tuple[datetime, int]]:
        """Count the number of changes in a given period grouped by step days."""
        # Count number of changes
        result = []
        for _unused in range(0, days, step):
            # Calculate interval
            int_start = dtstart
            int_end = int_start + timedelta(days=step)

            # Count changes
            int_base = self.filter(timestamp__range=(int_start, int_end))
            count = int_base.aggregate(Count("id"))

            # Append to result
            result.append((int_start, count["id__count"]))

            # Advance to next interval
            dtstart = int_end

        return result

    def base_stats(
        self,
        days: int,
        step: int,
        project: Project | None = None,
        component: Component | None = None,
        translation: Translation | None = None,
        language: Language | None = None,
        user: User | None = None,
    ) -> list[tuple[datetime, int]]:
        """Core of daily/weekly/monthly stats calculation."""
        # Get range (actually start)
        dtstart = timezone.now() - timedelta(days=days + 1)

        # Base for filtering
        base = self.all()

        # Filter by translation/project
        if translation is not None:
            base = base.filter(translation=translation)
        elif component is not None:
            base = base.filter(component=component)
        elif project is not None:
            base = base.filter(project=project)

        # Filter by language
        if language is not None:
            base = base.filter(language=language)

        # Filter by language
        if user is not None:
            base = base.filter(user=user)

        return base.count_stats(days, step, dtstart)

    def prefetch_for_render(self) -> ChangeQuerySet:
        """
        Prefetch needed related fields for rendering.

        Might be used with Change.fill_in_prefetched.
        """
        return self.prefetch().select_related(
            "alert",
            "screenshot",
            "announcement",
            "suggestion",
            "comment",
        )

    def prefetch(self) -> ChangeQuerySet:
        """
        Fetch related fields at once to avoid loading them individually.

        Call prefetch or prefetch_list later on paginated results to complete.
        """
        return self.prefetch_related(*PREFETCH_FIELDS)

    @overload
    def preload_list(
        self, results: ChangeQuerySet, skip: str | None = None
    ) -> ChangeQuerySet: ...
    @overload
    def preload_list(
        self, results: list[Change], skip: str | None = None
    ) -> list[Change]: ...
    def preload_list(self, results, skip=None):
        """Companion for prefetch to fill in nested references."""
        for item in results:
            if item.component and skip != "component":
                item.component.project = item.project
            if item.translation and skip != "translation":
                item.translation.component = item.component
                if item.language_id is not None:
                    item.translation.language = item.language
            if item.unit and skip != "unit":
                item.unit.translation = item.translation
        return results

    def authors_list(
        self,
        date_range: tuple[datetime, datetime] | None = None,
        *,
        values_list: tuple[str, ...] = (),
    ) -> Iterable[tuple]:
        """Return list of authors."""
        authors = self.content()
        if date_range is not None:
            authors = authors.filter(timestamp__range=date_range)
        return (
            authors.exclude(author__isnull=True)
            .values("author")
            .annotate(change_count=Count("id"))
            .values_list(
                "author__email",
                "author__username",
                "author__full_name",
                "change_count",
                *values_list,
            )
        )

    def order(self) -> ChangeQuerySet:
        return self.order_by("-timestamp")

    def recent(
        self, *, count: int = 10, skip_preload: str | None = None
    ) -> list[Change]:
        """
        Return recent changes to show on object pages.

        This uses iterator() as server-side cursors are typically
        more effective here.
        """
        result: list[Change] = []
        with transaction.atomic(), sentry_sdk.start_span(op="change.recent"):
            for change in self.order().iterator(chunk_size=count):
                result.append(change)
                if len(result) >= count:
                    break
            return self.preload_list(result, skip_preload)

    def bulk_create(self, *args, **kwargs) -> list[Change]:
        """
        Bulk creation of changes.

        Add processing to bulk creation.
        """
        from weblate.accounts.notifications import (  # noqa: PLC0415
            dispatch_changes_notifications,
        )

        changes = super().bulk_create(*args, **kwargs)

        # Dispatch notifications
        dispatch_changes_notifications(changes)

        # Executes post save to ensure messages are sent to fedora messaging
        change_bulk_create.send(Change, instances=changes)

        # Store last content change in cache for improved performance
        translations = set()
        for change in reversed(changes):
            # Process latest change on each translation (when invoked in
            # Translation.add_unit, it spans multiple translations)
            if (
                change.translation_id not in translations
                and change.is_last_content_change_storable()
            ):
                transaction.on_commit(change.update_cache_last_change)
                translations.add(change.translation_id)

        # Log to the log
        for change in changes:
            change.log_event()

        return changes

    def filter_components(self, user: User) -> ChangeQuerySet:
        if not user.needs_component_restrictions_filter:
            return self
        return self.filter(
            Q(component__isnull=True)
            | Q(component__restricted=False)
            | Q(component_id__in=user.component_permissions)
        )

    def filter_projects(self, user: User) -> ChangeQuerySet:
        if not user.needs_project_filter:
            return self
        return self.filter(project__in=user.allowed_projects)

    def lookup_project_rename(self, name: str) -> Project | None:
        lookup = cache.get(CHANGE_PROJECT_LOOKUP_KEY)
        if lookup is None:
            lookup = self.generate_project_rename_lookup()
        if name not in lookup:
            return None
        try:
            return Project.objects.get(pk=lookup[name])
        except Project.DoesNotExist:
            return None

    def generate_project_rename_lookup(self) -> dict[str, int]:
        lookup: dict[str, int] = {}
        for change in self.filter(action=ActionEvents.RENAME_PROJECT).order():
            if change.old not in lookup and change.project_id is not None:
                lookup[change.old] = change.project_id
        cache.set(CHANGE_PROJECT_LOOKUP_KEY, lookup, 3600 * 24 * 7)
        return lookup

    def filter_by_day(self, dt: datetime | date) -> ChangeQuerySet:
        """
        Filter changes by given date.

        Optimized to use Database index by not converting timestamp to date object
        """
        return self.filter(timestamp__range=dt_as_day_range(dt))

    def since_day(self, dt: datetime | date) -> ChangeQuerySet:
        """
        Filter changes since given date.

        Optimized to use Database index by not converting timestamp to date object
        """
        return self.filter(timestamp__gte=dt_as_day_range(dt)[0])

    def count_users(self) -> int:
        """
        Count contributing users.

        Used mostly in the metrics.
        """
        return (
            self.filter(user__is_active=True, user__is_bot=False)
            .values("user")
            .distinct()
            .count()
        )


class ChangeManager(models.Manager["Change"]):
    def create(self, *, user: User | None = None, **kwargs) -> Change:
        """
        Create a change object.

        Wrapper to avoid using anonymous user as change owner.
        """
        if user is not None and not user.is_authenticated:
            user = None
        return super().create(user=user, **kwargs)

    def last_changes(
        self,
        user: User,
        unit: Unit | None = None,
        translation: Translation | None = None,
        component: Component | None = None,
        project: Project | None = None,
        category: Category | None = None,
        language: Language | None = None,
    ) -> models.QuerySet[Change, Change]:
        """
        Return the most recent changes for an user.

        Filters Change objects by user permissions and fetches related fields for
        last changes display.
        """
        if unit is not None:
            if not user.can_access_component(unit.translation.component):
                return self.none()
            result = unit.change_set.all()
        elif translation is not None:
            if not user.can_access_component(translation.component):
                return self.none()
            result = translation.change_set.all()
        elif component is not None:
            if not user.can_access_component(component):
                return self.none()
            result = component.change_set.all()
        elif project is not None:
            if not user.can_access_project(project):
                return self.none()
            result = project.change_set.filter_components(user)
            if language is not None:
                result = result.filter(language=language)
            if category is not None:
                result = result.filter(category=category)
        elif language is not None:
            result = language.change_set.filter_projects(user).filter_components(user)
        else:
            result = self.filter_projects(user).filter_components(user)  # type: ignore[attr-defined]
        return result.prefetch_for_render().order()

    def latest_revertable_changes(
        self,
        user: User,
        *,
        project: Project | None = None,
    ) -> ChangeQuerySet:
        latest_revertable_change = (
            self.filter(unit=OuterRef("unit"), action__in=ACTIONS_REVERTABLE)
            .order_by("-timestamp", "-pk")
            .values("pk")[:1]
        )
        result = self.filter(
            user=user,
            unit__isnull=False,
            action__in=ACTIONS_REVERTABLE,
        )
        if project is not None:
            result = result.filter(project=project)
        return cast(
            "ChangeQuerySet",
            result.annotate(
                latest_revertable_change_id=Subquery(latest_revertable_change)
            )
            .filter(pk=F("latest_revertable_change_id"))
            .select_related("unit"),
        )

    def revert_user_edits(
        self,
        target_user: User,
        acting_user: User,
        *,
        project: Project | None = None,
        request=None,
    ) -> RevertUserEditsResult:
        base = self.filter(
            user=target_user,
            unit__isnull=False,
            action__in=ACTIONS_REVERTABLE,
        )
        if project is not None:
            base = base.filter(project=project)

        reverted = 0
        attempted = 0
        skipped_failed = 0
        total = base.values("unit_id").distinct().count()
        for change in self.latest_revertable_changes(
            target_user, project=project
        ).iterator(chunk_size=100):
            attempted += 1
            if change.revert_user_edits(
                acting_user,
                change_action=ActionEvents.USER_REVERT,
                request=request,
                change_details={"username": target_user.username},
            ):
                reverted += 1
            else:
                skipped_failed += 1

        skipped_newer = total - attempted
        return {
            "reverted": reverted,
            "skipped": skipped_newer + skipped_failed,
            "skipped_newer": skipped_newer,
            "skipped_failed": skipped_failed,
        }


class Change(models.Model, UserDisplayMixin):
    ACTIONS_DICT: ClassVar[dict[int, StrOrPromise]] = dict(ActionEvents.choices)
    ACTION_STRINGS: ClassVar[dict[str, int]] = {
        name.lower().replace(" ", "-"): value for value, name in ActionEvents.choices
    }

    ACTIONS_REVERTABLE = ACTIONS_REVERTABLE
    ACTIONS_CONTENT = ACTIONS_CONTENT
    ACTIONS_REPOSITORY = ACTIONS_REPOSITORY
    ACTIONS_SHOW_CONTENT = ACTIONS_SHOW_CONTENT
    ACTIONS_MERGE_FAILURE = ACTIONS_MERGE_FAILURE
    ACTIONS_ADDON = ACTIONS_ADDON

    ACTION_NAMES: ClassVar[dict[str, int]] = {
        str(name): value for value, name in ActionEvents.choices
    }
    AUTO_ACTIONS: ClassVar[dict[ActionEvents, StrOrPromise]] = {
        # Translators: Name of event in the history
        ActionEvents.LOCK: gettext_lazy(
            "The component was automatically locked because of an alert."
        ),
        # Translators: Name of event in the history
        ActionEvents.UNLOCK: gettext_lazy(
            "Fixing an alert automatically unlocked the component."
        ),
    }

    unit = models.ForeignKey(
        "trans.Unit", null=True, on_delete=models.deletion.CASCADE, db_index=False
    )
    language = models.ForeignKey(
        "lang.Language", null=True, on_delete=models.deletion.CASCADE, db_index=False
    )
    project = models.ForeignKey(
        "trans.Project", null=True, on_delete=models.deletion.CASCADE, db_index=False
    )
    category = models.ForeignKey(
        "trans.Category", null=True, on_delete=models.deletion.CASCADE, db_index=False
    )
    component = models.ForeignKey(
        "trans.Component", null=True, on_delete=models.deletion.CASCADE, db_index=False
    )
    translation = models.ForeignKey(
        "trans.Translation",
        null=True,
        on_delete=models.deletion.CASCADE,
        db_index=False,
    )
    comment = models.ForeignKey(
        "trans.Comment", null=True, on_delete=models.deletion.SET_NULL
    )
    suggestion = models.ForeignKey(
        "trans.Suggestion", null=True, on_delete=models.deletion.SET_NULL
    )
    announcement = models.ForeignKey(
        "trans.Announcement", null=True, on_delete=models.deletion.SET_NULL
    )
    screenshot = models.ForeignKey(
        "screenshots.Screenshot",
        null=True,
        on_delete=models.deletion.SET_NULL,
    )
    alert = models.ForeignKey(
        "trans.Alert", null=True, on_delete=models.deletion.SET_NULL
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.deletion.CASCADE
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        related_name="+",
        db_index=False,
        on_delete=models.deletion.CASCADE,
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    action = models.IntegerField(
        choices=ActionEvents.choices, default=ActionEvents.CHANGE
    )
    target = models.TextField(default="", blank=True)
    old = models.TextField(default="", blank=True)
    details = models.JSONField(default=dict)

    objects = ChangeManager.from_queryset(ChangeQuerySet)()

    class Meta:
        app_label = "trans"
        indexes = [  # noqa: RUF012
            models.Index(
                fields=["-timestamp", "action"],
                name="trans_change_action_idx",
            ),
            models.Index(
                fields=["project", "-timestamp", "action"],
                condition=Q(project__isnull=False),
                name="trans_change_project_idx",
            ),
            models.Index(
                fields=["language", "-timestamp", "action"],
                condition=Q(language__isnull=False),
                name="trans_change_language_idx",
            ),
            models.Index(
                fields=["project", "language", "-timestamp", "action"],
                condition=Q(project__isnull=False) & Q(language__isnull=False),
                name="trans_change_prj_language_idx",
            ),
            models.Index(
                fields=["component", "-timestamp", "action"],
                condition=Q(component__isnull=False),
                name="trans_change_component_idx",
            ),
            models.Index(
                fields=["translation", "-timestamp", "action"],
                condition=Q(translation__isnull=False),
                name="trans_change_translation_idx",
            ),
            models.Index(
                fields=["category", "-timestamp", "action"],
                condition=Q(category__isnull=False),
                name="trans_change_category_idx",
            ),
            models.Index(
                fields=["unit", "-timestamp", "action"],
                condition=Q(unit__isnull=False),
                name="trans_change_unit_idx",
            ),
            models.Index(
                fields=["user", "-timestamp", "action"],
                name="trans_change_user_idx",
            ),
        ]
        verbose_name = "history event"
        verbose_name_plural = "history events"

    def __str__(self) -> str:
        if self.user:
            # Translators: condensed rendering of a change action in history
            return gettext("%(action)s at %(time)s on %(translation)s by %(user)s") % {
                "action": self.get_action_display(),
                "time": self.timestamp,
                "translation": self.translation or self.component or self.project,
                "user": self.get_user_display(False),
            }
        # Translators: condensed rendering of a change action in history
        return gettext("%(action)s at %(time)s on %(translation)s") % {
            "action": self.get_action_display(),
            "time": self.timestamp,
            "translation": self.translation or self.component or self.project,
        }

    def __init__(self, *args, **kwargs) -> None:
        for attr in ("user", "author"):
            user = kwargs.get(attr)
            if user is not None and hasattr(user, "get_token_user"):
                # ProjectToken / ProjectUser integration
                kwargs[attr] = user.get_token_user()
        super().__init__(*args, **kwargs)
        if not self.pk:
            self.fixup_references()

    def save(self, *args, **kwargs) -> None:
        self.fixup_references()

        super().save(*args, **kwargs)

        if self.is_last_content_change_storable():
            translation = cast("Translation", self.translation)
            # Update cache for stats so that it does not have to hit
            # the database again
            translation.stats.last_change_cache = self
            # Update currently loaded
            if translation.stats.is_loaded:
                translation.stats.fetch_last_change()
            # Update stats at the end of transaction
            transaction.on_commit(self.update_cache_last_change)
            # Make sure stats is updated at the end of transaction
            translation.invalidate_cache()

        if self.action == ActionEvents.RENAME_PROJECT:
            Change.objects.generate_project_rename_lookup()

        self.log_event()

    def get_absolute_url(self) -> str:
        """Return link either to unit or translation."""
        if self.unit is not None:
            return self.unit.get_absolute_url()
        if self.screenshot is not None:
            return self.screenshot.get_absolute_url()
        if self.translation is not None:
            return self.translation.get_absolute_url()
        if self.component is not None:
            return self.component.get_absolute_url()
        if self.category is not None:
            return self.category.get_absolute_url()
        if self.project is not None:
            return self.project.get_absolute_url()
        return "/"

    def log_event(self) -> None:
        if self.action in ACTIONS_LOG:
            message = self.get_action_display()
            if self.user:
                message = f"{message} ({self.user.username})"
            if self.author and self.author != self.user:
                message = f"{message} ({self.author.username})"
            if self.target:
                message = f"{message}: {self.target}"
            if self.translation:
                self.translation.log_info("%s", message)
            elif self.component:
                self.component.log_info("%s", message)
            elif self.project:
                self.project.log_info("%s", message)
            else:
                LOGGER.info("%s", message)

    @property
    def path_object(self) -> Translation | Component | Category | Project | None:
        """Return link either to unit or translation."""
        if self.translation is not None:
            return self.translation
        if self.component is not None:
            return self.component
        if self.category is not None:
            return self.category
        if self.project is not None:
            return self.project
        return None

    @staticmethod
    def get_last_change_cache_key(translation_id: int) -> str:
        return f"last-content-change-{translation_id}"

    @classmethod
    def store_last_change(cls, translation: Translation, change: Change | None) -> None:
        translation.stats.last_change_cache = change
        cache_key = cls.get_last_change_cache_key(translation.id)
        cache.set(cache_key, change.pk if change else 0, 180 * 86400)

    def is_last_content_change_storable(self) -> bool:
        return self.translation_id is not None

    def update_cache_last_change(self) -> None:
        self.store_last_change(cast("Translation", self.translation), self)

    def fixup_references(self) -> None:
        """
        Update references based to least specific one.

        Update Change.fill_in_prefetched together with this one
        """
        if self.unit:
            self.translation = self.unit.translation
        if self.screenshot:
            self.translation = self.screenshot.translation
        if self.translation:
            self.component = self.translation.component
            self.language = self.translation.language
        if self.component:
            self.project = self.component.project
            self.category = self.component.category
        if (self.user is None or not self.user.is_authenticated) and (
            ip_address := self.get_ip_address()
        ):
            self.details["ip_address"] = ip_address

    @property
    def plural_count(self) -> int:
        return self.details.get("count", 1)

    @property
    def auto_status(self) -> bool:
        return self.details.get("auto", False)

    def get_action_display(self) -> str:  # type: ignore[no-redef]
        return str(self.ACTIONS_DICT.get(self.action, self.action))

    def get_state_display(self) -> StrOrPromise:
        state = self.details.get("state")
        if state is None:
            return ""
        return StringState(state).label

    def is_merge_failure(self) -> bool:
        return self.action in ACTIONS_MERGE_FAILURE

    def can_revert(self) -> bool:
        return (
            self.unit is not None
            and self.action in ACTIONS_REVERTABLE
            and "old_state" in self.details
        )

    def get_revert_state(self) -> StringState:
        return StringState(self.details["old_state"])

    def get_latest_user_revert_target(self) -> tuple[str, StringState] | None:
        if self.unit_id is None or self.user_id is None:
            return None

        boundary_old: str | None = None
        boundary_state: StringState | None = None
        history = (
            Change.objects.filter(unit_id=self.unit_id, action__in=ACTIONS_REVERTABLE)
            .order_by("-timestamp", "-pk")
            .values_list("pk", "user_id", "old", "details")
        )
        for pk, user_id, old, details in history.iterator(chunk_size=100):
            if boundary_old is None and (pk != self.pk or user_id != self.user_id):
                return None
            if user_id != self.user_id:
                break
            if "old_state" not in details:
                return None
            boundary_old = old
            boundary_state = StringState(details["old_state"])

        if boundary_old is None or boundary_state is None:
            return None
        return boundary_old, boundary_state

    @transaction.atomic
    def revert_user_edits(
        self,
        user: User,
        *,
        change_action: ActionEvents = ActionEvents.USER_REVERT,
        author: User | None = None,
        request=None,
        change_details: dict[str, str] | None = None,
    ) -> bool:
        if self.unit is None or self.action not in ACTIONS_REVERTABLE:
            return False

        unit = cast("Unit", self.unit)
        locked_unit = unit.__class__.objects.select_for_update().get(pk=unit.pk)
        revert_target = self.get_latest_user_revert_target()
        if revert_target is None:
            return False

        target, state = revert_target
        return locked_unit.translate(
            user,
            split_plural(target),
            state,
            change_action=change_action,
            author=author,
            request=request,
            select_for_update=False,
            change_details=change_details,
        )

    @transaction.atomic
    def revert(
        self,
        user: User,
        *,
        change_action: ActionEvents = ActionEvents.REVERT,
        author: User | None = None,
        request=None,
        change_details: dict[str, str] | None = None,
    ) -> bool:
        if self.unit is None or self.action not in ACTIONS_REVERTABLE:
            return False

        unit = cast("Unit", self.unit)
        locked_unit = unit.__class__.objects.select_for_update().get(pk=unit.pk)
        if "old_state" not in self.details:
            return False

        return locked_unit.translate(
            user,
            split_plural(self.old),
            self.get_revert_state(),
            change_action=change_action,
            author=author,
            request=request,
            select_for_update=False,
            change_details=change_details,
        )

    def show_source(self) -> bool:
        """Whether to show content as source change."""
        return self.action in {
            ActionEvents.SOURCE_CHANGE,
            ActionEvents.NEW_SOURCE,
            ActionEvents.NEW_SOURCE_UPLOAD,
            ActionEvents.NEW_SOURCE_REPO,
        }

    def show_diff(self) -> bool:
        """Whether to show content as diff."""
        return self.action in {
            ActionEvents.EXPLANATION,
            ActionEvents.EXTRA_FLAGS,
        }

    def show_removed_string(self) -> bool:
        """Whether to show content as source change."""
        return self.action == ActionEvents.STRING_REMOVE

    def show_content(self) -> bool:
        """Whether to show content as translation."""
        return self.action in ACTIONS_SHOW_CONTENT or self.action in ACTIONS_REVERTABLE

    def get_details_display(self) -> StrOrPromise:
        from weblate.trans.change_display import (  # noqa: PLC0415
            ChangeDetailsRenderFactory,
        )

        strategy = ChangeDetailsRenderFactory.get_strategy(self)
        return strategy.render_details(self)

    def get_distance(self) -> int:
        return DamerauLevenshtein.distance(self.old, self.target)

    def get_source(self) -> str:
        return self.details.get("source", cast("Unit", self.unit).source)

    def get_ip_address(self) -> str | None:
        if ip_address := self.details.get("ip_address"):
            return ip_address
        if self.suggestion and (
            ip_address := self.suggestion.userdetails.get("address")
        ):
            return ip_address
        if self.comment and (ip_address := self.comment.userdetails.get("address")):
            return ip_address
        return None

    def show_unit_state(self) -> bool:
        return "state" in self.details and self.action not in {
            ActionEvents.SUGGESTION,
            ActionEvents.SUGGESTION_DELETE,
            ActionEvents.SUGGESTION_CLEANUP,
        }

    def get_uuid(self) -> UUID:
        """Return uuid for this change."""
        return uuid5(WEBLATE_UUID_NAMESPACE, f"{self.action}.{self.id}")

    def fill_in_prefetched(self) -> None:
        """
        Fill in prefetched data into nested objects.

        - Based on fixup_references.
        - Uses data from prefetch_for_render
        """
        if self.unit:
            self.unit.translation = cast("Translation", self.translation)
        if self.screenshot:
            self.screenshot.translation = cast("Translation", self.translation)
        if self.translation:
            self.translation.component = cast("Component", self.component)
            if self.language_id is not None:
                self.translation.language = cast("Language", self.language)
        if self.component:
            self.component.project = cast("Project", self.project)
            self.component.category = cast("Category", self.category)


@receiver(post_save, sender=Change)
@disable_for_loaddata
def change_notify(sender, instance: Change, created: bool = False, **kwargs) -> None:
    from weblate.accounts.notifications import (  # noqa: PLC0415
        dispatch_changes_notifications,
    )

    dispatch_changes_notifications([instance])
