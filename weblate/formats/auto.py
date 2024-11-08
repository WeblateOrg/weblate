# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Automatic detection of file format."""

from __future__ import annotations

import os.path
from fnmatch import fnmatch
from typing import TYPE_CHECKING, Any

from translate.storage import factory

from weblate.formats.helpers import NamedBytesIO
from weblate.formats.models import FILE_FORMATS
from weblate.formats.ttkit import TTKitFormat

if TYPE_CHECKING:
    from collections.abc import Generator

    from weblate.formats.base import TranslationFormat


def detect_filename(filename: str) -> type[TranslationFormat] | None:
    """Filename based format autodetection."""
    name = os.path.basename(filename)
    for pattern, storeclass in FILE_FORMATS.autoload:
        if fnmatch(name, pattern):
            return storeclass
    return None


def formats_iter(
    filename: str, original_format: type[TranslationFormat] | None
) -> Generator[type[TranslationFormat], None, None]:
    # Detect based on the extension
    detected_format = detect_filename(filename)
    if detected_format is not None and detected_format != original_format:
        # Insert detected filename into most probable location. In case the extension
        # matches original, insert it after that as it is more likely that the upload
        # is in the original format (for example if component is monolingual PO file,
        # the uploaded PO file is more likely to be monolingual as well).
        if (
            original_format is not None
            and detected_format.extension() == original_format.extension()
        ):
            yield original_format
            yield detected_format
        else:
            yield detected_format
            if original_format is not None:
                yield original_format
    elif original_format is not None:
        yield original_format

    # Provide fallback to bilingual class in case using monolingual
    if (
        original_format is not None
        and original_format.bilingual_class
        and original_format.bilingual_class != detected_format
    ):
        yield original_format.bilingual_class

    # Fallback to translate-toolkit autodetection
    yield AutodetectFormat


def params_iter(
    file_format: type[TranslationFormat],
    template_store: TranslationFormat | None,
    is_template: bool = False,
) -> Generator[tuple[dict[str, Any], bool], None, None]:
    if file_format.monolingual in {True, None} and (template_store or is_template):
        yield {"template_store": template_store, "is_template": is_template}, True

    if file_format.monolingual in {False, None}:
        yield {}, False


def try_load(
    filename: str,
    content: bytes,
    original_format: type[TranslationFormat] | None,
    template_store: TranslationFormat | None,
    is_template: bool = False,
) -> TranslationFormat:
    """Try to load file by guessing type."""
    failure = None
    for file_format in formats_iter(filename, original_format):
        for kwargs, validate in params_iter(file_format, template_store, is_template):
            handle = NamedBytesIO(filename, content)
            try:
                result = file_format(handle, **kwargs)
                result.check_valid()
            except Exception as error:
                if failure is None:
                    failure = error
            else:
                # Skip if there is untranslated unit
                # this can easily happen when importing bilingual
                # storage which can be monolingual as well
                if not validate or any(result.iterate_merge("")):
                    return result

    if failure is None:
        msg = "Could not load file."
        raise ValueError(msg)
    raise failure


class AutodetectFormat(TTKitFormat):
    """
    Automatic detection based on translate-toolkit logic.

    This is last fallback when uploaded file was not correctly parsed before.
    """

    @classmethod
    def parse_store(cls, storefile):
        """Directly loads using translate-toolkit."""
        return factory.getobject(storefile)

    @classmethod
    def get_class(cls) -> None:
        return None
