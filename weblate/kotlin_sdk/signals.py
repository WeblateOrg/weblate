# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings

from weblate.kotlin_sdk.publication import STAGING_DIRECTORY
from weblate.kotlin_sdk.tasks import schedule_cleanup

if TYPE_CHECKING:
    from weblate.addons.models import Addon


def remove_publication(instance: Addon, using: str, **kwargs: object) -> None:
    """Remove origin files after deletion has waited for publishing's row lock."""
    if instance.name != "weblate.cdn.kotlin" or not settings.LOCALIZE_CDN_PATH:
        return
    uuid = instance.state.get("uuid", "")
    if not isinstance(uuid, str) or not re.fullmatch(r"[0-9a-f]{32}", uuid):
        return
    path = Path(settings.LOCALIZE_CDN_PATH) / uuid
    schedule_cleanup(path, using=using)
    schedule_cleanup(
        Path(settings.LOCALIZE_CDN_PATH) / STAGING_DIRECTORY / uuid, using=using
    )
