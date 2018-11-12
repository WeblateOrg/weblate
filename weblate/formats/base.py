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

from django.utils.functional import cached_property

import six

from translate.storage.base import TranslationStore
from translate.storage.lisa import LISAfile
from translate.storage.properties import propfile

from weblate.utils.errors import report_error
from weblate.utils.hash import calculate_hash

FLAGS_RE = re.compile(r'\b[-\w:]+\b')


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


class TranslationUnit(object):
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

    @cached_property
    def locations(self):
        """Return comma separated list of locations."""
        return ''

    def reformat_flags(self, typecomments):
        """Processe flags from PO file to nicer form."""
        # Grab flags
        flags = set(FLAGS_RE.findall('\n'.join(typecomments)))

        # Discard fuzzy flag, we don't care about that one
        flags.discard('fuzzy')

        # Join into string
        return ', '.join(flags)

    @cached_property
    def flags(self):
        """Return flags (typecomments) from units."""
        return ''

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

    @cached_property
    def source(self):
        """Return source string from a ttkit unit."""
        raise NotImplementedError()

    @cached_property
    def target(self):
        """Return target string from a ttkit unit."""
        raise NotImplementedError()

    @cached_property
    def context(self):
        """Return context of message.

        In some cases we have to use ID here to make all backends consistent.
        """
        raise NotImplementedError()

    @cached_property
    def previous_source(self):
        """Return previous message source if there was any."""
        return ''

    @cached_property
    def id_hash(self):
        """Return hash of source string, used for quick lookup.

        We use siphash as it is fast and works well for our purpose.
        """
        if self.template is None:
            return calculate_hash(self.source, self.context)
        return calculate_hash(None, self.context)

    @cached_property
    def content_hash(self):
        """Return hash of source string and context, used for quick lookup."""
        if self.template is None:
            return self.id_hash
        return calculate_hash(self.source, self.context)

    def is_translated(self):
        """Check whether unit is translated."""
        raise NotImplementedError()

    def is_approved(self, fallback=False):
        """Check whether unit is appoved."""
        return fallback

    def is_fuzzy(self, fallback=False):
        """Check whether unit needs edit."""
        return fallback

    def is_obsolete(self):
        """Check whether unit is marked as obsolete in backend."""
        return False

    def is_translatable(self):
        """Check whether unit is translatable."""
        return True

    def set_target(self, target):
        """Set translation unit target."""
        raise NotImplementedError()

    def mark_fuzzy(self, fuzzy):
        """Set fuzzy flag on translated unit."""
        raise NotImplementedError()

    def mark_approved(self, value):
        """Set approved flag on translated unit."""
        raise NotImplementedError()


class TranslationFormat(object):
    """Generic object defining file format loader."""
    name = ''
    format_id = ''
    loader = ('', '')
    monolingual = None
    check_flags = ()
    unit_class = TranslationUnit
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
        """Parse store and returns TranslationFormat instance."""
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

    @cached_property
    def has_template(self):
        """Check whether class is using template."""
        return (
            (self.monolingual or self.monolingual is None) and
            self.template_store is not None
        )

    @cached_property
    def _context_index(self):
        """ID based index for units."""
        return {unit.context: unit for unit in self.mono_units}

    def find_unit_mono(self, context):
        try:
            return self._context_index[context].unit
        except KeyError:
            return None

    def _find_unit_template(self, context):
        # Need to create new unit based on template
        template_ttkit_unit = self.template_store.find_unit_mono(context)
        # We search by ID when using template
        ttkit_unit = self.find_unit_mono(context)

        # We always need new unit to translate
        if ttkit_unit is None:
            ttkit_unit = template_ttkit_unit
            if template_ttkit_unit is None:
                return (None, False)
            add = True
        else:
            add = False

        return (self.unit_class(ttkit_unit, template_ttkit_unit), add)

    @cached_property
    def _source_index(self):
        """Context and source based index for units."""
        return {
            (unit.context, unit.source): unit
            for unit in self.all_units
        }

    def _find_unit_bilingual(self, context, source):
        try:
            return (self._source_index[context, source], False)
        except KeyError:
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
        return

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

    @cached_property
    def mono_units(self):
        return [self.unit_class(unit) for unit in self.store.units]

    @cached_property
    def all_units(self):
        """List of all units."""
        if not self.has_template:
            return self.mono_units
        return [
            self.unit_class(self.find_unit_mono(unit.context), unit.unit)
            for unit in self.template_store.mono_units
        ]

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
        except Exception as error:
            report_error(error)
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
        for unit in self.all_units:
            # Handle header and other special units
            if not unit.is_translatable():
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
