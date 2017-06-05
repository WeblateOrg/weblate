# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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
"""File format specific behavior."""

from __future__ import unicode_literals

from io import BytesIO
import os.path
import inspect
import re
import csv
import traceback
import importlib


from django.utils.translation import ugettext_lazy as _

import six

from translate.convert import po2php
from translate.misc import quote
from translate.storage.lisa import LISAfile
from translate.storage.php import phpunit, phpfile
from translate.storage.po import pounit, pofile
from translate.storage.poheader import default_header
from translate.storage.properties import propunit, propfile
from translate.storage.ts2 import tsfile
from translate.storage.xliff import xlifffile, ID_SEPARATOR
from translate.storage.poxliff import PoXliffFile
from translate.storage.resx import RESXFile
from translate.storage import factory

from weblate.trans.util import get_string, join_plural, add_configuration_error

from weblate.utils.hash import calculate_hash

import weblate


FILE_FORMATS = {}
FILE_DETECT = []
FLAGS_RE = re.compile(r'\b[-\w:]+\b')
LOCATIONS_RE = re.compile(r'^([+-]|.*, [+-]|.*:[+-])')


class ParseError(Exception):
    """Generic error for parsing."""


class StringIOMode(BytesIO):
    """StringIO with mode attribute to make ttkit happy."""
    def __init__(self, filename, data):
        super(StringIOMode, self).__init__(data)
        self.mode = 'r'
        self.name = filename


def register_fileformat(fileformat):
    """Register fileformat in dictionary."""
    try:
        fileformat.get_class()
        FILE_FORMATS[fileformat.format_id] = fileformat
        for autoload in fileformat.autoload:
            FILE_DETECT.append((autoload, fileformat))
    except (AttributeError, ImportError):
        add_configuration_error(
            'File format: {0}'.format(fileformat.format_id),
            traceback.format_exc()
        )
    return fileformat


def detect_filename(filename):
    """Filename based format autodetection"""
    name = os.path.basename(filename)
    for autoload, storeclass in FILE_DETECT:
        if not isinstance(autoload, tuple) and name.endswith(autoload):
            return storeclass
        elif (name.startswith(autoload[0]) and
              name.endswith(autoload[1])):
            return storeclass
    return None


def try_load(filename, content, original_format, template_store):
    """Try to load file by guessing type"""
    formats = [original_format, AutoFormat]
    detected_format = detect_filename(filename)
    if detected_format is not None:
        formats.insert(0, detected_format)
    failure = Exception('Bug!')
    for file_format in formats:
        if file_format.monolingual in (True, None) and template_store:
            try:
                return file_format.parse(
                    StringIOMode(filename, content),
                    template_store
                )
            except Exception as error:
                failure = error
        if file_format.monolingual in (False, None):
            try:
                return file_format.parse(StringIOMode(filename, content))
            except Exception as error:
                failure = error

    raise failure


