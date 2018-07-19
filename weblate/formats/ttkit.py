# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

import csv
import importlib
import re

from django.utils.translation import ugettext_lazy as _

import six

from translate.storage.po import pounit, pofile
from translate.storage.poheader import default_header
from translate.storage.ts2 import tsfile, tsunit
from translate.storage.xliff import xlifffile, ID_SEPARATOR
from translate.storage.poxliff import PoXliffFile
from translate.storage.resx import RESXFile

from weblate.formats.base import FileUnit, FileFormat

from weblate.trans.util import get_string, join_plural


FLAGS_RE = re.compile(r'\b[-\w:]+\b')
LOCATIONS_RE = re.compile(r'^([+-]|.*, [+-]|.*:[+-])')
SUPPORTS_FUZZY = (pounit, tsunit)


class ParseError(Exception):
    """Generic error for parsing."""


class PoUnit(FileUnit):
    """Wrapper for Gettext PO unit"""
    def mark_fuzzy(self, fuzzy):
        """Set fuzzy flag on translated unit."""
        super(PoUnit, self).mark_fuzzy(fuzzy)
        if not fuzzy:
            self.unit.prev_msgid = []
            self.unit.prev_msgid_plural = []
            self.unit.prev_msgctxt = []


class XliffUnit(FileUnit):
    """Wrapper unit for XLIFF

    XLIFF is special in ttkit - it uses locations for what
    is context in other formats.
    """

    def get_context(self):
        """Return context of message."""
        return self.mainunit.getid().replace(ID_SEPARATOR, '///')

    def get_locations(self):
        """Return comma separated list of locations."""
        return ''

    def get_flags(self):
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
        if self.unit is None:
            return False
        return bool(self.unit.target)

    def is_fuzzy(self, fallback=False):
        """Check whether unit needs edit.

        The isfuzzy on Xliff is really messing up approved flag with fuzzy
        and leading to various problems. That's why we completely ignore it.
        """
        return fallback

    def mark_fuzzy(self, fuzzy):
        """Set fuzzy flag on translated unit.

        We ignore this for now."""
        return


class MonolingualIDUnit(FileUnit):
    def get_context(self):
        if self.template is not None:
            return self.template.getid()
        return self.mainunit.getcontext()


class TSUnit(MonolingualIDUnit):
    def get_source(self):
        if self.template is None and self.mainunit.hasplural():
            # Need to apply special magic for plurals here
            # as there is no singlular/plural in the source string
            source = self.unit.source
            return join_plural([
                source,
                source.replace('(s)', 's'),
            ])
        return super(TSUnit, self).get_source()

    def get_locations(self):
        """Return comma separated list of locations."""
        result = super(TSUnit, self).get_locations()
        # Do not try to handle relative locations in Qt TS, see
        # http://doc.qt.io/qt-5/linguist-ts-file-format.html
        if LOCATIONS_RE.match(result):
            return ''
        return result

    def get_target(self):
        """Return target string from a ttkit unit."""
        if self.unit is None:
            return ''
        if not self.unit.isreview() and not self.unit.istranslated():
            # For Qt ts, empty translated string means source should be used
            return self.get_source()
        return super(TSUnit, self).get_target()

    def is_translated(self):
        """Check whether unit is translated."""
        if self.unit is None:
            return False
        # For Qt ts, empty translated string means source should be used
        return not self.unit.isreview() or self.unit.istranslated()


class MonolingualSimpleUnit(MonolingualIDUnit):
    def get_locations(self):
        return ''

    def get_source(self):
        if self.template is None:
            return self.mainunit.getid().lstrip('.')
        return get_string(self.template.target)

    def is_translatable(self):
        return True


class CSVUnit(MonolingualSimpleUnit):
    def get_context(self):
        # Needed to avoid translate-toolkit construct ID
        # as context\04source
        if self.template is not None:
            if self.template.id:
                return self.template.id
            elif self.template.context:
                return self.template.context
            return self.template.getid()
        return self.mainunit.getcontext()

    def get_source(self):
        # Needed to avoid translate-toolkit construct ID
        # as context\04source
        if self.template is None:
            return get_string(self.mainunit.source)
        return super(CSVUnit, self).get_source()


