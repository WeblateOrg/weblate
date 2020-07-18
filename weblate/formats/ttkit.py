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
"""Translate Toolkit based file format wrappers."""


import importlib
import inspect
import os
import re
import subprocess

from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from lxml.etree import XMLSyntaxError
from translate.misc import quote
from translate.misc.multistring import multistring
from translate.storage.base import TranslationStore
from translate.storage.csvl10n import csv
from translate.storage.lisa import LISAfile
from translate.storage.po import pofile, pounit
from translate.storage.poxliff import PoXliffFile
from translate.storage.resx import RESXFile
from translate.storage.ts2 import tsfile, tsunit
from translate.storage.xliff import ID_SEPARATOR, xlifffile

import weblate
from weblate.checks.flags import Flags
from weblate.formats.base import (
    BilingualUpdateMixin,
    TranslationFormat,
    TranslationUnit,
    UpdateError,
)
from weblate.trans.util import (
    get_clean_env,
    get_string,
    join_plural,
    rich_to_xliff_string,
    xliff_string_to_rich,
)
from weblate.utils.errors import report_error

LOCATIONS_RE = re.compile(r"^([+-]|.*, [+-]|.*:[+-])")
SUPPORTS_FUZZY = (pounit, tsunit)
XLIFF_FUZZY_STATES = {"new", "needs-translation", "needs-adaptation", "needs-l10n"}


class TTKitUnit(TranslationUnit):
    @cached_property
    def locations(self):
        """Return comma separated list of locations."""
        return ", ".join(x for x in self.mainunit.getlocations() if x is not None)

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
            return ""
        return get_string(self.unit.target)

    @cached_property
    def context(self):
        """Return context of message.

        In some cases we have to use ID here to make all backends consistent.
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
                comment = template_comment + "\n" + comment

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
            return self.unit.isfuzzy()
        return fallback

    def has_content(self):
        """Check whether unit has content."""
        return (
            not self.mainunit.isheader()
            and not self.mainunit.isblank()
            and not self.mainunit.isobsolete()
        )

    def is_readonly(self):
        return not self.mainunit.istranslatable()

    def set_target(self, target):
        """Set translation unit target."""
        self._invalidate_target()
        if isinstance(target, list):
            target = multistring(target)
        self.unit.target = target

    def mark_fuzzy(self, fuzzy):
        """Set fuzzy flag on translated unit."""
        if "flags" in self.__dict__:
            del self.__dict__["flags"]
        self.unit.markfuzzy(fuzzy)

    def mark_approved(self, value):
        """Set approved flag on translated unit."""
        if "flags" in self.__dict__:
            del self.__dict__["flags"]
        if hasattr(self.unit, "markapproved"):
            self.unit.markapproved(value)

    @cached_property
    def flags(self):
        """Return flags from unit.

        We currently extract maxwidth attribute.
        """
        flags = Flags()
        if hasattr(self.unit, "xmlelement"):
            flags.merge(self.unit.xmlelement)
        if hasattr(self.template, "xmlelement"):
            flags.merge(self.template.xmlelement)
        return flags.format()


class KeyValueUnit(TTKitUnit):
    @cached_property
    def source(self):
        """Return source string from a Translate Toolkit unit."""
        if self.template is not None:
            return self.template.value
        return self.unit.name

    @cached_property
    def target(self):
        """Return target string from a Translate Toolkit unit."""
        if self.unit is None:
            return ""
        return self.unit.value

    @cached_property
    def context(self):
        """Return context of message.

        In some cases we have to use ID here to make all backends consistent.
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
            return not self.unit.isfuzzy() and self.unit.value != ""
        return self.unit.istranslated()

    def set_target(self, target):
        """Set translation unit target."""
        super().set_target(target)
        # Propagate to value so that is_translated works correctly
        self.unit.value = self.unit.target


