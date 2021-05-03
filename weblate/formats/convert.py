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
"""Translate Toolkit convertor based file format wrappers."""

import codecs
import os
import shutil
from io import BytesIO
from typing import List, Optional, Union
from zipfile import ZipFile

from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from translate.convert.po2html import po2html
from translate.convert.po2idml import translate_idml, write_idml
from translate.convert.po2rc import rerc
from translate.convert.po2txt import po2txt
from translate.convert.rc2po import rc2po
from translate.convert.xliff2odf import translate_odf, write_odf
from translate.storage.html import htmlfile
from translate.storage.idml import INLINE_ELEMENTS, NO_TRANSLATE_ELEMENTS, open_idml
from translate.storage.odf_io import open_odf
from translate.storage.odf_shared import inline_elements, no_translate_content_elements
from translate.storage.po import pofile
from translate.storage.rc import rcfile
from translate.storage.txt import TxtFile
from translate.storage.xliff import xlifffile
from translate.storage.xml_extract.extract import (
    IdMaker,
    ParseState,
    build_idml_store,
    build_store,
    make_postore_adder,
)

from weblate.formats.base import TranslationFormat
from weblate.formats.helpers import BytesIOMode
from weblate.formats.ttkit import TTKitUnit, XliffUnit
from weblate.utils.errors import report_error
from weblate.utils.state import STATE_APPROVED


class ConvertUnit(TTKitUnit):
    def is_translated(self):
        """Check whether unit is translated."""
        return self.unit is not None

    def is_fuzzy(self, fallback=False):
        """Check whether unit needs editing."""
        return fallback

    def is_approved(self, fallback=False):
        """Check whether unit is appoved."""
        return fallback

    @cached_property
    def locations(self):
        return ""

    @cached_property
    def context(self):
        """Return context of message."""
        return "".join(self.mainunit.getlocations())


class ConvertXliffUnit(XliffUnit):
    def is_fuzzy(self, fallback=False):
        """Check whether unit needs editing."""
        return fallback

    def is_approved(self, fallback=False):
        """Check whether unit is appoved."""
        return fallback

    def is_translated(self):
        """Check whether unit is translated."""
        return self.unit is not None


class ConvertFormat(TranslationFormat):
    """
    Base class for convert based formats.

    This always uses intermediate representation.
    """

    monolingual = True
    can_add_unit = False
    needs_target_sync = True
    unit_class = ConvertUnit
    autoaddon = {"weblate.flags.same_edit": {}}

    def save_content(self, handle):
        """Store content to file."""
        raise NotImplementedError()

    def save(self):
        """Save underlaying store to disk."""
        self.save_atomic(self.storefile, self.save_content)

    @staticmethod
    def convertfile(storefile, template_store):
        raise NotImplementedError()

    @classmethod
    def load(cls, storefile, template_store):
        # Did we get file or filename?
        if not hasattr(storefile, "read"):
            storefile = open(storefile, "rb")
        # Adjust store to have translations
        store = cls.convertfile(storefile, template_store)
        for unit in store.units:
            if unit.isheader():
                continue
            # HTML does this properly on loading, others need it
            if cls.needs_target_sync:
                unit.target = unit.source
                unit.rich_target = unit.rich_source
        return store

    @classmethod
    def create_new_file(cls, filename, language, base):
        """Handle creation of new translation file."""
        if not base:
            raise ValueError("Not supported")
        # Copy file
        shutil.copy(base, filename)

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
            return False
        try:
            if not fast:
                cls.load(base, None)
            return True
        except Exception:
            report_error(cause="File parse error")
            return False

    def add_unit(self, ttkit_unit):
        self.store.addunit(ttkit_unit)

    @classmethod
    def get_class(cls):
        return None

    def create_unit(self, key: str, source: Union[str, List[str]]):
        raise ValueError("Not supported")

    def cleanup_unused(self) -> List[str]:
        """
        Bring target in sync with the source.

        This is done automatically on save as it reshapes translations
        based on the template.
        """
        self.save()
        return []


