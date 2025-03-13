# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © WofWca <wofwca@protonmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Translate Toolkit based file-format wrappers."""

from __future__ import annotations

import importlib
import inspect
import os
import re
import subprocess
from typing import TYPE_CHECKING, Any, BinaryIO

from django.core.exceptions import ValidationError
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy
from lxml import etree
from lxml.etree import XMLSyntaxError
from pyparsing import ParseException
from translate.misc import quote
from translate.misc.multistring import multistring
from translate.misc.xml_helpers import setXMLspace
from translate.storage.base import TranslationStore
from translate.storage.base import TranslationUnit as TranslateToolkitUnit
from translate.storage.csvl10n import csv, csvunit
from translate.storage.jsonl10n import BaseJsonUnit, JsonFile
from translate.storage.lisa import LISAfile
from translate.storage.po import pofile, pounit
from translate.storage.poxliff import PoXliffFile
from translate.storage.resx import RESXFile
from translate.storage.tbx import tbxfile, tbxunit
from translate.storage.ts2 import tsfile, tsunit
from translate.storage.xliff import ID_SEPARATOR, xlifffile, xliffunit

import weblate.utils.version
from weblate.checks.flags import Flags
from weblate.formats.base import (
    BilingualUpdateMixin,
    MissingTemplateError,
    TranslationFormat,
    TranslationUnit,
    UpdateError,
)
from weblate.lang.data import FORMULA_WITH_ZERO, ZERO_PLURAL_TYPES
from weblate.lang.models import Plural
from weblate.trans.util import (
    get_clean_env,
    get_string,
    rich_to_xliff_string,
    xliff_string_to_rich,
)
from weblate.utils.errors import report_error
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_READONLY,
    STATE_TRANSLATED,
)

if TYPE_CHECKING:
    from collections.abc import Callable

LOCATIONS_RE = re.compile(r"^([+-]|.*, [+-]|.*:[+-])")
PO_DOCSTRING_LOCATION = re.compile(r":docstring of [a-zA-Z0-9._]+:[0-9]+")
SUPPORTS_FUZZY = (pounit, tsunit, csvunit)
XLIFF_FUZZY_STATES = {"new", "needs-translation", "needs-adaptation", "needs-l10n"}


class TTKitUnit(TranslationUnit):
    template: TranslateToolkitUnit | None
    unit: TranslateToolkitUnit
    mainunit: TranslateToolkitUnit
    parent: TTKitFormat

    @cached_property
    def locations(self):
        """Return a comma-separated list of locations."""
        return ", ".join(self.mainunit.getlocations())

    @cached_property
    def source(self):
        """Return source string from a Translate Toolkit unit."""
        if self.template is not None:
            return get_string(self.template.target)
        return get_string(self.unit.source)

    @cached_property
    def target(self):
        """Return target string from a Translate Toolkit unit."""
        if self.unit is None:
            if self.parent.is_template and self.template is not None:
                return get_string(self.template.target)
            return ""
        return get_string(self.unit.target)

    @cached_property
    def context(self):
        """
        Return context of message.

        In some cases we have to use ID here to make all the back-ends consistent.
        """
        return self.mainunit.getcontext()

    @cached_property
    def notes(self):
        """Return notes or notes from units."""
        comment = ""

        if self.unit is not None:
            comment = self.unit.getnotes()

        if self.template is not None:
            # Avoid duplication in case template has same notes
            template_comment = self.template.getnotes()
            if template_comment != comment:
                comment = f"{template_comment}\n{comment}"

        return comment

    def is_translated(self):
        """Check whether unit is translated."""
        if self.unit is None:
            return False
        return self.unit.istranslated()

    def is_fuzzy(self, fallback=False):
        """Check whether unit needs editing."""
        if self.unit is None:
            return fallback
        # Most of the formats do not support this, but they
        # happily return False
        if isinstance(self.unit, SUPPORTS_FUZZY):
            return self.has_translation() and self.unit.isfuzzy()
        return fallback

    def has_content(self) -> bool:
        """Check whether unit has content."""
        return (
            not self.mainunit.isheader()
            and not self.mainunit.isblank()
            and not self.mainunit.isobsolete()
        )

    def is_readonly(self) -> bool:
        return not self.mainunit.istranslatable()

    def set_target(self, target: str | list[str]) -> None:
        """Set translation unit target."""
        self._invalidate_target()
        if isinstance(target, list):
            target = multistring(target)
        self.unit.target = target

    def set_state(self, state) -> None:
        """Set fuzzy /approved flag on translated unit."""
        if "flags" in self.__dict__:
            del self.__dict__["flags"]
        self.unit.markfuzzy(state == STATE_FUZZY)
        if hasattr(self.unit, "markapproved"):
            self.unit.markapproved(state == STATE_APPROVED)

    @cached_property
    def flags(self):
        """
        Return flags from unit.

        We currently extract maxwidth attribute.
        """
        flags = Flags()
        if hasattr(self.unit, "xmlelement"):
            flags.merge(self.unit.xmlelement)
        if self.template is not None and hasattr(self.template, "xmlelement"):
            flags.merge(self.template.xmlelement)
        return flags.format()

    def clone_template(self) -> None:
        super().clone_template()

        # do not copy notes from the template (#11133)
        self.unit.removenotes()

    def untranslate(self, language) -> None:
        target: str | list[str]
        target = [""] * language.plural.number if self.mainunit.hasplural() else ""
        self.set_target(target)
        self.set_state(STATE_EMPTY)


class KeyValueUnit(TTKitUnit):
    @cached_property
    def source(self):
        """Return source string from a Translate Toolkit unit."""
        if self.template is not None:
            return get_string(self.template.source)
        if self.unit is None:
            raise MissingTemplateError
        return get_string(self.unit.name)

    @cached_property
    def target(self):
        """Return target string from a Translate Toolkit unit."""
        if self.unit is None:
            return ""
        return get_string(self.unit.source)

    @cached_property
    def context(self):
        """
        Return context of message.

        In some cases we have to use ID here to make all the back-ends consistent.
        """
        context = super().context
        if not context:
            return self.mainunit.getid()
        return context

    def is_translated(self):
        """Check whether unit is translated."""
        if self.unit is None:
            return False
        # The hasattr check here is needed for merged storages
        # where template is different kind than translations
        if hasattr(self.unit, "value"):
            return not self.unit.isfuzzy() and self.unit.value
        return self.unit.istranslated()

    def set_target(self, target: str | list[str]) -> None:
        """Set translation unit target."""
        super().set_target(target)
        # Propagate to value so that searializing of empty values works correctly
        if not target:
            self.unit.value = self.unit.target