class FileUnit(object):
    """Wrapper for translate-toolkit unit.

    It handles ID/template based translations and other API differences.
    """

    def __init__(self, unit, template=None):
        """Create wrapper object."""
        self.unit = unit
        self.template = template
        if template is not None:
            self.mainunit = template
        else:
            self.mainunit = unit
        self.id_hash = None
        self.content_hash = None

    def get_locations(self):
        """Return comma separated list of locations."""
        # JSON, XLIFF and PHP are special in ttkit - it uses locations for what
        # is context in other formats
        if (isinstance(self.mainunit, propunit) or
                isinstance(self.mainunit, phpunit)):
            return ''
        result = ', '.join(
            [x for x in self.mainunit.getlocations() if x is not None]
        )
        # Do not try to handle relative locations in Qt TS, see
        # http://qt-project.org/doc/qt-4.8/linguist-ts-file-format.html
        if LOCATIONS_RE.match(result):
            return ''
        return result

    def reformat_flags(self, typecomments):
        """Processe flags from PO file to nicer form."""
        # Grab flags
        flags = set(FLAGS_RE.findall('\n'.join(typecomments)))

        # Discard fuzzy flag, we don't care about that one
        flags.discard('fuzzy')

        # Join into string
        return ', '.join(flags)

    def get_flags(self):
        """Return flags (typecomments) from units.

        This is Gettext (po) specific feature."""
        # Merge flags
        if hasattr(self.unit, 'typecomments'):
            return self.reformat_flags(self.unit.typecomments)
        elif hasattr(self.template, 'typecomments'):
            return self.reformat_flags(self.template.typecomments)
        else:
            return ''

    def get_comments(self):
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

    def is_unit_key_value(self):
        """Check whether unit is key = value based rather than translation.

        These are some files like PHP or properties, which for some
        reason do not correctly set source/target attributes.
        """
        return (
            hasattr(self.mainunit, 'name') and
            hasattr(self.mainunit, 'value') and
            hasattr(self.mainunit, 'translation')
        )

    def get_source(self):
        """Return source string from a ttkit unit."""
        if self.is_unit_key_value():
            # Need to decode property encoded string
            if isinstance(self.mainunit, propunit):
                if self.template is not None:
                    return quote.propertiesdecode(self.template.value)
                else:
                    return quote.propertiesdecode(self.unit.name)
            if self.template is not None:
                return self.template.value
            else:
                return self.unit.name
        else:
            if self.template is not None:
                return get_string(self.template.target)
            else:
                return get_string(self.unit.source)

    def get_target(self):
        """Return target string from a ttkit unit."""
        if self.unit is None:
            return ''
        if self.is_unit_key_value():
            # Need to decode property encoded string
            if isinstance(self.unit, propunit):
                # This is basically stolen from
                # translate.storage.properties.propunit.gettarget
                # which for some reason does not return translation
                value = quote.propertiesdecode(self.unit.value)
                value = re.sub('\\\\ ', ' ', value)
                return value
            return self.unit.value
        else:
            return get_string(self.unit.target)

    def get_context(self):
        """Return context of message.

        In some cases we have to use ID here to make all backends consistent.
        """
        if isinstance(self.mainunit, pounit) and self.template is not None:
            # Monolingual PO files
            return self.template.getid()
        else:
            context = self.mainunit.getcontext()
        if self.is_unit_key_value() and context == '':
            return self.mainunit.getid()
        return context

    def get_previous_source(self):
        """Return previous message source if there was any."""
        if not self.is_fuzzy() or not hasattr(self.unit, 'prev_source'):
            return ''
        return get_string(self.unit.prev_source)

    def get_id_hash(self):
        """Return hash of source string, used for quick lookup.

        We use siphash as it is fast and works well for our purpose.
        """
        if self.id_hash is None:
            if self.template is None:
                self.id_hash = calculate_hash(
                    self.get_source(), self.get_context()
                )
            else:
                self.id_hash = calculate_hash(
                    None, self.get_context()
                )

        return self.id_hash

    def get_content_hash(self):
        """Return hash of source string and context, used for quick lookup."""
        if self.template is None:
            return self.get_id_hash()

        if self.content_hash is None:
            self.content_hash = calculate_hash(
                self.get_source(), self.get_context()
            )

        return self.content_hash

    def is_translated(self):
        """Check whether unit is translated."""
        if self.unit is None:
            return False
        # The hasattr check here is needed for merged storages
        # where template is different kind than translations
        if self.is_unit_key_value() and hasattr(self.unit, 'value'):
            return not self.unit.isfuzzy() and self.unit.value != ''
        else:
            return self.unit.istranslated()

    def is_fuzzy(self):
        """Check whether unit is translated."""
        if self.unit is None:
            return False
        return self.unit.isfuzzy()

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
        self.unit.settarget(target)
        # Propagate to value so that is_translated works correctly
        if self.is_unit_key_value():
            self.unit.value = self.unit.translation

    def mark_fuzzy(self, fuzzy):
        """Set fuzzy flag on translated unit."""
        self.unit.markfuzzy(fuzzy)


class PoUnit(FileUnit):
    """Wrapper for Gettext PO unit"""
    def mark_fuzzy(self, fuzzy):
        """Set fuzzy flag on translated unit."""
        super(PoUnit, self).mark_fuzzy(fuzzy)
        if not fuzzy:
            self.unit.prev_source = ''
            self.unit.prev_msgctxt = []


class XliffUnit(FileUnit):
    """Wrapper unit for XLIFF

    XLIFF is special in ttkit - it uses locations for what
    is context in other formats.
    """

    @staticmethod
    def get_unit_context(unit):
        return unit.getid().replace(ID_SEPARATOR, '///')

    def get_context(self):
        """Return context of message.

        In some cases we have to use ID here to make all backends consistent.
        """
        if self.template is not None:
            return self.template.source
        return self.get_unit_context(self.mainunit)

    def get_locations(self):
        """Return comma separated list of locations."""
        return ''


