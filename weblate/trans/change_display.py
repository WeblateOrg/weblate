# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Any

from django.template.loader import render_to_string
from django.utils.html import escape, format_html
from django.utils.translation import gettext, gettext_lazy, npgettext, pgettext

from weblate.addons.models import ADDONS
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Change
from weblate.trans.models.alert import ALERTS
from weblate.trans.models.project import Project
from weblate.trans.templatetags.translations import (
    format_language_string,
    format_unit_source,
    format_unit_target,
)
from weblate.utils.files import FileUploadMethod, get_upload_message
from weblate.utils.markdown import render_markdown
from weblate.utils.pii import mask_email

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


class ChangeDetailsRenderFactory:
    @staticmethod
    def get_strategy(change: Change) -> "BaseDetailsRenderStrategy":
        """
        Get strategy for displaying change details.

        This is used to determine how to display the details of a change.
        """
        for strategy in [
            s for s in DETAILS_DISPLAY_STRATEGIES if not s.details_required
        ]:
            if change.action in strategy.actions:
                return strategy()

        if not change.details:
            return RenderEmptyDetails()

        for strategy in [s for s in DETAILS_DISPLAY_STRATEGIES if s.details_required]:
            if change.action in strategy.actions:
                return strategy()

        # No specific strategy is found, return an empty display strategy
        return RenderEmptyDetails()


DETAILS_DISPLAY_STRATEGIES: list[type["BaseDetailsRenderStrategy"]] = []


def register_strategy(
    strategy: type["BaseDetailsRenderStrategy"],
) -> type["BaseDetailsRenderStrategy"]:
    """
    Register a new strategy for displaying change details.

    This function allows you to add a new strategy to the list of available strategies.
    """
    DETAILS_DISPLAY_STRATEGIES.append(strategy)
    return strategy


class BaseDetailsRenderStrategy:
    actions: set[ActionEvents] = set()
    details_required: bool = False

    def render_details(self, change: Change) -> str:
        raise NotImplementedError


@register_strategy
class RenderEmptyDetails(BaseDetailsRenderStrategy):
    def render_details(self, change: Change) -> str:
        return ""


@register_strategy
class RenderFileUploadDetails(BaseDetailsRenderStrategy):
    actions = {ActionEvents.FILE_UPLOAD}

    def render_details(self, change: Change) -> str:
        details = change.details
        try:
            method = FileUploadMethod[details["method"].upper()].label
        except KeyError:
            method = details["method"]
        return format_html(
            "{}<br>{} {}",
            get_upload_message(
                details["filename"],
                details["skipped"],
                details["accepted"],
                details["total"],
            ),
            gettext("File upload mode:"),
            method,
        )


@register_strategy
class RenderTarget(BaseDetailsRenderStrategy):
    actions = {ActionEvents.ANNOUNCEMENT, ActionEvents.AGREEMENT_CHANGE}

    def render_details(self, change: Change) -> str:
        return render_markdown(change.target)


@register_strategy
class RenderComment(BaseDetailsRenderStrategy):
    actions = {ActionEvents.COMMENT_DELETE, ActionEvents.COMMENT}

    def render_details(self, change: Change) -> str:
        if "comment" in change.details:
            return render_markdown(change.details["comment"])
        return ""


@register_strategy
class RenderAddon(BaseDetailsRenderStrategy):
    actions = {
        ActionEvents.ADDON_CREATE,
        ActionEvents.ADDON_CHANGE,
        ActionEvents.ADDON_REMOVE,
    }

    def render_details(self, change: Change) -> str:
        try:
            return ADDONS[change.target].name
        except KeyError:
            return change.target