class TTKitFormat(TranslationFormat):
    unit_class = TTKitUnit
    loader = ("", "")
    set_context_bilingual = True
    # Use settarget/setsource to set language as well
    use_settarget = False
    force_encoding: str | None = None
    plural_preference: tuple[int, ...] | None = (
        Plural.SOURCE_CLDR,
        Plural.SOURCE_DEFAULT,
    )
    units: list[TranslateToolkitUnit]
    store: TranslationStore

    @staticmethod
    def serialize(store):
        """Serialize given Translate Toolkit store."""
        return bytes(store)

    def fixup(self, store) -> None:
        """Perform optional fixups on store."""
        if self.force_encoding is not None:
            store.encoding = self.force_encoding
        # This gets already native language code, so no conversion is needed
        if self.language_code is not None:
            store.settargetlanguage(self.language_code)
        if self.source_language is not None:
            store.setsourcelanguage(self.source_language)

    def load(
        self, storefile: str | BinaryIO, template_store: TranslationFormat | None
    ) -> TranslationStore:
        """Load file using defined loader."""
        if isinstance(storefile, TranslationStore):
            # Used by XLSX writer
            return storefile

        return self.parse_store(storefile)

    @classmethod
    def get_class(cls) -> TranslationStore:
        """Return class for handling this module."""
        # Direct class
        if inspect.isclass(cls.loader):
            return cls.loader
        # Tuple style loader, import from translate toolkit
        module_name, class_name = cls.loader
        if "." not in module_name:
            module_name = f"translate.storage.{module_name}"
        module = importlib.import_module(module_name)

        # Get the class
        return getattr(module, class_name)

    @staticmethod
    def get_class_kwargs():
        return {}

    def get_store_instance(self, **kwargs):
        kwargs.update(self.get_class_kwargs())
        store = self.get_class()(**kwargs)

        # Apply possible fixups
        self.fixup(store)

        return store

    def parse_store(self, storefile):
        """Parse the store."""
        store = self.get_store_instance()

        # Read the content
        if isinstance(storefile, str):
            with open(storefile, "rb") as handle:
                content = handle.read()
        else:
            content = storefile.read()

        # Parse the content
        store.parse(content)

        return store

    def add_unit(self, unit: TranslationUnit) -> None:
        """Add new unit to underlying store."""
        if isinstance(self.store, LISAfile):
            # LISA based stores need to know this
            self.store.addunit(unit.unit, new=True)
        else:
            self.store.addunit(unit.unit)

    def save_content(self, handle) -> None:
        """Store content to file."""
        self.store.serialize(handle)

    def save(self) -> None:
        """Save underlying store to disk."""
        self.save_atomic(self.storefile, self.save_content)

    @classmethod
    def mimetype(cls):
        """Return most common media type for format."""
        return cls.get_class().Mimetypes[0]

    @classmethod
    def extension(cls):
        """Return most common file extension for format."""
        return cls.get_class().Extensions[0]

    def is_valid(self) -> bool:
        """
        Check whether store seems to be valid.

        In some cases Translate Toolkit happily "parses" the file, even though it really
        did not do so (e.g. gettext parser on a random textfile).
        """
        if not super().is_valid():
            return False
        return self.store is not None

    def construct_unit(self, source: str):
        if self.use_settarget and self.source_language:
            # Setting source on LISAunit will make it use default language
            unit = self.store.UnitClass(None)
            unit.setsource(source, self.source_language)
        elif hasattr(self.store, "wrapper"):
            # gettext PO
            unit = self.store.UnitClass(source, wrapper=self.store.wrapper)
        else:
            unit = self.store.UnitClass(source)
        # Needed by some formats (Android) to set target
        unit._store = self.store  # noqa: SLF001
        return unit

    def create_unit_key(
        self, key: str, source: str | list[str] | multistring
    ) -> str | multistring:
        return key

    def create_unit(
        self,
        key: str,
        source: str | list[str],
        target: str | list[str] | None = None,
    ):
        # Make sure target is a string
        if target is None:
            target = ""
        # Process source
        if isinstance(source, list):
            context = source[0]
            # Single string passed plain or multistring
            source = context if len(source) == 1 else multistring(source)
        else:
            # This is string
            context = source

        # Process target
        if isinstance(target, list):
            target = target[0] if len(target) == 1 else multistring(target)

        # Build the unit
        unit = self.construct_unit(context)

        # Monolingual translation
        if self.is_template or self.template_store:
            unit.setid(key)
            if isinstance(unit, csvunit):
                unit.setcontext(key)
            target = source
            source = self.create_unit_key(key, source)
        # Bilingual translation
        elif isinstance(unit, tbxunit | xliffunit) and key:
            unit.setid(key)
        elif self.set_context_bilingual and key:
            unit.setcontext(key)
        elif isinstance(unit, BaseJsonUnit):
            unit.setid(context)

        if self.use_settarget and self.source_language:
            unit.setsource(source, self.source_language)
        else:
            unit.source = source

        if self.use_settarget and self.language_code:
            unit.settarget(target, self.language_code)
        else:
            unit.target = target

        return unit

    def untranslate_store(self, language) -> None:
        """Remove translations from Translate Toolkit store."""
        self.store.settargetlanguage(self.get_language_code(language.code))

        for unit in self.content_units:
            if unit.is_translated():
                unit.untranslate(language)

    @classmethod
    def get_new_file_content(cls):
        result = cls.new_translation
        if isinstance(result, str):
            result = result.encode()
        return result

    @classmethod
    def create_new_file(
        cls,
        filename: str,
        language: str,
        base: str,
        callback: Callable | None = None,
    ) -> None:
        """Handle creation of new translation file."""
        if base:
            # Parse file
            store = cls(base)
            if callback:
                callback(store)
            store.untranslate_store(language)
            store.store.savefile(filename)
        elif cls.new_translation is not None:
            with open(filename, "wb") as output:
                output.write(cls.get_new_file_content())
        else:
            msg = "Not supported"
            raise ValueError(msg)

    @classmethod
    def is_valid_base_for_new(
        cls,
        base: str,
        monolingual: bool,
        errors: list | None = None,
        fast: bool = False,
    ) -> bool:
        """Check whether base is valid."""
        if not base:
            if cls.create_empty_bilingual:
                return True
            return monolingual and cls.new_translation is not None
        try:
            if not fast:
                cls(base)
        except Exception as exception:
            if errors is not None:
                errors.append(exception)
            report_error("File-parsing error")
            return False
        return os.path.exists(base)

    @property
    def all_store_units(self):
        """Wrapper for all store unit filtering out obsolete."""
        return (
            unit
            for unit in self.store.units
            if not unit.isobsolete() and not unit.isheader()
        )

    def delete_unit(self, ttkit_unit) -> str | None:
        self.store.removeunit(ttkit_unit)
        return None


class PropertiesUnit(KeyValueUnit):
    """Wrapper for properties-based units."""

    @cached_property
    def locations(self) -> str:
        """Return a comma-separated list of locations."""
        return ""

    @cached_property
    def source(self):
        """Return source string from a Translate Toolkit unit."""
        if self.template is not None:
            return get_string(self.template.source)
        # Need to decode property encoded string
        return get_string(quote.propertiesdecode(self.unit.name))

    @cached_property
    def target(self):
        """Return target string from a Translate Toolkit unit."""
        if self.unit is None:
            return ""
        return get_string(self.unit.target or self.unit.source)


class PoUnit(TTKitUnit):
    """Wrapper for gettext PO unit."""

    def set_state(self, state) -> None:
        """Set fuzzy /approved flag on translated unit."""
        super().set_state(state)
        if state != STATE_FUZZY:
            self.unit.prev_msgid = []
            self.unit.prev_msgid_plural = []
            self.unit.prev_msgctxt = []

    @cached_property
    def flags(self):
        """Return flags or typecomments from units."""
        try:
            flags = Flags(*self.mainunit.typecomments)
        except ParseException as error:
            msg = f"Could not parse flags: {self.mainunit.typecomments!r}: {error}"
            raise ValueError(msg) from error
        flags.remove({"fuzzy"})
        return flags.format()

    @cached_property
    def previous_source(self):
        """Return previous message source if there was any."""
        if not self.is_fuzzy():
            return ""
        return get_string(self.unit.prev_source)

    @cached_property
    def locations(self):
        """
        Return comma separated list of locations.

        Here we clean up Sphinx-generated "docstring of ..." part.
        """
        locations = " ".join(self.mainunit.getlocations())
        locations = PO_DOCSTRING_LOCATION.sub("", locations)
        return ", ".join(locations.split())


