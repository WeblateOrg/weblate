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
    EVENT_STORE_POST_LOAD = 7, "Storage post-load"
    EVENT_UNIT_POST_SAVE = 8, "Unit post-save"
    EVENT_PRE_UPDATE = 9, "Repository pre-update"
    EVENT_PRE_PUSH = 10, "Repository pre-push"
    EVENT_DAILY = 11, "Daily"
    EVENT_COMPONENT_UPDATE = 12, "Component update"
    EVENT_CHANGE = 13, "Event change"


POST_CONFIGURE_EVENTS = {
    AddonEvent.EVENT_POST_COMMIT,
    AddonEvent.EVENT_POST_UPDATE,
    AddonEvent.EVENT_COMPONENT_UPDATE,
    AddonEvent.EVENT_POST_PUSH,
    AddonEvent.EVENT_DAILY,
}