class TTKitFormat(TranslationFormat):
    unit_class = TTKitUnit
    loader = ("", "")

    def __init__(
        self, storefile, template_store=None, language_code=None, is_template=False
    ):
        super().__init__(storefile, template_store, language_code, is_template)
        # Set language (needed for some which do not include this)
        if language_code is not None and self.store.gettargetlanguage() is None:
            self.store.settargetlanguage(self.get_language_code(language_code))

    @staticmethod
    def serialize(store):
        """Serialize given Translate Toolkit store."""
        return bytes(store)

    @classmethod
    def fixup(cls, store):
        """Perform optional fixups on store."""
        return

    @classmethod
    def load(cls, storefile):
        """Load file using defined loader."""
        # Add missing mode attribute to Django file wrapper
        if isinstance(storefile, TranslationStore):
            # Used by XLSX writer
            return storefile

        return cls.parse_store(storefile)

    @classmethod
    def get_class(cls):
        """Return class for handling this module."""
        # Direct class
        if inspect.isclass(cls.loader):
            return cls.loader
        # Tuple style loader, import from translate toolkit
        module_name, class_name = cls.loader
        if "." not in module_name:
            module_name = "translate.storage.{0}".format(module_name)
        module = importlib.import_module(module_name)

        # Get the class
        return getattr(module, class_name)

    @staticmethod
    def get_class_kwargs():
        return {}

    @classmethod
    def parse_store(cls, storefile):
        """Parse the store."""
        store = cls.get_class()(**cls.get_class_kwargs())

        # Apply possible fixups
        cls.fixup(store)

        # Read the content
        if isinstance(storefile, str):
            with open(storefile, "rb") as handle:
                content = handle.read()
        else:
            content = storefile.read()

        # Parse the content
        store.parse(content)

        return store

    def add_unit(self, ttkit_unit):
        """Add new unit to underlaying store."""
        if isinstance(self.store, LISAfile):
            # LISA based stores need to know this
            self.store.addunit(ttkit_unit, new=True)
        else:
            self.store.addunit(ttkit_unit)

    def save_content(self, handle):
        """Store content to file."""
        self.store.serialize(handle)

    def save(self):
        """Save underlaying store to disk."""
        self.save_atomic(self.storefile, self.save_content)

    @classmethod
    def mimetype(cls):
        """Return most common media type for format."""
        return cls.get_class().Mimetypes[0]

    @classmethod
    def extension(cls):
        """Return most common file extension for format."""
        return cls.get_class().Extensions[0]

    def is_valid(self):
        """Check whether store seems to be valid.

        In some cases Translate Toolkit happily "parses" the file, even though it really
        did not do so (e.g. gettext parser on random text file).
        """
        if self.store is None:
            return False

        return True

    def construct_unit(self, source):
        return self.store.UnitClass(source)

    def create_unit(self, key, source):
        unit = self.construct_unit(source)
        unit.setid(key)
        unit.source = key
        unit.target = source
        return unit

    @classmethod
    def untranslate_store(cls, store, language, fuzzy=False):
        """Remove translations from Translate Toolkit store."""
        store.settargetlanguage(cls.get_language_code(language.code))
        plural = language.plural

        for unit in store.units:
            if unit.istranslatable():
                if hasattr(unit, "markapproved"):
                    # Xliff only
                    unit.markapproved(False)
                else:
                    unit.markfuzzy(fuzzy)
                if unit.hasplural():
                    unit.target = [""] * plural.number
                else:
                    unit.target = ""

    @classmethod
    def get_new_file_content(cls):
        result = cls.new_translation
        if isinstance(result, str):
            result = result.encode()
        return result

    @classmethod
    def create_new_file(cls, filename, language, base):
        """Handle creation of new translation file."""
        if base:
            # Parse file
            store = cls.parse_store(base)
            cls.untranslate_store(store, language)
            store.savefile(filename)
        elif cls.new_translation is None:
            raise ValueError("Not supported")
        else:
            with open(filename, "wb") as output:
                output.write(cls.get_new_file_content())

    @classmethod
    def is_valid_base_for_new(cls, base, monolingual):
        """Check whether base is valid."""
        if not base:
            return monolingual and cls.new_translation is not None
        try:
            cls.parse_store(base)
            return True
        except Exception:
            report_error(cause="File parse error")
            return False

    @property
    def all_store_units(self):
        """Wrapper for all store unit filtering out obsolete."""
        return (unit for unit in self.store.units if not unit.isobsolete())


