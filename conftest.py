# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from weblate.utils.version import VERSION_BASE, Release

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(scope="session", autouse=True)  # ruff: ignore[pytest-fixture-autouse]
def offline_version_check() -> Iterator[None]:
    """Supply a local release for deployment checks that would query PyPI."""
    release = Release(VERSION_BASE, datetime(2000, 1, 1, tzinfo=UTC))
    with patch("weblate.utils.apps.get_latest_version", return_value=release):
        yield
