# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations


class PermissionResult:
    def __init__(self, reason: str = "") -> None:
        self._reason: str = reason

    @property
    def reason(self) -> str:
        return self._reason

    def __bool__(self) -> bool:
        raise NotImplementedError


class Allowed(PermissionResult):
    def __bool__(self) -> bool:
        return True


class Denied(PermissionResult):
    def __bool__(self) -> bool:
        return False
