# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, overload
from uuid import UUID, uuid5

import sentry_sdk
from django.conf import settings
from django.core.cache import cache
from django.db import connection, models, transaction
from django.db.models import Count, Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.translation import gettext, gettext_lazy, pgettext
from rapidfuzz.distance import DamerauLevenshtein

from weblate.lang.models import Language
from weblate.trans.actions import (
    ACTIONS_ADDON,
    ACTIONS_CONTENT,
    ACTIONS_MERGE_FAILURE,
    ACTIONS_REPOSITORY,
    ACTIONS_REVERTABLE,
    ACTIONS_SHOW_CONTENT,
    ActionEvents,
)
from weblate.trans.mixins import UserDisplayMixin
from weblate.trans.models.alert import ALERTS
from weblate.trans.models.project import Project
from weblate.trans.signals import change_bulk_create
from weblate.utils.const import WEBLATE_UUID_NAMESPACE
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.files import FileUploadMethod, get_upload_message
from weblate.utils.pii import mask_email
from weblate.utils.state import StringState

if TYPE_CHECKING:
    from collections.abc import Iterable

    from weblate.auth.models import User
    from weblate.trans.models import Translation


CHANGE_PROJECT_LOOKUP_KEY = "change:project-lookup"

PREFETCH_FIELDS = (
    "user",
    "author",
    "translation",
    "component",
    "project",
    "component__source_language",
    "unit",
    "unit__source_unit",
    "translation__language",
    "translation__plural",
)


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
    def content(self, prefetch=False) -> ChangeQuerySet:
        """Return queryset with content changes."""
        base = self
        if prefetch:
            base = base.prefetch()
        return base.filter(action__in=ACTIONS_CONTENT)

    def for_category(self, category) -> ChangeQuerySet:
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
        project=None,
        component=None,
        translation=None,
        language=None,
        user=None,
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
        from weblate.accounts.notifications import dispatch_changes_notifications

        if connection.features.can_return_rows_from_bulk_insert:
            changes = super().bulk_create(*args, **kwargs)

            # Dispatch notifications
            dispatch_changes_notifications(changes)

            # Executes post save to ensure messages are sent to fedora messaging
            change_bulk_create.send(Change, instances=changes)
        else:
            # bulk_create doesn't set the .pk of instance with MySQL
            # Save each instance individually in order to set it
            changes = []
            for change in args[0]:
                change.save()
                changes.append(change)

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
    def create(self, *, user=None, **kwargs):
        """
        Create a change object.

        Wrapper to avoid using anonymous user as change owner.
        """
        if user is not None and not user.is_authenticated:
            user = None
        return super().create(user=user, **kwargs)

    def last_changes(
        self,
        user,
        unit=None,
        translation=None,
        component=None,
        project=None,
        category=None,
        language=None,
    ):
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
            result = self.filter_projects(user).filter_components(user)
        return result.prefetch_for_render().order()