class PoMonoUnit(PoUnit):
    @cached_property
    def context(self):
        """
        Return context of message.

        In some cases we have to use ID here to make all the backends consistent.
        """
        # Monolingual PO files
        if self.template is not None:
            context = self.template.getcontext()
            source = self.template.source
            if source and context:
                return f"{context}.{source}"
            return source or context
        return super().context

    @cached_property
    def notes(self):
        result = []
        notes = super().notes
        if notes:
            result.append(notes)
        # Use unit context as note only in case source is present, otherwise
        # it is used as a context (see above)
        if self.template is not None and self.template.source:
            context = self.template.getcontext()
            if context:
                result.append(context)
        return "\n".join(result)

    def set_target(self, target: str | list[str]) -> None:
        """Set translation unit target."""
        # Add blank msgid_plural to store plural
        if isinstance(target, list | multistring) and not self.unit.hasplural():
            self.unit.msgid_plural = ['""']

        super().set_target(target)


class XliffUnit(TTKitUnit):
    """
    Wrapper unit for XLIFF.

    XLIFF is special in Translate Toolkit — it uses locations for what
    is context in other formats.
    """

    @staticmethod
    def get_unit_node(unit, element: str = "target"):
        if unit is not None:
            return unit.xmlelement.find(unit.namespaced(element))
        return None

    def get_xliff_units(self):
        # Iterate over poxliff sub-units, or main unit
        return getattr(self.unit, "units", [self.unit])

    def get_xliff_nodes(self):
        return (self.get_unit_node(unit) for unit in self.get_xliff_units())

    def get_xliff_states(self) -> set[str]:
        result = set()
        for node in self.get_xliff_nodes():
            if node is None:
                continue
            state = node.get("state", None)
            if state is not None:
                result.add(state)
        return result

    @cached_property
    def context(self):
        """
        Return context of message.

        Use resname if available as it usually is more interesting for the translator
        than ID.
        """
        resname = self.mainunit.xmlelement.get("resname")
        if resname:
            return resname
        return self.mainunit.getid().replace(ID_SEPARATOR, "///")

    def is_translated(self):
        """
        Check whether unit is translated.

        We replace Translate Toolkit logic here as the isfuzzy is pretty much wrong
        there, see is_fuzzy docs.
        """
        return self.has_translation()

    def is_fuzzy(self, fallback: bool = False) -> bool:
        """
        Check whether unit needs edit.

        The isfuzzy on XLIFF is really messing up the "approved" flag with "fuzzy"
        flag, leading to various problems.

        That's why we handle it on our own.
        """
        return self.has_translation() and bool(
            XLIFF_FUZZY_STATES.intersection(self.get_xliff_states())
        )

    def set_state(self, state) -> None:
        """Set fuzzy /approved flag on translated unit."""
        self.unit.markapproved(state == STATE_APPROVED)
        target_state = None
        if state == STATE_FUZZY:
            # Always set state for fuzzy
            target_state = "needs-translation"
        elif state == STATE_TRANSLATED:
            # Always set state for translated
            target_state = "translated"
        elif state == STATE_APPROVED:
            target_state = "final"
        elif self.get_xliff_states():
            # Only update state if it exists
            target_state = "new"

        if target_state:
            for xliff_node in self.get_xliff_nodes():
                xliff_node.set("state", target_state)

    def is_approved(self, fallback=False):
        """Check whether unit is approved."""
        if self.unit is None:
            return fallback
        if hasattr(self.unit, "isapproved"):
            return self.unit.isapproved()
        return fallback

    def has_content(self):
        """
        Check whether unit has content.

        For some reason, blank string does not mean non-translatable unit in XLIFF, so
        lets skip those as well.
        """
        return (
            not self.mainunit.isheader()
            and bool(self.source)
            and not self.mainunit.isobsolete()
        )

    def untranslate(self, language) -> None:
        super().untranslate(language)
        # Delete empty <target/> tag
        for xmlnode in self.get_xliff_nodes():
            if xmlnode is not None:
                xmlnode.getparent().remove(xmlnode)

    def set_target(self, target: str | list[str]) -> None:
        """Set translation unit target."""
        if self.get_unit_node(self.unit, "source") is None:
            # Make sure source element is present, otherwise it breaks
            # translate-toolkit expectations.
            self.unit.set_source_dom(
                self.unit.createlanguageNode(self.parent.source_language, "", "source")
            )

        self._invalidate_target()
        if isinstance(target, list):
            target = multistring(target)
        if self.template is not None:
            if self.parent.is_template:
                # Use source for monolingual files if editing template
                self.unit.source = target
            elif self.unit.source:
                # Update source to match current source
                self.unit.source = self.template.source
        # Always set target, even in monolingual template
        self.unit.target = target

    @cached_property
    def source(self):
        """Return source string from a Translate Toolkit unit."""
        if self.template is not None:
            # Use target if set, otherwise fall back to source
            if self.template.target:
                return get_string(self.template.target)
            return get_string(self.template.source)
        return get_string(self.unit.source)

    @cached_property
    def target(self):
        """Return target string from a Translate Toolkit unit."""
        if self.unit is None:
            return ""

        # Use source for monolingual base if target is not set
        if self.unit.target is None:
            if self.parent.is_template or isinstance(self.unit, csvunit):
                return get_string(self.unit.source)
            return ""

        return get_string(self.unit.target)


class RichXliffUnit(XliffUnit):
    """Wrapper unit for XLIFF with XML elements."""

    @cached_property
    def source(self):
        """Return source string from a Translate Toolkit unit."""
        if self.template is not None:
            # Use target if set, otherwise fall back to source
            if self.template.target:
                return rich_to_xliff_string(self.template.rich_target)
            return rich_to_xliff_string(self.template.rich_source)
        return rich_to_xliff_string(self.unit.rich_source)

    @cached_property
    def target(self):
        """Return target string from a Translate Toolkit unit."""
        if self.unit is None:
            return ""

        # Use source for monolingual base if target is not set
        if self.unit.target is None:
            if self.parent.is_template:
                return rich_to_xliff_string(self.unit.rich_source)
            return ""

        return rich_to_xliff_string(self.unit.rich_target)

    @cached_property
    def flags(self):
        flags = Flags(super().flags)
        flags.merge("xml-text")
        return flags.format()

    def set_target(self, target: str | list[str]) -> None:
        """Set translation unit target."""
        self._invalidate_target()
        # Delete the empty target element
        if not target:
            for xmlnode in self.get_xliff_nodes():
                if xmlnode is not None:
                    xmlnode.getparent().remove(xmlnode)
            return
        try:
            converted = xliff_string_to_rich(target)
        except (XMLSyntaxError, TypeError, KeyError):
            # KeyError happens on missing attribute
            converted = [target]
        if self.template is not None:
            if self.parent.is_template:
                # Use source for monolingual files if editing template
                self.unit.rich_source = converted
            elif self.unit.source:
                # Update source to match current source
                self.unit.rich_source = self.template.rich_source
        # Always set target, even in monolingual template
        self.unit.rich_target = converted


class FlatXMLUnit(TTKitUnit):
    @cached_property
    def context(self):
        if self.template is not None:
            return self.template.source
        return self.mainunit.source

    @cached_property
    def source(self):
        return get_string(self.mainunit.target)

    def has_content(self):
        """
        Check whether unit has content.

        The attribute-less units will have context None.
        """
        if self.context is None:
            return False
        return super().has_content()


class MonolingualIDUnit(TTKitUnit):
    @cached_property
    def context(self):
        if self.template is not None:
            return self.template.getid()
        return self.mainunit.getcontext()