class PropertiesUnit(KeyValueUnit):
    """Wrapper for properties based units."""

    @cached_property
    def locations(self):
        """Return comma separated list of locations."""
        return ""

    @cached_property
    def source(self):
        # Need to decode property encoded string
        return quote.propertiesdecode(super().source)

    @cached_property
    def target(self):
        """Return target string from a Translate Toolkit unit."""
        if self.unit is None:
            return ""
        # Need to decode property encoded string
        # This is basically stolen from
        # translate.storage.properties.propunit.gettarget
        # which for some reason does not return translation
        value = quote.propertiesdecode(self.unit.value)
        value = re.sub("\\\\ ", " ", value)
        return value


class PoUnit(TTKitUnit):
    """Wrapper for gettext PO unit."""

    def mark_fuzzy(self, fuzzy):
        """Set fuzzy flag on translated unit."""
        super().mark_fuzzy(fuzzy)
        if not fuzzy:
            self.unit.prev_msgid = []
            self.unit.prev_msgid_plural = []
            self.unit.prev_msgctxt = []

    @cached_property
    def flags(self):
        """Return flags or typecomments from units."""
        flags = Flags(*self.mainunit.typecomments)
        flags.remove({"fuzzy"})
        return flags.format()

    @cached_property
    def previous_source(self):
        """Return previous message source if there was any."""
        if not self.is_fuzzy():
            return ""
        return get_string(self.unit.prev_source)


class PoMonoUnit(PoUnit):
    @cached_property
    def context(self):
        """Return context of message.

        In some cases we have to use ID here to make all backends consistent.
        """
        # Monolingual PO files
        if self.template is not None:
            return self.template.source or self.template.getcontext()
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
        return "\n".join(notes)


class XliffUnit(TTKitUnit):
    """Wrapper unit for XLIFF.

    XLIFF is special in Translate Toolkit - it uses locations for what
    is context in other formats.
    """

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

    def set_target(self, target):
        """Set translation unit target."""
        self._invalidate_target()
        try:
            converted = xliff_string_to_rich(target)
        except XMLSyntaxError:
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

    @cached_property
    def xliff_node(self):
        return self.unit.getlanguageNode(lang=None, index=1)

    @property
    def xliff_state(self):
        if self.xliff_node is None:
            return None
        return self.xliff_node.get("state", None)

    @cached_property
    def context(self):
        """Return context of message.

        Use resname if available as it usually is more interesting for the translator
        than ID.
        """
        resname = self.mainunit.xmlelement.get("resname")
        if resname:
            return resname
        return self.mainunit.getid().replace(ID_SEPARATOR, "///")

    @cached_property
    def locations(self):
        """Return comma separated list of locations."""
        return ""

    def is_translated(self):
        """Check whether unit is translated.

        We replace Translate Toolkit logic here as the isfuzzy is pretty much wrong
        there, see is_fuzzy docs.
        """
        return bool(self.target)

    def is_fuzzy(self, fallback=False):
        """Check whether unit needs edit.

        The isfuzzy on XLIFF is really messing up approved flag with fuzzy
        and leading to various problems.

        That's why we handle it on our own.
        """
        return self.target and self.xliff_state in XLIFF_FUZZY_STATES

    def mark_fuzzy(self, fuzzy):
        """Set fuzzy flag on translated unit.

        We handle this on our own.
        """
        if fuzzy:
            self.xliff_node.set("state", "needs-translation")
        elif self.xliff_state:
            self.xliff_node.set("state", "translated")

    def is_approved(self, fallback=False):
        """Check whether unit is appoved."""
        if self.unit is None:
            return fallback
        if hasattr(self.unit, "isapproved"):
            return self.unit.isapproved()
        return fallback

    def mark_approved(self, value):
        super().mark_approved(value)
        if self.xliff_state:
            self.xliff_node.set("state", "final" if value else "translated")

    def has_content(self):
        """Check whether unit has content.

        For some reason, blank string does not mean non translatable unit in XLIFF, so
        lets skip those as well.
        """
        return (
            not self.mainunit.isheader()
            and bool(rich_to_xliff_string(self.mainunit.rich_source))
            and not self.mainunit.isobsolete()
        )