class HTMLFormat(ConvertFormat):
    name = _("HTML file")
    autoload = ("*.htm", "*.html")
    format_id = "html"
    check_flags = ("safe-html", "strict-same")
    needs_target_sync = False

    @staticmethod
    def convertfile(storefile, template_store):
        store = pofile()
        # Fake input file with a blank filename
        htmlparser = htmlfile(inputfile=BytesIOMode("", storefile.read()))
        for htmlunit in htmlparser.units:
            locations = htmlunit.getlocations()
            if template_store:
                # Transalation
                template = template_store.find_unit_mono("".join(locations))
                if template is None:
                    # Skip locations not present in the source HTML file
                    continue
                # Create unit with matching source
                thepo = store.addsourceunit(template.source)
                thepo.target = htmlunit.source
            else:
                # Source file
                thepo = store.addsourceunit(htmlunit.source)
                thepo.target = htmlunit.source
            thepo.addlocations(htmlunit.getlocations())
            thepo.addnote(htmlunit.getnotes(), "developer")
        store.removeduplicates("msgctxt")
        return store

    def save_content(self, handle):
        """Store content to file."""
        convertor = po2html()
        templatename = self.template_store.storefile
        if hasattr(templatename, "name"):
            templatename = templatename.name
        with open(templatename, "rb") as templatefile:
            outputstring = convertor.mergestore(
                self.store, templatefile, includefuzzy=False
            )
        handle.write(outputstring.encode("utf-8"))

    @staticmethod
    def mimetype():
        """Return most common mime type for format."""
        return "text/html"

    @staticmethod
    def extension():
        """Return most common file extension for format."""
        return "html"


class OpenDocumentFormat(ConvertFormat):
    name = _("OpenDocument file")
    autoload = (
        "*.sxw",
        "*.odt",
        "*.ods",
        "*.odp",
        "*.odg",
        "*.odc",
        "*.odf",
        "*.odi",
        "*.odm",
        "*.ott",
        "*.ots",
        "*.otp",
        "*.otg",
        "*.otc",
        "*.otf",
        "*.oti",
        "*.oth",
    )
    format_id = "odf"
    check_flags = ("strict-same",)
    unit_class = ConvertXliffUnit

    @staticmethod
    def convertfile(storefile, template_store):
        store = xlifffile()
        store.setfilename(store.getfilenode("NoName"), "odf")
        contents = open_odf(storefile)
        for data in contents.values():
            parse_state = ParseState(no_translate_content_elements, inline_elements)
            build_store(BytesIO(data), store, parse_state)
        return store

    def save_content(self, handle):
        """Store content to file."""
        templatename = self.template_store.storefile
        if hasattr(templatename, "name"):
            templatename = templatename.name
        # This is workaround for weird fuzzy handling in translate-toolkit
        for unit in self.all_units:
            if unit.xliff_state == "translated":
                unit.set_state(STATE_APPROVED)

        with open(templatename, "rb") as templatefile:
            dom_trees = translate_odf(templatefile, self.store)
            write_odf(templatefile, handle, dom_trees)

    @staticmethod
    def mimetype():
        """Return most common mime type for format."""
        return "application/vnd.oasis.opendocument.text"

    @staticmethod
    def extension():
        """Return most common file extension for format."""
        return "odt"


