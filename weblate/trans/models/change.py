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

from django.conf import settings
from django.db import models, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext_lazy, pgettext
from jellyfish import damerau_levenshtein_distance

from weblate.lang.models import Language
from weblate.trans.mixins import UserDisplayMixin
from weblate.trans.models.alert import ALERTS
from weblate.trans.models.project import Project
from weblate.utils.fields import JSONField


class ChangeQuerySet(models.QuerySet):
    # pylint: disable=no-init

    def content(self, prefetch=False):
        """Return queryset with content changes."""
        base = self
        if prefetch:
            base = base.prefetch()
        return base.filter(action__in=Change.ACTIONS_CONTENT)

    @staticmethod
    def count_stats(days, step, dtstart, base):
        """Count number of changes in given dataset and period grouped by step days."""
        # Count number of changes
        result = []
        for _unused in range(0, days, step):
            # Calculate interval
            int_start = dtstart
            int_end = int_start + timezone.timedelta(days=step)

            # Count changes
            int_base = base.filter(timestamp__range=(int_start, int_end))
            count = int_base.aggregate(Count("id"))

            # Append to result
            result.append((int_start, count["id__count"]))

            # Advance to next interval
            dtstart = int_end

        return result

    def base_stats(
        self,
        days,
        step,
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

        return self.count_stats(days, step, dtstart, base)

    def prefetch(self):
        """Fetch related fields in a big chungs to avoid loading them individually."""
        return self.prefetch_related(
            "user",
            "translation",
            "component",
            "project",
            "unit",
            "translation__language",
            "translation__component",
            "translation__component__project",
            "unit__translation",
            "unit__translation__language",
            "unit__translation__plural",
            "unit__translation__component",
            "unit__translation__component__project",
            "component__project",
        )

    def last_changes(self, user):
        """Return last changes for an user.

        Prefilter Changes by ACL for users and fetches related fields for last changes
        display.
        """
        if user.is_superuser:
            return self.prefetch().order()
        return (
            self.prefetch()
            .filter(
                Q(project_id__in=user.allowed_project_ids)
                & (
                    Q(component__isnull=True)
                    | Q(component__restricted=False)
                    | Q(component_id__in=user.component_permissions)
                )
            )
            .order()
        )

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


class ChangeManager(models.Manager):
    def create(self, user=None, **kwargs):
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
    ACTION_DUPLICATE_STRING = 16
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
    ACTION_DUPLICATE_LANGUAGE = 40
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
        (ACTION_DUPLICATE_STRING, gettext_lazy("Found duplicated string")),
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
        (ACTION_DUPLICATE_LANGUAGE, gettext_lazy("Found duplicated language")),
        # Translators: Name of event in the history
        (ACTION_RENAME_PROJECT, gettext_lazy("Renamed project")),
        # Translators: Name of event in the history
        (ACTION_RENAME_COMPONENT, gettext_lazy("Renamed component")),
        # Translators: Name of event in the history
        (ACTION_MOVE_COMPONENT, gettext_lazy("Moved component")),
        # Not translated, used plural instead
        (ACTION_NEW_STRING, "New string to translate"),
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
        ACTION_DUPLICATE_LANGUAGE,
    }

    # Actions where target is rendered as translation string
    ACTIONS_SHOW_CONTENT = {
        ACTION_SUGGESTION,
        ACTION_SUGGESTION_DELETE,
        ACTION_SUGGESTION_CLEANUP,
        ACTION_BULK_EDIT,
        ACTION_NEW_UNIT,
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
        ACTION_LOCK: gettext_lazy("Component automatically locked"),
        # Translators: Name of event in the history
        ACTION_UNLOCK: gettext_lazy("Component automatically unlocked"),
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
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.IntegerField(
        choices=ACTION_CHOICES, default=ACTION_CHANGE, db_index=True
    )
    target = models.TextField(default="", blank=True)
    old = models.TextField(default="", blank=True)
    details = JSONField()

    objects = ChangeManager.from_queryset(ChangeQuerySet)()

    class Meta:
        app_label = "trans"
        index_together = [
            ("translation", "action", "timestamp"),
        ]
        verbose_name = "history event"
        verbose_name_plural = "history events"

    def __str__(self):
        return _("%(action)s at %(time)s on %(translation)s by %(user)s") % {
            "action": self.get_action_display(),
            "time": self.timestamp,
            "translation": self.translation,
            "user": self.get_user_display(False),
        }

    def save(self, *args, **kwargs):
        from weblate.accounts.tasks import notify_change

        if self.unit:
            self.translation = self.unit.translation
        if self.screenshot:
            self.translation = self.screenshot.translation
        if self.translation:
            self.component = self.translation.component
            self.language = self.translation.language
        if self.component:
            self.project = self.component.project
        super().save(*args, **kwargs)
        transaction.on_commit(lambda: notify_change.delay(self.pk))

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
        super().__init__(*args, **kwargs)

    @property
    def plural_count(self):
        return self.details.get("count", 1)

    @property
    def auto_status(self):
        return self.details.get("auto", False)

    def get_action_display(self):
        if self.action in self.PLURAL_ACTIONS:
            return self.PLURAL_ACTIONS[self.action] % self.plural_count
        if self.action in self.AUTO_ACTIONS and self.auto_status:
            return str(self.AUTO_ACTIONS[self.action])
        return str(self.ACTIONS_DICT.get(self.action, self.action))

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
        return self.action == self.ACTION_SOURCE_CHANGE

    def show_content(self):
        """Whether to show content as translation."""
        return (
            self.action in self.ACTIONS_SHOW_CONTENT
            or self.action in self.ACTIONS_REVERTABLE
        )

    def get_details_display(self):  # noqa: C901
        from weblate.utils.markdown import render_markdown

        if self.action in (self.ACTION_ANNOUNCEMENT, self.ACTION_AGREEMENT_CHANGE):
            return render_markdown(self.target)

        if self.action == self.ACTION_LICENSE_CHANGE:
            not_available = pgettext("License information not available", "N/A")
            return _(
                "License for component %(component)s was changed "
                "from %(old)s to %(target)s."
            ) % {
                "component": self.component,
                "old": self.old or not_available,
                "target": self.target or not_available,
            }

        # Following rendering relies on details present
        if not self.details:
            return ""
        user_actions = {
            self.ACTION_ADD_USER,
            self.ACTION_INVITE_USER,
            self.ACTION_REMOVE_USER,
        }
        if self.action == self.ACTION_ACCESS_EDIT:
            for number, name in Project.ACCESS_CHOICES:
                if number == self.details["access_control"]:
                    return name
            return "Unknonwn {}".format(self.details["access_control"])
        if self.action in user_actions:
            if "group" in self.details:
                return "{username} ({group})".format(**self.details)
            return self.details["username"]
        if self.action in (
            self.ACTION_ADDED_LANGUAGE,
            self.ACTION_REQUESTED_LANGUAGE,
        ):  # noqa: E501
            try:
                return Language.objects.get(code=self.details["language"])
            except Language.DoesNotExist:
                return self.details["language"]
        if self.action == self.ACTION_ALERT:
            try:
                return ALERTS[self.details["alert"]].verbose
            except KeyError:
                return self.details["alert"]
        if self.action == self.ACTION_PARSE_ERROR:
            return "{filename}: {error_message}".format(**self.details)
        if self.action == self.ACTION_HOOK:
            return "{service_long_name}: {repo_url}, {branch}".format(**self.details)
        if self.action == self.ACTION_COMMENT and "comment" in self.details:
            return render_markdown(self.details["comment"])

        return ""

    def get_distance(self):
        try:
            return damerau_levenshtein_distance(self.old, self.target)
        except MemoryError:
            # Too long strings
            return abs(len(self.old) - len(self.target))
