# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

EVENT_POST_PUSH = 1
EVENT_POST_UPDATE = 2
EVENT_PRE_COMMIT = 3
EVENT_POST_COMMIT = 4
EVENT_POST_ADD = 5
EVENT_UNIT_PRE_CREATE = 6
EVENT_STORE_POST_LOAD = 7
EVENT_UNIT_POST_SAVE = 8
EVENT_PRE_UPDATE = 9
EVENT_PRE_PUSH = 10
EVENT_DAILY = 11
EVENT_COMPONENT_UPDATE = 12

EVENT_CHOICES = (
    (EVENT_PRE_PUSH, "repository pre-push"),
    (EVENT_POST_PUSH, "repository post-push"),
    (EVENT_PRE_UPDATE, "repository pre-update"),
    (EVENT_POST_UPDATE, "repository post-update"),
    (EVENT_PRE_COMMIT, "repository pre-commit"),
    (EVENT_POST_COMMIT, "repository post-commit"),
    (EVENT_POST_ADD, "repository post-add"),
    (EVENT_UNIT_PRE_CREATE, "unit post-create"),
    (EVENT_UNIT_POST_SAVE, "unit post-save"),
    (EVENT_STORE_POST_LOAD, "storage post-load"),
    (EVENT_DAILY, "daily"),
    (EVENT_COMPONENT_UPDATE, "component update"),
)
EVENT_NAMES = dict(EVENT_CHOICES)