class MonolingualIDUnit(FileUnit):
    def get_context(self):
        if self.template is not None:
            return self.template.getid()
        else:
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


class RESXUnit(FileUnit):
    def get_locations(self):
        return ''

    def get_context(self):
        if self.template is not None:
            return self.template.getid()
        else:
            return self.unit.getid()

    def get_source(self):
        if self.template is None:
            return self.mainunit.getid()
        return get_string(self.template.target)


class PHPUnit(FileUnit):
    def get_locations(self):
        return ''

    def get_context(self):
        if self.template is not None:
            return self.template.getsource()
        return ''

    def get_source(self):
        if self.template is not None:
            return self.template.getsource()
        return self.unit.getid()

    def get_target(self):
        if self.unit is None:
            return ''
        return self.unit.getsource()


class FileFormat(object):
    """Generic object defining file format loader."""
    name = ''
    format_id = ''
    loader = ('', '')
    monolingual = None
    check_flags = ()
    unit_class = FileUnit
    new_translation = None
    autoload = ()
    language_pack = None

    @staticmethod
    def serialize(store):
        """Serialize given ttkit store"""
        return bytes(store)

    @classmethod
    def parse(cls, storefile, template_store=None, language_code=None):
        """Parse store and returns FileFormat instance."""
        return cls(storefile, template_store, language_code)

    @classmethod
    def fixup(cls, store):
        """Perform optional fixups on store."""
        return store

    @classmethod
    def load(cls, storefile):
        """Load file using defined loader."""
        # Add missing mode attribute to Django file wrapper
        if (not isinstance(storefile, six.string_types) and
                not hasattr(storefile, 'mode')):
            storefile.mode = 'r'

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

    def __init__(self, storefile, template_store=None, language_code=None):
        """Create file format object, wrapping up translate-toolkit's store."""
        self.storefile = storefile
        # Load store
        self.store = self.load(storefile)
        # Check store validity
        if not self.is_valid(self.store):
            raise ValueError(
                'Invalid file format {0}'.format(self.store)
            )
        # Remember template
        self.template_store = template_store
        # Set language (needed for some which do not include this)
        if (language_code is not None and
                self.store.gettargetlanguage() is None):
            self.store.settargetlanguage(language_code)

    @property
    def has_template(self):
        """Check whether class is using template."""
        return (
            (self.monolingual or self.monolingual is None) and
            self.template_store is not None
        )

    def _find_unit_mono(self, context, store):
        # We search by ID when using template
        ttkit_unit = store.findid(context)

        if ttkit_unit is not None:
            return ttkit_unit

        # Do not use findid as it does not work for empty translations
        for search_unit in store.units:
            if search_unit.getid() == context:
                return search_unit

    def _find_unit_template(self, context):
        # Need to create new unit based on template
        template_ttkit_unit = self._find_unit_mono(
            context, self.template_store.store
        )
        # We search by ID when using template
        ttkit_unit = self._find_unit_mono(
            context, self.store
        )

        # We always need new unit to translate
        if ttkit_unit is None:
            ttkit_unit = template_ttkit_unit
            if template_ttkit_unit is None:
                return (None, False)
            add = True
        else:
            add = False

        return (self.unit_class(ttkit_unit, template_ttkit_unit), add)

    def _find_unit_bilingual(self, context, source):
        # Find all units with same source
        found_units = self.store.findunits(source)
        # Find is broken for propfile, ignore results
        if len(found_units) > 0 and not isinstance(self.store, propfile):
            for ttkit_unit in found_units:
                # Does context match?
                if ttkit_unit.getcontext() == context:
                    return (self.unit_class(ttkit_unit), False)
        else:
            # Fallback to manual find for value based files
            for ttkit_unit in self.store.units:
                ttkit_unit = self.unit_class(ttkit_unit)
                if ttkit_unit.get_source() == source:
                    return (ttkit_unit, False)
        return (None, False)

    def find_unit(self, context, source):
        """Find unit by context and source.

        Returns tuple (ttkit_unit, created) indicating whether returned
        unit is new one.
        """
        if self.has_template:
            return self._find_unit_template(context)
        else:
            return self._find_unit_bilingual(context, source)

    def add_unit(self, ttkit_unit):
        """Add new unit to underlaying store."""
        if isinstance(self.store, LISAfile):
            # LISA based stores need to know this
            self.store.addunit(ttkit_unit.unit, new=True)
        else:
            self.store.addunit(ttkit_unit.unit)

    def update_header(self, **kwargs):
        """Update store header if available."""
        if not hasattr(self.store, 'updateheader'):
            return

        kwargs['x_generator'] = 'Weblate {0}'.format(weblate.VERSION)

        # Adjust Content-Type header if needed
        header = self.store.parseheader()
        if ('Content-Type' not in header or
                'charset=CHARSET' in header['Content-Type'] or
                'charset=ASCII' in header['Content-Type']):
            kwargs['Content_Type'] = 'text/plain; charset=UTF-8'

        self.store.updateheader(**kwargs)

    def save(self):
        """Save underlaying store to disk."""
        with open(self.storefile, 'wb') as handle:
            self.store.serialize(handle)

    def find_matching(self, template_unit):
        """Find matching store unit for template"""
        return self.store.findid(template_unit.getid())

    def all_units(self):
        """Generator of all units."""
        if not self.has_template:
            for tt_unit in self.store.units:

                # Create wrapper object
                yield self.unit_class(tt_unit)
        else:
            for template_unit in self.template_store.store.units:

                # Create wrapper object (not translated)
                yield self.unit_class(
                    self.find_matching(template_unit),
                    template_unit
                )

    def count_units(self):
        """Return count of units."""
        if not self.has_template:
            return len(self.store.units)
        else:
            return len(self.template_store.store.units)

    @property
    def mimetype(self):
        """Return most common mime type for format."""
        if self.store.Mimetypes is None:
            # Properties files do not expose mimetype
            return 'text/plain'
        else:
            return self.store.Mimetypes[0]

    @property
    def extension(self):
        """Return most common file extension for format."""
        if self.store.Extensions is None:
            return 'txt'
        else:
            return self.store.Extensions[0]

    @classmethod
    def is_valid(cls, store):
        """Check whether store seems to be valid.

        In some cases ttkit happily "parses" the file, even though it
        really did not do so (eg. Gettext parser on random text file).
        """
        if store is None:
            return False

        if cls.monolingual is False and cls.serialize(store) == b'':
            return False

        return True

    @classmethod
    def supports_new_language(cls):
        """Whether it supports creating new translation."""
        return cls.new_translation is not None

    @classmethod
    def is_valid_base_for_new(cls, base):
        """Check whether base is valid."""
        return True

    @staticmethod
    def get_language_code(code):
        """Doe any possible formatting needed for language code."""
        return code

    @classmethod
    def get_language_filename(cls, mask, code):
        """
        Return full filename of a language file for given
        path, filemask and language code.
        """
        return mask.replace('*', cls.get_language_code(code))

    @classmethod
    def add_language(cls, filename, language, base):
        """Add new language file."""
        # Create directory for a translation
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        cls.create_new_file(filename, language, base)

    @classmethod
    def create_new_file(cls, filename, language, base):
        """Handle creation of new translation file."""
        if cls.new_translation is None:
            raise ValueError('Not supported')

        with open(filename, 'w') as output:
            output.write(cls.new_translation)

    def iterate_merge(self, fuzzy):
        """Iterate over units for merging.

        Note: This can change fuzzy state of units!
        """
        for unit in self.all_units():
            # Handle header
            if unit.unit and unit.unit.isheader():
                continue

            # Skip fuzzy (if asked for that)
            if unit.is_fuzzy():
                if not fuzzy:
                    continue
            elif not unit.is_translated():
                continue

            # Unmark unit as fuzzy (to allow merge)
            set_fuzzy = False
            if fuzzy and unit.is_fuzzy():
                unit.mark_fuzzy(False)
                if fuzzy != 'approve':
                    set_fuzzy = True

            yield set_fuzzy, unit

    def merge_header(self, otherstore):
        """Try to merge headers"""
        return

    @staticmethod
    def untranslate_store(store, language, fuzzy=False):
        """Remove translations from ttkit store"""
        store.settargetlanguage(language.code)

        for unit in store.units:
            if unit.istranslatable():
                unit.markfuzzy(fuzzy)
                if unit.hasplural():
                    unit.settarget([''] * language.nplurals)
                else:
                    unit.settarget('')


