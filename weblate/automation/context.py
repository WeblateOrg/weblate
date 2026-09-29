# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextvars import ContextVar

# Kept separate from add-on discovery so Change can record provenance without
# importing add-on models. Deferred event delivery reads the persisted value.
automation_origin: ContextVar[int | None] = ContextVar(
    "automation_origin", default=None
)

manual_actor: ContextVar[int | None] = ContextVar("manual_actor", default=None)
