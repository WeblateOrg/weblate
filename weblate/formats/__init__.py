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
"""File format specific behavior."""

from __future__ import unicode_literals

import csv
import importlib
import inspect
from io import BytesIO
import os
import re
import sys
import tempfile
import traceback


from django.utils.translation import ugettext_lazy as _

import six

from translate.misc import quote
from translate.misc.multistring import multistring
from translate.storage.lisa import LISAfile
from translate.storage.po import pounit, pofile
from translate.storage.poheader import default_header
from translate.storage.properties import propunit, propfile
from translate.storage.ts2 import tsfile, tsunit
from translate.storage.xliff import xlifffile, ID_SEPARATOR
from translate.storage.poxliff import PoXliffFile
from translate.storage.resx import RESXFile
from translate.storage import factory

from weblate.trans.util import get_string, join_plural, add_configuration_error

from weblate.utils.hash import calculate_hash

import weblate

default_app_config = 'weblate.formats.apps.FormatsConfig'

FLAGS_RE = re.compile(r'\b[-\w:]+\b')
LOCATIONS_RE = re.compile(r'^([+-]|.*, [+-]|.*:[+-])')
SUPPORTS_FUZZY = (pounit, tsunit)


def move_atomic(source, target):
    """Tries to perform atomic move.

    This is tricky on Windows as until Python 3.3 there is no
    function for that. And even on Python 3.3 the MoveFileEx
    is not guarateed to be atomic, so it might fail in some cases.
    Anyway we try to choose best available method.
    """
    # Use os.replace if available
    if sys.version_info >= (3, 3):
        os.replace(source, target)
    else:
        # Remove target on Windows if exists
        if sys.platform == 'win32' and os.path.exists(target):
            os.unlink(target)
        # Use os.rename
        os.rename(source, target)


class ParseError(Exception):
    """Generic error for parsing."""


