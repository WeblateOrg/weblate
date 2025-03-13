# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exporter using translate-toolkit."""

from __future__ import annotations

import re
from itertools import chain
from typing import TYPE_CHECKING, ClassVar

from django.utils.translation import gettext_lazy
from lxml.etree import XMLSyntaxError
from translate.misc.multistring import multistring
from translate.storage.aresource import AndroidResourceFile
from translate.storage.csvl10n import csvfile
from translate.storage.jsonl10n import JsonFile, JsonNestedFile
from translate.storage.mo import mofile
from translate.storage.po import pofile
from translate.storage.poxliff import PoXliffFile
from translate.storage.properties import stringsutf8file
from translate.storage.tbx import tbxfile
from translate.storage.tmx import tmxfile
from translate.storage.xliff import xlifffile

import weblate.utils.version
from weblate.formats.external import XlsxFormat
from weblate.trans.util import xliff_string_to_rich
from weblate.utils.csv import PROHIBITED_INITIAL_CHARS

from .base import BaseExporter

if TYPE_CHECKING:
    from translate.storage.base import TranslationStore
    from translate.storage.lisa import LISAfile

# Map to remove control characters except newlines and tabs
# Based on lxml - src/lxml/apihelpers.pxi _is_valid_xml_utf8
XML_REPLACE_CHARMAP = dict.fromkeys(
    chain(
        (x for x in range(32) if x not in {9, 10, 13}),
        [0xFFFE, 0xFFFF],
        range(0xD800, 0xDFFF + 1),
    )
)

DASHES = re.compile(r"--+")


class PoExporter(BaseExporter):
    name = "po"
    content_type = "text/x-po"
    extension = "po"
    verbose = gettext_lazy("gettext PO")
    storage_class: ClassVar[type[TranslationStore]] = pofile

    def store_flags(self, output, flags) -> None:
        for flag in flags.items():
            output.settypecomment(flags.format_flag(flag))

    def get_storage(self):
        store = super().get_storage()
        plural = self.plural

        # Set po file header
        store.updateheader(
            add=True,
            language=self.language.code,
            x_generator=f"Weblate {weblate.utils.version.VERSION}",
            project_id_version=f"{self.language.name} ({self.project.name})",
            plural_forms=plural.plural_form,
            language_team=f"{self.language.name} <{self.url}>",
        )
        return store


class XMLFilterMixin(BaseExporter):
    def string_filter(self, text):
        return super().string_filter(text).translate(XML_REPLACE_CHARMAP)


class XMLExporter(XMLFilterMixin, BaseExporter):
    """Wrapper for XML based exporters to strip control characters."""

    storage_class: ClassVar[type[LISAfile]]

    def get_storage(self):
        return self.storage_class(
            sourcelanguage=self.source_language.code,
            targetlanguage=self.language.code,
        )

    def add(self, unit, word) -> None:
        unit.settarget(word, self.language.code)


class PoXliffExporter(XMLExporter):
    name = "xliff"
    content_type = "application/x-xliff+xml"
    extension = "xlf"
    set_id = True
    verbose = gettext_lazy("XLIFF 1.1 with gettext extensions")
    storage_class: ClassVar[type[LISAfile]] = PoXliffFile

    def store_flags(self, output, flags) -> None:
        if flags.has_value("max-length"):
            output.xmlelement.set("maxwidth", str(flags.get_value("max-length")))

        output.xmlelement.set("weblate-flags", flags.format())

    def handle_plurals(self, plurals):
        if len(plurals) == 1:
            return self.string_filter(plurals[0])
        return multistring([self.string_filter(plural) for plural in plurals])

    def build_unit(self, unit):
        output = super().build_unit(unit)
        try:
            converted_source = xliff_string_to_rich(unit.get_source_plurals())
            converted_target = xliff_string_to_rich(unit.get_target_plurals())
        except (XMLSyntaxError, TypeError, KeyError):
            return output
        output.set_rich_source(converted_source, self.source_language.code)
        output.set_rich_target(converted_target, self.language.code)
        return output


class XliffExporter(PoXliffExporter):
    name = "xliff11"
    content_type = "application/x-xliff+xml"
    extension = "xlf"
    set_id = True
    verbose = gettext_lazy("XLIFF 1.1")
    storage_class = xlifffile


class TBXExporter(XMLExporter):
    name = "tbx"
    content_type = "application/x-tbx"
    extension = "tbx"
    verbose = gettext_lazy("TBX")
    storage_class = tbxfile


class TMXExporter(XMLExporter):
    name = "tmx"
    content_type = "application/x-tmx"
    extension = "tmx"
    verbose = gettext_lazy("TMX")
    storage_class = tmxfile


