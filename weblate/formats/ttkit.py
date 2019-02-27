# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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
"""translate-toolkit based file format wrappers."""

from __future__ import unicode_literals

import importlib
import inspect
import re

from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from lxml.etree import XMLSyntaxError

import six

from translate.misc import quote
from translate.misc.multistring import multistring
from translate.storage.base import TranslationStore
from translate.storage.csvl10n import csv
from translate.storage.lisa import LISAfile
from translate.storage.po import pofile, pounit
from translate.storage.ts2 import tsfile, tsunit
from translate.storage.xliff import xlifffile, ID_SEPARATOR
from translate.storage.poxliff import PoXliffFile
from translate.storage.resx import RESXFile

import weblate

from weblate.formats.base import TranslationUnit, TranslationFormat

from weblate.trans.util import (
    get_string, join_plural, xliff_string_to_rich, rich_to_xliff_string
)

from weblate.utils.errors import report_error


LOCATIONS_RE = re.compile(r'^([+-]|.*, [+-]|.*:[+-])')
SUPPORTS_FUZZY = (pounit, tsunit)


class TTKitUnit(TranslationUnit):
    @cached_property
    def locations(self):
        """Return comma separated list of locations."""
        return ', '.join(
            [x for x in self.mainunit.getlocations() if x is not None]
        )

    @cached_property
    def source(self):
        """Return source string from a ttkit unit."""
        if self.template is not None:
            return get_string(self.template.target)
        return get_string(self.unit.source)

    @cached_property
    def target(self):
        """Return target string from a ttkit unit."""
        if self.unit is None:
            return ''
        return get_string(self.unit.target)

    @cached_property
    def context(self):
        """Return context of message.

        In some cases we have to use ID here to make all backends consistent.
        """
        return self.mainunit.getcontext()

    @cached_property
    def comments(self):
        """Return comments (notes) from units."""
        comment = ''

        if self.unit is not None:
            comment = self.unit.getnotes()

        if self.template is not None:
            # Avoid duplication in case template has same comments
            template_comment = self.template.getnotes()
            if template_comment != comment:
                comment = template_comment + ' ' + comment

        return comment

    def is_translated(self):
        """Check whether unit is translated."""
        if self.unit is None:
            return False
        return self.unit.istranslated()

    def is_fuzzy(self, fallback=False):
        """Check whether unit needs edit."""
        if self.unit is None:
            return fallback
        # Most of the formats do not support this, but they
        # happily return False
        if isinstance(self.unit, SUPPORTS_FUZZY):
            return self.unit.isfuzzy()
        return fallback

    def is_obsolete(self):
        """Check whether unit is marked as obsolete in backend."""
        return self.mainunit.isobsolete()

    def is_translatable(self):
        """Check whether unit is translatable.

        For some reason, blank string does not mean non translatable
        unit in some formats (XLIFF), so lets skip those as well.
        """
        return self.mainunit.istranslatable() and not self.mainunit.isblank()

    def set_target(self, target):
        """Set translation unit target."""
        if 'target' in self.__dict__:
            del self.__dict__['target']
        if isinstance(target, list):
            target = multistring(target)
        self.unit.target = target

    def mark_fuzzy(self, fuzzy):
        """Set fuzzy flag on translated unit."""
        if 'flags' in self.__dict__:
            del self.__dict__['flags']
        self.unit.markfuzzy(fuzzy)

    def mark_approved(self, value):
        """Set approved flag on translated unit."""
        if 'flags' in self.__dict__:
            del self.__dict__['flags']
        if hasattr(self.unit, 'markapproved'):
            self.unit.markapproved(value)


