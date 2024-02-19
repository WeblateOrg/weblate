# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db.models import IntegerChoices


class AddonEvent(IntegerChoices):
    EVENT_POST_PUSH = 1, "repository post-push"
    EVENT_POST_UPDATE = 2, "repository post-update"
    EVENT_PRE_COMMIT = 3, "repository pre-commit"
    EVENT_POST_COMMIT = 4, "repository post-commit"
    EVENT_POST_ADD = 5, "repository post-add"
    EVENT_UNIT_PRE_CREATE = 6, "unit post-create"
    EVENT_STORE_POST_LOAD = 7, "storage post-load"
    EVENT_UNIT_POST_SAVE = 8, "unit post-save"
    EVENT_PRE_UPDATE = 9, "repository pre-update"
    EVENT_PRE_PUSH = 10, "repository pre-push"
    EVENT_DAILY = 11, "daily"
    EVENT_COMPONENT_UPDATE = 12, "component update"
