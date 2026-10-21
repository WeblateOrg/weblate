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

    from weblate.auth.models import User


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
ACTING_USER_HEADER = "weblate_acting_user_id"
acting_user: ContextVar[User | None] = ContextVar("acting_user", default=None)


def get_acting_user() -> User | None:
    """Return the operation's actor, independently of its content author."""
    return acting_user.get()


def set_acting_user(user: User | None) -> None:
    """Update an actor inside an existing request or operation scope."""
    if user is not None and hasattr(user, "get_token_user"):
        user = user.get_token_user()
    acting_user.set(user)


@contextmanager
def acting_user_context(user: User | None) -> Generator[None]:
    """Scope attribution without attaching transient state to model instances."""
    token = acting_user.set(None)
    try:
        set_acting_user(user)
        yield
    finally:
        acting_user.reset(token)


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
    """Keep provenance and actor when a callback outlives its operation scope."""
    origin = get_change_origin()
    automation = automation_origin.get()
    user = get_acting_user()

    @wraps(callback)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        token = automation_origin.set(automation)
        try:
            with change_origin_context(origin), acting_user_context(user):
                return callback(*args, **kwargs)
        finally:
            automation_origin.reset(token)

    return wrapped
