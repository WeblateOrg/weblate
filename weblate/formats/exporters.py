#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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
"""Exporter using translate-toolkit."""

from django.http import HttpResponse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from lxml.etree import XMLSyntaxError
from translate.misc.multistring import multistring
from translate.storage.csvl10n import csvfile
from translate.storage.mo import mofile
from translate.storage.po import pofile
from translate.storage.poxliff import PoXliffFile
from translate.storage.tbx import tbxfile
from translate.storage.tmx import tmxfile
from translate.storage.xliff import xlifffile

import weblate
from weblate.formats.external import XlsxFormat
from weblate.formats.ttkit import TTKitFormat
from weblate.trans.util import split_plural, xliff_string_to_rich
from weblate.utils.site import get_site_url

# Map to remove control characters except newlines and tabs
_CHARMAP = dict.fromkeys(x for x in range(32) if x not in (9, 10, 13))

EXPORTERS = {}


def register_exporter(exporter):
    """Register an exporter."""
    EXPORTERS[exporter.name] = exporter
    return exporter


def get_exporter(name):
    """Return registered exporter."""
    return EXPORTERS[name]


def list_exporters(translation):
    return [
        {"name": x.name, "verbose": x.verbose}
        for x in sorted(EXPORTERS.values(), key=lambda x: x.name)
        if x.supports(translation)
    ]


class BaseExporter:
    content_type = "text/plain"
    extension = "txt"
    name = ""
    verbose = ""
    set_id = False

    def __init__(
        self, project=None, language=None, url=None, translation=None, fieldnames=None
    ):
        if translation is not None:
            self.plural = translation.plural
            self.project = translation.component.project
            self.language = translation.language
            self.url = get_site_url(translation.get_absolute_url())
        else:
            self.project = project
            self.language = language
            self.plural = language.plural
            self.url = url
        self.fieldnames = fieldnames

    @staticmethod
    def supports(translation):
        return True

    @cached_property
    def storage(self):
        storage = self.get_storage()
        storage.setsourcelanguage(self.project.source_language.code)
        storage.settargetlanguage(self.language.code)
        return storage

    def string_filter(self, text):
        return text

    def handle_plurals(self, plurals):
        if len(plurals) == 1:
            return self.string_filter(plurals[0])
        return multistring([self.string_filter(plural) for plural in plurals])

    def get_storage(self):
        return self.storage_class()

    def add(self, unit, word):
        unit.target = word

    def add_dictionary(self, word):
        """Add dictionary word."""
        unit = self.storage.UnitClass(self.string_filter(word.source))
        self.add(unit, self.string_filter(word.target))
        self.storage.addunit(unit)

    def add_units(self, units):
        for unit in units.iterator():
            self.add_unit(unit)

    def build_unit(self, unit):
        output = self.storage.UnitClass(self.handle_plurals(unit.get_source_plurals()))
        self.add(output, self.handle_plurals(unit.get_target_plurals()))
        return output

    def add_unit(self, unit):
        output = self.build_unit(unit)
        # Location needs to be set prior to ID to avoid overwrite
        # on some formats (for example xliff)
        for location in unit.location.split():
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
            output.addnote(note, origin="developer")
        # In Weblate explanation
        note = self.string_filter(unit.explanation)
        if note:
            output.addnote(note, origin="developer")
        # Comments
        for comment in unit.all_comments:
            output.addnote(comment.comment, origin="translator")
        # Suggestions
        for suggestion in unit.suggestions:
            output.addnote(
                "Suggested in Weblate: {}".format(
                    ", ".join(split_plural(suggestion.target))
                ),
                origin="translator",
            )

        # Store flags
        if unit.all_flags:
            self.store_flags(output, unit.all_flags)

        # Store fuzzy flag
        if unit.fuzzy:
            output.markfuzzy(True)

        self.storage.addunit(output)

    def get_response(self, filetemplate="{project}-{language}.{extension}"):
        filename = filetemplate.format(
            project=self.project.slug,
            language=self.language.code,
            extension=self.extension,
        )

        response = HttpResponse(
            content_type="{0}; charset=utf-8".format(self.content_type)
        )
        response["Content-Disposition"] = "attachment; filename={0}".format(filename)

        # Save to response
        response.write(self.serialize())

        return response

    def serialize(self):
        """Return storage content."""
        return TTKitFormat.serialize(self.storage)

    def store_flags(self, output, flags):
        return