class TSUnit(MonolingualIDUnit):
    @cached_property
    def source(self):
        if self.template is None and self.mainunit.hasplural():
            # Need to apply special magic for plurals here
            # as there is no singular/plural in the source string
            source = self.unit.source
            return get_string([source.replace("(s)", ""), source.replace("(s)", "s")])
        return super().source

    @cached_property
    def locations(self):
        """Return a comma-separated list of locations."""
        result = super().locations
        # Do not try to handle relative locations in Qt TS, see
        # http://doc.qt.io/qt-5/linguist-ts-file-format.html
        if LOCATIONS_RE.match(result):
            return ""
        return result

    @cached_property
    def target(self):
        """Return target string from a Translate Toolkit unit."""
        if self.unit is None:
            return ""
        if not self.unit.isreview() and not self.unit.istranslated():
            # For Qt ts, empty translated string means source should be used
            return self.source
        return super().target

    def is_translated(self):
        """Check whether unit is translated."""
        if self.unit is None:
            return False
        # For Qt ts, empty translated string means source should be used
        return not self.unit.isreview() or self.unit.istranslated()

    def set_state(self, state) -> None:
        """Set fuzzy /approved flag on translated unit."""
        super().set_state(state)
        if state == STATE_EMPTY:
            # We need to mark all units as fuzzy to get
            # type="unfinished" on empty strings, which are otherwise
            # treated as translated same as source
            self.unit.markfuzzy(True)


class MonolingualSimpleUnit(MonolingualIDUnit):
    @cached_property
    def locations(self) -> str:
        return ""

    @cached_property
    def source(self):
        if self.template is None:
            return self.mainunit.getid().lstrip(".")
        return get_string(self.template.target)

    def has_content(self) -> bool:
        return not self.mainunit.isheader()

    def is_readonly(self) -> bool:
        return False


class JSONUnit(MonolingualSimpleUnit):
    @cached_property
    def context(self):
        context = super().context
        if context.startswith("."):
            return context[1:]
        return context


class PlaceholdersJSONUnit(JSONUnit):
    @cached_property
    def flags(self):
        placeholders = self.mainunit.placeholders
        if not placeholders:
            return ""
        flags = ""
        if isinstance(placeholders, list):
            # golang placeholders
            placeholder_ids = [f"{{{p['id']}}}" for p in placeholders]
        else:
            # WebExtension placeholders
            placeholder_ids = [f"${key.upper()}$" for key in placeholders]
            flags = ",case-insensitive"
        return "placeholders:{}{}".format(
            ":".join(Flags.format_value(key) for key in placeholder_ids), flags
        )


class CSVUnit(MonolingualSimpleUnit):
    @staticmethod
    def unescape_csv(string):
        r"""
        Remove Excel-specific escaping from CSV.

        See weblate.formats.exporters.CSVExporter.string_filter

        Note: | is replaced by \ in the condition as it is escaped
        """
        if (
            len(string) > 2
            and string[0] == "'"
            and string[-1] == "'"
            and string[1] in {"=", "+", "-", "@", "\\", "%"}
        ):
            return get_string(string[1:-1].replace("\\|", "|"))
        return get_string(string)

    @cached_property
    def context(self):
        def get_context(unit):
            if unit.id:
                return unit.id
            if unit.context:
                return unit.context
            return unit.getid()

        # Needed to avoid Translate Toolkit construct ID
        # as context\04source
        if self.template is not None:
            return get_context(self.template)
        if self.parent.is_template:
            return get_context(self.unit)
        return self.unescape_csv(self.mainunit.getcontext())

    @cached_property
    def locations(self):
        return self.mainunit.location

    @cached_property
    def source(self):
        # Needed to avoid Translate Toolkit construct ID
        # as context\04source
        if self.template is None:
            return self.unescape_csv(get_string(self.mainunit.source))
        return self.unescape_csv(super().source)

    @cached_property
    def target(self):
        if (
            not self.parent.is_template
            and self.template is not None
            and self.unit is not None
            and "target" not in self.parent.store.fieldnames
        ):
            # Use source if target is not stored
            target = get_string(self.unit.source)
        else:
            target = super().target
        return self.unescape_csv(target)

    def set_target(self, target: str | list[str]) -> None:
        super().set_target(target)
        if (
            self.template is not None
            and not self.parent.is_template
            and "target" not in self.parent.store.fieldnames
        ):
            # Update source for bilingual as CSV fields can contain just source
            self.unit.source = self.unit.target

    def is_fuzzy(self, fallback=False):
        # Report fuzzy state only if present in the fields
        if "fuzzy" not in self.parent.store.fieldnames:
            return fallback
        return super().is_fuzzy()


class RESXUnit(TTKitUnit):
    @cached_property
    def locations(self) -> str:
        return ""

    @cached_property
    def context(self):
        if self.template is not None:
            return self.template.getid()
        return self.unit.getid()

    @cached_property
    def source(self):
        if self.template is None:
            return self.mainunit.getid()
        return get_string(self.template.target)


class PHPUnit(KeyValueUnit):
    @cached_property
    def locations(self) -> str:
        return ""

    @cached_property
    def source(self):
        if self.template is not None:
            return get_string(self.template.source)
        return get_string(self.unit.getid())

    @cached_property
    def target(self):
        if self.unit is None:
            return ""
        return get_string(self.unit.source)


class INIUnit(TTKitUnit):
    @cached_property
    def locations(self) -> str:
        return ""

    @cached_property
    def context(self):
        if self.template is not None:
            return self.template.location
        return self.unit.location

    def has_content(self) -> bool:
        return True

    def is_readonly(self) -> bool:
        return False


class AndroidUnit(MonolingualIDUnit):
    """Wrapper unit for Android Resource."""

    def set_state(self, state) -> None:
        """Tag unit as translatable/readonly aside from fuzzy and approved flags."""
        super().set_state(state)
        if state == STATE_READONLY:
            self.unit.marktranslatable(False)


class BasePoFormat(TTKitFormat):
    loader = pofile
    plural_preference = None
    supports_plural: bool = True
    store: pofile

    @classmethod
    def get_plural(cls, language, store=None):
        """Return matching plural object."""
        # Fallback will trigger KeyError later
        header = store.store.parseheader() if store else {}

        try:
            number, formula = Plural.parse_plural_forms(header["Plural-Forms"])
        except (ValueError, KeyError):
            return super().get_plural(language, store)

        # Find matching one
        for plural in language.plural_set.iterator():
            if plural.same_plural(number, formula):
                return plural

        # Create new one
        return Plural.objects.create(
            language=language,
            source=Plural.SOURCE_GETTEXT,
            number=number,
            formula=formula,
        )

    def untranslate_store(self, language) -> None:
        """Remove translations from Translate Toolkit store."""
        super().untranslate_store(language)
        plural = language.plural

        self.store.updateheader(
            last_translator="Automatically generated",
            plural_forms=plural.plural_form,
            language_team="none",
        )

    def update_header(self, **kwargs) -> None:
        """Update store header if available."""
        kwargs["x_generator"] = f"Weblate {weblate.utils.version.VERSION}"

        # Adjust Content-Type header if needed
        header = self.store.parseheader()
        if (
            "Content-Type" not in header
            or "charset=CHARSET" in header["Content-Type"]
            or "charset=ASCII" in header["Content-Type"]
        ):
            kwargs["Content_Type"] = "text/plain; charset=UTF-8"

        self.store.updateheader(**kwargs)

    def add_unit(self, unit: TranslationUnit) -> None:
        self.store.require_index()
        # Check if there is matching obsolete unit
        old_unit = self.store.id_index.get(unit.unit.getid())
        if old_unit and old_unit.isobsolete():
            self.store.removeunit(old_unit)
        super().add_unit(unit)