class MoExporter(PoExporter):
    name = "mo"
    content_type = "application/x-gettext-catalog"
    extension = "mo"
    verbose = gettext_lazy("gettext MO")
    storage_class = mofile

    def __init__(
        self,
        project=None,
        source_language=None,
        language=None,
        url=None,
        translation=None,
        fieldnames=None,
    ) -> None:
        super().__init__(
            project=project,
            source_language=source_language,
            language=language,
            url=url,
            translation=translation,
            fieldnames=fieldnames,
        )
        # Detect storage properties
        self.monolingual = False
        self.use_context = False
        if translation:
            self.monolingual = translation.component.has_template()
            if self.monolingual:
                try:
                    unit = translation.store.content_units[0]
                    self.use_context = not unit.template.source
                except IndexError:
                    pass

    def store_flags(self, output, flags) -> None:
        return

    def add_unit(self, unit) -> None:
        # Parse properties from unit
        if self.monolingual:
            if self.use_context:
                source = ""
                context = unit.context
            else:
                source = unit.context
                context = ""
        else:
            source = self.handle_plurals(unit.get_source_plurals())
            context = unit.context
        # Actually create the unit and set attributes
        output = self.create_unit(source)
        output.target = self.handle_plurals(unit.get_target_plurals())
        if context:
            output.setcontext(context)
        # Add unit to the storage
        self.storage.addunit(output)

    @staticmethod
    def supports(translation):
        return translation.component.file_format in {"po", "po-mono"}


class CVSBaseExporter(BaseExporter):
    storage_class = csvfile

    def get_storage(self):
        storage = self.storage_class(fieldnames=self.fieldnames)
        # Use Excel dialect instead of translate-toolkit "default" to avoid
        # unnecessary escaping with backslash which later confuses our importer
        # at it is typically used occasionally.
        storage.dialect = "excel"
        return storage


class CSVExporter(CVSBaseExporter):
    name = "csv"
    content_type = "text/csv"
    extension = "csv"
    verbose = gettext_lazy("CSV")

    def string_filter(self, text):
        """
        Avoid Excel interpreting text as formula.

        This is really bad idea, implemented in Excel, as this change leads to
        displaying additional ' in all other tools, but this seems to be what most
        people have gotten used to. Hopefully these characters are not widely used at
        first position of translatable strings, so that harm is reduced.

        Reverse for this is in weblate.formats.ttkit.CSVUnit.unescape_csv
        """
        if text and text[0] in PROHIBITED_INITIAL_CHARS:
            return "'{}'".format(text.replace("|", "\\|"))
        return text


class XlsxExporter(XMLFilterMixin, CVSBaseExporter):
    name = "xlsx"
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    extension = "xlsx"
    verbose = gettext_lazy("XLSX")

    def serialize(self):
        """Return storage content."""
        return XlsxFormat.serialize(self.storage)


class MonolingualExporter(BaseExporter):
    """Base class for monolingual exports."""

    @staticmethod
    def supports(translation):
        return translation.component.has_template()

    def build_unit(self, unit):
        output = self.create_unit(unit.context)
        output.setid(unit.context)
        self.add(output, self.handle_plurals(unit.get_target_plurals()))
        return output


class JSONExporter(MonolingualExporter):
    storage_class = JsonFile
    name = "json"
    content_type = "application/json"
    extension = "json"
    verbose = gettext_lazy("JSON")


class JSONNestedExporter(JSONExporter):
    name = "json-nested"
    verbose = gettext_lazy("JSON nested structure file")
    storage_class = JsonNestedFile


class AndroidResourceExporter(XMLFilterMixin, MonolingualExporter):
    storage_class = AndroidResourceFile
    name = "aresource"
    content_type = "application/xml"
    extension = "xml"
    verbose = gettext_lazy("Android String Resource")

    def add(self, unit, word) -> None:
        # Need to have storage to handle plurals
        unit._store = self.storage  # noqa: SLF001
        super().add(unit, word)

    def add_note(self, output, note: str, origin: str) -> None:
        # Remove -- from the comment or - at the end as that is not
        # allowed inside XML comment
        note = DASHES.sub("-", note)
        if note.endswith("-"):
            note += " "
        super().add_note(output, note, origin)


class StringsExporter(MonolingualExporter):
    storage_class = stringsutf8file
    name = "strings"
    content_type = "text/plain"
    extension = "strings"
    verbose = gettext_lazy("iOS strings")

    def create_unit(self, source):
        return self.storage.UnitClass(source, self.storage.personality.name)
