# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING

from askalono import identify
from django.conf import settings

from weblate.utils.licensedata import LICENSES

if TYPE_CHECKING:
    from pathlib import Path

    from askalono import License

ALL_LICENSES = (*LICENSES, *settings.LICENSE_EXTRA)

LIBRE_IDS = {name for name, _verbose, _url, is_libre in ALL_LICENSES if is_libre}
LICENSE_URLS = {name: url for name, _verbose, url, _is_libre in ALL_LICENSES}
LICENSE_NAMES = {name: verbose for name, verbose, _url, _is_libre in ALL_LICENSES}

LICENSE_FILENAMES: list[str] = ["LICEN[CS]E*", "COPYING*", "COPYRIGHT*", "LICENSES/*"]


def is_libre(name: str) -> bool:
    return name in LIBRE_IDS


def get_license_url(name: str) -> str | None:
    return LICENSE_URLS.get(name)


def get_license_name(name: str) -> str:
    return LICENSE_NAMES.get(name, name)


def get_license_choices() -> list[tuple[str, str]]:
    license_filter = settings.LICENSE_FILTER
    if license_filter is None or "proprietary" in license_filter:
        result = [("proprietary", "Proprietary")]
    else:
        result = []

    result.extend(
        (name, verbose)
        for name, verbose, _url, _is_libre in LICENSES
        if license_filter is None or name in license_filter
    )

    result.extend(
        (name, verbose) for name, verbose, _url, _is_libre in settings.LICENSE_EXTRA
    )

    return result


def detect_license(path: Path, *, threshold: float = 0.98) -> str | None:
    """
    Detect a license of a path.

    It performs really simple heuristics assuming the project follows best
    practice to store license files.
    """
    matches: list[License] = []

    for filename in chain.from_iterable(path.glob(mask) for mask in LICENSE_FILENAMES):
        # Look into files only
        # TODO: Use is_file(follow_symlinks=False) with Python 3.13+
        if filename.is_symlink() or not filename.is_file():
            continue
        match = identify(filename.read_text())
        # We have good match, stop right now
        if match.score >= threshold:
            return match.name
        matches.append(match)

    if not matches:
        return None

    # Find the best match, sorted alphabetically to make this deterministic
    return min(matches, key=lambda match: (-match.score, match.name)).name