class FlatXMLUnit(TTKitUnit):
    @cached_property
    def context(self):
        if self.template is not None:
            return self.template.source
        return self.mainunit.source

    @cached_property
    def source(self):
        return self.mainunit.target


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
            # as there is no singlular/plural in the source string
            source = self.unit.source
            return join_plural([source.replace("(s)", ""), source.replace("(s)", "s")])
        return super().source

    @cached_property
    def locations(self):
        """Return comma separated list of locations."""
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


class MonolingualSimpleUnit(MonolingualIDUnit):
    @cached_property
    def locations(self):
        return ""

    @cached_property
    def source(self):
        if self.template is None:
            return self.mainunit.getid().lstrip(".")
        return get_string(self.template.target)

    def has_content(self):
        return not self.mainunit.isheader()

    def is_readonly(self):
        return False


class WebExtensionJSONUnit(MonolingualSimpleUnit):
    @cached_property
    def flags(self):
        placeholders = self.mainunit.placeholders
        if not placeholders:
            return ""
        return "placeholders:{}".format(
            ":".join(
                Flags.format_value("${}$".format(key.upper()))
                for key in placeholders.keys()
            )
        )


class ARBJSONUnit(MonolingualSimpleUnit):
    @cached_property
    def flags(self):
        placeholders = self.mainunit.placeholders
        if not placeholders:
            return ""
        return "placeholders:{}".format(
            ":".join(
                Flags.format_value("{{{}}}".format(key.upper()))
                for key in placeholders.keys()
            )
        )


class CSVUnit(MonolingualSimpleUnit):
    @cached_property
    def context(self):
        # Needed to avoid Translate Toolkit construct ID
        # as context\04source
        if self.template is not None:
            if self.template.id:
                return self.template.id
            if self.template.context:
                return self.template.context
            return self.template.getid()
        return self.mainunit.getcontext()

    @cached_property
    def source(self):
        # Needed to avoid Translate Toolkit construct ID
        # as context\04source
        if self.template is None:
            return get_string(self.mainunit.source)
        return super().source


class RESXUnit(TTKitUnit):
    @cached_property
    def locations(self):
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
    def locations(self):
        return ""

    @cached_property
    def source(self):
        if self.template is not None:
            return self.template.source
        return self.unit.getid()

    @cached_property
    def target(self):
        if self.unit is None:
            return ""
        return self.unit.source


class INIUnit(TTKitUnit):
    @cached_property
    def locations(self):
        return ""

    @cached_property
    def context(self):
        if self.template is not None:
            return self.template.location
        return self.unit.location

    def has_content(self):
        return True

    def is_readonly(self):
        return False