@register_fileformat
class AutoFormat(FileFormat):
    name = _('Automatic detection')
    format_id = 'auto'

    @classmethod
    def parse(cls, storefile, template_store=None, language_code=None):
        """Parse store and returns FileFormat instance.

        First attempt own autodetection, then fallback to ttkit.
        """
        if hasattr(storefile, 'read'):
            filename = getattr(storefile, 'name', None)
        else:
            filename = storefile
        if filename is not None:
            storeclass = detect_filename(filename)
            if storeclass is not None:
                return storeclass(storefile, template_store, language_code)
        return cls(storefile, template_store, language_code)

    @classmethod
    def parse_store(cls, storefile):
        """Directly loads using translate-toolkit."""
        return factory.getobject(storefile)

    @classmethod
    def get_class(cls):
        return None


@register_fileformat
class PoFormat(FileFormat):
    name = _('Gettext PO file')
    format_id = 'po'
    loader = pofile
    monolingual = False
    autoload = ('.po', '.pot')
    language_pack = 'mo'
    unit_class = PoUnit

    @classmethod
    def supports_new_language(cls):
        """Check whether we can create new language file."""
        return True

    @classmethod
    def is_valid_base_for_new(cls, base):
        """Check whether base is valid."""
        try:
            cls.loader.parsefile(base)
            return True
        except Exception:
            return False

    @classmethod
    def create_new_file(cls, filename, language, base):
        """Handle creation of new translation file."""
        store = pofile.parsefile(base)

        cls.untranslate_store(store, language)

        store.updateheader(
            last_translator='Automatically generated',
            plural_forms=language.get_plural_form(),
            language_team='none',
        )

        store.savefile(filename)

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


