#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Automatic detection of file format."""

import os.path
from fnmatch import fnmatch
from typing import Optional

from translate.storage import factory

from weblate.formats.helpers import BytesIOMode
from weblate.formats.models import FILE_FORMATS
from weblate.formats.ttkit import TTKitFormat


def detect_filename(filename):
    """Filename based format autodetection."""
    name = os.path.basename(filename)
    for pattern, storeclass in FILE_FORMATS.autoload:
        if fnmatch(name, pattern):
            return storeclass
    return None


def try_load(filename, content, original_format, template_store):
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
        if file_format.monolingual in (True, None) and template_store:
            try:
                result = file_format.parse(
                    BytesIOMode(filename, content), template_store
                )
                result.check_valid()
                # Skip if there is not translated unit
                # this can easily happen when importing bilingual
                # storage which can be monolingual as well
                if list(result.iterate_merge(False)):
                    return result
            except Exception as error:
                failure = error
        if file_format.monolingual in (False, None):
            try:
                result = file_format.parse(BytesIOMode(filename, content))
                result.check_valid()
                return result
            except Exception as error:
                failure = error

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
        language_code: Optional[str] = None,
        source_language: Optional[str] = None,
        is_template: bool = False,
    ):
        """Parse store and returns TTKitFormat instance.

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
                )
        return cls(
            storefile,
            template_store=template_store,
            language_code=language_code,
            is_template=is_template,
        )

    @classmethod
    def parse_store(cls, storefile):
        """Directly loads using translate-toolkit."""
        return factory.getobject(storefile)

    @classmethod
    def get_class(cls):
        return None
