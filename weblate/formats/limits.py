# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Common acceptance limits for translation files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import IO

from django.conf import settings
from django.utils.translation import gettext

MAX_TRANSLATION_UNITS = 100_000


class TranslationLimitError(ValueError):
    """A file exceeds the shared translation-file acceptance limits."""


def translation_max_size() -> int:
    """Resolve the optional parser limit against the configured upload limit."""
    limit = settings.TRANSLATION_MAX_SIZE
    return settings.TRANSLATION_UPLOAD_MAX_SIZE if limit is None else limit


def check_translation_size(size: int) -> None:
    """Reject oversized input before passing it to a parser."""
    limit = translation_max_size()
    if size > limit:
        raise TranslationLimitError(
            gettext("Translation file exceeds the maximum allowed size of %d bytes.")
            % limit
        )


def check_translation_file_size(storefile: str | Path | IO[bytes]) -> None:
    """Measure a path or seekable stream without consuming its content."""
    if isinstance(storefile, (str, Path)):
        size = os.stat(storefile).st_size
    else:
        position = storefile.tell()
        try:
            storefile.seek(0, os.SEEK_END)
            size = storefile.tell()
        finally:
            storefile.seek(position)
    check_translation_size(size)


def check_translation_unit_count(count: int) -> None:
    """Reject oversized logical stores before syncing or importing their units."""
    if count > MAX_TRANSLATION_UNITS:
        raise TranslationLimitError(
            gettext("Translation file exceeds the maximum allowed count of %d strings.")
            % MAX_TRANSLATION_UNITS
        )
