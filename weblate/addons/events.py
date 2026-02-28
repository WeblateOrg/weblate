# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db.models import IntegerChoices


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

    @classmethod
    def descriptions(cls) -> dict[int, str]:
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
        }


POST_CONFIGURE_EVENTS = {
    AddonEvent.EVENT_POST_COMMIT,
    AddonEvent.EVENT_POST_UPDATE,
    AddonEvent.EVENT_COMPONENT_UPDATE,
    AddonEvent.EVENT_POST_PUSH,
    AddonEvent.EVENT_DAILY,
}
