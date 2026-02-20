# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Translate Toolkit converter based file format wrappers."""

from __future__ import annotations

import codecs
import os
import shutil
from collections import defaultdict
from io import BytesIO
from operator import attrgetter
from typing import IO, TYPE_CHECKING, Any, ClassVar, NoReturn, cast
from zipfile import ZipFile

from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy
from translate.convert.po2asciidoc import AsciiDocTranslator
from translate.convert.po2html import po2html
from translate.convert.po2idml import translate_idml, write_idml
from translate.convert.po2rc import rerc
from translate.convert.po2txt import po2txt
from translate.convert.rc2po import rc2po
from translate.convert.xliff2odf import translate_odf, write_odf
from translate.storage.asciidoc import AsciiDocFile
from translate.storage.html import htmlfile
from translate.storage.idml import INLINE_ELEMENTS, NO_TRANSLATE_ELEMENTS, open_idml
from translate.storage.odf_io import open_odf
from translate.storage.odf_shared import inline_elements, no_translate_content_elements
from translate.storage.pypo import pofile
from translate.storage.rc import rcfile
from translate.storage.txt import TxtFile
from translate.storage.wxl import WxlFile
from translate.storage.xliff import Xliff1File
from translate.storage.xml_extract.extract import (
    IdMaker,
    ParseState,
    build_idml_store,
    build_store,
    make_postore_adder,
)

from weblate.formats.base import (
    TranslationFormat,
)
from weblate.formats.helpers import NamedBytesIO
from weblate.formats.ttkit import PoUnit, XliffUnit
from weblate.trans.util import get_string
from weblate.utils.concurrency import MARKDOWN_LOCK
from weblate.utils.errors import report_error
from weblate.utils.state import STATE_APPROVED

if TYPE_CHECKING:
    from collections.abc import Callable

    from translate.storage.base import TranslationStore
    from translate.storage.base import TranslationUnit as TranslateToolkitUnit

    from weblate.formats.base import TranslationUnit
    from weblate.trans.file_format_params import FileFormatParams
    from weblate.trans.models import Unit


class ConvertPoUnit(PoUnit):
    id_hash_with_source: bool = True

    def is_translated(self) -> bool:
        """Check whether unit is translated."""
        if self.parent.is_template:
            return self.has_translation()
        return self.unit is not None and self.has_translation()

    def is_fuzzy(self, fallback: bool = False) -> bool:
        """Check whether unit needs editing."""
        return fallback

    def is_approved(self, fallback: bool = False) -> bool:
        """Check whether unit is approved."""
        return fallback

    @cached_property
    def source(self) -> str:
        """Return source string from a Translate Toolkit unit."""
        if self.template:
            return get_string(self.template.source)
        return get_string(self.unit.source)


class ConvertXliffUnit(XliffUnit):
    remove_flags: ClassVar[list[str]] = ["xml-text"]

    def is_fuzzy(self, fallback: bool = False) -> bool:
        """Check whether unit needs editing."""
        return fallback

    def is_approved(self, fallback: bool = False) -> bool:
        """Check whether unit is approved."""
        return fallback

    def is_translated(self) -> bool:
        """Check whether unit is translated."""
        if self.parent.is_template:
            return self.has_translation()
        return self.unit is not None