@register_fileformat
class PoMonoFormat(PoFormat):
    name = _('Gettext PO file (monolingual)')
    format_id = 'po-mono'
    monolingual = True


@register_fileformat
class TSFormat(FileFormat):
    name = _('Qt Linguist Translation File')
    format_id = 'ts'
    loader = tsfile
    autoload = ('.ts',)
    unit_class = TSUnit

    @classmethod
    def supports_new_language(cls):
        """Check whether we can create new language file."""
        return True

    @classmethod
    def create_new_file(cls, filename, language, base):
        store = tsfile.parsefile(base)

        cls.untranslate_store(store, language, True)

        store.savefile(filename)

    @classmethod
    def is_valid_base_for_new(cls, base):
        """Check whether base is valid."""
        try:
            cls.loader.parsefile(base)
            return True
        except Exception:
            return False


@register_fileformat
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

    def _find_unit_bilingual(self, context, source):
        # Find all units with same source
        found_units = self.store.findunits(source)
        # Find is broken for propfile, ignore results
        for ttkit_unit in found_units:
            # Does context match?
            found_context = XliffUnit.get_unit_context(ttkit_unit)
            if found_context == context:
                return (self.unit_class(ttkit_unit), False)
        return (None, False)

    @classmethod
    def supports_new_language(cls):
        """Check whether we can create new language file."""
        return True

    @classmethod
    def is_valid_base_for_new(cls, base):
        """Check whether base is valid."""
        try:
            cls.loader.parsefile(base)
            return True
        except Exception:
            return False

    @classmethod
    def create_new_file(cls, filename, language, base):
        """Handle creation of new translation file."""
        content = cls.loader.parsefile(base)
        content.settargetlanguage(language.code)
        content.savefile(filename)

    def _find_unit_mono(self, context, store):
        # Do not use findid as it does not work for empty translations
        for search_unit in store.units:
            loc = search_unit.source
            if loc == context:
                return search_unit


@register_fileformat
class PoXliffFormat(XliffFormat):
    name = _('XLIFF Translation File with PO extensions')
    format_id = 'poxliff'
    autoload = ('.poxliff',)
    loader = PoXliffFile


@register_fileformat
class StringsFormat(FileFormat):
    name = _('OS X Strings')
    format_id = 'strings'
    loader = ('properties', 'stringsfile')
    new_translation = '\n'.encode('utf-16')
    autoload = ('.strings',)


@register_fileformat
class StringsUtf8Format(FileFormat):
    name = _('OS X Strings (UTF-8)')
    format_id = 'strings-utf8'
    loader = ('properties', 'stringsutf8file')
    new_translation = '\n'


@register_fileformat
class PropertiesUtf8Format(FileFormat):
    name = _('Java Properties (UTF-8)')
    format_id = 'properties-utf8'
    loader = ('properties', 'javautf8file')
    monolingual = True
    new_translation = '\n'