class PoFormat(BasePoFormat, BilingualUpdateMixin):
    name = gettext_lazy("gettext PO file")
    format_id = "po"
    monolingual = False
    autoload: tuple[str, ...] = ("*.po", "*.pot")
    unit_class = PoUnit

    @classmethod
    def get_new_file_content(cls) -> bytes:
        """Empty PO file content."""
        return b""

    @classmethod
    def do_bilingual_update(
        cls, in_file: str, out_file: str, template: str, **kwargs
    ) -> None:
        """
        Perform update of a bilingual file.

        Wrapper around msgmerge.
        """
        cmd = [
            "msgmerge",
            *kwargs.pop("args", ["--previous"]),
            "--output-file",
            out_file,
            in_file,
            template,
        ]
        if kwargs:
            msg = f"Unsupported arguments: {kwargs!r}"
            raise ValueError(msg)

        try:
            result = subprocess.run(
                cmd,
                env=get_clean_env(),
                cwd=os.path.dirname(out_file),
                capture_output=True,
                check=True,
                text=True,
            )
        except FileNotFoundError as error:
            report_error("Failed msgmerge")
            msg = "msgmerge not found, please install gettext"
            raise UpdateError(msg, error) from error
        except OSError as error:
            report_error("Failed msgmerge")
            raise UpdateError(" ".join(cmd), error) from error
        except subprocess.CalledProcessError as error:
            report_error("Failed msgmerge")
            raise UpdateError(" ".join(cmd), error.output + error.stderr) from error
        else:
            # The warnings can cause corruption (for example in case
            # PO file header is missing ASCII encoding is assumed)
            errors = []
            for line in result.stderr.splitlines():
                if (
                    "warning: internationalized messages should not contain the" in line
                    or ". done." in line
                ):
                    continue
                errors.append(line)
            if errors:
                raise UpdateError(" ".join(cmd), "\n".join(errors))


class PoMonoFormat(BasePoFormat):
    name = gettext_lazy("gettext PO file (monolingual)")
    format_id = "po-mono"
    monolingual = True
    autoload: tuple[str, ...] = ()
    new_translation = (
        'msgid ""\n'
        'msgstr "X-Generator: Weblate\\n'
        "MIME-Version: 1.0\\n"
        "Content-Type: text/plain; charset=UTF-8\\n"
        'Content-Transfer-Encoding: 8bit"'
    )
    unit_class = PoMonoUnit
    bilingual_class = PoFormat
    set_context_bilingual = False

    def create_unit_key(
        self, key: str, source: str | list[str] | multistring
    ) -> str | multistring:
        if isinstance(source, list | multistring):
            return multistring([key, f"{key}_plural"])
        return key


class TSFormat(TTKitFormat):
    name = gettext_lazy("Qt Linguist translation file")
    format_id = "ts"
    loader = tsfile
    autoload: tuple[str, ...] = ("*.ts",)
    unit_class = TSUnit
    set_context_bilingual = False
    supports_plural: bool = True
    plural_preference = (
        Plural.SOURCE_QT,
        Plural.SOURCE_DEFAULT,
    )


class XliffFormat(TTKitFormat):
    name = gettext_lazy("XLIFF 1.2 translation file")
    format_id = "plainxliff"
    loader = xlifffile
    autoload: tuple[str, ...] = ()
    unit_class = XliffUnit
    language_format = "bcp"
    use_settarget = True

    def construct_unit(self, source: str):
        unit = super().construct_unit(source)
        # Make sure new unit is using same namespace as the original
        # file (xliff 1.1/1.2)
        unit.namespace = self.store.namespace
        unit.xmlelement = etree.Element(unit.namespaced(unit.rootNode))
        setXMLspace(unit.xmlelement, "preserve")
        return unit

    def create_unit(
        self,
        key: str,
        source: str | list[str],
        target: str | list[str] | None = None,
    ):
        unit = super().create_unit(key, source, target)
        unit.marktranslated()
        unit.markapproved(False)
        return unit


class RichXliffFormat(XliffFormat):
    name = gettext_lazy("XLIFF 1.2 with placeables support")
    format_id = "xliff"
    autoload: tuple[str, ...] = ("*.xlf", "*.xliff", "*.sdlxliff", "*.mxliff")
    unit_class = RichXliffUnit


class PoXliffFormat(XliffFormat):
    name = gettext_lazy("XLIFF 1.2 with gettext extensions")
    format_id = "poxliff"
    autoload: tuple[str, ...] = ("*.poxliff",)
    loader = PoXliffFile
    supports_plural: bool = True


class PropertiesBaseFormat(TTKitFormat):
    unit_class = PropertiesUnit

    def is_valid(self):
        result = super().is_valid()
        if not result:
            return False

        # Accept empty file, but reject file without a delimiter.
        # Translate Toolkit happily parses anything into a property
        # even if there is no delimiter used in the line.
        return not self.store.units or self.store.units[0].delimiter

    @staticmethod
    def mimetype() -> str:
        """Return most common media type for format."""
        # Properties files do not expose mimetype
        return "text/plain"

    def construct_unit(self, source: str):
        return self.store.UnitClass(source, personality=self.store.personality.name)


class StringsFormat(PropertiesBaseFormat):
    name = gettext_lazy("iOS strings (UTF-16)")
    format_id = "strings"
    loader = ("properties", "stringsfile")
    new_translation: str | bytes | None = "\n".encode("utf-16")
    autoload: tuple[str, ...] = ("*.strings",)
    language_format = "bcp"


class StringsUtf8Format(StringsFormat):
    name = gettext_lazy("iOS strings (UTF-8)")
    format_id = "strings-utf8"
    loader = ("properties", "stringsutf8file")
    new_translation = "\n"


class PropertiesUtf8Format(PropertiesBaseFormat):
    name = gettext_lazy("Java Properties (UTF-8)")
    format_id = "properties-utf8"
    loader = ("properties", "javautf8file")
    new_translation = "\n"
    language_format = "linux"
    check_flags = ("auto-java-messageformat",)


class PropertiesUtf16Format(PropertiesBaseFormat):
    name = gettext_lazy("Java Properties (UTF-16)")
    format_id = "properties-utf16"
    loader = ("properties", "javafile")
    language_format = "linux"
    new_translation = "\n"
    # Translate Toolkit autodetection might fail in some cases.
    force_encoding = "utf-16"


class PropertiesFormat(PropertiesBaseFormat):
    name = gettext_lazy("Java Properties (ISO 8859-1)")
    format_id = "properties"
    loader = ("properties", "javafile")
    language_format = "linux"
    new_translation = "\n"
    autoload: tuple[str, ...] = ("*.properties",)
    # Java properties need to be ISO 8859-1, but Translate Toolkit converts
    # them to UTF-8.
    force_encoding = "iso-8859-1"


class JoomlaFormat(PropertiesBaseFormat):
    name = gettext_lazy("Joomla language file")
    format_id = "joomla"
    loader = ("properties", "joomlafile")
    monolingual = True
    new_translation = "\n"
    autoload: tuple[str, ...] = ("*.ini",)


class GWTFormat(StringsFormat):
    name = gettext_lazy("GWT properties (UTF-8)")
    format_id = "gwt"
    loader = ("properties", "gwtfile")
    new_translation = "\n"
    check_flags = ("auto-java-messageformat",)
    language_format = "linux"
    supports_plural: bool = True