class BasePoFormat(TTKitFormat, BilingualUpdateMixin):
    loader = pofile

    def is_valid(self):
        result = super().is_valid()
        if not result:
            return False

        # Avoid empty files with possibly syntax errors
        # This can be removed once https://github.com/translate/translate/pull/3912
        # is merged and relased in the Translate Toolkit
        return bool(self.store.units)

    def get_plural(self, language):
        """Return matching plural object."""
        from weblate.lang.models import Plural

        header = self.store.parseheader()
        try:
            number, formula = Plural.parse_plural_forms(header["Plural-Forms"])
        except (ValueError, KeyError):
            return super().get_plural(language)

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

    @classmethod
    def untranslate_store(cls, store, language, fuzzy=False):
        """Remove translations from Translate Toolkit store."""
        super().untranslate_store(store, language, fuzzy)
        plural = language.plural

        store.updateheader(
            last_translator="Automatically generated",
            plural_forms=plural.plural_form,
            language_team="none",
        )

    def update_header(self, **kwargs):
        """Update store header if available."""
        kwargs["x_generator"] = "Weblate {0}".format(weblate.VERSION)

        # Adjust Content-Type header if needed
        header = self.store.parseheader()
        if (
            "Content-Type" not in header
            or "charset=CHARSET" in header["Content-Type"]
            or "charset=ASCII" in header["Content-Type"]
        ):
            kwargs["Content_Type"] = "text/plain; charset=UTF-8"

        self.store.updateheader(**kwargs)

    @classmethod
    def do_bilingual_update(cls, in_file: str, out_file: str, template: str, **kwargs):
        """Wrapper around msgmerge."""
        args = [
            "--output-file",
            out_file,
            in_file,
            template,
        ]
        if "args" in kwargs:
            args = kwargs["args"] + args
        else:
            args = ["--previous"] + args

        cmd = ["msgmerge"] + args
        try:
            result = subprocess.run(
                cmd,
                env=get_clean_env(),
                cwd=os.path.dirname(out_file),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                universal_newlines=True,
            )
            # The warnings can cause corruption (for example in case
            # PO file header is missing ASCII encoding is assumed)
            if "warning:" in result.stderr:
                raise UpdateError(" ".join(cmd), result.stderr)
        except (OSError, subprocess.CalledProcessError) as error:
            report_error(cause="Failed msgmerge")
            raise UpdateError(" ".join(cmd), getattr(error, "output", str(error)))


class PoFormat(BasePoFormat):
    name = _("gettext PO file")
    format_id = "po"
    monolingual = False
    autoload = ("*.po", "*.pot")
    unit_class = PoUnit

    @classmethod
    def get_new_file_content(cls):
        """Empty PO file content."""
        return b""


class PoMonoFormat(BasePoFormat):
    name = _("gettext PO file (monolingual)")
    format_id = "po-mono"
    monolingual = True
    autoload = ()
    new_translation = (
        'msgid ""\n'
        'msgstr "X-Generator: Weblate\\n'
        "MIME-Version: 1.0\\n"
        "Content-Type: text/plain; charset=UTF-8\\n"
        'Content-Transfer-Encoding: 8bit"'
    )
    unit_class = PoMonoUnit


class TSFormat(TTKitFormat):
    name = _("Qt Linguist translation file")
    format_id = "ts"
    loader = tsfile
    autoload = ("*.ts",)
    unit_class = TSUnit

    @classmethod
    def untranslate_store(cls, store, language, fuzzy=False):
        """Remove translations from Translate Toolkit store."""
        # We need to mark all units as fuzzy to get
        # type="unfinished" on empty strings, which are otherwise
        # treated as translated same as source
        super().untranslate_store(store, language, True)


class XliffFormat(TTKitFormat):
    name = _("XLIFF translation file")
    format_id = "xliff"
    loader = xlifffile
    autoload = ("*.xlf", "*.xliff")
    unit_class = XliffUnit
    language_format = "bcp"

    def create_unit(self, key, source):
        unit = super().create_unit(key, source)
        unit.marktranslated()
        unit.markapproved(False)
        return unit


class PoXliffFormat(XliffFormat):
    name = _("XLIFF translation file with PO extensions")
    format_id = "poxliff"
    autoload = ("*.poxliff",)
    loader = PoXliffFile