class ConvertFormat(TranslationFormat):
    """
    Base class for convert based formats.

    This always uses intermediate representation.
    """

    monolingual = True
    can_add_unit = False
    can_delete_unit = False
    can_edit_base: bool = False
    unit_class: type[TranslationUnit] = ConvertPoUnit
    autoaddon: ClassVar[dict[str, dict[str, Any]]] = {
        "weblate.flags.same_edit": {},
        "weblate.cleanup.generic": {},
    }
    create_style = "copy"
    units: list[TranslateToolkitUnit]
    store: TranslationStore

    def save_content(self, handle: IO[bytes]) -> None:
        """Store content to file."""
        raise NotImplementedError

    def save(self) -> None:
        """Save underlying store to disk."""
        if not isinstance(self.storefile, str):
            msg = "Can save only to a file."
            raise TypeError(msg)
        self.save_atomic(self.storefile, self.save_content)

    def convertfile(
        self, storefile: IO[bytes], template_store: TranslationFormat | None
    ) -> TranslationStore:
        raise NotImplementedError

    @staticmethod
    def needs_target_sync(template_store: TranslationFormat | None) -> bool:  # noqa: ARG004
        return False

    def load(
        self,
        storefile: str | IO[bytes],
        template_store: TranslationFormat | None,
    ) -> TranslationStore:
        # Did we get file or filename?
        if not hasattr(storefile, "read"):
            with open(storefile, "rb") as handle:
                store: TranslationStore = self.convertfile(handle, template_store)
        else:
            store = self.convertfile(cast("IO[bytes]", storefile), template_store)
        # Adjust store to have translations
        if self.needs_target_sync(template_store):
            for unit in store.units:
                if unit.isheader():
                    continue
                # HTML does this properly on loading, others need it
                unit.target = unit.source
                unit.rich_target = unit.rich_source
        return store

    @classmethod
    def create_new_file(
        cls,
        filename: str,
        language: str,  # noqa: ARG003
        base: str,
        callback: Callable | None = None,  # noqa: ARG003
        file_format_params: FileFormatParams | None = None,  # noqa: ARG003
    ) -> None:
        """Handle creation of new translation file."""
        if not base:
            msg = "Not supported"
            raise ValueError(msg)
        # Copy file
        shutil.copy(base, filename)

    @classmethod
    def is_valid_base_for_new(
        cls,
        base: str,
        monolingual: bool,  # noqa: ARG003
        errors: list[Exception] | None = None,
        fast: bool = False,
        file_format_params: FileFormatParams | None = None,  # noqa: ARG003
    ) -> bool:
        """Check whether base is valid."""
        if not base:
            return False
        try:
            if not fast:
                cls(base, None)
        except Exception as exception:
            if errors is not None:
                errors.append(exception)
            report_error("File-parsing error")
            return False
        return True

    def add_unit(self, unit: TranslationUnit) -> None:
        self.store.addunit(unit.unit)

    @classmethod
    def get_class(cls) -> None:
        return None

    def create_unit(
        self,
        key: str,
        source: str | list[str],
        target: str | list[str] | None = None,
    ) -> NoReturn:
        msg = "Not supported"
        raise ValueError(msg)

    def cleanup_unused(self) -> list[str]:
        """
        Bring target in sync with the source.

        This is done automatically on save as it reshapes translations
        based on the template.
        """
        self.save()
        return []

    def convert_to_po(
        self,
        parser: TranslationStore,
        template_store: TranslationFormat | None,
        use_location: bool = True,
        duplicate_style: str = "msgctxt",
        source_attribute: str = "source",
    ) -> pofile:
        store = pofile()
        get_text = attrgetter(source_attribute)
        # Prepare index of existing translations
        unitindex: dict[str, list[Unit]] = defaultdict(list)
        for existing_unit in self.existing_units:
            for source in existing_unit.get_source_plurals():
                unitindex[source].append(existing_unit)

        # Convert store
        if template_store:
            parser.makeindex()
            for unit in template_store.content_units:
                thepo = store.addsourceunit(unit.source)
                ttkit_unit = cast("TranslateToolkitUnit", unit.unit)
                locations = ttkit_unit.getlocations()
                thepo.addlocations(locations)
                thepo.addnote(ttkit_unit.getnotes(), "developer")
                if self.is_template:
                    thepo.target = unit.source
                elif use_location and not unitindex:
                    # Try to import initial translation from the file
                    for location in locations:
                        try:
                            translation = parser.locationindex[location]
                            thepo.target = get_text(translation)
                            break
                        except KeyError:
                            continue
        else:
            for htmlunit in parser.units:
                # Source file
                thepo = store.addsourceunit(get_text(htmlunit))
                thepo.target = get_text(htmlunit)
                thepo.addlocations(htmlunit.getlocations())
                thepo.addnote(htmlunit.getnotes(), "developer")

        # Handle duplicate strings (use context to differentiate them)
        store.removeduplicates(duplicate_style)

        # Merge existing translations
        if unitindex and not self.is_template:
            for unit in store.units:
                possible_translations = unitindex[unit.source]
                # Single match
                if len(possible_translations) == 1:
                    unit.target = possible_translations[0].target
                    continue
                # None match
                if not possible_translations:
                    continue
                # Multiple matches
                for translation in possible_translations:
                    if translation.context == unit.getcontext():
                        unit.target = translation.target
                        break

        return store


