# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Custom Weblate signals."""

from django.dispatch import Signal

vcs_pre_push = Signal()
vcs_post_push = Signal()
vcs_post_update = Signal()
vcs_pre_update = Signal()
vcs_pre_commit = Signal()
vcs_post_commit = Signal()
translation_post_add = Signal()
component_post_update = Signal()
unit_pre_create = Signal()
user_pre_delete = Signal()
store_post_load = Signal()
change_bulk_create = Signal()