@register_fileformat
class PropertiesUtf16Format(PropertiesUtf8Format):
    name = _('Java Properties (UTF-16)')
    format_id = 'properties-utf16'
    loader = ('properties', 'javafile')


@register_fileformat
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


@register_fileformat
class JoomlaFormat(FileFormat):
    name = _('Joomla Language File')
    format_id = 'joomla'
    loader = ('properties', 'joomlafile')
    monolingual = True
    new_translation = '\n'
    autoload = ('.ini',)


@register_fileformat
class PhpFormat(FileFormat):
    name = _('PHP strings')
    format_id = 'php'
    loader = phpfile
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

    def save(self):
        """Save underlaying store to disk.

        This is workaround for .save() not working as intended in
        translate-toolkit.
        """
        with open(self.store.filename, 'rb') as handle:
            convertor = po2php.rephp(handle, self.store)

            outputphplines = convertor.convertstore(False)

        with open(self.store.filename, 'wb') as handle:
            handle.writelines(outputphplines)

    def _find_unit_mono(self, context, store):
        # Do not use findid as it does not work for empty translations
        for search_unit in store.units:
            if search_unit.source == context:
                return search_unit


@register_fileformat
class RESXFormat(FileFormat):
    name = _('.Net resource file')
    format_id = 'resx'
    loader = RESXFile
    monolingual = True
    unit_class = RESXUnit
    new_translation = RESXFile.XMLskeleton
    autoload = ('.resx',)


@register_fileformat
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
        """Doe any possible formatting needed for language code."""
        # Android doesn't use Hans/Hant, but rahter TW/CN variants
        if code == 'zh_Hans':
            return 'zh-rCN'
        elif code == 'zh_Hant':
            return 'zh-rTW'
        return code.replace('_', '-r')


@register_fileformat
class JSONFormat(FileFormat):
    name = _('JSON file')
    format_id = 'json'
    loader = ('jsonl10n', 'JsonFile')
    unit_class = MonolingualSimpleUnit
    autoload = ('.json',)

    @classmethod
    def supports_new_language(cls):
        """Check whether we can create new language file."""
        return True

    @classmethod
    def create_new_file(cls, filename, language, base):
        """Handle creation of new translation file."""
        content = b'{}\n'
        if base:
            with open(base, 'rb') as handle:
                content = handle.read()
        with open(filename, 'wb') as output:
            output.write(content)

    @property
    def mimetype(self):
        """Return most common mime type for format."""
        return 'application/json'

    @property
    def extension(self):
        """Return most common file extension for format."""
        return 'json'


@register_fileformat
class CSVFormat(FileFormat):
    name = _('CSV file')
    format_id = 'csv'
    loader = ('csvl10n', 'csvfile')
    unit_class = MonolingualSimpleUnit
    autoload = ('.csv',)

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


@register_fileformat
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


@register_fileformat
class CSVSimpleFormatISO(CSVSimpleFormat):
    name = _('Simple CSV file (ISO-8859-1)')
    format_id = 'csv-simple-iso'
    encoding = 'iso-8859-1'


@register_fileformat
class YAMLFormat(FileFormat):
    name = _('YAML file')
    format_id = 'yaml'
    loader = ('yaml', 'YAMLFile')
    unit_class = MonolingualSimpleUnit
    autoload = ('.pyml',)

    @classmethod
    def supports_new_language(cls):
        """Check whether we can create new language file."""
        return True

    @classmethod
    def create_new_file(cls, filename, language, base):
        """Handle creation of new translation file."""
        if base:
            storeclass = cls.get_class()

            # Parse file
            store = storeclass.parsefile(base)
            cls.untranslate_store(store, language)
            store.savefile(filename)
        else:
            with open(filename, 'wb') as output:
                output.write(b'{}\n')

    @property
    def mimetype(self):
        """Return most common mime type for format."""
        return 'text/yaml'

    @property
    def extension(self):
        """Return most common file extension for format."""
        return 'yml'


@register_fileformat
class RubyYAMLFormat(YAMLFormat):
    name = _('Ruby YAML file')
    format_id = 'ruby-yaml'
    loader = ('yaml', 'RubyYAMLFile')
    autoload = ('.ryml', '.yml', '.yaml')


FILE_FORMAT_CHOICES = [
    (fmt, FILE_FORMATS[fmt].name) for fmt in sorted(FILE_FORMATS)
]