class HTMLFormat(ConvertFormat):
    # Translators: File format name
    name = gettext_lazy("HTML file")
    autoload = ("*.htm", "*.html")
    format_id = "html"
    check_flags = ("safe-html", "strict-same")

    def convertfile(
        self, storefile: IO[bytes], template_store: TranslationFormat | None
    ) -> TranslationStore:
        # Fake input file with a blank filename
        htmlparser = htmlfile(inputfile=NamedBytesIO("", storefile.read()))
        duplicate_style = "msgctxt"
        if self.file_format_params.get("merge_duplicates"):
            duplicate_style = "merge"

        return self.convert_to_po(
            htmlparser, template_store, duplicate_style=duplicate_style
        )

    def save_content(self, handle: IO[bytes]) -> None:
        """Store content to file."""
        converter = po2html()
        if self.template_store is None:
            msg = "Template store is required."
            raise TypeError(msg)
        templatename = self.template_store.storefile
        if hasattr(templatename, "name"):
            templatename = templatename.name
        with open(templatename, "rb") as templatefile:
            outputstring = converter.mergestore(
                self.store, templatefile, includefuzzy=True
            )
        handle.write(outputstring.encode("utf-8"))

    @staticmethod
    def mimetype() -> str:
        """Return most common mime type for format."""
        return "text/html"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "html"


class MarkdownFormat(ConvertFormat):
    # Translators: File format name
    name = gettext_lazy("Markdown file")
    autoload = ("*.md", "*.markdown")
    format_id = "markdown"
    check_flags = ("safe-html", "strict-same", "md-text")

    def convertfile(
        self, storefile: IO[bytes], template_store: TranslationFormat | None
    ) -> TranslationStore:
        # Lazy import as mistletoe is expensive
        from translate.storage.markdown import MarkdownFile

        # Hold Markdown lock because this is not thread-safe, see
        # https://github.com/miyuchina/mistletoe/issues/210
        with MARKDOWN_LOCK:
            # Fake input file with a blank filename
            mdparser = MarkdownFile(inputfile=NamedBytesIO("", storefile.read()))

        duplicate_style = "msgctxt"
        if self.file_format_params.get("merge_duplicates"):
            duplicate_style = "merge"

        return self.convert_to_po(
            mdparser,
            template_store,
            use_location=False,
            duplicate_style=duplicate_style,
        )

    def save_content(self, handle: IO[bytes]) -> None:
        """Store content to file."""
        # Lazy import as mistletoe is expensive
        from translate.convert.po2md import MarkdownTranslator

        # Hold Markdown lock because this is not thread-safe, see
        # https://github.com/miyuchina/mistletoe/issues/210
        with MARKDOWN_LOCK:
            converter = MarkdownTranslator(
                inputstore=self.store,
                includefuzzy=True,
                outputthreshold=None,
                maxlength=80,
            )
            if self.template_store is None:
                msg = "Template store is required."
                raise TypeError(msg)
            templatename = self.template_store.storefile
            if hasattr(templatename, "name"):
                templatename = templatename.name
            with open(templatename, "rb") as templatefile:
                converter.translate(templatefile, handle)

    @staticmethod
    def mimetype() -> str:
        """Return most common mime type for format."""
        return "text/markdown"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "md"


