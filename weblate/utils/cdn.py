# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Content metadata shared by CDN publishers."""

from __future__ import annotations

import hashlib
import os
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from pathlib import Path


class ContentMetadata(TypedDict):
    sha256: str
    size: int


class CDNFileMetadata(ContentMetadata):
    url: str


def content_metadata(content: bytes | bytearray | memoryview | Path) -> ContentMetadata:
    """Describe bytes or hash a file without loading it into memory."""
    if isinstance(content, (bytes, bytearray, memoryview)):
        return {
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": content.nbytes if isinstance(content, memoryview) else len(content),
        }
    with content.open("rb") as handle:
        return {
            "sha256": hashlib.file_digest(handle, "sha256").hexdigest(),
            "size": os.fstat(handle.fileno()).st_size,
        }
