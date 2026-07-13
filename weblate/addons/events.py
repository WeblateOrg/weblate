# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass

from django.db.models import IntegerChoices, TextChoices
from django.utils.translation import gettext_lazy


class AddonEvent(IntegerChoices):
    EVENT_POST_PUSH = 1, "Repository post-push"
    EVENT_POST_UPDATE = 2, "Repository post-update"
    EVENT_PRE_COMMIT = 3, "Repository pre-commit"
    EVENT_POST_COMMIT = 4, "Repository post-commit"
    EVENT_POST_ADD = 5, "Repository post-add"
    EVENT_UNIT_PRE_CREATE = 6, "Unit pre-create"
    # Used to be EVENT_STORE_POST_LOAD = 7, "Storage post-load"
    EVENT_UNIT_POST_SAVE = 8, "Unit post-save"
    EVENT_PRE_UPDATE = 9, "Repository pre-update"
    EVENT_PRE_PUSH = 10, "Repository pre-push"
    EVENT_DAILY = 11, "Daily"
    EVENT_COMPONENT_UPDATE = 12, "Component update"
    EVENT_CHANGE = 13, "Event change"
    EVENT_UNIT_POST_SYNC = 14, "Unit post-sync"
    EVENT_INSTALL = 15, "Add-on installation"
    EVENT_POST_REMOVE = 16, "Repository post-remove"
    EVENT_MANUAL = 17, "Manual trigger"

    @classmethod
    def descriptions(cls) -> dict[AddonEvent, str]:
        return {
            cls.EVENT_POST_PUSH: "Triggered just after the repository is pushed upstream.",
            cls.EVENT_POST_UPDATE: "Triggered whenever new changes are pulled from the upstream repository.",
            cls.EVENT_PRE_COMMIT: "Triggered just before the changes are committed.",
            cls.EVENT_POST_COMMIT: "Triggered just after the changes are committed.",
            cls.EVENT_POST_ADD: "Triggered just after the new translation is added and committed.",
            cls.EVENT_UNIT_PRE_CREATE: "Triggered just after the newly created string is saved.",
            cls.EVENT_UNIT_POST_SAVE: "Triggered just after the string is saved.",
            cls.EVENT_PRE_UPDATE: "Triggered just before the repository update is attempted.",
            cls.EVENT_PRE_PUSH: "Triggered just before the repository is pushed upstream.",
            cls.EVENT_DAILY: "Triggered daily, but add-ons usually split the daily load between components depending on :setting:`BACKGROUND_TASKS`.",
            cls.EVENT_COMPONENT_UPDATE: """Triggered whenever a change happens in a component such as:

* Strings are changed in the repository.
* A string is added.
* A new translation is added.""",
            cls.EVENT_CHANGE: "Triggered after a Change event is created.",
            cls.EVENT_UNIT_POST_SYNC: "Triggered after the string is synchronized with the VCS.",
            cls.EVENT_INSTALL: "Triggered when add-on is being installed.",
            cls.EVENT_POST_REMOVE: "Triggered just after a translation is removed.",
            cls.EVENT_MANUAL: "Triggered when an add-on is run manually from add-on management or the API.",
        }


class AddonActivityLogStatus(IntegerChoices):
    PENDING = 0, gettext_lazy("Pending")
    SUCCESS = 1, gettext_lazy("Success")
    ERROR = 2, gettext_lazy("Error")
    SKIPPED = 3, gettext_lazy("Skipped")


class AddonActivityLogReason(TextChoices):
    INCOMPATIBLE_COMPONENT = (
        "incompatible-component",
        gettext_lazy("The add-on is not compatible with this component."),
    )
    NO_COMPATIBLE_COMPONENTS = (
        "no-compatible-components",
        gettext_lazy("There are no compatible components to process."),
    )
    NOT_SCHEDULED = (
        "not-scheduled",
        gettext_lazy("The add-on is not scheduled to run yet."),
    )
    NO_RELEVANT_CHANGES = (
        "no-relevant-changes",
        gettext_lazy("There are no relevant changes to process."),
    )
    BACKGROUND_TASKS_DISABLED = (
        "background-tasks-disabled",
        gettext_lazy("Background processing is disabled."),
    )
    BACKGROUND_CADENCE = (
        "background-cadence",
        gettext_lazy("The component is not scheduled for background processing today."),
    )
    NO_ELIGIBLE_UNITS = (
        "no-eligible-units",
        gettext_lazy("There are no eligible strings to process."),
    )
    TARGET_MISSING = (
        "target-missing",
        gettext_lazy("The target no longer exists."),
    )
    REQUIRED_FILE_MISSING = (
        "required-file-missing",
        gettext_lazy("A required file is not available."),
    )
    NO_OUTGOING_COMMITS = (
        "no-outgoing-commits",
        gettext_lazy("There are no outgoing commits to process."),
    )
    NOT_APPLICABLE = (
        "not-applicable",
        gettext_lazy("The add-on does not apply to this event."),
    )
    NO_SOURCE_FILES = "no-source-files", gettext_lazy("No source files are configured.")
    INVALID_OUTPUT = (
        "invalid-output",
        gettext_lazy("The configured output path is invalid."),
    )
    EXECUTION_FAILED = "execution-failed", gettext_lazy("The add-on execution failed.")


@dataclass(frozen=True)
class AddonEventOutcome:
    status: AddonActivityLogStatus
    reason: AddonActivityLogReason | None = None
    result: object | None = None

    @classmethod
    def pending(cls) -> AddonEventOutcome:
        return cls(AddonActivityLogStatus.PENDING)

    @classmethod
    def skipped(cls, reason: AddonActivityLogReason) -> AddonEventOutcome:
        return cls(AddonActivityLogStatus.SKIPPED, reason=reason)

    @classmethod
    def error(
        cls,
        reason: AddonActivityLogReason = AddonActivityLogReason.EXECUTION_FAILED,
        result: object | None = None,
    ) -> AddonEventOutcome:
        return cls(AddonActivityLogStatus.ERROR, reason=reason, result=result)


type AddonEventResult = dict | AddonEventOutcome | None


POST_CONFIGURE_EVENTS = {
    AddonEvent.EVENT_POST_COMMIT,
    AddonEvent.EVENT_POST_UPDATE,
    AddonEvent.EVENT_COMPONENT_UPDATE,
    AddonEvent.EVENT_POST_PUSH,
    AddonEvent.EVENT_DAILY,
}