class OpenDocumentFormat(ConvertFormat):
    # Translators: File format name
    name = gettext_lazy("OpenDocument file")
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

    def convertfile(
        self, storefile: IO[bytes], template_store: TranslationFormat | None
    ) -> TranslationStore:
        store: Xliff1File = Xliff1File()
        store.setfilename(store.getfilenode("NoName"), "odf")
        contents = open_odf(storefile)
        for data in contents.values():
            parse_state = ParseState(no_translate_content_elements, inline_elements)
            build_store(BytesIO(data), store, parse_state)
        return store

    def save_content(self, handle: IO[bytes]) -> None:
        """Store content to file."""
        if self.template_store is None:
            msg = "Template store is required."
            raise TypeError(msg)
        templatename = self.template_store.storefile
        if hasattr(templatename, "name"):
            templatename = templatename.name
        # This is workaround for weird fuzzy handling in translate-toolkit
        for unit in self.all_units:
            if any(state == "translated" for state in unit.get_xliff_states()):  # type: ignore[attr-defined]
                unit.set_state(STATE_APPROVED)

        with open(templatename, "rb") as templatefile:
            dom_trees = translate_odf(templatefile, self.store)
            write_odf(templatefile, handle, dom_trees)

    @staticmethod
    def mimetype() -> str:
        """Return most common mime type for format."""
        return "application/vnd.oasis.opendocument.text"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "odt"

    @staticmethod
    def needs_target_sync(template_store: TranslationFormat | None) -> bool:  # noqa: ARG004
        return True


class IDMLFormat(ConvertFormat):
    # Translators: File format name
    name = gettext_lazy("IDML file")
    autoload = ("*.idml", "*.idms")
    format_id = "idml"
    check_flags = ("strict-same",)

    def convertfile(
        self, storefile: IO[bytes], template_store: TranslationFormat | None
    ) -> TranslationStore:
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

    def save_content(self, handle: IO[bytes]) -> None:
        """Store content to file."""
        if self.template_store is None:
            msg = "Template store is required."
            raise TypeError(msg)
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
    def mimetype() -> str:
        """Return most common mime type for format."""
        return "application/octet-stream"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "idml"

    @staticmethod
    def needs_target_sync(template_store: TranslationFormat | None) -> bool:  # noqa: ARG004
        return True


class WindowsRCFormat(ConvertFormat):
    # Translators: File format name
    name = gettext_lazy("RC file")
    format_id = "rc"
    autoload = ("*.rc",)
    language_format = "bcp"

    @staticmethod
    def needs_target_sync(template_store: TranslationFormat | None) -> bool:
        return template_store is None

    @staticmethod
    def mimetype() -> str:
        """Return most common media type for format."""
        return "text/plain"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "rc"

    def convertfile(
        self, storefile: IO[bytes], template_store: TranslationFormat | None
    ) -> TranslationStore:
        input_store = rcfile()
        input_store.parse(storefile.read())
        converter = rc2po()
        if template_store:
            store = converter.merge_store(
                template_store.store.rcfile,  # type: ignore[union-attr]
                input_store,
            )
        else:
            store = converter.convert_store(input_store)
        store.rcfile = input_store
        return store

    def save_content(self, handle: IO[bytes]) -> None:
        """Store content to file."""
        # Fallback language
        lang = "LANG_ENGLISH"
        sublang = "SUBLANG_DEFAULT"

        # Keep existing language tags
        storage = self.store.rcfile  # type: ignore[attr-defined]
        if storage.lang:
            lang = storage.lang
            if storage.sublang:
                sublang = storage.sublang
        if self.template_store is None:
            msg = "Template store is required."
            raise TypeError(msg)
        templatename = self.template_store.storefile
        if hasattr(templatename, "name"):
            templatename = templatename.name
        encoding = "utf-8"
        with open(templatename, "rb") as templatefile:
            bom = templatefile.read(2)
            if bom == codecs.BOM_UTF16_LE or b"\000" in bom:
                encoding = "utf-16-le"
            templatefile.seek(0)
            converter = rerc(
                templatefile,
                lang=lang,
                sublang=sublang,
                charset=encoding,
            )
            outputrclines = converter.convertstore(self.store, includefuzzy=True)
            try:
                handle.write(outputrclines.encode(encoding))
            except UnicodeEncodeError:
                handle.write(codecs.BOM_UTF16_LE)
                handle.write(outputrclines.encode("utf-16-le"))