class KeyValueUnit(TTKitUnit):
    @cached_property
    def source(self):
        """Return source string from a ttkit unit."""
        if self.template is not None:
            return self.template.value
        return self.unit.name

    @cached_property
    def target(self):
        """Return target string from a ttkit unit."""
        if self.unit is None:
            return ''
        return self.unit.value

    @cached_property
    def context(self):
        """Return context of message.

        In some cases we have to use ID here to make all backends consistent.
        """
        context = super(KeyValueUnit, self).context
        if not context:
            return self.mainunit.getid()
        return context

    def is_translated(self):
        """Check whether unit is translated."""
        if self.unit is None:
            return False
        # The hasattr check here is needed for merged storages
        # where template is different kind than translations
        if hasattr(self.unit, 'value'):
            return not self.unit.isfuzzy() and self.unit.value != ''
        return self.unit.istranslated()

    def set_target(self, target):
        """Set translation unit target."""
        super(KeyValueUnit, self).set_target(target)
        # Propagate to value so that is_translated works correctly
        self.unit.value = self.unit.translation


class TTKitFormat(TranslationFormat):
    unit_class = TTKitUnit
    loader = ('', '')
    new_translation = None

    def __init__(self, storefile, template_store=None, language_code=None):
        super(TTKitFormat, self).__init__(
            storefile, template_store, language_code
        )
        # Set language (needed for some which do not include this)
        if (language_code is not None and
                self.store.gettargetlanguage() is None):
            self.store.settargetlanguage(
                self.get_language_code(language_code)
            )

    @staticmethod
    def serialize(store):
        """Serialize given ttkit store"""
        return bytes(store)

    @classmethod
    def fixup(cls, store):
        """Perform optional fixups on store."""
        return store

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
        if '.' not in module_name:
            module_name = 'translate.storage.{0}'.format(module_name)
        module = importlib.import_module(module_name)

        # Get the class
        return getattr(module, class_name)

    @classmethod
    def parse_store(cls, storefile):
        """Parse the store."""
        storeclass = cls.get_class()

        # Parse file
        store = storeclass.parsefile(storefile)

        # Apply possible fixups and return
        return cls.fixup(store)

    def add_unit(self, ttkit_unit):
        """Add new unit to underlaying store."""
        if isinstance(self.store, LISAfile):
            # LISA based stores need to know this
            self.store.addunit(ttkit_unit, new=True)
        else:
            self.store.addunit(ttkit_unit)

    def save_content(self, handle):
        """Stores content to file."""
        self.store.serialize(handle)

    def save(self):
        """Save underlaying store to disk."""
        self.save_atomic(self.storefile, self.save_content)

    @property
    def mimetype(self):
        """Return most common mime type for format."""
        return self.store.Mimetypes[0]

    @property
    def extension(self):
        """Return most common file extension for format."""
        return self.store.Extensions[0]

    @classmethod
    def is_valid(cls, store):
        """Check whether store seems to be valid.

        In some cases ttkit happily "parses" the file, even though it
        really did not do so (eg. Gettext parser on random text file).
        """
        if store is None:
            return False

        if cls.monolingual is False and not store.units:
            return False

        return True

    def create_unit(self, key, source):
        unit = self.store.UnitClass(source)
        unit.setid(key)
        unit.source = key
        unit.target = source
        return unit

    @classmethod
    def untranslate_store(cls, store, language, fuzzy=False):
        """Remove translations from ttkit store"""
        store.settargetlanguage(
            cls.get_language_code(language.code)
        )
        plural = language.plural

        for unit in store.units:
            if unit.istranslatable():
                if hasattr(unit, 'markapproved'):
                    # Xliff only
                    unit.markapproved(False)
                else:
                    unit.markfuzzy(fuzzy)
                if unit.hasplural():
                    unit.target = [''] * plural.number
                else:
                    unit.target = ''

    @classmethod
    def create_new_file(cls, filename, language, base):
        """Handle creation of new translation file."""
        if base:
            # Parse file
            store = cls.parse_store(base)
            cls.untranslate_store(store, language)
            store.savefile(filename)
        elif cls.new_translation is None:
            raise ValueError('Not supported')
        else:
            with open(filename, 'w') as output:
                output.write(cls.new_translation)

    @classmethod
    def is_valid_base_for_new(cls, base, monolingual):
        """Check whether base is valid."""
        if not base:
            return monolingual and cls.new_translation is not None
        try:
            cls.parse_store(base)
            return True
        except Exception as error:
            report_error(error)
            return False


