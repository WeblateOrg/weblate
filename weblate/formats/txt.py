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
"""Plain text file formats."""

import os
from collections import OrderedDict
from glob import glob
from itertools import chain
from typing import List, Optional, Tuple, Union

from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from weblate.formats.base import TranslationFormat, TranslationUnit
from weblate.utils.errors import report_error


class TextItem:
    """Actual text unit object."""

    def __init__(self, filename, line, text, flags=None):
        self.filename = filename
        self.line = line
        self.text = text
        self.flags = flags

    @cached_property
    def location(self):
        return f"{self.filename}:{self.line}"

    def getid(self):
        return self.location


class TextParser:
    """Simple text parser returning all content as single unit."""

    def __init__(self, storefile, filename=None, flags=None):
        with open(storefile) as handle:
            content = handle.read()
        if filename:
            self.filename = filename
        else:
            self.filename = os.path.basename(storefile)
        self.units = [TextItem(self.filename, 1, content.strip(), flags)]


class TextSerializer:
    def __init__(self, filename, units):
        self.units = [unit for unit in units if unit.filename == filename]

    def __call__(self, handle):
        for unit in self.units:
            handle.write(unit.text.encode())
            handle.write(b"\n")


class MultiParser:
    filenames: Tuple[Tuple[str, str], ...] = ()

    def __init__(self, storefile):
        if not isinstance(storefile, str):
            raise ValueError("Needs string as a storefile!")

        self.base = storefile
        self.parsers = self.load_parser()
        self.units = list(
            chain.from_iterable(parser.units for parser in self.parsers.values())
        )

    def file_key(self, filename):
        return filename

    def load_parser(self):
        result = OrderedDict()
        for name, flags in self.filenames:
            filename = self.get_filename(name)
            for match in sorted(glob(filename), key=self.file_key):
                # Needed to allow overlapping globs, more specific first
                if match in result:
                    continue
                result[match] = TextParser(
                    match, os.path.relpath(match, self.base), flags
                )
        return result

    def get_filename(self, name):
        return os.path.join(self.base, name)


class AppStoreParser(MultiParser):
    filenames = (
        ("title.txt", "max-length:50"),
        ("short[_-]description.txt", "max-length:80"),
        ("full[_-]description.txt", "max-length:4000"),
        ("subtitle.txt", "max-length:80"),
        ("description.txt", "max-length:4000"),
        ("keywords.txt", "max-length:100"),
        ("video.txt", "max-length:256, url"),
        ("marketing_url.txt", "max-length:256, url"),
        ("privacy_url.txt", "max-length:256, url"),
        ("support_url.txt", "max-length:256, url"),
        ("changelogs/*.txt", "max-length:500"),
        ("*.txt", ""),
    )

    def file_key(self, filename):
        parts = filename.rsplit("changelogs/", 1)
        if len(parts) == 2:
            try:
                return "-{}".format(int(parts[1].split(".")[0]))
            except ValueError:
                pass
        return filename


class TextUnit(TranslationUnit):
    @cached_property
    def locations(self):
        """Return comma separated list of locations."""
        return self.mainunit.location

    @cached_property
    def source(self):
        """Return source string from a ttkit unit."""
        if self.template is not None:
            return self.template.text
        return self.unit.text

    @cached_property
    def target(self):
        """Return target string from a ttkit unit."""
        if self.unit is None:
            return ""
        return self.unit.text

    @cached_property
    def context(self):
        """Return context of message."""
        return self.mainunit.location

    @cached_property
    def flags(self):
        """Return flags from unit."""
        if self.mainunit.flags:
            return self.mainunit.flags
        return ""

    def set_target(self, target):
        """Set translation unit target."""
        self._invalidate_target()
        self.unit.text = target

    def mark_fuzzy(self, fuzzy):
        """Set fuzzy flag on translated unit."""
        return

    def mark_approved(self, value):
        """Set approved flag on translated unit."""
        return


class AppStoreFormat(TranslationFormat):
    name = _("App store metadata files")
    format_id = "appstore"
    can_add_unit = False
    monolingual = True
    unit_class = TextUnit
    simple_filename = False
    language_format = "java"

    @classmethod
    def load(cls, storefile, template_store):
        return AppStoreParser(storefile)

    def create_unit(self, key: str, source: Union[str, List[str]]):
        raise ValueError("Create not supported")

    @classmethod
    def create_new_file(cls, filename, language, base):
        """Handle creation of new translation file."""
        os.makedirs(filename)

    def add_unit(self, ttkit_unit):
        """Add new unit to underlaying store."""
        self.store.units.append(ttkit_unit)

    def save(self):
        """Save underlaying store to disk."""
        for unit in self.store.units:
            if not unit.text:
                continue
            self.save_atomic(
                self.store.get_filename(unit.filename),
                TextSerializer(unit.filename, self.store.units),
            )

    def get_filenames(self):
        return [self.store.get_filename(unit.filename) for unit in self.store.units]

    @classmethod
    def get_class(cls):
        return None

    @classmethod
    def is_valid_base_for_new(
        cls,
        base: str,
        monolingual: bool,
        errors: Optional[List] = None,
        fast: bool = False,
    ) -> bool:
        """Check whether base is valid."""
        if not base:
            return True
        try:
            if not fast:
                AppStoreParser(base)
            return True
        except Exception:
            report_error(cause="File parse error")
            return False

    def delete_unit(self, ttkit_unit) -> Optional[str]:
        filename = self.store.get_filename(ttkit_unit.filename)
        os.unlink(filename)
        return filename
