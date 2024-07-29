# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from ssl import CertificateError
from typing import TYPE_CHECKING

from django.apps import AppConfig
from django.conf import settings
from django.core.checks import CheckMessage, register

from weblate.accounts.avatar import download_avatar_image
from weblate.utils.checks import weblate_check

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


@register(deploy=True)
def check_avatars(
    *,
    app_configs: Sequence[AppConfig] | None,
    databases: Sequence[str] | None,
    **kwargs,
) -> Iterable[CheckMessage]:
    if not settings.ENABLE_AVATARS:
        return []
    try:
        download_avatar_image("noreply@weblate.org", 32)
    except (OSError, CertificateError) as error:
        return [weblate_check("weblate.E018", f"Could not download avatar: {error}")]
    return []


class AccountsConfig(AppConfig):
    name = "weblate.accounts"
    label = "accounts"
    verbose_name = "User profiles"
