# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Final

from django.core.exceptions import ImproperlyConfigured

VERSION_DISPLAY_SHOW: Final = "show"
VERSION_DISPLAY_SOFT: Final = "soft"
VERSION_DISPLAY_HIDE: Final = "hide"
VERSION_DISPLAY_VALUES: Final[frozenset[str]] = frozenset(
    {
        VERSION_DISPLAY_SHOW,
        VERSION_DISPLAY_SOFT,
        VERSION_DISPLAY_HIDE,
    }
)

TRUE_VALUES: Final[frozenset[str]] = frozenset({"true", "yes", "1"})


def normalize_version_display(
    version_display: str | None,
    hide_version: bool | str | None = None,
) -> str:
    """Normalize version visibility settings to one of the supported modes."""
    if version_display is not None:
        normalized = str(version_display).strip().lower()
        if normalized not in VERSION_DISPLAY_VALUES:
            choices = ", ".join(sorted(VERSION_DISPLAY_VALUES))
            msg = f"Unsupported VERSION_DISPLAY value {version_display!r}, expected one of: {choices}"
            raise ImproperlyConfigured(msg)
        return normalized

    if isinstance(hide_version, str):
        hide_version = hide_version.strip().lower() in TRUE_VALUES

    return VERSION_DISPLAY_HIDE if hide_version else VERSION_DISPLAY_SHOW


def hide_prominent_version(version_display: str) -> bool:
    """Return whether the exact version should be hidden from shared chrome."""
    return version_display != VERSION_DISPLAY_SHOW


def hide_detailed_version(version_display: str) -> bool:
    """Return whether dedicated version views should hide exact versions."""
    return version_display == VERSION_DISPLAY_HIDE


def show_metrics_version(version_display: str) -> bool:
    """Return whether the metrics endpoint should expose the version."""
    return version_display != VERSION_DISPLAY_HIDE
