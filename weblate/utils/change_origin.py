# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from typing import TYPE_CHECKING, NotRequired, TypedDict

from weblate.automation.context import automation_origin

if TYPE_CHECKING:
    from collections.abc import Callable, Generator


class ChangeOriginToken(TypedDict):
    """A future token's stable identifier, never its credential."""

    type: str
    id: str


class ChangeOriginAutomation(TypedDict):
    """Identify an automation installation and its execution log."""

    addon_id: int
    activity_id: int


class ChangeOrigin(TypedDict):
    scope: str
    token: NotRequired[ChangeOriginToken]
    automation: NotRequired[ChangeOriginAutomation]


change_origin: ContextVar[ChangeOrigin | None] = ContextVar(
    "change_origin", default=None
)
CHANGE_ORIGIN_HEADER = "weblate_change_origin"


def get_change_origin() -> ChangeOrigin:
    """Return a snapshot that can outlive the current request or task."""
    return deepcopy(change_origin.get() or {"scope": "system"})


@contextmanager
def change_origin_context(origin: ChangeOrigin) -> Generator[None]:
    snapshot = deepcopy(origin)
    token = change_origin.set(snapshot)
    automation = snapshot.get("automation")
    automation_token = (
        automation_origin.set(automation["activity_id"]) if automation else None
    )
    try:
        yield
    finally:
        change_origin.reset(token)
        if automation_token is not None:
            automation_origin.reset(automation_token)


def capture_change_origin[**P, R](callback: Callable[P, R]) -> Callable[P, R]:
    """Keep provenance when a callback runs after the originating scope exits."""
    origin = get_change_origin()
    automation = automation_origin.get()

    @wraps(callback)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        token = automation_origin.set(automation)
        try:
            with change_origin_context(origin):
                return callback(*args, **kwargs)
        finally:
            automation_origin.reset(token)

    return wrapped
