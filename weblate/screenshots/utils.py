# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os.path
from typing import TYPE_CHECKING

from weblate.utils.validators import validate_bitmap

if TYPE_CHECKING:
    from django.core.files import File


IMAGE_EXTENSIONS = {
    "image/png": (".png", ".apng"),
    "image/apng": (".png", ".apng"),
    "image/jpeg": (".jpg", ".jpeg", ".jpe"),
    "image/gif": (".gif",),
    "image/webp": (".webp",),
}


def normalize_screenshot_filename(image: File) -> str:
    """Repair legacy filenames using validated image contents."""
    validate_bitmap(image)
    extensions = IMAGE_EXTENSIONS[getattr(image, "content_type", "")]
    name = image.name or "screenshot"
    stem, extension = os.path.splitext(name)
    if extension.lower() in extensions:
        return name
    return stem + extensions[0]