class RESXUnit(FileUnit):
    def get_locations(self):
        return ''

    def get_context(self):
        if self.template is not None:
            return self.template.getid()
        return self.unit.getid()

    def get_source(self):
        if self.template is None:
            return self.mainunit.getid()
        return get_string(self.template.target)


class PHPUnit(FileUnit):
    def get_locations(self):
        return ''

    def get_source(self):
        if self.template is not None:
            return self.template.source
        return self.unit.getid()

    def get_target(self):
        if self.unit is None:
            return ''
        return self.unit.source


class PoFormat(FileFormat):
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

    def merge_header(self, otherstore):
        """Try to merge headers"""
        if (not hasattr(self.store, 'updateheader') or
                not hasattr(otherstore.store, 'parseheader')):
            return
        values = otherstore.store.parseheader()
        skip_list = (
            'Plural-Forms',
            'Content-Type',
            'Content-Transfer-Encoding',
            'MIME-Version',
            'Language',
        )
        update = {}
        for key in values:
            if key in skip_list:
                continue
            if values[key] == default_header.get(key):
                continue
            update[key] = values[key]

        self.store.updateheader(**update)

        header = self.store.header()
        newheader = otherstore.store.header()
        if not header or not newheader:
            return

        header.removenotes()
        header.addnote(newheader.getnotes())


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


class TSFormat(FileFormat):
    name = _('Qt Linguist Translation File')
    format_id = 'ts'
    loader = tsfile
    autoload = ('.ts',)
    unit_class = TSUnit


class XliffFormat(FileFormat):
    name = _('XLIFF Translation File')
    format_id = 'xliff'
    loader = xlifffile
    autoload = ('.xlf', '.xliff')
    unit_class = XliffUnit

    def find_matching(self, template_unit):
        """Find matching store unit for template"""
        return self._find_unit_mono(
            template_unit.source,
            self.store
        )

    def find_unit(self, context, source):
        return super(XliffFormat, self).find_unit(
            context.replace('///', ID_SEPARATOR), source
        )

    def _find_unit_bilingual(self, context, source):
        return (
            self.unit_class(self._find_unit_mono(context, self.store)),
            False
        )


class PoXliffFormat(XliffFormat):
    name = _('XLIFF Translation File with PO extensions')
    format_id = 'poxliff'
    autoload = ('.poxliff',)
    loader = PoXliffFile


class StringsFormat(FileFormat):
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


class PropertiesUtf8Format(FileFormat):
    name = _('Java Properties (UTF-8)')
    format_id = 'properties-utf8'
    loader = ('properties', 'javautf8file')
    monolingual = True
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
        """Fixe encoding.

        Java properties need to be iso-8859-1, but
        ttkit converts them to utf-8.

        This will be fixed in translate-toolkit 1.14.0, we could then
        merge utf-16 and this one as the encoding detection should do
        the correct magic then.
        """
        store.encoding = 'iso-8859-1'
        return store


class JoomlaFormat(FileFormat):
    name = _('Joomla Language File')
    format_id = 'joomla'
    loader = ('properties', 'joomlafile')
    monolingual = True
    new_translation = '\n'
    autoload = ('.ini',)


class PhpFormat(FileFormat):
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


class RESXFormat(FileFormat):
    name = _('.Net resource file')
    format_id = 'resx'
    loader = RESXFile
    monolingual = True
    unit_class = RESXUnit
    new_translation = RESXFile.XMLskeleton
    autoload = ('.resx',)


class AndroidFormat(FileFormat):
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
        elif code == 'zh_Hant':
            return 'zh-rTW'
        return code.replace('_', '-r')


class JSONFormat(FileFormat):
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


class CSVFormat(FileFormat):
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

        if not isinstance(content, six.string_types) and six.PY3:
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
        if six.PY3:
            result.parse(content.encode('utf-8'))
        else:
            result.parse(content)
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


class YAMLFormat(FileFormat):
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


class DTDFormat(FileFormat):
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


class WindowsRCFormat(FileFormat):
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
