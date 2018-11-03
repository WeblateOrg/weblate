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
"""Base classses for file formats."""

from __future__ import unicode_literals

import importlib
import inspect
import os
import re
import sys
import tempfile

import six

from translate.misc import quote
from translate.misc.multistring import multistring
from translate.storage.base import TranslationStore
from translate.storage.lisa import LISAfile
from translate.storage.po import pounit
from translate.storage.properties import propunit, propfile
from translate.storage.ts2 import tsunit

from weblate.trans.util import get_string

from weblate.utils.hash import calculate_hash

import weblate

FLAGS_RE = re.compile(r'\b[-\w:]+\b')
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
        if isinstance(storefile, TranslationStore):
            # Used by XLSX writer
            self.store = storefile
        else:
            self.store = self.load(storefile)
        # Check store validity
        if not self.is_valid(self.store):
            raise ValueError(
                'Invalid file format {0}'.format(repr(self.store))
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

    def save_content(self, handle):
        """Stores content to file."""
        self.store.serialize(handle)

    def save(self):
        """Save underlaying store to disk."""
        dirname, basename = os.path.split(self.storefile)
        temp = tempfile.NamedTemporaryFile(
            prefix=basename, dir=dirname, delete=False
        )
        try:
            self.save_content(temp)
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
    def is_valid_base_for_new(cls, base, monolingual):
        """Check whether base is valid."""
        if not base:
            return monolingual and cls.new_translation is not None
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

    @classmethod
    def untranslate_store(cls, store, language, fuzzy=False):
        """Remove translations from ttkit store"""
        store.settargetlanguage(language.code)
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
