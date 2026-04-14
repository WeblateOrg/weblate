# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from ssl import CertificateError
from typing import TYPE_CHECKING

from django.apps import AppConfig
from django.conf import settings
from django.core.checks import register

from weblate.accounts.avatar import download_avatar_image
from weblate.accounts.data import NotificationFrequency, NotificationScope
from weblate.auth.utils import get_auth_keys
from weblate.utils.checks import weblate_check

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from django.core.checks import CheckMessage


@register(deploy=True)
def check_auth(
    *,
    app_configs: Sequence[AppConfig] | None,
    databases: Sequence[str] | None,
    **kwargs,
) -> Iterable[CheckMessage]:
    result: list[CheckMessage] = []
    if settings.REGISTRATION_ALLOW_BACKENDS:
        backends = get_auth_keys()
        result.extend(
            weblate_check(
                "weblate.C042",
                f"REGISTRATION_ALLOW_BACKENDS contains invalid backend: {name}",
            )
            for name in settings.REGISTRATION_ALLOW_BACKENDS
            if name not in backends
        )

    return result


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


@register(deploy=True)
def check_notification_settings(
    *,
    app_configs: Sequence[AppConfig] | None,
    databases: Sequence[str] | None,
    **kwargs,
) -> Iterable[CheckMessage]:
    errors: list[CheckMessage] = []
    name = "DEFAULT_NOTIFICATIONS"

    if not isinstance(settings.DEFAULT_NOTIFICATIONS, list):
        errors.append(
            weblate_check("weblate.C045", f"{name} configuration must be a list")
        )
    else:
        for notification in settings.DEFAULT_NOTIFICATIONS:
            if not isinstance(notification, tuple) or len(notification) != 3:
                errors.append(
                    weblate_check(
                        "weblate.C045",
                        f"Each item in {name} must be a tuple with three entries",
                    )
                )
            else:
                scope, frequency, handler = notification
                if scope not in NotificationScope.values:
                    errors.append(
                        weblate_check(
                            "weblate.C045",
                            f"{name} contains a invalid notification scope {scope}",
                        )
                    )
                if frequency not in NotificationFrequency.values:
                    errors.append(
                        weblate_check(
                            "weblate.C045",
                            f"{name} contains a invalid notification frequency {frequency}",
                        )
                    )
                if not isinstance(handler, str):
                    errors.append(
                        weblate_check(
                            "weblate.C045",
                            f"{name} contains a invalid notification handler {handler}",
                        )
                    )

    return errors


class AccountsConfig(AppConfig):
    name = "weblate.accounts"
    label = "accounts"
    verbose_name = "User profiles"
