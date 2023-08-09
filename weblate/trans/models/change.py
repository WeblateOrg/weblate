# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import datetime

from django.conf import settings
from django.core.cache import cache
from django.db import models, transaction
from django.db.models import Count, Q
from django.db.models.base import post_save
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.translation import (
    gettext,
    gettext_lazy,
    ngettext,
    ngettext_lazy,
    pgettext,
    pgettext_lazy,
)
from rapidfuzz.distance import DamerauLevenshtein

from weblate.lang.models import Language
from weblate.trans.mixins import UserDisplayMixin
from weblate.trans.models.alert import ALERTS
from weblate.trans.models.project import Project
from weblate.utils.pii import mask_email
from weblate.utils.state import STATE_LOOKUP


class ChangeQuerySet(models.QuerySet):
    def content(self, prefetch=False):
        """Return queryset with content changes."""
        base = self
        if prefetch:
            base = base.prefetch()
        return base.filter(action__in=Change.ACTIONS_CONTENT)

    def count_stats(self, days: int, step: int, dtstart: datetime):
        """Count the number of changes in a given period grouped by step days."""
        # Count number of changes
        result = []
        for _unused in range(0, days, step):
            # Calculate interval
            int_start = dtstart
            int_end = int_start + timezone.timedelta(days=step)

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
    ):
        """Core of daily/weekly/monthly stats calculation."""
        # Get range (actually start)
        dtstart = timezone.now() - timezone.timedelta(days=days + 1)

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

    def prefetch(self):
        """
        Fetch related fields at once to avoid loading them individually.

        Call prefetch or prefetch_list later on paginated results to complete.
        """
        return self.prefetch_related(
            "user",
            "translation",
            "component",
            "project",
            "component__source_language",
            "unit",
            "translation__language",
            "translation__plural",
        )

    @staticmethod
    def preload_list(results, *args):
        """Companion for prefetch to fill in nested references."""
        for item in results:
            if item.component and "component" not in args:
                item.component.project = item.project
            if item.translation and "translation" not in args:
                item.translation.component = item.component
            if item.unit and "unit" not in args:
                item.unit.translation = item.translation
        return results

    def preload(self, *args):
        """Companion for prefetch to fill in nested references."""
        return self.preload_list(self, *args)

    def last_changes(
        self, user, unit=None, translation=None, component=None, project=None
    ):
        """
        Return the most recent changes for an user.

        Filters Change objects by user permissions and fetches related fields for
        last changes display.
        """
        result = self
        if unit is not None:
            result = result.filter(unit=unit)
            if not user.can_access_component(unit.translation.component):
                result = result.none()
        elif translation is not None:
            result = result.filter(translation=translation)
            if not user.can_access_component(translation.component):
                result = result.none()
        elif component is not None:
            result = result.filter(component=component)
            if not user.can_access_component(component):
                result = result.none()
        elif project is not None:
            result = result.filter(project=project)
            if not user.can_access_project(project):
                result = result.none()
        elif not user.is_superuser:
            result = result.filter(
                Q(project__in=user.allowed_projects)
                & (
                    Q(component__isnull=True)
                    | Q(component__restricted=False)
                    | Q(component_id__in=user.component_permissions)
                )
            )
        return result.prefetch().order()

    def authors_list(self, date_range=None):
        """Return list of authors."""
        authors = self.content()
        if date_range is not None:
            authors = authors.filter(timestamp__range=date_range)
        return (
            authors.exclude(author__isnull=True)
            .values("author")
            .annotate(change_count=Count("id"))
            .values_list("author__email", "author__full_name", "change_count")
        )

    def order(self):
        return self.order_by("-timestamp")

    def bulk_create(self, *args, **kwargs):
        """Adds processing to bulk creation."""
        changes = super().bulk_create(*args, **kwargs)
        # Executes post save to ensure messages are sent to fedora messaging
        for change in changes:
            post_save.send(change.__class__, instance=change, created=True)
        # Store last content change in cache for improved performance
        for change in reversed(changes):
            if change.is_last_content_change_storable():
                transaction.on_commit(change.update_cache_last_change)
                break
        return changes


class ChangeManager(models.Manager):
    def create(self, *, user=None, **kwargs):
        """Wrapper to avoid using anonymous user as change owner."""
        if user is not None and not user.is_authenticated:
            user = None
        return super().create(user=user, **kwargs)