class PropertiesBaseFormat(TTKitFormat):
    unit_class = PropertiesUnit

    def is_valid(self):
        result = super().is_valid()
        if not result:
            return False

        # Accept emty file, but reject file without a delimiter.
        # Translate Toolkit happily parses anything into a property
        # even if there is no delimiter used in the line.
        return not self.store.units or self.store.units[0].delimiter

    @staticmethod
    def mimetype():
        """Return most common media type for format."""
        # Properties files do not expose mimetype
        return "text/plain"

    def construct_unit(self, source):
        return self.store.UnitClass(source, personality=self.store.personality.name)


class StringsFormat(PropertiesBaseFormat):
    name = _("iOS strings")
    format_id = "strings"
    loader = ("properties", "stringsfile")
    new_translation = "\n".encode("utf-16")
    autoload = ("*.strings",)
    language_format = "bcp"


class StringsUtf8Format(StringsFormat):
    name = _("iOS strings (UTF-8)")
    format_id = "strings-utf8"
    loader = ("properties", "stringsutf8file")
    new_translation = "\n"


class PropertiesUtf8Format(PropertiesBaseFormat):
    name = _("Java Properties (UTF-8)")
    format_id = "properties-utf8"
    loader = ("properties", "javautf8file")
    new_translation = "\n"
    language_format = "java"


class PropertiesUtf16Format(PropertiesUtf8Format):
    name = _("Java Properties (UTF-16)")
    format_id = "properties-utf16"
    loader = ("properties", "javafile")
    language_format = "java"

    @classmethod
    def fixup(cls, store):
        """Force encoding.

        Translate Toolkit autodetection might fail in some cases.
        """
        store.encoding = "utf-16"


class PropertiesFormat(PropertiesUtf8Format):
    name = _("Java Properties (ISO 8859-1)")
    format_id = "properties"
    loader = ("properties", "javafile")
    autoload = ("*.properties",)
    language_format = "java"

    @classmethod
    def fixup(cls, store):
        """Force encoding.

        Java properties need to be ISO 8859-1, but Translate Toolkit converts them to
        UTF-8.
        """
        store.encoding = "iso-8859-1"


class JoomlaFormat(PropertiesBaseFormat):
    name = _("Joomla Language File")
    format_id = "joomla"
    loader = ("properties", "joomlafile")
    monolingual = True
    new_translation = "\n"
    autoload = ("*.ini",)


class GWTFormat(StringsFormat):
    name = _("GWT Properties")
    format_id = "gwt"
    loader = ("properties", "gwtfile")
    new_translation = "\n"


class PhpFormat(TTKitFormat):
    name = _("PHP strings")
    format_id = "php"
    loader = ("php", "phpfile")
    new_translation = "<?php\n"
    autoload = ("*.php",)
    unit_class = PHPUnit

    @staticmethod
    def mimetype():
        """Return most common media type for format."""
        return "text/x-php"

    @staticmethod
    def extension():
        """Return most common file extension for format."""
        return "php"


class LaravelPhpFormat(PhpFormat):
    name = _("Laravel PHP strings")
    format_id = "laravel"
    loader = ("php", "LaravelPHPFile")


class RESXFormat(TTKitFormat):
    name = _(".NET resource file")
    format_id = "resx"
    loader = RESXFile
    monolingual = True
    unit_class = RESXUnit
    new_translation = RESXFile.XMLskeleton
    autoload = ("*.resx",)


class AndroidFormat(TTKitFormat):
    name = _("Android String Resource")
    format_id = "aresource"
    loader = ("aresource", "AndroidResourceFile")
    monolingual = True
    unit_class = MonolingualIDUnit
    new_translation = '<?xml version="1.0" encoding="utf-8"?>\n<resources></resources>'
    autoload = ("strings*.xml", "values*.xml")
    language_format = "android"


class JSONFormat(TTKitFormat):
    name = _("JSON file")
    format_id = "json"
    loader = ("jsonl10n", "JsonFile")
    unit_class = MonolingualSimpleUnit
    autoload = ("*.json",)
    new_translation = "{}\n"

    @staticmethod
    def mimetype():
        """Return most common media type for format."""
        return "application/json"

    @staticmethod
    def extension():
        """Return most common file extension for format."""
        return "json"


