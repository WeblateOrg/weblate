# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Automatic detection of file format."""

from __future__ import annotations

import os.path
from fnmatch import fnmatch
from typing import Any

from translate.storage import factory

from weblate.formats.helpers import NamedBytesIO
from weblate.formats.models import FILE_FORMATS
from weblate.formats.ttkit import TTKitFormat


def detect_filename(filename):
    """Filename based format autodetection."""
    name = os.path.basename(filename)
    for pattern, storeclass in FILE_FORMATS.autoload:
        if fnmatch(name, pattern):
            return storeclass
    return None


def try_load(
    filename, content, original_format, template_store, as_template: bool = False
):
    """Try to load file by guessing type."""
    # Start with original format and translate-toolkit based autodetection
    formats = [original_format, AutodetectFormat]
    detected_format = detect_filename(filename)
    if detected_format is not None and detected_format != original_format:
        # Insert detected filename into most probable location. In case the extension
        # matches original, insert it after that as it is more likely that the upload
        # is in the original format (for example if component is monolingual PO file,
        # the uploaded PO file is more likely to be monolingual as well).
        formats.insert(
            1 if detected_format.extension() == original_format.extension() else 0,
            detected_format,
        )
    # Provide fallback to bilingual class in case using monolingual
    if (
        original_format.bilingual_class
        and original_format.bilingual_class != detected_format
    ):
        formats.insert(1, original_format.bilingual_class)
    failure = Exception("Bug!")
    for file_format in formats:
        if file_format.monolingual in (True, None) and (template_store or as_template):
            try:
                result = file_format.parse(
                    NamedBytesIO(filename, content), template_store
                )
                result.check_valid()
                # Skip if there is untranslated unit
                # this can easily happen when importing bilingual
                # storage which can be monolingual as well
                if list(result.iterate_merge("")):
                    return result
            except Exception as error:
                failure = error
        if file_format.monolingual in (False, None):
            try:
                result = file_format.parse(NamedBytesIO(filename, content))
                result.check_valid()
            except Exception as error:
                failure = error
            else:
                return result

    raise failure


class AutodetectFormat(TTKitFormat):
    """
    Automatic detection based on translate-toolkit logic.

    This is last fallback when uploaded file was not correctly parsed before.
    """

    @classmethod
    def parse(
        cls,
        storefile,
        template_store=None,
        language_code: str | None = None,
        source_language: str | None = None,
        is_template: bool = False,
        existing_units: list[Any] | None = None,
    ):
        """
        Parse store and returns TTKitFormat instance.

        First attempt own autodetection, then fallback to ttkit.
        """
        if hasattr(storefile, "read"):
            filename = getattr(storefile, "name", None)
        else:
            filename = storefile
        if filename is not None:
            storeclass = detect_filename(filename)
            if storeclass is not None:
                return storeclass(
                    storefile,
                    template_store=template_store,
                    language_code=language_code,
                    source_language=source_language,
                    is_template=is_template,
                    existing_units=existing_units,
                )
        return cls(
            storefile,
            template_store=template_store,
            language_code=language_code,
            is_template=is_template,
            existing_units=existing_units,
        )

    @classmethod
    def parse_store(cls, storefile):
        """Directly loads using translate-toolkit."""
        return factory.getobject(storefile)

    @classmethod
    def get_class(cls):
        return None