class Change(models.Model, UserDisplayMixin):
    ACTION_UPDATE = 0
    ACTION_COMPLETE = 1
    ACTION_CHANGE = 2
    ACTION_COMMENT = 3
    ACTION_SUGGESTION = 4
    ACTION_NEW = 5
    ACTION_AUTO = 6
    ACTION_ACCEPT = 7
    ACTION_REVERT = 8
    ACTION_UPLOAD = 9
    ACTION_NEW_SOURCE = 13
    ACTION_LOCK = 14
    ACTION_UNLOCK = 15
    # Used to be ACTION_DUPLICATE_STRING = 16
    ACTION_COMMIT = 17
    ACTION_PUSH = 18
    ACTION_RESET = 19
    ACTION_MERGE = 20
    ACTION_REBASE = 21
    ACTION_FAILED_MERGE = 22
    ACTION_FAILED_REBASE = 23
    ACTION_PARSE_ERROR = 24
    ACTION_REMOVE_TRANSLATION = 25
    ACTION_SUGGESTION_DELETE = 26
    ACTION_REPLACE = 27
    ACTION_FAILED_PUSH = 28
    ACTION_SUGGESTION_CLEANUP = 29
    ACTION_SOURCE_CHANGE = 30
    ACTION_NEW_UNIT = 31
    ACTION_BULK_EDIT = 32
    ACTION_ACCESS_EDIT = 33
    ACTION_ADD_USER = 34
    ACTION_REMOVE_USER = 35
    ACTION_APPROVE = 36
    ACTION_MARKED_EDIT = 37
    ACTION_REMOVE_COMPONENT = 38
    ACTION_REMOVE_PROJECT = 39
    # Used to be ACTION_DUPLICATE_LANGUAGE = 40
    ACTION_RENAME_PROJECT = 41
    ACTION_RENAME_COMPONENT = 42
    ACTION_MOVE_COMPONENT = 43
    ACTION_NEW_STRING = 44
    ACTION_NEW_CONTRIBUTOR = 45
    ACTION_ANNOUNCEMENT = 46
    ACTION_ALERT = 47
    ACTION_ADDED_LANGUAGE = 48
    ACTION_REQUESTED_LANGUAGE = 49
    ACTION_CREATE_PROJECT = 50
    ACTION_CREATE_COMPONENT = 51
    ACTION_INVITE_USER = 52
    ACTION_HOOK = 53
    ACTION_REPLACE_UPLOAD = 54
    ACTION_LICENSE_CHANGE = 55
    ACTION_AGREEMENT_CHANGE = 56
    ACTION_SCREENSHOT_ADDED = 57
    ACTION_SCREENSHOT_UPLOADED = 58
    ACTION_STRING_REPO_UPDATE = 59
    ACTION_ADDON_CREATE = 60
    ACTION_ADDON_CHANGE = 61
    ACTION_ADDON_REMOVE = 62
    ACTION_STRING_REMOVE = 63
    ACTION_COMMENT_DELETE = 64
    ACTION_COMMENT_RESOLVE = 65
    ACTION_EXPLANATION = 66

    ACTION_CHOICES = (
        # Translators: Name of event in the history
        (ACTION_UPDATE, gettext_lazy("Resource update")),
        # Translators: Name of event in the history
        (ACTION_COMPLETE, gettext_lazy("Translation completed")),
        # Translators: Name of event in the history
        (ACTION_CHANGE, gettext_lazy("Translation changed")),
        # Translators: Name of event in the history
        (ACTION_NEW, gettext_lazy("New translation")),
        # Translators: Name of event in the history
        (ACTION_COMMENT, gettext_lazy("Comment added")),
        # Translators: Name of event in the history
        (ACTION_SUGGESTION, gettext_lazy("Suggestion added")),
        # Translators: Name of event in the history
        (ACTION_AUTO, gettext_lazy("Automatic translation")),
        # Translators: Name of event in the history
        (ACTION_ACCEPT, gettext_lazy("Suggestion accepted")),
        # Translators: Name of event in the history
        (ACTION_REVERT, gettext_lazy("Translation reverted")),
        # Translators: Name of event in the history
        (ACTION_UPLOAD, gettext_lazy("Translation uploaded")),
        # Translators: Name of event in the history
        (ACTION_NEW_SOURCE, gettext_lazy("New source string")),
        # Translators: Name of event in the history
        (ACTION_LOCK, gettext_lazy("Component locked")),
        # Translators: Name of event in the history
        (ACTION_UNLOCK, gettext_lazy("Component unlocked")),
        # Translators: Name of event in the history
        (ACTION_COMMIT, gettext_lazy("Committed changes")),
        # Translators: Name of event in the history
        (ACTION_PUSH, gettext_lazy("Pushed changes")),
        # Translators: Name of event in the history
        (ACTION_RESET, gettext_lazy("Reset repository")),
        # Translators: Name of event in the history
        (ACTION_MERGE, gettext_lazy("Merged repository")),
        # Translators: Name of event in the history
        (ACTION_REBASE, gettext_lazy("Rebased repository")),
        # Translators: Name of event in the history
        (ACTION_FAILED_MERGE, gettext_lazy("Failed merge on repository")),
        # Translators: Name of event in the history
        (ACTION_FAILED_REBASE, gettext_lazy("Failed rebase on repository")),
        # Translators: Name of event in the history
        (ACTION_FAILED_PUSH, gettext_lazy("Failed push on repository")),
        # Translators: Name of event in the history
        (ACTION_PARSE_ERROR, gettext_lazy("Parse error")),
        # Translators: Name of event in the history
        (ACTION_REMOVE_TRANSLATION, gettext_lazy("Removed translation")),
        # Translators: Name of event in the history
        (ACTION_SUGGESTION_DELETE, gettext_lazy("Suggestion removed")),
        # Translators: Name of event in the history
        (ACTION_REPLACE, gettext_lazy("Search and replace")),
        # Translators: Name of event in the history
        (ACTION_SUGGESTION_CLEANUP, gettext_lazy("Suggestion removed during cleanup")),
        # Translators: Name of event in the history
        (ACTION_SOURCE_CHANGE, gettext_lazy("Source string changed")),
        # Translators: Name of event in the history
        (ACTION_NEW_UNIT, gettext_lazy("New string added")),
        # Translators: Name of event in the history
        (ACTION_BULK_EDIT, gettext_lazy("Bulk status change")),
        # Translators: Name of event in the history
        (ACTION_ACCESS_EDIT, gettext_lazy("Changed visibility")),
        # Translators: Name of event in the history
        (ACTION_ADD_USER, gettext_lazy("Added user")),
        # Translators: Name of event in the history
        (ACTION_REMOVE_USER, gettext_lazy("Removed user")),
        # Translators: Name of event in the history
        (ACTION_APPROVE, gettext_lazy("Translation approved")),
        # Translators: Name of event in the history
        (ACTION_MARKED_EDIT, gettext_lazy("Marked for edit")),
        # Translators: Name of event in the history
        (ACTION_REMOVE_COMPONENT, gettext_lazy("Removed component")),
        # Translators: Name of event in the history
        (ACTION_REMOVE_PROJECT, gettext_lazy("Removed project")),
        # Translators: Name of event in the history
        (ACTION_RENAME_PROJECT, gettext_lazy("Renamed project")),
        # Translators: Name of event in the history
        (ACTION_RENAME_COMPONENT, gettext_lazy("Renamed component")),
        # Translators: Name of event in the history
        (ACTION_MOVE_COMPONENT, gettext_lazy("Moved component")),
        # Using pgettext to differentiate from the plural
        # Translators: Name of event in the history
        (
            ACTION_NEW_STRING,
            pgettext_lazy("Name of event in the history", "New string to translate"),
        ),
        # Translators: Name of event in the history
        (ACTION_NEW_CONTRIBUTOR, gettext_lazy("New contributor")),
        # Translators: Name of event in the history
        (ACTION_ANNOUNCEMENT, gettext_lazy("New announcement")),
        # Translators: Name of event in the history
        (ACTION_ALERT, gettext_lazy("New alert")),
        # Translators: Name of event in the history
        (ACTION_ADDED_LANGUAGE, gettext_lazy("Added new language")),
        # Translators: Name of event in the history
        (ACTION_REQUESTED_LANGUAGE, gettext_lazy("Requested new language")),
        # Translators: Name of event in the history
        (ACTION_CREATE_PROJECT, gettext_lazy("Created project")),
        # Translators: Name of event in the history
        (ACTION_CREATE_COMPONENT, gettext_lazy("Created component")),
        # Translators: Name of event in the history
        (ACTION_INVITE_USER, gettext_lazy("Invited user")),
        # Translators: Name of event in the history
        (ACTION_HOOK, gettext_lazy("Received repository notification")),
        # Translators: Name of event in the history
        (ACTION_REPLACE_UPLOAD, gettext_lazy("Replaced file by upload")),
        # Translators: Name of event in the history
        (ACTION_LICENSE_CHANGE, gettext_lazy("License changed")),
        # Translators: Name of event in the history
        (ACTION_AGREEMENT_CHANGE, gettext_lazy("Contributor agreement changed")),
        # Translators: Name of event in the history
        (ACTION_SCREENSHOT_ADDED, gettext_lazy("Screnshot added")),
        # Translators: Name of event in the history
        (ACTION_SCREENSHOT_UPLOADED, gettext_lazy("Screnshot uploaded")),
        # Translators: Name of event in the history
        (ACTION_STRING_REPO_UPDATE, gettext_lazy("String updated in the repository")),
        # Translators: Name of event in the history
        (ACTION_ADDON_CREATE, gettext_lazy("Add-on installed")),
        # Translators: Name of event in the history
        (ACTION_ADDON_CHANGE, gettext_lazy("Add-on configuration changed")),
        # Translators: Name of event in the history
        (ACTION_ADDON_REMOVE, gettext_lazy("Add-on uninstalled")),
        # Translators: Name of event in the history
        (ACTION_STRING_REMOVE, gettext_lazy("Removed string")),
        # Translators: Name of event in the history
        (ACTION_COMMENT_DELETE, gettext_lazy("Removed comment")),
        # Translators: Name of event in the history
        (
            ACTION_COMMENT_RESOLVE,
            pgettext_lazy("Name of event in the history", "Resolved comment"),
        ),
        # Translators: Name of event in the history
        (ACTION_EXPLANATION, gettext_lazy("Explanation updated")),
    )
    ACTIONS_DICT = dict(ACTION_CHOICES)
    ACTION_STRINGS = {
        name.lower().replace(" ", "-"): value for value, name in ACTION_CHOICES
    }
    ACTION_NAMES = {str(name): value for value, name in ACTION_CHOICES}

    # Actions which can be reverted
    ACTIONS_REVERTABLE = {
        ACTION_ACCEPT,
        ACTION_REVERT,
        ACTION_CHANGE,
        ACTION_UPLOAD,
        ACTION_NEW,
        ACTION_REPLACE,
        ACTION_AUTO,
        ACTION_APPROVE,
        ACTION_MARKED_EDIT,
        ACTION_STRING_REPO_UPDATE,
    }

    # Content changes considered when looking for last author
    ACTIONS_CONTENT = {
        ACTION_CHANGE,
        ACTION_NEW,
        ACTION_AUTO,
        ACTION_ACCEPT,
        ACTION_REVERT,
        ACTION_UPLOAD,
        ACTION_REPLACE,
        ACTION_BULK_EDIT,
        ACTION_APPROVE,
        ACTION_MARKED_EDIT,
        ACTION_SOURCE_CHANGE,
        ACTION_EXPLANATION,
    }

    # Actions shown on the repository management page
    ACTIONS_REPOSITORY = {
        ACTION_COMMIT,
        ACTION_PUSH,
        ACTION_RESET,
        ACTION_MERGE,
        ACTION_REBASE,
        ACTION_FAILED_MERGE,
        ACTION_FAILED_REBASE,
        ACTION_FAILED_PUSH,
        ACTION_LOCK,
        ACTION_UNLOCK,
    }

    # Actions where target is rendered as translation string
    ACTIONS_SHOW_CONTENT = {
        ACTION_SUGGESTION,
        ACTION_SUGGESTION_DELETE,
        ACTION_SUGGESTION_CLEANUP,
        ACTION_BULK_EDIT,
        ACTION_NEW_UNIT,
        ACTION_STRING_REPO_UPDATE,
    }

    # Actions indicating a repository merge failure
    ACTIONS_MERGE_FAILURE = {
        ACTION_FAILED_MERGE,
        ACTION_FAILED_REBASE,
        ACTION_FAILED_PUSH,
    }

    PLURAL_ACTIONS = {
        ACTION_NEW_STRING: ngettext_lazy(
            "New string to translate", "New strings to translate"
        ),
    }
    AUTO_ACTIONS = {
        # Translators: Name of event in the history
        ACTION_LOCK: gettext_lazy(
            "The component was automatically locked because of an alert."
        ),
        # Translators: Name of event in the history
        ACTION_UNLOCK: gettext_lazy(
            "Fixing an alert automatically unlocked the component."
        ),
    }

    unit = models.ForeignKey("Unit", null=True, on_delete=models.deletion.CASCADE)
    language = models.ForeignKey(
        "lang.Language", null=True, on_delete=models.deletion.CASCADE
    )
    project = models.ForeignKey("Project", null=True, on_delete=models.deletion.CASCADE)
    component = models.ForeignKey(
        "Component", null=True, on_delete=models.deletion.CASCADE
    )
    translation = models.ForeignKey(
        "Translation", null=True, on_delete=models.deletion.CASCADE
    )
    comment = models.ForeignKey(
        "Comment", null=True, on_delete=models.deletion.SET_NULL
    )
    suggestion = models.ForeignKey(
        "Suggestion", null=True, on_delete=models.deletion.SET_NULL
    )
    announcement = models.ForeignKey(
        "Announcement", null=True, on_delete=models.deletion.SET_NULL
    )
    screenshot = models.ForeignKey(
        "screenshots.Screenshot", null=True, on_delete=models.deletion.SET_NULL
    )
    alert = models.ForeignKey("Alert", null=True, on_delete=models.deletion.SET_NULL)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.deletion.CASCADE
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        related_name="author_set",
        on_delete=models.deletion.CASCADE,
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    action = models.IntegerField(
        choices=ACTION_CHOICES, default=ACTION_CHANGE, db_index=True
    )
    target = models.TextField(default="", blank=True)
    old = models.TextField(default="", blank=True)
    details = models.JSONField(default=dict)

    objects = ChangeManager.from_queryset(ChangeQuerySet)()

    class Meta:
        app_label = "trans"
        indexes = [
            models.Index(
                fields=["timestamp", "project", "component", "language", "action"]
            ),
            models.Index(fields=["action", "translation", "timestamp"]),
            models.Index(fields=["user", "timestamp"]),
        ]
        verbose_name = "history event"
        verbose_name_plural = "history events"

    def __str__(self):
        return gettext("%(action)s at %(time)s on %(translation)s by %(user)s") % {
            "action": self.get_action_display(),
            "time": self.timestamp,
            "translation": self.translation,
            "user": self.get_user_display(False),
        }

    def save(self, *args, **kwargs):
        from weblate.accounts.tasks import notify_change

        self.fixup_refereces()

        super().save(*args, **kwargs)
        transaction.on_commit(lambda: notify_change.delay(self.pk))
        if self.is_last_content_change_storable():
            transaction.on_commit(self.update_cache_last_change)

    def get_absolute_url(self):
        """Return link either to unit or translation."""
        if self.unit is not None:
            return self.unit.get_absolute_url()
        if self.screenshot is not None:
            return self.screenshot.get_absolute_url()
        if self.translation is not None:
            if self.action == self.ACTION_NEW_STRING:
                return self.translation.get_translate_url() + "?q=is:untranslated"
            return self.translation.get_absolute_url()
        if self.component is not None:
            return self.component.get_absolute_url()
        if self.project is not None:
            return self.project.get_absolute_url()
        return None

    def __init__(self, *args, **kwargs):
        self.notify_state = {}
        for attr in ("user", "author"):
            user = kwargs.get(attr)
            if user is not None and hasattr(user, "get_token_user"):
                # ProjectToken / ProjectUser integration
                kwargs[attr] = user.get_token_user()
        super().__init__(*args, **kwargs)
        if not self.pk:
            self.fixup_refereces()

    @staticmethod
    def get_last_change_cache_key(translation_id: int):
        return f"last-content-change-{translation_id}"

    def is_last_content_change_storable(self):
        return self.translation_id and self.action in self.ACTIONS_CONTENT

    def update_cache_last_change(self):
        cache_key = self.get_last_change_cache_key(self.translation_id)
        cache.set(cache_key, self.pk, 180 * 86400)
        return True

    def fixup_refereces(self):
        """Updates references based to least specific one."""
        if self.unit:
            self.translation = self.unit.translation
        if self.screenshot:
            self.translation = self.screenshot.translation
        if self.translation:
            self.component = self.translation.component
            self.language = self.translation.language
        if self.component:
            self.project = self.component.project

    @property
    def plural_count(self):
        return self.details.get("count", 1)

    @property
    def auto_status(self):
        return self.details.get("auto", False)

    def get_action_display(self):
        if self.action in self.PLURAL_ACTIONS:
            return self.PLURAL_ACTIONS[self.action] % self.plural_count
        return str(self.ACTIONS_DICT.get(self.action, self.action))

    def get_state_display(self):
        state = self.details.get("state")
        if not state:
            return ""
        return STATE_LOOKUP[state]

    def is_merge_failure(self):
        return self.action in self.ACTIONS_MERGE_FAILURE

    def can_revert(self):
        return (
            self.unit is not None
            and self.old
            and self.action in self.ACTIONS_REVERTABLE
        )

    def show_source(self):
        """Whether to show content as source change."""
        return self.action in (self.ACTION_SOURCE_CHANGE, self.ACTION_NEW_SOURCE)

    def show_removed_string(self):
        """Whether to show content as source change."""
        return self.action == self.ACTION_STRING_REMOVE

    def show_content(self):
        """Whether to show content as translation."""
        return (
            self.action in self.ACTIONS_SHOW_CONTENT
            or self.action in self.ACTIONS_REVERTABLE
        )

    def get_details_display(self):  # noqa: C901
        from weblate.addons.models import ADDONS
        from weblate.utils.markdown import render_markdown

        details = self.details

        if self.action == self.ACTION_NEW_STRING:
            result = ngettext(
                "%d new string to translate appeared in the translation.",
                "%d new strings to translate appeared to the translation.",
                self.plural_count,
            )
            try:
                return result % self.plural_count
            except TypeError:
                # The string does not contain %d
                return result

        if self.action in (self.ACTION_ANNOUNCEMENT, self.ACTION_AGREEMENT_CHANGE):
            return render_markdown(self.target)

        if self.action in (
            self.ACTION_ADDON_CREATE,
            self.ACTION_ADDON_CHANGE,
            self.ACTION_ADDON_REMOVE,
        ):
            try:
                return ADDONS[self.target].name
            except KeyError:
                return self.target

        if self.action in self.AUTO_ACTIONS and self.auto_status:
            return str(self.AUTO_ACTIONS[self.action])

        if self.action == self.ACTION_UPDATE:
            reason = details.get("reason", "content changed")
            filename = format_html(
                "<code>{}</code>",
                details.get(
                    "filename",
                    self.translation.filename if self.translation else "",
                ),
            )
            if reason == "content changed":
                return format_html(
                    escape(gettext('The "{}" file was changed.')), filename
                )
            if reason == "check forced":
                return format_html(
                    escape(gettext('Parsing of the "{}" file was enforced.')), filename
                )
            if reason == "new file":
                return format_html(escape(gettext("File {} was added.")), filename)
            raise ValueError(f"Unknown reason: {reason}")

        if self.action == self.ACTION_LICENSE_CHANGE:
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
            self.ACTION_ADD_USER,
            self.ACTION_INVITE_USER,
            self.ACTION_REMOVE_USER,
        }
        if self.action == self.ACTION_ACCESS_EDIT:
            for number, name in Project.ACCESS_CHOICES:
                if number == details["access_control"]:
                    return name
            return "Unknown {}".format(details["access_control"])
        if self.action in user_actions:
            if "username" in details:
                result = details["username"]
            else:
                result = mask_email(details["email"])
            if "group" in details:
                result = "result ({details['group']})"
            return result
        if self.action in (
            self.ACTION_ADDED_LANGUAGE,
            self.ACTION_REQUESTED_LANGUAGE,
        ):
            try:
                return Language.objects.get(code=details["language"])
            except Language.DoesNotExist:
                return details["language"]
        if self.action == self.ACTION_ALERT:
            try:
                return ALERTS[details["alert"]].verbose
            except KeyError:
                return details["alert"]
        if self.action == self.ACTION_PARSE_ERROR:
            return "{filename}: {error_message}".format(**details)
        if self.action == self.ACTION_HOOK:
            return "{service_long_name}: {repo_url}, {branch}".format(**details)
        if self.action == self.ACTION_COMMENT and "comment" in details:
            return render_markdown(details["comment"])

        return ""

    def get_distance(self):
        return DamerauLevenshtein.distance(self.old, self.target)

    def get_source(self):
        return self.details.get("source", self.unit.source)

    def get_ip_address(self):
        if self.suggestion and "address" in self.suggestion.userdetails:
            return self.suggestion.userdetails["address"]
        if self.comment and "address" in self.comment.userdetails:
            return self.comment.userdetails["address"]
        return None

    def show_unit_state(self):
        return "state" in self.details and self.action not in (
            self.ACTION_SUGGESTION,
            self.ACTION_SUGGESTION_DELETE,
            self.ACTION_SUGGESTION_CLEANUP,
        )