@register_exporter
class PoExporter(BaseExporter):
    name = "po"
    content_type = "text/x-po"
    extension = "po"
    verbose = _("gettext PO")
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
            x_generator="Weblate {0}".format(weblate.VERSION),
            project_id_version="{0} ({1})".format(
                self.language.name, self.project.name
            ),
            plural_forms=plural.plural_form,
            language_team="{0} <{1}>".format(self.language.name, self.url),
        )
        return store


class XMLExporter(BaseExporter):
    """Wrapper for XML based exporters to strip control characters."""

    def string_filter(self, text):
        return text.translate(_CHARMAP)

    def add(self, unit, word):
        unit.settarget(word, self.language.code)


@register_exporter
class PoXliffExporter(XMLExporter):
    name = "xliff"
    content_type = "application/x-xliff+xml"
    extension = "xlf"
    set_id = True
    verbose = _("XLIFF with gettext extensions")
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
        except (XMLSyntaxError, TypeError):
            return output
        output.rich_source = converted_source
        output.set_rich_target(converted_target, self.language.code)
        return output


@register_exporter
class XliffExporter(PoXliffExporter):
    name = "xliff11"
    content_type = "application/x-xliff+xml"
    extension = "xlf"
    set_id = True
    verbose = _("XLIFF 1.1")
    storage_class = xlifffile


@register_exporter
class TBXExporter(XMLExporter):
    name = "tbx"
    content_type = "application/x-tbx"
    extension = "tbx"
    verbose = _("TBX")
    storage_class = tbxfile


@register_exporter
class TMXExporter(XMLExporter):
    name = "tmx"
    content_type = "application/x-tmx"
    extension = "tmx"
    verbose = _("TMX")
    storage_class = tmxfile


@register_exporter
class MoExporter(PoExporter):
    name = "mo"
    content_type = "application/x-gettext-catalog"
    extension = "mo"
    verbose = _("gettext MO")
    storage_class = mofile

    def __init__(
        self, project=None, language=None, url=None, translation=None, fieldnames=None
    ):
        super().__init__(project, language, url, translation, fieldnames)
        # Detect storage properties
        self.monolingual = False
        self.use_context = False
        if translation:
            self.monolingual = translation.component.has_template()
            if self.monolingual:
                unit = next(translation.store.content_units, None)
                self.use_context = unit is not None and not unit.template.source

    def store_flags(self, output, flags):
        return

    def add_unit(self, unit):
        # We do not store not translated units
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
        output = self.storage.UnitClass(source)
        output.target = self.handle_plurals(unit.get_target_plurals())
        if context:
            # The setcontext doesn't work on mounit
            output.msgctxt = [context]
        # Add unit to the storage
        self.storage.addunit(output)

    @staticmethod
    def supports(translation):
        return translation.component.file_format == "po"


class CVSBaseExporter(BaseExporter):
    storage_class = csvfile

    def get_storage(self):
        return self.storage_class(fieldnames=self.fieldnames)


@register_exporter
class CSVExporter(CVSBaseExporter):
    name = "csv"
    content_type = "text/csv"
    extension = "csv"
    verbose = _("CSV")

    def string_filter(self, text):
        """Avoid Excel interpreting text as formula.

        This is really bad idea, implemented in Excel, as this change leads to
        displaying additional ' in all other tools, but this seems to be what most
        people have gotten used to. Hopefully these characters are not widely used at
        first position of translatable strings, so that harm is reduced.
        """
        if text and text[0] in ("=", "+", "-", "@", "|", "%"):
            return "'{0}'".format(text.replace("|", "\\|"))
        return text


@register_exporter
class XlsxExporter(CVSBaseExporter):
    name = "xlsx"
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    extension = "xlsx"
    verbose = _("Excel Open XML")

    def serialize(self):
        """Return storage content."""
        return XlsxFormat.serialize(self.storage)