class PropertiesUnit(KeyValueUnit):
    """Wrapper for properties based units."""
    @cached_property
    def locations(self):
        """Return comma separated list of locations."""
        return ''

    @cached_property
    def source(self):
        # Need to decode property encoded string
        return quote.propertiesdecode(
            super(PropertiesUnit, self).source
        )

    @cached_property
    def target(self):
        """Return target string from a ttkit unit."""
        if self.unit is None:
            return ''
        # Need to decode property encoded string
        # This is basically stolen from
        # translate.storage.properties.propunit.gettarget
        # which for some reason does not return translation
        value = quote.propertiesdecode(self.unit.value)
        value = re.sub('\\\\ ', ' ', value)
        return value


class PoUnit(TTKitUnit):
    """Wrapper for Gettext PO unit"""
    def mark_fuzzy(self, fuzzy):
        """Set fuzzy flag on translated unit."""
        super(PoUnit, self).mark_fuzzy(fuzzy)
        if not fuzzy:
            self.unit.prev_msgid = []
            self.unit.prev_msgid_plural = []
            self.unit.prev_msgctxt = []

    @cached_property
    def context(self):
        """Return context of message.

        In some cases we have to use ID here to make all backends consistent.
        """
        if self.template is not None:
            # Monolingual PO files
            return self.template.source or self.template.getcontext()
        return super(PoUnit, self).context

    @cached_property
    def flags(self):
        """Return flags (typecomments) from units."""
        if self.template is not None:
            return self.reformat_flags(self.template.typecomments)
        return self.reformat_flags(self.unit.typecomments)

    @cached_property
    def previous_source(self):
        """Return previous message source if there was any."""
        if not self.is_fuzzy():
            return ''
        return get_string(self.unit.prev_source)


class XliffUnit(TTKitUnit):
    """Wrapper unit for XLIFF

    XLIFF is special in ttkit - it uses locations for what
    is context in other formats.
    """
    FUZZY_STATES = frozenset((
        'new', 'needs-translation', 'needs-adaptation', 'needs-l10n'
    ))

    @cached_property
    def source(self):
        """Return source string from a ttkit unit."""

        if self.template is not None:
            # Use target if set, otherwise fall back to source
            if self.template.target:
                return rich_to_xliff_string(self.template.rich_target)
            return rich_to_xliff_string(self.template.rich_source)
        return rich_to_xliff_string(self.unit.rich_source)

    @cached_property
    def target(self):
        """Return target string from a ttkit unit."""
        if self.unit is None:
            return ''

        # Use source for monolingual files if target is not set
        if self.template is not None and not self.template.target:
            return rich_to_xliff_string(self.template.rich_source)

        if self.unit.target is None:
            return ''

        return rich_to_xliff_string(self.unit.rich_target)

    def set_target(self, target):
        """Set translation unit target."""
        try:
            converted = xliff_string_to_rich(target)
        except XMLSyntaxError:
            converted = target
        # Use source for monolingual files if target is not set
        if self.template is not None and not self.template.target:
            self.unit.rich_source = converted
        else:
            self.unit.rich_target = converted

    @cached_property
    def xliff_node(self):
        return self.unit.getlanguageNode(lang=None, index=1)

    @property
    def xliff_state(self):
        if self.xliff_node is None:
            return None
        return self.xliff_node.get('state', None)

    @cached_property
    def context(self):
        """Return context of message.

        Use resname if available as it usually is more interesting
        for translator than id."""
        resname = self.mainunit.xmlelement.get('resname')
        if resname:
            return resname
        return self.mainunit.getid().replace(ID_SEPARATOR, '///')

    @cached_property
    def locations(self):
        """Return comma separated list of locations."""
        return ''

    @cached_property
    def flags(self):
        """Return flags from unit.

        We currently extract maxwidth attribute.
        """
        maxwidth = None
        if self.unit is not None:
            maxwidth = self.unit.xmlelement.get('maxwidth')
        if not maxwidth and self.template is not None:
            maxwidth = self.template.xmlelement.get('maxwidth')

        if maxwidth:
            return 'max-length:{0}'.format(maxwidth)

        return ''

    def is_translated(self):
        """Check whether unit is translated.

        We replace translate-toolkit logic here as the isfuzzy
        is pretty much wrong there, see is_fuzzy docs.
        """
        return bool(self.target)

    def is_fuzzy(self, fallback=False):
        """Check whether unit needs edit.

        The isfuzzy on Xliff is really messing up approved flag with fuzzy
        and leading to various problems.

        That's why we handle it on our own.
        """
        return self.target and self.xliff_state in self.FUZZY_STATES

    def mark_fuzzy(self, fuzzy):
        """Set fuzzy flag on translated unit.

        We handle this on our own."""
        if fuzzy:
            self.xliff_node.set('state', 'needs-translation')
        elif self.xliff_state:
            self.xliff_node.set('state', 'translated')
        return

    def is_approved(self, fallback=False):
        """Check whether unit is appoved."""
        if self.unit is None:
            return fallback
        if hasattr(self.unit, 'isapproved'):
            return self.unit.isapproved()
        return fallback

    def mark_approved(self, value):
        super(XliffUnit, self).mark_approved(value)
        if self.xliff_state:
            self.xliff_node.set('state', 'final' if value else 'translated')


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
            return join_plural([
                source,
                source.replace('(s)', 's'),
            ])
        return super(TSUnit, self).source

    @cached_property
    def locations(self):
        """Return comma separated list of locations."""
        result = super(TSUnit, self).locations
        # Do not try to handle relative locations in Qt TS, see
        # http://doc.qt.io/qt-5/linguist-ts-file-format.html
        if LOCATIONS_RE.match(result):
            return ''
        return result

    @cached_property
    def target(self):
        """Return target string from a ttkit unit."""
        if self.unit is None:
            return ''
        if not self.unit.isreview() and not self.unit.istranslated():
            # For Qt ts, empty translated string means source should be used
            return self.source
        return super(TSUnit, self).target

    def is_translated(self):
        """Check whether unit is translated."""
        if self.unit is None:
            return False
        # For Qt ts, empty translated string means source should be used
        return not self.unit.isreview() or self.unit.istranslated()


