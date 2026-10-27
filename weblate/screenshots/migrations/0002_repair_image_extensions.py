# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import os.path
import warnings
from io import BytesIO
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import migrations
from PIL import Image

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


LOGGER = logging.getLogger("weblate.screenshots")
IMAGE_EXTENSIONS = {
    "PNG": (".png", ".apng"),
    "JPEG": (".jpg", ".jpeg", ".jpe"),
    "GIF": (".gif",),
    "WEBP": (".webp",),
}


def get_image_extensions(content: bytes) -> tuple[str, ...]:
    """Freeze the screenshot content policy used when this migration was added."""
    if len(content) > settings.ALLOWED_ASSET_SIZE:
        msg = "Image exceeds the asset size limit"
        raise ValueError(msg)
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(content), formats=list(IMAGE_EXTENSIONS)) as image:
            image.verify()
            if image.width > 2000 or image.height > 2000:
                msg = "Image exceeds the screenshot dimension limit"
                raise ValueError(msg)
            return IMAGE_EXTENSIONS[image.format or ""]


def repair_image_extensions(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    """Copy incorrectly named images before updating their storage references."""
    Screenshot = apps.get_model("screenshots", "Screenshot")
    screenshots = Screenshot.objects.using(schema_editor.connection.alias)
    # ruff: ignore[private-member-access]
    field = Screenshot._meta.get_field("image")
    storage = field.storage
    names = (
        screenshots.exclude(image="")
        .order_by("image")
        .values_list("image", flat=True)
        .distinct()
    )
    for name in names.iterator(chunk_size=1000):
        screenshot_ids = screenshots.filter(image=name).values_list("pk", flat=True)
        try:
            with storage.open(name, "rb") as handle:
                content = handle.read(settings.ALLOWED_ASSET_SIZE + 1)
        except FileNotFoundError:
            LOGGER.warning(
                "Could not repair screenshot image %s (screenshots %s): file is missing",
                name,
                list(screenshot_ids),
            )
            continue
        try:
            extensions = get_image_extensions(content)
        except (
            OSError,
            SyntaxError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as error:
            LOGGER.warning(
                "Could not repair screenshot image %s (screenshots %s): %s",
                name,
                list(screenshot_ids),
                error,
            )
            continue
        stem, extension = os.path.splitext(name)
        if extension.lower() in extensions:
            continue
        new_name = storage.save(
            stem + extensions[0], ContentFile(content), max_length=field.max_length
        )
        # One atomic UPDATE also preserves references shared by several screenshots.
        # Keep the original file for rollback; scheduled cleanup removes it later.
        screenshots.filter(image=name).update(image=new_name)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [("screenshots", "0001_squashed_weblate_5")]

    operations = [
        migrations.RunPython(repair_image_extensions, migrations.RunPython.noop),
    ]
