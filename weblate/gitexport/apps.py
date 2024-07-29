# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.apps import AppConfig
from django.core.checks import CheckMessage, register

from weblate.gitexport.utils import find_git_http_backend
from weblate.utils.checks import weblate_check

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


class GitExportConfig(AppConfig):
    name = "weblate.gitexport"
    label = "gitexport"
    verbose_name = "Git Exporter"


@register
def check_git_backend(
    *,
    app_configs: Sequence[AppConfig] | None,
    databases: Sequence[str] | None,
    **kwargs,
) -> Iterable[CheckMessage]:
    if find_git_http_backend() is None:
        return [
            weblate_check(
                "weblate.E022",
                "Could not find git-http-backend, the git exporter will not work.",
            )
        ]
    return []