class MonolingualSimpleUnit(MonolingualIDUnit):
    @cached_property
    def locations(self):
        return ''

    @cached_property
    def source(self):
        if self.template is None:
            return self.mainunit.getid().lstrip('.')
        return get_string(self.template.target)

    def is_translatable(self):
        return True


class CSVUnit(MonolingualSimpleUnit):
    @cached_property
    def context(self):
        # Needed to avoid translate-toolkit construct ID
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
        # Needed to avoid translate-toolkit construct ID
        # as context\04source
        if self.template is None:
            return get_string(self.mainunit.source)
        return super(CSVUnit, self).source


class RESXUnit(TTKitUnit):
    @cached_property
    def locations(self):
        return ''

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
        return ''

    @cached_property
    def source(self):
        if self.template is not None:
            return self.template.source
        return self.unit.getid()

    @cached_property
    def target(self):
        if self.unit is None:
            return ''
        return self.unit.source


class PoFormat(TTKitFormat):
    name = _('Gettext PO file')
    format_id = 'po'
    loader = pofile
    monolingual = False
    autoload = ('.po', '.pot')
    unit_class = PoUnit

    def get_plural(self, language):
        """Return matching plural object."""
        from weblate.lang.models import Plural
        header = self.store.parseheader()
        try:
            number, equation = Plural.parse_formula(header['Plural-Forms'])
        except (ValueError, KeyError):
            return super(PoFormat, self).get_plural(language)

        # Find matching one
        for plural in language.plural_set.all():
            if plural.same_plural(number, equation):
                return plural

        # Create new one
        return Plural.objects.create(
            language=language,
            source=Plural.SOURCE_GETTEXT,
            number=number,
            equation=equation,
        )

    @classmethod
    def untranslate_store(cls, store, language, fuzzy=False):
        """Remove translations from ttkit store"""
        super(PoFormat, cls).untranslate_store(store, language, fuzzy)
        plural = language.plural

        store.updateheader(
            last_translator='Automatically generated',
            plural_forms=plural.plural_form,
            language_team='none',
        )

    def update_header(self, **kwargs):
        """Update store header if available."""
        kwargs['x_generator'] = 'Weblate {0}'.format(weblate.VERSION)

        # Adjust Content-Type header if needed
        header = self.store.parseheader()
        if ('Content-Type' not in header or
                'charset=CHARSET' in header['Content-Type'] or
                'charset=ASCII' in header['Content-Type']):
            kwargs['Content_Type'] = 'text/plain; charset=UTF-8'

        self.store.updateheader(**kwargs)


