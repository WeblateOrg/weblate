# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Storage of uploaded fonts and their local rendering cache."""

from __future__ import annotations

import os
from shutil import copyfileobj
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, cast

from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage, storages
from django.core.signals import setting_changed
from django.dispatch import receiver
from django.utils.functional import LazyObject, empty

from weblate.utils.data import data_dir, data_path

if TYPE_CHECKING:
    from pathlib import Path

    from django.db.models.fields.files import FieldFile


class FontStorage(LazyObject):
    """Storage configured as ``fonts`` in STORAGES, DATA_DIR/fonts by default."""

    _wrapped: object

    def _setup(self) -> None:
        if "fonts" in settings.STORAGES:
            self._wrapped = storages["fonts"]
        else:
            self._wrapped = FileSystemStorage(location=data_dir("fonts"))

    def reset(self) -> None:
        self._wrapped = empty


_font_storage = FontStorage()
font_storage = cast("Storage", _font_storage)


def get_font_storage() -> Storage:
    """Return the font storage, used as a callable to keep migrations stable."""
    return font_storage


@receiver(setting_changed)
def reset_font_storage(*, setting: str, **kwargs: object) -> None:
    if setting in {"STORAGES", "DATA_DIR"}:
        _font_storage.reset()


def get_font_cache_dir() -> Path:
    return data_path("cache") / "fonts"


def get_cached_font(file: FieldFile, font_id: int, version: str) -> str:
    """
    Return a local path to a stored font, downloading it when needed.

    Matplotlib loads fonts by filesystem path, so fonts are copied from the
    storage into the cache. The version has to change whenever the file
    content changes. Files are written atomically, so concurrent workers can
    share the cache directory.
    """
    target = get_font_cache_dir() / f"{font_id}-{version}"
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=target.parent, prefix=".", delete=False) as temp:
            try:
                with file.open("rb") as source:
                    copyfileobj(source, temp)
            except BaseException:
                os.unlink(temp.name)
                raise
        os.replace(temp.name, target)
        # Remove copies of the previous versions of this font
        remove_cached_font(font_id, keep=target)
    return str(target)


def remove_cached_font(font_id: int, keep: Path | None = None) -> None:
    for path in get_font_cache_dir().glob(f"{font_id}-*"):
        if path != keep:
            path.unlink(missing_ok=True)