class Change(models.Model, UserDisplayMixin):
    ACTIONS_DICT = dict(ActionEvents.choices)
    ACTION_STRINGS = {
        name.lower().replace(" ", "-"): value for value, name in ActionEvents.choices
    }

    ACTIONS_REVERTABLE = ACTIONS_REVERTABLE
    ACTIONS_CONTENT = ACTIONS_CONTENT
    ACTIONS_REPOSITORY = ACTIONS_REPOSITORY
    ACTIONS_SHOW_CONTENT = ACTIONS_SHOW_CONTENT
    ACTIONS_MERGE_FAILURE = ACTIONS_MERGE_FAILURE
    ACTIONS_ADDON = ACTIONS_ADDON

    ACTION_NAMES = {str(name): value for value, name in ActionEvents.choices}
    AUTO_ACTIONS = {
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
        indexes = [
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
        self.notify_state = {}
        for attr in ("user", "author"):
            user = kwargs.get(attr)
            if user is not None and hasattr(user, "get_token_user"):
                # ProjectToken / ProjectUser integration
                kwargs[attr] = user.get_token_user()
        super().__init__(*args, **kwargs)
        if not self.pk:
            self.fixup_refereces()

    def save(self, *args, **kwargs) -> None:
        self.fixup_refereces()

        super().save(*args, **kwargs)

        if self.is_last_content_change_storable():
            # Update cache for stats so that it does not have to hit
            # the database again
            self.translation.stats.last_change_cache = self
            # Update currently loaded
            if self.translation.stats.is_loaded:
                self.translation.stats.fetch_last_change()
            # Update stats at the end of transaction
            transaction.on_commit(self.update_cache_last_change)
            # Make sure stats is updated at the end of transaction
            self.translation.invalidate_cache()

        if self.action == ActionEvents.RENAME_PROJECT:
            Change.objects.generate_project_rename_lookup()

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

    @property
    def path_object(self):
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
        self.store_last_change(self.translation, self)

    def fixup_refereces(self) -> None:
        """Update references based to least specific one."""
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
    def plural_count(self):
        return self.details.get("count", 1)

    @property
    def auto_status(self):
        return self.details.get("auto", False)

    def get_action_display(self):
        return str(self.ACTIONS_DICT.get(self.action, self.action))

    def get_state_display(self):
        state = self.details.get("state")
        if state is None:
            return ""
        return StringState(state).label

    def is_merge_failure(self):
        return self.action in ACTIONS_MERGE_FAILURE

    def can_revert(self):
        return self.unit is not None and self.old and self.action in ACTIONS_REVERTABLE

    def show_source(self):
        """Whether to show content as source change."""
        return self.action in {
            ActionEvents.SOURCE_CHANGE,
            ActionEvents.NEW_SOURCE,
        }

    def show_diff(self):
        """Whether to show content as diff."""
        return self.action in {
            ActionEvents.EXPLANATION,
            ActionEvents.EXTRA_FLAGS,
        }

    def show_removed_string(self):
        """Whether to show content as source change."""
        return self.action == ActionEvents.STRING_REMOVE

    def show_content(self):
        """Whether to show content as translation."""
        return self.action in ACTIONS_SHOW_CONTENT or self.action in ACTIONS_REVERTABLE

    def get_details_display(self):  # noqa: C901
        from weblate.addons.models import ADDONS
        from weblate.utils.markdown import render_markdown

        details = self.details
        action = self.action

        if action == ActionEvents.FILE_UPLOAD:
            try:
                method = FileUploadMethod[details["method"].upper()].label
            except KeyError:
                method = details["method"]
            return format_html(
                "{}<br>{} {}",
                get_upload_message(
                    details["not_found"],
                    details["skipped"],
                    details["accepted"],
                    details["total"],
                ),
                gettext("File upload mode:"),
                method,
            )

        if action in {
            ActionEvents.ANNOUNCEMENT,
            ActionEvents.AGREEMENT_CHANGE,
        }:
            return render_markdown(self.target)

        if action == ActionEvents.COMMENT_DELETE and "comment" in details:
            return render_markdown(details["comment"])

        if action in {
            ActionEvents.ADDON_CREATE,
            ActionEvents.ADDON_CHANGE,
            ActionEvents.ADDON_REMOVE,
        }:
            try:
                return ADDONS[self.target].name
            except KeyError:
                return self.target

        if action in self.AUTO_ACTIONS and self.auto_status:
            return str(self.AUTO_ACTIONS[action])

        if action == ActionEvents.UPDATE:
            reason = details.get("reason", "content changed")
            filename = format_html(
                "<code>{}</code>",
                details.get(
                    "filename",
                    self.translation.filename if self.translation else "",
                ),
            )
            if reason == "content changed":
                message = gettext("The “{}” file was changed.")
            elif reason == "check forced":
                message = gettext("Parsing of the “{}” file was enforced.")
            elif reason == "new file":
                message = gettext("File “{}” was added.")
            else:
                msg = f"Unknown reason: {reason}"
                raise ValueError(msg)
            return format_html(escape(message), filename)

        if action == ActionEvents.LICENSE_CHANGE:
            not_available = pgettext("License information not available", "N/A")
            return gettext(
                'The license of the "%(component)s" component was changed '
                "from %(old)s to %(target)s."
            ) % {
                "component": self.component,
                "old": self.old or not_available,
                "target": self.target or not_available,
            }

        # Following rendering relies on details present
        if not details:
            return ""
        user_actions = {
            ActionEvents.ADD_USER,
            ActionEvents.INVITE_USER,
            ActionEvents.REMOVE_USER,
        }
        if action == ActionEvents.ACCESS_EDIT:
            for number, name in Project.ACCESS_CHOICES:
                if number == details["access_control"]:
                    return name
            return "Unknown {}".format(details["access_control"])
        if action in user_actions:
            if "username" in details:
                result = details["username"]
            else:
                result = mask_email(details["email"])
            if "group" in details:
                result = f"{result} ({details['group']})"
            return result
        if action in {
            ActionEvents.ADDED_LANGUAGE,
            ActionEvents.REQUESTED_LANGUAGE,
        }:
            try:
                return Language.objects.get(code=details["language"])
            except Language.DoesNotExist:
                return details["language"]
        if action == ActionEvents.ALERT:
            try:
                return ALERTS[details["alert"]].verbose
            except KeyError:
                return details["alert"]
        if action == ActionEvents.PARSE_ERROR:
            return "{filename}: {error_message}".format(**details)
        if action == ActionEvents.HOOK:
            return "{service_long_name}: {repo_url}, {branch}".format(**details)
        if action == ActionEvents.COMMENT and "comment" in details:
            return render_markdown(details["comment"])
        if action in {
            ActionEvents.RESET,
            ActionEvents.MERGE,
            ActionEvents.REBASE,
        }:
            return format_html(
                "{}<br/><br/>{}<br/>{}",
                self.get_action_display(),
                format_html(
                    escape(gettext("Original revision: {}")),
                    details.get("previous_head", "N/A"),
                ),
                format_html(
                    escape(gettext("New revision: {}")),
                    details.get("new_head", "N/A"),
                ),
            )

        return ""

    def get_distance(self):
        return DamerauLevenshtein.distance(self.old, self.target)

    def get_source(self):
        return self.details.get("source", self.unit.source)

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

    def show_unit_state(self):
        return "state" in self.details and self.action not in {
            ActionEvents.SUGGESTION,
            ActionEvents.SUGGESTION_DELETE,
            ActionEvents.SUGGESTION_CLEANUP,
        }

    def get_uuid(self) -> UUID:
        """Return uuid for this change."""
        return uuid5(WEBLATE_UUID_NAMESPACE, f"{self.action}.{self.id}")


@receiver(post_save, sender=Change)
@disable_for_loaddata
def change_notify(sender, instance, created=False, **kwargs) -> None:
    from weblate.accounts.notifications import dispatch_changes_notifications

    dispatch_changes_notifications([instance])