class PoMonoFormat(PoFormat):
    name = _('Gettext PO file (monolingual)')
    format_id = 'po-mono'
    monolingual = True
    new_translation = (
        'msgid ""\n'
        'msgstr "X-Generator: Weblate\\n'
        'MIME-Version: 1.0\\n'
        'Content-Type: text/plain; charset=UTF-8\\n'
        'Content-Transfer-Encoding: 8bit"'
    )


class TSFormat(TTKitFormat):
    name = _('Qt Linguist Translation File')
    format_id = 'ts'
    loader = tsfile
    autoload = ('.ts',)
    unit_class = TSUnit

    @classmethod
    def untranslate_store(cls, store, language, fuzzy=False):
        """Remove translations from ttkit store"""
        # We need to mark all units as fuzzy to get
        # type="unfinished" on empty strings, which are otherwise
        # treated as translated same as source
        super(TSFormat, cls).untranslate_store(store, language, True)


class XliffFormat(TTKitFormat):
    name = _('XLIFF Translation File')
    format_id = 'xliff'
    loader = xlifffile
    autoload = ('.xlf', '.xliff')
    unit_class = XliffUnit

    def create_unit(self, key, source):
        unit = super(XliffFormat, self).create_unit(key, source)
        unit.marktranslated()
        unit.markapproved(False)
        return unit

    @staticmethod
    def get_language_code(code):
        """Do any possible formatting needed for language code."""
        return code.replace('_', '-')


class PoXliffFormat(XliffFormat):
    name = _('XLIFF Translation File with PO extensions')
    format_id = 'poxliff'
    autoload = ('.poxliff',)
    loader = PoXliffFile


class PropertiesBaseFormat(TTKitFormat):
    unit_class = PropertiesUnit

    @classmethod
    def is_valid(cls, store):
        result = super(PropertiesBaseFormat, cls).is_valid(store)
        if not result:
            return False

        # Accept emty file, but reject file without a delimiter.
        # Translate-toolkit happily parses anything into a property
        # even if there is no delimiter used in the line.
        return not store.units or store.units[0].delimiter

    @property
    def mimetype(self):
        """Return most common mime type for format."""
        # Properties files do not expose mimetype
        return 'text/plain'


class StringsFormat(PropertiesBaseFormat):
    name = _('OS X Strings')
    format_id = 'strings'
    loader = ('properties', 'stringsfile')
    new_translation = '\n'.encode('utf-16')
    autoload = ('.strings',)

    @staticmethod
    def get_language_code(code):
        """Do any possible formatting needed for language code."""
        return code.replace('_', '-')


class StringsUtf8Format(StringsFormat):
    name = _('OS X Strings (UTF-8)')
    format_id = 'strings-utf8'
    loader = ('properties', 'stringsutf8file')
    new_translation = '\n'


class PropertiesUtf8Format(PropertiesBaseFormat):
    name = _('Java Properties (UTF-8)')
    format_id = 'properties-utf8'
    loader = ('properties', 'javautf8file')
    new_translation = '\n'


class PropertiesUtf16Format(PropertiesUtf8Format):
    name = _('Java Properties (UTF-16)')
    format_id = 'properties-utf16'
    loader = ('properties', 'javafile')


