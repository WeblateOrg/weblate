# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Plain text file formats."""

from __future__ import annotations

import os
from glob import glob
from itertools import chain
from typing import TYPE_CHECKING, BinaryIO, NoReturn

from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy

from weblate.formats.base import (
    BaseItem,
    BaseStore,
    TranslationFormat,
    TranslationUnit,
)
from weblate.utils.errors import report_error

if TYPE_CHECKING:
    from collections.abc import Callable


class MultiparserError(Exception):
    def __init__(self, filename, original) -> None:
        super().__init__()
        self.filename = filename
        self.original = original

    def __str__(self) -> str:
        return f"{self.filename}: {self.original}"


class TextItem(BaseItem):
    """Actual text unit object."""

    def __init__(self, filename, line, text, flags=None) -> None:
        self.filename = filename
        self.line = line
        self.text = text
        self.flags = flags

    @cached_property
    def location(self) -> str:
        return f"{self.filename}:{self.line}"

    def getid(self):
        return self.location


class TextParser:
    """Simple text parser returning all content as single unit."""

    def __init__(self, storefile, filename=None, flags=None) -> None:
        with open(storefile) as handle:
            content = handle.read()
        if filename:
            self.filename = filename
        else:
            self.filename = os.path.basename(storefile)
        self.units = [TextItem(self.filename, 1, content.strip(), flags)]


class TextSerializer:
    def __init__(self, filename, units) -> None:
        self.units = [unit for unit in units if unit.filename == filename]

    def __call__(self, handle):
        for unit in self.units:
            handle.write(unit.text.encode())
            handle.write(b"\n")


class MultiParser(BaseStore):
    filenames: tuple[tuple[str, str], ...] = ()
    units: list[TextItem]

    def __init__(self, storefile) -> None:
        if not isinstance(storefile, str):
            msg = "Needs string as a storefile!"
            raise TypeError(msg)

        if not os.path.isdir(storefile):
            raise ValueError(gettext("Should be a directory with metadata files!"))

        self.base = storefile
        self.parsers = self.load_parser()
        self.units = list(
            chain.from_iterable(parser.units for parser in self.parsers.values())
        )

    def file_key(self, filename):
        return filename

    def load_parser(self):
        result = {}
        for name, flags in self.filenames:
            filename = self.get_filename(name)
            for match in sorted(glob(filename), key=self.file_key):
                # Needed to allow overlapping globs, more specific first
                if match in result:
                    continue
                try:
                    result[match] = TextParser(
                        match, os.path.relpath(match, self.base), flags
                    )
                except Exception as error:
                    raise MultiparserError(match, error) from error
        return result

    def get_filename(self, name):
        return os.path.join(self.base, name)


class AppStoreParser(MultiParser):
    filenames = (
        ("title.txt", "max-length:30"),
        ("name.txt", "max-length:30"),
        ("short[_-]description.txt", "max-length:80"),
        ("summary.txt", "max-length:80"),
        ("full[_-]description.txt", "max-length:4000"),
        ("subtitle.txt", "max-length:80"),
        ("description.txt", "max-length:4000"),
        ("keywords.txt", "max-length:100"),
        ("video.txt", "max-length:256, url"),
        ("marketing_url.txt", "max-length:256, url"),
        ("privacy_url.txt", "max-length:256, url"),
        ("support_url.txt", "max-length:256, url"),
        ("antifeatures/*.txt", "max-length:500"),
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
    template: TextItem | None
    unit: TextItem
    mainunit: TextItem

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

    def set_target(self, target: str | list[str]) -> None:
        """Set translation unit target."""
        self._invalidate_target()
        self.unit.text = target

    def set_state(self, state) -> None:
        """Set fuzzy /approved flag on translated unit."""
        return


class AppStoreFormat(TranslationFormat):
    name = gettext_lazy("App store metadata files")
    format_id = "appstore"
    can_add_unit = False
    can_delete_unit = True
    monolingual = True
    unit_class = TextUnit
    simple_filename = False
    language_format = "googleplay"
    create_style = "directory"
    store: AppStoreParser

    def load(
        self, storefile: str | BinaryIO, template_store: TranslationFormat | None
    ) -> AppStoreParser:
        return AppStoreParser(storefile)

    def create_unit(
        self,
        key: str,
        source: str | list[str],
        target: str | list[str] | None = None,
    ) -> NoReturn:
        msg = "Create not supported"
        raise ValueError(msg)

    @classmethod
    def create_new_file(
        cls,
        filename: str,
        language: str,  # noqa: ARG003
        base: str,  # noqa: ARG003
        callback: Callable | None = None,  # noqa: ARG003
    ) -> None:
        """Handle creation of new translation file."""
        os.makedirs(filename)

    def add_unit(self, unit: TextUnit) -> None:  # type: ignore[override]
        """Add new unit to underlying store."""
        self.store.units.append(unit.unit)

    def save(self) -> None:
        """Save underlying store to disk."""
        for unit in self.store.units:
            filename = self.store.get_filename(unit.filename)
            if not unit.text:
                if os.path.exists(filename):
                    os.unlink(filename)
                continue
            self.save_atomic(
                filename,
                TextSerializer(unit.filename, self.store.units),
            )

    def get_filenames(self):
        return [self.store.get_filename(unit.filename) for unit in self.store.units]

    @classmethod
    def get_class(cls) -> None:
        return None

    @classmethod
    def is_valid_base_for_new(
        cls,
        base: str,
        monolingual: bool,  # noqa: ARG003
        errors: list | None = None,
        fast: bool = False,
    ) -> bool:
        """Check whether base is valid."""
        if not base:
            return True
        try:
            if not fast:
                AppStoreParser(base)
        except Exception as exception:
            if errors is not None:
                errors.append(exception)
            report_error("File-parsing error")
            return False
        return True

    def delete_unit(self, ttkit_unit) -> str | None:
        filename = self.store.get_filename(ttkit_unit.filename)
        os.unlink(filename)
        return filename