class GWTISOFormat(GWTFormat):
    name = gettext_lazy("GWT properties (ISO-8859-1)")
    format_id = "gwt-iso"
    force_encoding = "iso-8859-1"


class PhpFormat(TTKitFormat):
    name = gettext_lazy("PHP strings")
    format_id = "php"
    loader = ("php", "phpfile")
    new_translation = "<?php\n"
    autoload: tuple[str, ...] = ("*.php",)
    unit_class = PHPUnit

    @staticmethod
    def mimetype() -> str:
        """Return most common media type for format."""
        return "text/x-php"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "php"


class LaravelPhpFormat(PhpFormat):
    name = gettext_lazy("Laravel PHP strings")
    format_id = "laravel"
    loader = ("php", "LaravelPHPFile")
    supports_plural: bool = True


class RESXFormat(TTKitFormat):
    name = gettext_lazy(".NET resource file")
    format_id = "resx"
    loader = RESXFile
    monolingual = True
    unit_class = RESXUnit
    new_translation = RESXFile.XMLskeleton
    autoload: tuple[str, ...] = ("*.resx",)
    language_format = "bcp"
    supports_plural: bool = True


class AndroidFormat(TTKitFormat):
    name = gettext_lazy("Android String Resource")
    format_id = "aresource"
    loader = ("aresource", "AndroidResourceFile")
    monolingual = True
    unit_class = AndroidUnit
    new_translation = '<?xml version="1.0" encoding="utf-8"?>\n<resources></resources>'
    autoload: tuple[str, ...] = ("strings*.xml", "values*.xml")
    language_format = "android"
    check_flags = ("java-printf-format",)
    autoaddon = {"weblate.cleanup.blank": {}}
    plural_preference = (
        Plural.SOURCE_ANDROID,
        Plural.SOURCE_CLDR,
        Plural.SOURCE_DEFAULT,
    )
    strict_format_plurals: bool = True
    supports_plural: bool = True


class MOKOFormat(AndroidFormat):
    name = gettext_lazy("Mobile Kotlin Resource")
    format_id = "moko-resource"
    loader = ("aresource", "MOKOResourceFile")


class DictStoreFormat(TTKitFormat):
    @classmethod
    def validate_context(cls, context: str) -> None:
        id_class = cls.get_class().UnitClass.IdClass

        try:
            id_class.from_string(context)
        except Exception as error:
            raise ValidationError(
                gettext("Could not parse the key: %s") % error
            ) from error


class JSONFormat(DictStoreFormat):
    name = gettext_lazy("JSON file")
    format_id = "json"
    loader = JsonFile
    unit_class = JSONUnit
    autoload: tuple[str, ...] = ("*.json",)
    new_translation = "{}\n"
    set_context_bilingual = False

    @staticmethod
    def mimetype() -> str:
        """Return most common media type for format."""
        return "application/json"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "json"


class JSONNestedFormat(JSONFormat):
    name = gettext_lazy("JSON nested structure file")
    format_id = "json-nested"
    loader = ("jsonl10n", "JsonNestedFile")
    autoload: tuple[str, ...] = ()


class WebExtensionJSONFormat(JSONFormat):
    name = gettext_lazy("WebExtension JSON file")
    format_id = "webextension"
    loader = ("jsonl10n", "WebExtensionJsonFile")
    monolingual = True
    autoload: tuple[str, ...] = ("messages*.json",)
    unit_class = PlaceholdersJSONUnit
    supports_plural: bool = True


class I18NextFormat(JSONFormat):
    name = gettext_lazy("i18next JSON file v3")
    format_id = "i18next"
    loader = ("jsonl10n", "I18NextFile")
    autoload: tuple[str, ...] = ()
    check_flags = ("i18next-interpolation",)
    language_format: str = "bcp"
    supports_plural: bool = True


class I18NextV4Format(I18NextFormat):
    name = gettext_lazy("i18next JSON file v4")
    format_id = "i18nextv4"
    loader = ("jsonl10n", "I18NextV4File")


class GoI18JSONFormat(JSONFormat):
    name = gettext_lazy("go-i18n v1 JSON file")
    format_id = "go-i18n-json"
    loader = ("jsonl10n", "GoI18NJsonFile")
    autoload: tuple[str, ...] = ()
    new_translation = "[]\n"
    supports_plural: bool = True


class GoI18V2JSONFormat(JSONFormat):
    name = gettext_lazy("go-i18n v2 JSON file")
    format_id = "go-i18n-json-v2"
    loader = ("jsonl10n", "GoI18NV2JsonFile")
    autoload: tuple[str, ...] = ()
    supports_plural: bool = True


class ARBFormat(JSONFormat):
    name = gettext_lazy("ARB file")
    format_id = "arb"
    loader = ("jsonl10n", "ARBJsonFile")
    autoload: tuple[str, ...] = ("*.arb",)
    unit_class = PlaceholdersJSONUnit
    check_flags = ("icu-message-format",)


class GoTextFormat(JSONFormat):
    name = gettext_lazy("gotext JSON file")
    format_id = "gotext"
    loader = ("jsonl10n", "GoTextJsonFile")
    autoload: tuple[str, ...] = ()
    unit_class = PlaceholdersJSONUnit
    supports_plural: bool = True


class FormatJSFormat(JSONFormat):
    name = gettext_lazy("Format.JS JSON file")
    format_id = "formatjs"
    loader = ("jsonl10n", "FormatJSJsonFile")
    autoload: tuple[str, ...] = ()
    check_flags = ("icu-message-format",)


class CSVFormat(TTKitFormat):
    name = gettext_lazy("CSV file")
    format_id = "csv"
    loader = ("csvl10n", "csvfile")
    unit_class = CSVUnit
    autoload: tuple[str, ...] = ("*.csv",)
    force_encoding = "auto"

    def __init__(
        self,
        storefile,
        template_store=None,
        language_code: str | None = None,
        source_language: str | None = None,
        is_template: bool = False,
        existing_units: list[Any] | None = None,
    ) -> None:
        super().__init__(
            storefile,
            template_store=template_store,
            language_code=language_code,
            source_language=source_language,
            is_template=is_template,
            existing_units=existing_units,
        )
        # Remove template if the file contains source, this is needed
        # for import, but probably usable elsewhere as well
        if "source" in self.store.fieldnames and not isinstance(
            template_store, CSVFormat
        ):
            self.template_store = None

    @staticmethod
    def mimetype() -> str:
        """Return most common media type for format."""
        return "text/csv"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "csv"

    @staticmethod
    def get_content_and_filename(storefile):
        # Did we get file or filename or file object?
        if hasattr(storefile, "read"):
            filename = getattr(storefile, "name", getattr(storefile, "filename", None))
            content = storefile.read()
            storefile.close()
        else:
            filename = storefile
            with open(filename, "rb") as handle:
                content = handle.read()
        return content, filename

    def parse_store(self, storefile, *, dialect: str | None = None):
        """Parse the store."""
        content, filename = self.get_content_and_filename(storefile)

        # Parse file
        store = self.get_store_instance()
        store.parse(
            content,
            sample_length=40000 if dialect is None else None,
            dialect=dialect,
        )
        # Did detection of headers work?
        if store.fieldnames != ["location", "source", "target"]:
            return store

        fileobj = csv.StringIO(
            store.detect_encoding(content, default_encodings=["utf-8", "utf-16"])[0]
        )

        # Try reading header
        reader = csv.reader(fileobj, store.dialect)
        header = next(reader)
        fileobj.close()

        # Check if the file is not two column only, in that case translate-toolkit detection
        # wrongly assumes three column files
        if len(header) != 2:
            return store

        return self.parse_simple_csv(content, filename, header=header)

    def parse_simple_csv(self, content, filename, header: list[str] | None = None):
        fieldnames = ["source", "target"]
        if header and all(
            field in {"source", "target", "context", "id"} for field in header
        ):
            fieldnames = header
        elif self.is_template or self.template_store:
            fieldnames = ["context", "target"]
        result = self.get_store_instance(fieldnames=fieldnames)
        result.parse(content, sample_length=None)
        result.filename = filename
        return result


