# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exporter using translate-toolkit."""

from __future__ import annotations

import re
from itertools import chain
from typing import TYPE_CHECKING

from django.http import HttpResponse
from django.utils.functional import cached_property
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
from weblate.formats.ttkit import TTKitFormat
from weblate.trans.util import split_plural, xliff_string_to_rich
from weblate.utils.site import get_site_url

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise


# Map to remove control characters except newlines and tabs
# Based on lxml - src/lxml/apihelpers.pxi _is_valid_xml_utf8
XML_REPLACE_CHARMAP = dict.fromkeys(
    chain(
        (x for x in range(32) if x not in (9, 10, 13)),
        [0xFFFE, 0xFFFF],
        range(0xD800, 0xDFFF + 1),
    )
)

DASHES = re.compile("--+")


class BaseExporter:
    content_type = "text/plain"
    extension = "txt"
    name = ""
    verbose: StrOrPromise = ""
    set_id = False

    def __init__(
        self,
        project=None,
        source_language=None,
        language=None,
        url=None,
        translation=None,
        fieldnames=None,
    ):
        self.translation = translation
        if translation is not None:
            self.plural = translation.plural
            self.project = translation.component.project
            self.source_language = translation.component.source_language
            self.language = translation.language
            self.url = get_site_url(translation.get_absolute_url())
        else:
            self.project = project
            self.language = language
            self.source_language = source_language
            self.plural = language.plural
            self.url = url
        self.fieldnames = fieldnames

    @staticmethod
    def supports(translation):  # noqa: ARG004
        return True

    @cached_property
    def storage(self):
        storage = self.get_storage()
        storage.setsourcelanguage(self.source_language.code)
        storage.settargetlanguage(self.language.code)
        return storage

    def string_filter(self, text):
        return text

    def handle_plurals(self, plurals):
        if len(plurals) == 1:
            return self.string_filter(plurals[0])
        return multistring([self.string_filter(plural) for plural in plurals])

    @classmethod
    def get_identifier(cls):
        return cls.name

    def get_storage(self):
        return self.storage_class()

    def add(self, unit, word):
        unit.target = word

    def create_unit(self, source):
        return self.storage.UnitClass(source)

    def add_units(self, units):
        for unit in units:
            self.add_unit(unit)

    def build_unit(self, unit):
        output = self.create_unit(self.handle_plurals(unit.get_source_plurals()))
        # Propagate source language
        if hasattr(output, "setsource"):
            output.setsource(output.source, sourcelang=self.source_language.code)
        self.add(output, self.handle_plurals(unit.get_target_plurals()))
        return output

    def add_note(self, output, note: str, origin: str):
        output.addnote(note, origin=origin)

    def add_unit(self, unit):
        output = self.build_unit(unit)
        # Location needs to be set prior to ID to avoid overwrite
        # on some formats (for example xliff)
        for location in unit.location.split(","):
            location = location.strip()
            if location:
                output.addlocation(location)

        # Store context as context and ID
        context = self.string_filter(unit.context)
        if context:
            output.setcontext(context)
            if self.set_id:
                output.setid(context)
        elif self.set_id:
            # Use checksum based ID on formats requiring it
            output.setid(unit.checksum)

        # Store note
        note = self.string_filter(unit.note)
        if note:
            self.add_note(output, note, origin="developer")
        # In Weblate explanation
        note = self.string_filter(unit.source_unit.explanation)
        if note:
            self.add_note(output, note, origin="developer")
        # Comments
        for comment in unit.unresolved_comments:
            self.add_note(output, comment.comment, origin="translator")
        # Suggestions
        for suggestion in unit.suggestions:
            self.add_note(
                output,
                "Suggested in Weblate: {}".format(
                    ", ".join(split_plural(suggestion.target))
                ),
                origin="translator",
            )

        # Store flags
        if unit.all_flags:
            self.store_flags(output, unit.all_flags)

        # Store fuzzy flag
        self.store_unit_state(output, unit)

        self.storage.addunit(output)

    def store_unit_state(self, output, unit):
        if unit.fuzzy:
            output.markfuzzy(True)
        if hasattr(output, "markapproved"):
            output.markapproved(unit.approved)

    def get_filename(self, filetemplate: str = "{path}.{extension}"):
        return filetemplate.format(
            project=self.project.slug,
            language=self.language.code,
            extension=self.extension,
            path="-".join(
                self.translation.get_url_path()
                if self.translation
                else (self.project.slug, self.language.code)
            ),
        )

    def get_response(self, filetemplate: str = "{path}.{extension}"):
        filename = self.get_filename(filetemplate)

        response = HttpResponse(content_type=f"{self.content_type}; charset=utf-8")
        response["Content-Disposition"] = f"attachment; filename={filename}"

        # Save to response
        response.write(self.serialize())

        return response

    def serialize(self):
        """Return storage content."""
        return TTKitFormat.serialize(self.storage)

    def store_flags(self, output, flags):
        return


class PoExporter(BaseExporter):
    name = "po"
    content_type = "text/x-po"
    extension = "po"
    verbose = gettext_lazy("gettext PO")
    storage_class = pofile

    def store_flags(self, output, flags):
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


class XMLFilterMixin:
    def string_filter(self, text):
        return super().string_filter(text).translate(XML_REPLACE_CHARMAP)


class XMLExporter(XMLFilterMixin, BaseExporter):
    """Wrapper for XML based exporters to strip control characters."""

    def get_storage(self):
        return self.storage_class(
            sourcelanguage=self.source_language.code,
            targetlanguage=self.language.code,
        )

    def add(self, unit, word):
        unit.settarget(word, self.language.code)


class PoXliffExporter(XMLExporter):
    name = "xliff"
    content_type = "application/x-xliff+xml"
    extension = "xlf"
    set_id = True
    verbose = gettext_lazy("XLIFF 1.1 with gettext extensions")
    storage_class = PoXliffFile

    def store_flags(self, output, flags):
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
    ):
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

    def store_flags(self, output, flags):
        return

    def add_unit(self, unit):
        # We do not store untranslated units
        if not unit.translated:
            return
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
        return translation.component.file_format == "po"


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
        if text and text[0] in ("=", "+", "-", "@", "|", "%"):
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

    def add(self, unit, word):
        # Need to have storage to handle plurals
        unit._store = self.storage
        super().add(unit, word)

    def add_note(self, output, note: str, origin: str):
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