class JSONNestedFormat(JSONFormat):
    name = _("JSON nested structure file")
    format_id = "json-nested"
    loader = ("jsonl10n", "JsonNestedFile")
    autoload = ()


class WebExtensionJSONFormat(JSONFormat):
    name = _("WebExtension JSON file")
    format_id = "webextension"
    loader = ("jsonl10n", "WebExtensionJsonFile")
    monolingual = True
    autoload = ("messages*.json",)
    unit_class = WebExtensionJSONUnit


class I18NextFormat(JSONFormat):
    name = _("i18next JSON file")
    format_id = "i18next"
    loader = ("jsonl10n", "I18NextFile")
    autoload = ()
    check_flags = ("i18next-interpolation",)


class GoI18JSONFormat(JSONFormat):
    name = _("go-i18n JSON file")
    format_id = "go-i18n-json"
    loader = ("jsonl10n", "GoI18NJsonFile")
    autoload = ()


class ARBFormat(JSONFormat):
    name = _("ARB file")
    format_id = "arb"
    loader = ("jsonl10n", "ARBJsonFile")
    autoload = ("*.arb",)
    unit_class = ARBJSONUnit


class CSVFormat(TTKitFormat):
    name = _("CSV file")
    format_id = "csv"
    loader = ("csvl10n", "csvfile")
    unit_class = CSVUnit
    autoload = ("*.csv",)
    encoding = "auto"

    def __init__(
        self, storefile, template_store=None, language_code=None, is_template=False
    ):
        super().__init__(storefile, template_store, language_code, is_template)
        # Remove template if the file contains source, this is needed
        # for import, but probably usable elsewhere as well
        if "source" in self.store.fieldnames and not isinstance(
            template_store, CSVFormat
        ):
            self.template_store = None

    @staticmethod
    def mimetype():
        """Return most common media type for format."""
        return "text/csv"

    @staticmethod
    def extension():
        """Return most common file extension for format."""
        return "csv"

    @classmethod
    def parse_store(cls, storefile):
        """Parse the store."""
        storeclass = cls.get_class()

        # Did we get file or filename?
        if not hasattr(storefile, "read"):
            storefile = open(storefile, "rb")

        # Read content for fixups
        content = storefile.read()
        storefile.close()

        # Parse file
        store = storeclass()
        store.parse(content)
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

        # Check if the file is not two column only
        if len(header) != 2:
            return store

        return cls.parse_simple_csv(content, storefile)

    @classmethod
    def parse_simple_csv(cls, content, storefile):
        storeclass = cls.get_class()
        result = storeclass(fieldnames=["source", "target"], encoding=cls.encoding)
        result.parse(content)
        result.fileobj = storefile
        filename = getattr(storefile, "name", getattr(storefile, "filename", None))
        if filename:
            result.filename = filename
        return result


class CSVSimpleFormat(CSVFormat):
    name = _("Simple CSV file")
    format_id = "csv-simple"
    autoload = ("*.txt",)
    encoding = "auto"

    @staticmethod
    def extension():
        """Return most common file extension for format."""
        return "csv"

    @classmethod
    def parse_store(cls, storefile):
        """Parse the store."""
        # Did we get file or filename?
        if not hasattr(storefile, "read"):
            storefile = open(storefile, "rb")

        return cls.parse_simple_csv(storefile.read(), storefile)


class CSVSimpleFormatISO(CSVSimpleFormat):
    name = _("Simple CSV file (ISO-8859-1)")
    format_id = "csv-simple-iso"
    encoding = "iso-8859-1"
    autoload = ()


class YAMLFormat(TTKitFormat):
    name = _("YAML file")
    format_id = "yaml"
    loader = ("yaml", "YAMLFile")
    unit_class = MonolingualSimpleUnit
    autoload = ("*.pyml",)
    new_translation = "{}\n"

    @staticmethod
    def mimetype():
        """Return most common media type for format."""
        return "text/yaml"

    @staticmethod
    def extension():
        """Return most common file extension for format."""
        return "yml"