class PropertiesFormat(PropertiesUtf8Format):
    name = _('Java Properties (ISO-8859-1)')
    format_id = 'properties'
    loader = ('properties', 'javafile')
    autoload = ('.properties',)

    @classmethod
    def fixup(cls, store):
        """Force encoding.

        Java properties need to be iso-8859-1, but
        ttkit converts them to utf-8.
        """
        store.encoding = 'iso-8859-1'
        return store


class JoomlaFormat(PropertiesBaseFormat):
    name = _('Joomla Language File')
    format_id = 'joomla'
    loader = ('properties', 'joomlafile')
    monolingual = True
    new_translation = '\n'
    autoload = ('.ini',)


class PhpFormat(TTKitFormat):
    name = _('PHP strings')
    format_id = 'php'
    loader = ('php', 'phpfile')
    new_translation = '<?php\n'
    autoload = ('.php',)
    unit_class = PHPUnit

    @property
    def mimetype(self):
        """Return most common mime type for format."""
        return 'text/x-php'

    @property
    def extension(self):
        """Return most common file extension for format."""
        return 'php'


class RESXFormat(TTKitFormat):
    name = _('.Net resource file')
    format_id = 'resx'
    loader = RESXFile
    monolingual = True
    unit_class = RESXUnit
    new_translation = RESXFile.XMLskeleton
    autoload = ('.resx',)


class AndroidFormat(TTKitFormat):
    name = _('Android String Resource')
    format_id = 'aresource'
    loader = ('aresource', 'AndroidResourceFile')
    monolingual = True
    # Whitespace is ignored in this format
    check_flags = (
        'ignore-begin-space',
        'ignore-end-space',
        'ignore-begin-newline',
        'ignore-end-newline',
    )
    unit_class = MonolingualIDUnit
    new_translation = (
        '<?xml version="1.0" encoding="utf-8"?>\n<resources></resources>'
    )
    autoload = (('strings', '.xml'),)

    @staticmethod
    def get_language_code(code):
        """Do any possible formatting needed for language code."""
        # Android doesn't use Hans/Hant, but rather TW/CN variants
        if code == 'zh_Hans':
            return 'zh-rCN'
        if code == 'zh_Hant':
            return 'zh-rTW'
        sanitized = code.replace('-', '_')
        if '_' in sanitized and len(sanitized.split('_')[1]) > 2:
            return 'b+{}'.format(sanitized.replace('_', '+'))
        return sanitized.replace('_', '-r')


class JSONFormat(TTKitFormat):
    name = _('JSON file')
    format_id = 'json'
    loader = ('jsonl10n', 'JsonFile')
    unit_class = MonolingualSimpleUnit
    autoload = ('.json',)
    new_translation = '{}\n'

    @property
    def mimetype(self):
        """Return most common mime type for format."""
        return 'application/json'

    @property
    def extension(self):
        """Return most common file extension for format."""
        return 'json'


class JSONNestedFormat(JSONFormat):
    name = _('JSON nested structure file')
    format_id = 'json-nested'
    loader = ('jsonl10n', 'JsonNestedFile')


class WebExtensionJSONFormat(JSONFormat):
    name = _('WebExtension JSON file')
    format_id = 'webextension'
    loader = ('jsonl10n', 'WebExtensionJsonFile')
    monolingual = True
    autoload = (('messages', '.json'),)


class I18NextFormat(JSONFormat):
    name = _('i18next JSON file')
    format_id = 'i18next'
    loader = ('jsonl10n', 'I18NextFile')