class IDMLFormat(ConvertFormat):
    name = _("IDML file")
    autoload = ("*.idml", "*.idms")
    format_id = "idml"
    check_flags = ("strict-same",)

    @staticmethod
    def convertfile(storefile, template_store):
        store = pofile()

        contents = open_idml(storefile)

        # Create it here to avoid having repeated ids.
        id_maker = IdMaker()

        for filename, translatable_file in contents.items():
            parse_state = ParseState(NO_TRANSLATE_ELEMENTS, INLINE_ELEMENTS)
            po_store_adder = make_postore_adder(store, id_maker, filename)
            build_idml_store(
                BytesIO(translatable_file),
                store,
                parse_state,
                store_adder=po_store_adder,
            )

        return store

    def save_content(self, handle):
        """Store content to file."""
        templatename = self.template_store.storefile
        if hasattr(templatename, "name"):
            templatename = templatename.name
        with ZipFile(templatename, "r") as template_zip:
            translatable_files = [
                filename
                for filename in template_zip.namelist()
                if filename.startswith("Stories/")
            ]

            dom_trees = translate_idml(templatename, self.store, translatable_files)

            write_idml(template_zip, handle, dom_trees)

    @staticmethod
    def mimetype():
        """Return most common mime type for format."""
        return "application/octet-stream"

    @staticmethod
    def extension():
        """Return most common file extension for format."""
        return "idml"


class WindowsRCFormat(ConvertFormat):
    name = _("RC file")
    format_id = "rc"
    autoload = ("*.rc",)
    language_format = "bcp"

    @staticmethod
    def mimetype():
        """Return most common media type for format."""
        return "text/plain"

    @staticmethod
    def extension():
        """Return most common file extension for format."""
        return "rc"

    @staticmethod
    def convertfile(storefile, template_store):

        input_store = rcfile(storefile)
        convertor = rc2po()
        store = convertor.convert_store(input_store)
        store.rcfile = input_store
        return store

    def save_content(self, handle):
        """Store content to file."""
        # Fallback language
        lang = "LANG_ENGLISH"
        sublang = "SUBLANG_DEFAULT"

        # Keep existing language tags
        storage = self.store.rcfile
        if storage.lang:
            lang = storage.lang
            if storage.sublang:
                sublang = storage.sublang

        templatename = self.template_store.storefile
        if hasattr(templatename, "name"):
            templatename = templatename.name
        encoding = "utf-8"
        with open(templatename, "rb") as templatefile:
            bom = templatefile.read(2)
            if bom == codecs.BOM_UTF16_LE or b"\000" in bom:
                encoding = "utf-16-le"
            templatefile.seek(0)
            convertor = rerc(
                templatefile,
                lang=lang,
                sublang=sublang,
                charset=encoding,
            )
            outputrclines = convertor.convertstore(self.store)
            try:
                handle.write(outputrclines.encode(encoding))
            except UnicodeEncodeError:
                handle.write(codecs.BOM_UTF16_LE)
                handle.write(outputrclines.encode("utf-16-le"))


class PlainTextFormat(ConvertFormat):
    name = _("Plain text file")
    format_id = "txt"
    autoload = ("*.txt",)
    flavour = "plain"

    @staticmethod
    def mimetype():
        """Return most common media type for format."""
        return "text/plain"

    @staticmethod
    def extension():
        """Return most common file extension for format."""
        return "txt"

    @classmethod
    def convertfile(cls, storefile, template_store):
        input_store = TxtFile(encoding="utf-8", flavour=cls.flavour)
        input_store.filename = os.path.basename(storefile.name)
        input_store.parse(storefile.readlines())
        store = pofile()
        # This is translate.convert.txt2po.txt2po.convert_store
        for source_unit in input_store.units:
            target_unit = store.addsourceunit(source_unit.source)
            target_unit.addlocations(source_unit.getlocations())
        return store

    def save_content(self, handle):
        """Store content to file."""
        templatename = self.template_store.storefile
        if hasattr(templatename, "name"):
            templatename = templatename.name
        with open(templatename, "rb") as templatefile:
            converter = po2txt(
                input_file=self.store,
                output_file=None,
                template_file=templatefile,
            )
            outputstring = converter.merge_stores()
        handle.write(outputstring.encode("utf-8"))


class DokuWikiFormat(PlainTextFormat):
    name = _("DokuWiki text file")
    format_id = "dokuwiki"
    autoload = ("*.dw",)
    flavour = "dokuwiki"


class MediaWikiFormat(PlainTextFormat):
    name = _("MediaWiki text file")
    format_id = "mediawiki"
    autoload = ("*.mw",)
    flavour = "mediawiki"