class RubyYAMLFormat(YAMLFormat):
    name = _("Ruby YAML file")
    format_id = "ruby-yaml"
    loader = ("yaml", "RubyYAMLFile")
    autoload = ("*.ryml", "*.yml", "*.yaml")


class DTDFormat(TTKitFormat):
    name = _("DTD file")
    format_id = "dtd"
    loader = ("dtd", "dtdfile")
    autoload = ("*.dtd",)
    unit_class = MonolingualSimpleUnit
    new_translation = "\n"

    @staticmethod
    def mimetype():
        """Return most common media type for format."""
        return "application/xml-dtd"

    @staticmethod
    def extension():
        """Return most common file extension for format."""
        return "dtd"

    @property
    def all_store_units(self):
        """Wrapper for all store unit filtering out null."""
        return (unit for unit in self.store.units if not unit.isnull())


class SubtitleUnit(MonolingualIDUnit):
    @cached_property
    def source(self):
        return self.template.source

    @cached_property
    def target(self):
        """Return target string from a Translate Toolkit unit."""
        if self.unit is None:
            return ""
        return get_string(self.unit.source)

    def is_translated(self):
        """Check whether unit is translated."""
        return bool(self.target)


class SubRipFormat(TTKitFormat):
    name = _("SubRip subtitle file")
    format_id = "srt"
    loader = ("subtitles", "SubRipFile")
    unit_class = SubtitleUnit
    autoload = ("*.srt",)
    monolingual = True

    @staticmethod
    def mimetype():
        """Return most common media type for format."""
        return "text/plain"


class MicroDVDFormat(SubRipFormat):
    name = _("MicroDVD subtitle file")
    format_id = "sub"
    loader = ("subtitles", "MicroDVDFile")
    autoload = ("*.sub",)


class AdvSubStationAlphaFormat(SubRipFormat):
    name = _("Advanced SubStation Alpha subtitle file")
    format_id = "ass"
    loader = ("subtitles", "AdvSubStationAlphaFile")
    autoload = ("*.ass",)


class SubStationAlphaFormat(SubRipFormat):
    name = _("SubStation Alpha subtitle file")
    format_id = "ssa"
    loader = ("subtitles", "SubStationAlphaFile")
    autoload = ("*.ssa",)


class FlatXMLFormat(TTKitFormat):
    name = _("Flat XML file")
    format_id = "flatxml"
    loader = ("flatxml", "FlatXMLFile")
    monolingual = True
    unit_class = FlatXMLUnit
    new_translation = '<?xml version="1.0" encoding="utf-8"?>\n<root></root>'


class INIFormat(TTKitFormat):
    name = _("INI file")
    format_id = "ini"
    loader = ("ini", "inifile")
    monolingual = True
    unit_class = INIUnit
    new_translation = "\n"

    @staticmethod
    def mimetype():
        """Return most common media type for format."""
        # INI files do not expose mimetype
        return "text/plain"

    @classmethod
    def extension(cls):
        """Return most common file extension for format."""
        # INI files do not expose extension
        return "ini"

    @classmethod
    def load(cls, storefile):
        store = super().load(storefile)
        # Adjust store to have translations
        for unit in store.units:
            unit.target = unit.source
            unit.rich_target = unit.rich_source
        return store

    def create_unit(self, key, source):
        unit = super().create_unit(key, source)
        unit.location = key
        return unit


class InnoSetupINIFormat(INIFormat):
    name = _("InnoSetup INI file")
    format_id = "islu"
    loader = ("ini", "inifile")

    @classmethod
    def extension(cls):
        """Return most common file extension for format."""
        # INI files do not expose extension
        return "islu"

    @staticmethod
    def get_class_kwargs():
        return {"dialect": "inno"}