@register_strategy
class RenderUpdateEventDetails(BaseDetailsRenderStrategy):
    """Strategy for displaying details of an update event."""

    actions = {ActionEvents.UPDATE}

    def render_details(self, change: Change) -> str:
        details = change.details
        reason = details.get("reason", "content changed")
        filename = format_html(
            "<code>{}</code>",
            details.get(
                "filename",
                change.translation.filename if change.translation else "",
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


@register_strategy
class RenderLicenceChangeDetails(BaseDetailsRenderStrategy):
    """Strategy for displaying details of a license change event."""

    actions = {ActionEvents.LICENSE_CHANGE}

    def render_details(self, change: Change) -> str:
        details = change.details
        not_available = pgettext("License information not available", "N/A")
        return gettext(
            'The license of the "%(component)s" component was changed '
            "from %(old)s to %(target)s."
        ) % {
            "component": change.component,
            "old": details.get("old", not_available),
            "target": details.get("target", not_available),
        }


@register_strategy
class RenderAutoActions(BaseDetailsRenderStrategy):
    actions = set(AUTO_ACTIONS.keys())

    def render_details(self, change: Change) -> str:
        if change.auto_status:
            return str(AUTO_ACTIONS[change.action])
        return ""


@register_strategy
class RenderAccessEdit(BaseDetailsRenderStrategy):
    """Strategy for displaying details of an access edit event."""

    details_required = True
    actions = {ActionEvents.ACCESS_EDIT}

    def render_details(self, change: Change) -> str:
        for number, name in Project.ACCESS_CHOICES:
            if number == change.details["access_control"]:
                return name
        return "Unknown {}".format(change.details["access_control"])


@register_strategy
class RenderUserActions(BaseDetailsRenderStrategy):
    """Strategy for displaying details of user actions."""

    actions = {
        ActionEvents.ADD_USER,
        ActionEvents.INVITE_USER,
        ActionEvents.REMOVE_USER,
    }
    details_required = True

    def render_details(self, change: Change) -> str:
        details = change.details
        if "username" in details:
            result = details["username"]
        else:
            result = mask_email(details["email"])
        if "group" in details:
            result = f"{result} ({details['group']})"
        return result


@register_strategy
class RenderLanguage(BaseDetailsRenderStrategy):
    """Strategy for displaying details of language actions."""

    actions = {
        ActionEvents.ADDED_LANGUAGE,
        ActionEvents.REQUESTED_LANGUAGE,
    }
    details_required = True

    def render_details(self, change: Change) -> str:
        try:
            return Language.objects.get(code=change.details["language"])
        except Language.DoesNotExist:
            return change.details["language"]


@register_strategy
class RenderAlert(BaseDetailsRenderStrategy):
    """Strategy for displaying details of an alert event."""

    actions = {ActionEvents.ALERT}
    details_required = True

    def render_details(self, change: Change) -> str:
        try:
            return ALERTS[change.details["alert"]].verbose
        except KeyError:
            return change.details["alert"]


@register_strategy
class RenderRepositoryDetails(BaseDetailsRenderStrategy):
    """Strategy for displaying details of repository events."""

    actions = {
        ActionEvents.RESET,
        ActionEvents.MERGE,
        ActionEvents.REBASE,
    }

    def render_details(self, change: Change) -> str:
        return format_html(
            "{}<br/><br/>{}<br/>{}",
            change.get_action_display(),
            format_html(
                escape(gettext("Original revision: {}")),
                change.details.get("previous_head", "N/A"),
            ),
            format_html(
                escape(gettext("New revision: {}")),
                change.details.get("new_head", "N/A"),
            ),
        )


@register_strategy
class RenderParseError(BaseDetailsRenderStrategy):
    """Strategy for displaying details of a parse error event."""

    format_string = "{filename}: {error_message}"
    actions = {ActionEvents.PARSE_ERROR}
    details_required = True

    def render_details(self, change: Change) -> str:
        return self.format_string.format(**change.details)


@register_strategy
class RenderHook(BaseDetailsRenderStrategy):
    """Strategy for displaying details of a hook event."""

    actions = {ActionEvents.HOOK}
    format_string = "{service_long_name}: {repo_url}, {branch}"
    details_required = True

    def render_details(self, change: Change) -> str:
        return self.format_string.format(**change.details)


def get_change_history_context(change: Change) -> dict[str, Any]:
    """
    Get context for rendering change history.

    This function returns a dictionary containing the main content and fields
    for displaying the change history.
    """
    if details := change.get_details_display():
        return {"main_content": details, "fields": []}
    if change.show_content() and change.unit:
        return ShowChangeContent(change).get_context()
    if change.show_source():
        return ShowChangeSource(change).get_context()
    if change.show_diff():
        return ShowChangeDiff(change).get_context()
    if change.show_removed_string():
        return ShowRemovedString(change).get_context()
    if change.target:
        return ShowChangeTarget(change).get_context()
    return ShowChangeAction(change).get_context()


class BaseChangeHistoryContext:
    """Base class for change history context rendering."""

    def __init__(self, change: Change) -> None:
        self.change = change

    def get_context(self) -> dict[str, Any]:
        """Get context for rendering change history."""
        return {
            "main_content": self.get_main_content(),
            "fields": self.get_fields(),
        }

    def get_main_content(self) -> str | None:
        return None

    def get_fields(self) -> list[dict]:
        return []

    def make_field(
        self,
        label: str,
        field_content: str,
        label_badges: list[str] | None = None,
        extra_label_classes: list[str] | None = None,
    ) -> dict:
        return {
            "label": label,
            "content": field_content or [],
            "tags": label_badges,
            "label_class": " ".join(extra_label_classes or []),
        }

    def format_translation(self, context: dict) -> str:
        """Format translation context for rendering."""
        return render_to_string("snippets/format-translation.html", context)

    def make_distance_badge(self, count: int) -> str:
        """Create a badge for the Damerau–Levenshtein distance."""  # noqa: RUF002
        return npgettext(
            "Number of edits on a change in Damerau–Levenshtein distance",
            "%(count)d character edited",
            "%(count)d characters edited",
            count,
        ) % {"count": count}


class ShowChangeTarget(BaseChangeHistoryContext):
    """Display the target of a change in the history context."""

    def get_main_content(self) -> str | None:
        return format_html("<pre>{}</pre>", self.change.target)


class ShowChangeAction(BaseChangeHistoryContext):
    """Display the action of a change in the history context."""

    def get_main_content(self) -> str | None:
        return self.change.get_action_display()


class ShowChangeContent(BaseChangeHistoryContext):
    """Display the content of a change in the history context."""

    SIMPLE_CONTENT_TEMPLATE = """
    <div class="list-group">
        <div class="list-group-item sidebar-button">{0}</div>
    </div>
    """

    def get_fields(self) -> list[dict]:
        """Return the fields to be displayed in the change history."""
        fields = []
        change = self.change

        # rejection reason field
        if "rejection_reason" in change.details:
            fields.append(
                self.make_field(
                    gettext("Rejection reason"),
                    format_html(
                        self.SIMPLE_CONTENT_TEMPLATE, change.details["rejection_reason"]
                    ),
                )
            )

        # source language field
        fields.append(
            self.make_field(
                change.unit.translation.component.source_language,
                self.format_translation(
                    format_unit_source(change.unit, value=self.change.get_source())
                ),
            )
        )

        # translation language field
        translation_language_badges = [
            self.make_distance_badge(change.get_distance()),
        ]

        if change.unit.target == change.target:
            translation_language_badges.append(gettext("Current translation"))
        else:
            translation_language_badges.append(gettext("Previous translation"))
        if change.show_unit_state():
            state = change.get_state_display()
            translation_language_badges.append(
                gettext("State: %(state)s") % {"state": state}
            )

        fields.append(
            self.make_field(
                change.unit.translation.language,
                self.format_translation(
                    format_unit_target(
                        change.unit, value=change.target, diff=change.old
                    )
                ),
                label_badges=translation_language_badges,
                extra_label_classes=["tags-list"],
            )
        )
        return fields


class ShowChangeSource(BaseChangeHistoryContext):
    """Display the source of a change in the history context."""

    def get_fields(self) -> list[dict]:
        fields = []
        change = self.change

        # source language field
        source_lang_badges = [
            self.make_distance_badge(change.get_distance()),
        ]
        if change.show_unit_state():
            source_lang_badges.append(change.get_state_display())

        if change.target:
            souce_lang_content = format_unit_source(
                change.unit, value=change.target, diff=change.old
            )
        else:
            souce_lang_content = format_unit_source(change.unit)

        fields.append(
            self.make_field(
                change.unit.translation.component.source_language,
                self.format_translation(souce_lang_content),
                label_badges=source_lang_badges,
            )
        )
        return fields


class ShowChangeDiff(BaseChangeHistoryContext):
    """Display the diff of a change in the history context."""

    def get_fields(self) -> list[dict]:
        change = self.change
        return [
            self.make_field(
                "",
                self.format_translation(
                    format_unit_source(
                        change.unit, value=change.target, diff=change.old
                    )
                ),
                label_badges=[self.make_distance_badge(change.get_distance())],
            )
        ]


class ShowRemovedString(BaseChangeHistoryContext):
    """Display the removed string of a change in the history context."""

    def get_fields(self) -> list[dict]:
        change = self.change
        fields = [
            self.make_field(
                change.component.source_translation.language,
                self.format_translation(
                    format_language_string(
                        change.details.source, change.component.source_translation
                    )
                ),
            )
        ]
        if change.details.target and not change.translation.is_source:
            fields.append(
                self.make_field(
                    change.translation.language,
                    self.format_translation(
                        format_language_string(
                            change.details.target, change.translation
                        )
                    ),
                )
            )
        return fields