class CSVUtf8Format(CSVFormat):
    name = gettext_lazy("CSV file (UTF-8)")
    format_id = "csv-utf-8"
    autoload: tuple[str, ...] = ()
    force_encoding = "utf-8"


class CSVSimpleFormat(CSVFormat):
    name = gettext_lazy("Simple CSV file")
    format_id = "csv-simple"
    autoload: tuple[str, ...] = ("*.txt",)
    force_encoding = "auto"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "csv"

    def parse_store(self, storefile):
        """Parse the store."""
        content, filename = self.get_content_and_filename(storefile)

        return self.parse_simple_csv(content, filename)


class CSVSimpleFormatISO(CSVSimpleFormat):
    name = gettext_lazy("Simple CSV file (ISO-8859-1)")
    format_id = "csv-simple-iso"
    force_encoding = "iso-8859-1"
    autoload: tuple[str, ...] = ()


class CSVUtf8SimpleFormat(CSVSimpleFormat):
    name = gettext_lazy("Simple CSV file (UTF-8)")
    format_id = "csv-simple-utf-8"
    force_encoding = "utf-8"
    autoload: tuple[str, ...] = ()


class YAMLFormat(DictStoreFormat):
    name = gettext_lazy("YAML file")
    format_id = "yaml"
    loader = ("yaml", "YAMLFile")
    unit_class = MonolingualSimpleUnit
    autoload: tuple[str, ...] = ("*.pyml",)
    new_translation = "{}\n"

    @staticmethod
    def mimetype() -> str:
        """Return most common media type for format."""
        return "text/yaml"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "yml"


class RubyYAMLFormat(YAMLFormat):
    name = gettext_lazy("Ruby YAML file")
    format_id = "ruby-yaml"
    loader = ("yaml", "RubyYAMLFile")
    autoload: tuple[str, ...] = ("*.ryml", "*.yml", "*.yaml")
    supports_plural: bool = True


class DTDFormat(TTKitFormat):
    name = gettext_lazy("DTD file")
    format_id = "dtd"
    loader = ("dtd", "dtdfile")
    autoload: tuple[str, ...] = ("*.dtd",)
    unit_class = MonolingualSimpleUnit
    new_translation = "\n"
    can_add_unit: bool = False

    @staticmethod
    def mimetype() -> str:
        """Return most common media type for format."""
        return "application/xml-dtd"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "dtd"

    @property
    def all_store_units(self):
        """Wrapper for all store unit filtering out null."""
        return (unit for unit in self.store.units if not unit.isblank())


class SubtitleUnit(MonolingualIDUnit):
    @cached_property
    def source(self):
        if self.template is not None:
            return self.template.source
        return self.unit.source

    @cached_property
    def target(self):
        """Return target string from a Translate Toolkit unit."""
        if self.unit is None:
            return ""
        return get_string(self.unit.source)

    def is_translated(self):
        """Check whether unit is translated."""
        return self.has_translation()


class SubRipFormat(TTKitFormat):
    name = gettext_lazy("SubRip subtitle file")
    format_id = "srt"
    loader = ("subtitles", "SubRipFile")
    unit_class = SubtitleUnit
    autoload: tuple[str, ...] = ("*.srt",)
    monolingual = True
    autoaddon = {"weblate.flags.same_edit": {}}

    @staticmethod
    def mimetype() -> str:
        """Return most common media type for format."""
        return "text/plain"


class MicroDVDFormat(SubRipFormat):
    name = gettext_lazy("MicroDVD subtitle file")
    format_id = "sub"
    loader = ("subtitles", "MicroDVDFile")
    autoload: tuple[str, ...] = ("*.sub",)


class AdvSubStationAlphaFormat(SubRipFormat):
    name = gettext_lazy("Advanced SubStation Alpha subtitle file")
    format_id = "ass"
    loader = ("subtitles", "AdvSubStationAlphaFile")
    autoload: tuple[str, ...] = ("*.ass",)


class SubStationAlphaFormat(SubRipFormat):
    name = gettext_lazy("SubStation Alpha subtitle file")
    format_id = "ssa"
    loader = ("subtitles", "SubStationAlphaFile")
    autoload: tuple[str, ...] = ("*.ssa",)


class FlatXMLFormat(TTKitFormat):
    name = gettext_lazy("Flat XML file")
    format_id = "flatxml"
    loader = ("flatxml", "FlatXMLFile")
    monolingual = True
    unit_class = FlatXMLUnit
    new_translation = '<?xml version="1.0" encoding="utf-8"?>\n<root></root>'


class ResourceDictionaryFormat(FlatXMLFormat):
    name = gettext_lazy("ResourceDictionary file")
    format_id = "resourcedictionary"
    loader = ("resourcedictionary", "ResourceDictionaryFile")
    check_flags = ("c-sharp-format",)
    language_format = "bcp_legacy"
    new_translation = """<ResourceDictionary
  xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
  xmlns:system="clr-namespace:System;assembly=mscorlib">
</ResourceDictionary>"""


class INIFormat(TTKitFormat):
    name = gettext_lazy("INI file")
    format_id = "ini"
    loader = ("ini", "inifile")
    monolingual = True
    unit_class = INIUnit
    new_translation = "\n"

    @staticmethod
    def mimetype() -> str:
        """Return most common media type for format."""
        # INI files do not expose mimetype
        return "text/plain"

    @classmethod
    def extension(cls) -> str:
        """Return most common file extension for format."""
        # INI files do not expose extension
        return "ini"

    def load(
        self, storefile: str | BinaryIO, template_store: TranslationFormat | None
    ) -> TranslationStore:
        store = super().load(storefile, template_store)
        # Adjust store to have translations
        for unit in store.units:
            unit.target = unit.source
            unit.rich_target = unit.rich_source
        return store

    def create_unit(
        self,
        key: str,
        source: str | list[str],
        target: str | list[str] | None = None,
    ):
        unit = super().create_unit(key, source, target)
        unit.location = key
        return unit


class InnoSetupINIFormat(INIFormat):
    name = gettext_lazy("Inno Setup INI file")
    format_id = "islu"
    loader = ("ini", "inifile")

    @classmethod
    def extension(cls) -> str:
        """Return most common file extension for format."""
        # INI files do not expose extension
        return "islu"

    @staticmethod
    def get_class_kwargs():
        return {"dialect": "inno"}


class XWikiUnit(PropertiesUnit):
    """
    Dedicated unit for XWiki.

    Inspired from PropertiesUnit, allow to override the methods to use the right
    XWikiDialect methods for decoding properties.
    """

    @cached_property
    def source(self):
        # Need to decode property encoded string
        return get_string(quote.xwiki_properties_decode(super().source))

    @cached_property
    def target(self):
        """Return target string from a Translate Toolkit unit."""
        if self.unit is None:
            return ""
        # Need to decode property encoded string
        # This is basically stolen from
        # translate.storage.properties.propunit.gettarget
        # which for some reason does not return translation
        value = quote.xwiki_properties_decode(self.unit.value)
        value = re.sub(r"\\ ", " ", value)
        return get_string(value)