class PlainTextFormat(ConvertFormat):
    # Translators: File format name
    name = gettext_lazy("Plain text file")
    format_id = "txt"
    autoload = ("*.txt",)
    flavour = "plain"

    @staticmethod
    def mimetype() -> str:
        """Return most common media type for format."""
        return "text/plain"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "txt"

    def convertfile(
        self, storefile: IO[bytes], template_store: TranslationFormat | None
    ) -> TranslationStore:
        input_store = TxtFile(encoding="utf-8", flavour=self.flavour)
        input_store.parse(storefile.readlines())
        input_store.filename = os.path.basename(storefile.name)
        duplicate_style = "msgctxt"
        if self.file_format_params.get("merge_duplicates"):
            duplicate_style = "merge"

        return self.convert_to_po(
            input_store, template_store, duplicate_style=duplicate_style
        )

    def save_content(self, handle: IO[bytes]) -> None:
        """Store content to file."""
        if self.template_store is None:
            msg = "Template store is required."
            raise TypeError(msg)
        templatename = self.template_store.storefile
        if hasattr(templatename, "name"):
            templatename = templatename.name
        with open(cast("str", templatename), "rb") as templatefile:
            converter = po2txt(
                input_file=self.store,
                output_file=None,
                template_file=templatefile,
                flavour=self.flavour,
            )
            outputstring = converter.merge_stores()
        handle.write(outputstring.encode("utf-8"))


class DokuWikiFormat(PlainTextFormat):
    # Translators: File format name
    name = gettext_lazy("DokuWiki text file")
    format_id = "dokuwiki"
    autoload = ("*.dw",)
    flavour = "dokuwiki"


class MediaWikiFormat(PlainTextFormat):
    # Translators: File format name
    name = gettext_lazy("MediaWiki text file")
    format_id = "mediawiki"
    autoload = ("*.mw",)
    flavour = "mediawiki"


class AsciiDocFormat(ConvertFormat):
    # Translators: File format name
    name = gettext_lazy("AsciiDoc file")
    autoload = ("*.ad", "*.adoc", "*.asciidoc")
    format_id = "asciidoc"
    check_flags = ("safe-html", "strict-same")

    def convertfile(
        self, storefile: IO[bytes], template_store: TranslationFormat | None
    ) -> TranslationStore:
        # Fake input file with a blank filename
        adocparser = AsciiDocFile(inputfile=NamedBytesIO("", storefile.read()))

        duplicate_style = "msgctxt"
        if self.file_format_params.get("merge_duplicates"):
            duplicate_style = "merge"

        return self.convert_to_po(
            adocparser,
            template_store,
            use_location=False,
            duplicate_style=duplicate_style,
        )

    def save_content(self, handle: IO[bytes]) -> None:
        """Store content to file."""
        converter = AsciiDocTranslator(
            inputstore=self.store, includefuzzy=True, outputthreshold=None
        )
        if self.template_store is None:
            msg = "Template store is required."
            raise TypeError(msg)
        templatename = self.template_store.storefile
        if hasattr(templatename, "name"):
            templatename = templatename.name
        with open(templatename, "rb") as templatefile:
            converter.translate(templatefile, handle)

    @staticmethod
    def mimetype() -> str:
        """Return most common mime type for format."""
        return "text/x-asciidoc"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "adoc"


class WXLFormat(ConvertFormat):
    # Translators: File format name
    name = gettext_lazy("WixLocalization file")
    format_id = "wxl"
    autoload: tuple[str, ...] = ("*.wxl",)
    language_format: str = "bcp_long_lower"

    def convertfile(
        self, storefile: IO[bytes], template_store: TranslationFormat | None
    ) -> TranslationStore:
        # Fake input file with a blank filename
        wxlparser = WxlFile(inputfile=NamedBytesIO("", storefile.read()))

        return self.convert_to_po(
            wxlparser,
            template_store,
            source_attribute="target",
        )

    def save_content(self, handle: IO[bytes]) -> None:
        """Store content to file."""
        if self.template_store is None:
            msg = "Template store is required."
            raise TypeError(msg)
        templatename = self.template_store.storefile
        if hasattr(templatename, "name"):
            templatename = templatename.name
        with open(cast("str", templatename), "rb") as templatefile:
            wxlparser = WxlFile(inputfile=templatefile)

        wxlparser.makeindex()

        for unit in self.store.units:
            if unit.isheader() or not unit.istranslated():
                continue
            key = unit.getlocations()[0]
            if not key or key not in wxlparser.locationindex:
                continue

            wxlparser.locationindex[key].target = unit.target

        wxlparser.serialize(handle)

    @staticmethod
    def mimetype() -> str:
        """Return most common mime type for format."""
        return "application/xml"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "wxl"