class CSVFormat(TTKitFormat):
    name = _('CSV file')
    format_id = 'csv'
    loader = ('csvl10n', 'csvfile')
    unit_class = CSVUnit
    autoload = ('.csv',)

    def __init__(self, storefile, template_store=None, language_code=None):
        super(CSVFormat, self).__init__(
            storefile, template_store, language_code
        )
        # Remove template if the file contains source, this is needed
        # for import, but probably usable elsewhere as well
        if ('source' in self.store.fieldnames and
                not isinstance(template_store, CSVFormat)):
            self.template_store = None

    @property
    def mimetype(self):
        """Return most common mime type for format."""
        return 'text/csv'

    @property
    def extension(self):
        """Return most common file extension for format."""
        return 'csv'

    @classmethod
    def parse_store(cls, storefile):
        """Parse the store."""
        storeclass = cls.get_class()

        # Did we get file or filename?
        if not hasattr(storefile, 'read'):
            storefile = open(storefile, 'rb')

        # Read content for fixups
        content = storefile.read()
        storefile.seek(0)

        # Parse file
        store = storeclass.parsefile(storefile)

        # Did headers detection work?
        if store.fieldnames != ['location', 'source', 'target']:
            return store

        content = content.decode('utf-8')

        fileobj = csv.StringIO(content)
        storefile.close()

        # Try reading header
        reader = csv.reader(fileobj, store.dialect)
        header = next(reader)
        fileobj.close()

        # We seem to have match
        if len(header) != 2:
            return store

        result = storeclass(fieldnames=['source', 'target'])
        result.parse(content.encode('utf-8'))
        return result


class CSVSimpleFormat(CSVFormat):
    name = _('Simple CSV file')
    format_id = 'csv-simple'
    autoload = ('.txt',)
    encoding = 'auto'

    @property
    def extension(self):
        """Return most common file extension for format."""
        return 'txt'

    @classmethod
    def parse_store(cls, storefile):
        """Parse the store."""
        storeclass = cls.get_class()

        # Did we get file or filename?
        if not hasattr(storefile, 'read'):
            storefile = open(storefile, 'rb')

        result = storeclass(
            fieldnames=['source', 'target'],
            encoding=cls.encoding,
        )
        result.parse(storefile.read())
        result.fileobj = storefile
        filename = getattr(
            storefile,
            "name",
            getattr(storefile, "filename", None)
        )
        if filename:
            result.filename = filename
        return result


class CSVSimpleFormatISO(CSVSimpleFormat):
    name = _('Simple CSV file (ISO-8859-1)')
    format_id = 'csv-simple-iso'
    encoding = 'iso-8859-1'


class YAMLFormat(TTKitFormat):
    name = _('YAML file')
    format_id = 'yaml'
    loader = ('yaml', 'YAMLFile')
    unit_class = MonolingualSimpleUnit
    autoload = ('.pyml',)
    new_translation = '{}\n'

    @property
    def mimetype(self):
        """Return most common mime type for format."""
        return 'text/yaml'

    @property
    def extension(self):
        """Return most common file extension for format."""
        return 'yml'


class RubyYAMLFormat(YAMLFormat):
    name = _('Ruby YAML file')
    format_id = 'ruby-yaml'
    loader = ('yaml', 'RubyYAMLFile')
    autoload = ('.ryml', '.yml', '.yaml')


class DTDFormat(TTKitFormat):
    name = _('DTD file')
    format_id = 'dtd'
    loader = ('dtd', 'dtdfile')
    autoload = ('.dtd',)
    unit_class = MonolingualSimpleUnit
    new_translation = '\n'

    @property
    def mimetype(self):
        """Return most common mime type for format."""
        return 'application/xml-dtd'

    @property
    def extension(self):
        """Return most common file extension for format."""
        return 'dtd'

    @classmethod
    def fixup(cls, store):
        """Perform optional fixups on store."""
        # Filter out null units (those IMHO should not be exposed by ttkit)
        store.units = [u for u in store.units if not u.isnull()]
        return store


class WindowsRCFormat(TTKitFormat):
    name = _('RC file')
    format_id = 'rc'
    loader = ('rc', 'rcfile')
    autoload = ('.rc',)
    unit_class = MonolingualSimpleUnit
    can_add_unit = False

    @property
    def mimetype(self):
        """Return most common mime type for format."""
        return 'text/plain'

    @property
    def extension(self):
        """Return most common file extension for format."""
        return 'rc'

    @staticmethod
    def get_language_code(code):
        """Do any possible formatting needed for language code."""
        return code.replace('_', '-')

    @classmethod
    def get_class(cls):
        """Return class for handling this module."""
        if six.PY3:
            raise ImportError(
                'Windows RC file format is not supported on Python 3'
            )
        return importlib.import_module(
            'translate.storage.rc'
        ).rcfile