class XWikiPropertiesFormat(PropertiesBaseFormat):
    """
    Represents an XWiki Java Properties translation file.

    This format specification is detailed in
    https://dev.xwiki.org/xwiki/bin/view/Community/XWiki%20Translations%20Formats/#HXWikiJavaProperties
    """

    unit_class = XWikiUnit
    name = "XWiki Java Properties"
    format_id = "xwiki-java-properties"
    loader = ("properties", "xwikifile")
    language_format = "linux"
    autoload: tuple[str, ...] = ("*.properties",)
    new_translation = "\n"
    can_add_unit: bool = False
    can_delete_unit: bool = False
    set_context_bilingual: bool = True
    supports_plural: bool = True

    # Ensure that untranslated units are saved too as missing properties and
    # comments are preserved as in the original source file.
    def save_content(self, handle) -> None:
        current_units = self.all_units
        store_units = self.store.units

        # We empty the store units since we want to control what we'll serialize
        self.store.units = []

        for unit in current_units:
            # If the translation unit is missing and the current unit is not
            # only about comment.
            if unit.unit is None and unit.has_content():
                # We first check if the unit has not been translated as part of a
                # new language: in that case the unit is not linked yet.
                found_store_unit = None
                for store_unit in store_units:
                    if unit.context == store_unit.name:
                        found_store_unit = store_unit

                # If we found a unit for same context not linked, we just link it.
                if found_store_unit is not None:
                    unit.unit = found_store_unit
                # else it's a missing unit: we need to mark it as missing.
                else:
                    missingunit = self.unit_class(self, unit.mainunit, unit.template)
                    unit.unit = missingunit.unit
                    unit.unit.missing = True
            # if the unit was only a comment, we take back the original source file unit
            # to avoid any change.
            elif not unit.has_content():
                unit.unit = unit.mainunit
            self.add_unit(unit)

        self.store.serialize(handle)


class XWikiPagePropertiesFormat(XWikiPropertiesFormat):
    """
    Represents an XWiki Page Properties translation file.

    This format specification is detailed in
    https://dev.xwiki.org/xwiki/bin/view/Community/XWiki%20Translations%20Formats/#HXWikiPageProperties
    """

    name = "XWiki Page Properties"
    format_id = "xwiki-page-properties"
    loader = ("properties", "XWikiPageProperties")
    force_encoding = "utf-8"

    def save_content(self, handle) -> None:
        if self.store.root is None:
            self.store.root = self.template_store.store.root
        super().save_content(handle)


class XWikiFullPageFormat(XWikiPagePropertiesFormat):
    """
    Represents an XWiki Full Page translation file.

    This format specification is detailed in
    https://dev.xwiki.org/xwiki/bin/view/Community/XWiki%20Translations%20Formats/#HXWikiFullContentTranslation
    """

    name = "XWiki Full Page"
    format_id = "xwiki-fullpage"
    loader = ("properties", "XWikiFullPage")


class TBXUnit(TTKitUnit):
    def _get_notes(self, *origins: str) -> str:
        notes = []
        for origin in origins:
            note = self.unit.getnotes(origin)
            if note:
                notes.append(note)
        return "\n".join(notes)

    @cached_property
    def notes(self):
        """Return notes or notes from units."""
        return self._get_notes("pos", "developer")

    @cached_property
    def context(self):
        return self.unit.xmlelement.get("id") or ""

    def set_explanation(self, explanation: str) -> None:
        if explanation or self.explanation:
            self.unit.addnote(explanation, origin="translator", position="replace")
        self.__dict__.pop("explanation", None)

    @cached_property
    def explanation(self) -> str:
        return self._get_notes("translator")

    def set_source_explanation(self, explanation: str) -> None:
        if explanation or self.source_explanation:
            self.unit.addnote(explanation, origin="definition", position="replace")
        self.__dict__.pop("source_explanation", None)

    @cached_property
    def source_explanation(self) -> str:
        return self._get_notes("definition")


class TBXFormat(TTKitFormat):
    name = gettext_lazy("TermBase eXchange file")
    format_id = "tbx"
    loader = tbxfile
    autoload: tuple[str, ...] = ("*.tbx",)
    new_translation = tbxfile.XMLskeleton
    unit_class = TBXUnit
    create_empty_bilingual: bool = True
    use_settarget = True
    monolingual = False
    supports_explanation: bool = True
    store: tbxfile

    def __init__(
        self,
        storefile,
        template_store=None,
        language_code: str | None = None,
        source_language: str | None = None,
        is_template: bool = False,
        existing_units: list[Any] | None = None,
    ) -> None:
        super().__init__(
            storefile,
            template_store=template_store,
            language_code=language_code,
            is_template=is_template,
            source_language=source_language,
            existing_units=existing_units,
        )
        # Add language header if not present
        self.store.addheader()


class PropertiesMi18nFormat(PropertiesUtf8Format):
    name = gettext_lazy("@draggable/i18n lang file")
    format_id = "mi18n-lang"
    new_translation = "\n"
    language_format = "bcp_legacy"
    check_flags = ("es-format",)
    monolingual = True


class StringsdictFormat(DictStoreFormat):
    name = gettext_lazy("Stringsdict file")
    format_id = "stringsdict"
    loader = ("stringsdict", "StringsDictFile")
    unit_class = MonolingualSimpleUnit
    autoload: tuple[str, ...] = ("*.stringsdict",)
    new_translation = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
    </dict>
</plist>
"""
    supports_plural: bool = True

    @staticmethod
    def mimetype() -> str:
        """Return most common media type for format."""
        return "application/xml"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "stringsdict"

    @classmethod
    def get_plural(cls, language, store=None):
        """Return matching plural object."""
        plural = super().get_plural(language, store)
        if plural.type in ZERO_PLURAL_TYPES:
            return plural

        from weblate.lang.models import Plural

        return language.plural_set.get_or_create(
            source=Plural.SOURCE_CLDR_ZERO,
            defaults={
                "formula": FORMULA_WITH_ZERO[plural.formula],
                "number": plural.number + 1,
            },
        )[0]

    def fixup(self, store) -> None:
        if self.language_code:
            store.settargetlanguage(self.language_code)
        elif self.source_language:
            store.settargetlanguage(self.source_language)


class FluentUnit(MonolingualSimpleUnit):
    def set_target(self, target: str | list[str]) -> None:
        old_target = self.unit.target
        old_source = self.unit.source
        super().set_target(target)
        self.unit.source = target
        try:
            # This triggers serialization discovering any syntax issues
            self.unit.to_entry()
        except Exception:
            # Restore previous content
            self.unit.target = old_target
            self.unit.source = old_source
            raise

    @cached_property
    def flags(self):
        flags = Flags()
        flags.set_value("fluent-type", self.mainunit.fluent_type)
        return flags.format()


class FluentFormat(TTKitFormat):
    name = gettext_lazy("Fluent file")
    format_id = "fluent"
    loader = ("fluent", "FluentFile")
    unit_class = FluentUnit
    autoload: tuple[str, ...] = ("*.ftl",)
    new_translation = ""
    check_flags = (
        "fluent-source-syntax",
        "fluent-target-syntax",
        "fluent-parts",
        "fluent-references",
        "fluent-source-inner-html",
        "fluent-target-inner-html",
        # Ignore xml check since we have inner-html checks.
        "ignore-xml-tags",
        "ignore-xml-invalid",
    )

    @staticmethod
    def mimetype() -> str:
        """Return most common media type for format."""
        return "text/x-fluent"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "ftl"

    def create_unit(
        self,
        key: str,
        source: str | list[str],
        target: str | list[str] | None = None,
    ):
        unit = super().create_unit(key, source, target)
        unit.source = unit.target
        return unit