class StringIOMode(BytesIO):
    """StringIO with mode attribute to make ttkit happy."""
    def __init__(self, filename, data):
        super(StringIOMode, self).__init__(data)
        self.mode = 'r'
        self.name = filename


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
        if isinstance(self.mainunit, propunit):
            return ''
        return ', '.join(
            [x for x in self.mainunit.getlocations() if x is not None]
        )

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

    def is_unit_key_value(self, unit):
        """Check whether unit is key = value based rather than translation.

        These are some files like PHP or properties, which for some
        reason do not correctly set source/target attributes.
        """
        return (
            hasattr(unit, 'name') and
            hasattr(unit, 'value') and
            hasattr(unit, 'translation')
        )

    def get_source(self):
        """Return source string from a ttkit unit."""
        if self.is_unit_key_value(self.mainunit):
            # Need to decode property encoded string
            if isinstance(self.mainunit, propunit):
                if self.template is not None:
                    return quote.propertiesdecode(self.template.value)
                return quote.propertiesdecode(self.unit.name)
            if self.template is not None:
                return self.template.value
            return self.unit.name
        else:
            if self.template is not None:
                return get_string(self.template.target)
            return get_string(self.unit.source)

    def get_target(self):
        """Return target string from a ttkit unit."""
        if self.unit is None:
            return ''
        if self.is_unit_key_value(self.unit):
            # Need to decode property encoded string
            if isinstance(self.unit, propunit):
                # This is basically stolen from
                # translate.storage.properties.propunit.gettarget
                # which for some reason does not return translation
                value = quote.propertiesdecode(self.unit.value)
                value = re.sub('\\\\ ', ' ', value)
                return value
            return self.unit.value
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
        if self.is_unit_key_value(self.mainunit) and context == '':
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
        if self.is_unit_key_value(self.unit) and hasattr(self.unit, 'value'):
            return not self.unit.isfuzzy() and self.unit.value != ''
        return self.unit.istranslated()

    def is_approved(self, fallback=False):
        """Check whether unit is appoved."""
        if self.unit is None:
            return fallback
        if hasattr(self.unit, 'isapproved'):
            return self.unit.isapproved()
        return fallback

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
        if isinstance(target, list):
            target = multistring(target)
        self.unit.target = target
        # Propagate to value so that is_translated works correctly
        if self.is_unit_key_value(self.unit):
            self.unit.value = self.unit.translation

    def mark_fuzzy(self, fuzzy):
        """Set fuzzy flag on translated unit."""
        self.unit.markfuzzy(fuzzy)

    def mark_approved(self, value):
        """Set approved flag on translated unit."""
        if hasattr(self.unit, 'markapproved'):
            self.unit.markapproved(value)


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
    can_add_unit = True

    @classmethod
    def get_identifier(cls):
        return cls.format_id

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

    def get_plural(self, language):
        """Return matching plural object."""
        return language.plural

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

        return None

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
        if found_units and not isinstance(self.store, propfile):
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
        return self._find_unit_bilingual(context, source)

    def add_unit(self, ttkit_unit):
        """Add new unit to underlaying store."""
        if isinstance(self.store, LISAfile):
            # LISA based stores need to know this
            self.store.addunit(ttkit_unit, new=True)
        else:
            self.store.addunit(ttkit_unit)

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
        dirname, basename = os.path.split(self.storefile)
        temp = tempfile.NamedTemporaryFile(
            prefix=basename, dir=dirname, delete=False
        )
        try:
            self.store.serialize(temp)
            temp.close()
            move_atomic(temp.name, self.storefile)
        finally:
            if os.path.exists(temp.name):
                os.unlink(temp.name)

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
        return len(self.template_store.store.units)

    @property
    def mimetype(self):
        """Return most common mime type for format."""
        if self.store.Mimetypes is None:
            # Properties files do not expose mimetype
            return 'text/plain'
        return self.store.Mimetypes[0]

    @property
    def extension(self):
        """Return most common file extension for format."""
        if self.store.Extensions is None:
            return 'txt'
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

    @classmethod
    def is_valid_base_for_new(cls, base):
        """Check whether base is valid."""
        if not base:
            return cls.new_translation is not None
        try:
            cls.parse_store(base)
            return True
        except Exception:
            return False

    @staticmethod
    def get_language_code(code):
        """Do any possible formatting needed for language code."""
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

    @classmethod
    def untranslate_store(cls, store, language, fuzzy=False):
        """Remove translations from ttkit store"""
        store.settargetlanguage(language.code)
        plural = language.plural

        for unit in store.units:
            if unit.istranslatable():
                if hasattr(unit, 'markapproved'):
                    # Xliff only
                    unit.markapproved(not fuzzy)
                else:
                    unit.markfuzzy(fuzzy)
                if unit.hasplural():
                    unit.target = [''] * plural.number
                else:
                    unit.target = ''

    def create_unit(self, key, source):
        unit = self.store.UnitClass(source)
        unit.setid(key)
        unit.source = key
        unit.target = source
        return unit

    def new_unit(self, key, source):
        """Add new unit to monolingual store."""
        unit = self.create_unit(key, source)
        self.add_unit(unit)
        self.save()


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
            from weblate.formats.models import detect_filename
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


class PoFormat(FileFormat):
    name = _('Gettext PO file')
    format_id = 'po'
    loader = pofile
    monolingual = False
    autoload = ('.po', '.pot')
    unit_class = PoUnit

    @classmethod
    def is_valid_base_for_new(cls, base):
        """Check whether base is valid."""
        try:
            cls.loader.parsefile(base)
            return True
        except Exception:
            return False

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


class TSFormat(FileFormat):
    name = _('Qt Linguist Translation File')
    format_id = 'ts'
    loader = tsfile
    autoload = ('.ts',)
    unit_class = TSUnit

    @classmethod
    def is_valid_base_for_new(cls, base):
        """Check whether base is valid."""
        try:
            cls.loader.parsefile(base)
            return True
        except Exception:
            return False


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

    @classmethod
    def is_valid_base_for_new(cls, base):
        """Check whether base is valid."""
        try:
            cls.loader.parsefile(base)
            return True
        except Exception:
            return False


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
            raise ImportError('RC not supported on Python 3')
        return importlib.import_module(
            'translate.storage.rc'
        ).rcfile
