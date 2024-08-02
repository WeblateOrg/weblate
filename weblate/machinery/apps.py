# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.apps import AppConfig
from django.core.checks import CheckMessage, register
from django.core.checks import Warning as DjangoWarning

from weblate.utils.checks import weblate_check

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


@register
def check_machinery(
    *,
    app_configs: Sequence[AppConfig] | None,
    databases: Sequence[str] | None,
    **kwargs,
) -> Iterable[CheckMessage]:
    from weblate.machinery.models import MACHINERY

    # Needed to load the data
    MACHINERY.data  # noqa: B018
    return [
        weblate_check(
            f"weblate.W039.{key.split('.')[-1]}",
            str(value),
            DjangoWarning,
        )
        for key, value in MACHINERY.errors.items()
    ]


class VCSConfig(AppConfig):
    name = "weblate.machinery"
    label = "machinery"
    verbose_name = "Machinery"
