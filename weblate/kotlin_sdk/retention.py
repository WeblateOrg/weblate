# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from weblate.kotlin_sdk.models import KotlinSDKBuild


def select_retired_builds(
    builds: Sequence[KotlinSDKBuild],
    *,
    maximum: int,
    cutoff: datetime,
    reserve: int = 0,
) -> list[KotlinSDKBuild]:
    """Select retirements from newest-first builds without changing their state."""
    published_total = sum(build.published is not None for build in builds)
    pending_limit = maximum - min(maximum, published_total) + 1 - reserve
    published_count = pending_count = 0
    retired = []
    for build in builds:
        unpublished = build.published is None
        if (
            build.created <= cutoff
            or published_count >= maximum
            or (unpublished and pending_count >= pending_limit)
        ):
            retired.append(build)
        elif unpublished:
            pending_count += 1
        else:
            published_count += 1
    return retired
