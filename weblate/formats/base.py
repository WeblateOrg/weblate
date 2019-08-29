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
"""Base classses for file formats."""

from __future__ import unicode_literals

import os
import sys
import tempfile
from copy import deepcopy

import six
from django.utils.functional import cached_property
from django.utils.translation import ugettext as _

from weblate.utils.hash import calculate_hash


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


class UnitNotFound(Exception):
    pass


class TranslationUnit(object):
    """Wrapper for translate-toolkit unit.

    It handles ID/template based translations and other API differences.
    """

    def __init__(self, parent, unit, template=None):
        """Create wrapper object."""
        self.unit = unit
        self.template = template
        self.parent = parent
        if template is not None:
            self.mainunit = template
        else:
            self.mainunit = unit

    def _invalidate_target(self):
        """Invalidate target cache."""
        if 'target' in self.__dict__:
            del self.__dict__['target']

    @cached_property
    def locations(self):
        """Return comma separated list of locations."""
        return ''

    @cached_property
    def flags(self):
        """Return flags or typecomments from units."""
        return ''

    @cached_property
    def comments(self):
        """Return comments or notes from units."""
        return ''

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
        return bool(self.target)

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
    monolingual = None
    check_flags = ()
    unit_class = TranslationUnit
    autoload = ()
    can_add_unit = True
    language_format = 'posix'
    simple_filename = True
    new_translation = None

    @classmethod
    def get_identifier(cls):
        return cls.format_id

    @classmethod
    def parse(cls, storefile, template_store=None, language_code=None,
              is_template=False):
        """Parse store and returns TranslationFormat instance.

        This wrapper is needed for AutodetectFormat to be able to return
        instance of different class."""
        return cls(storefile, template_store, language_code, is_template)

    def __init__(self, storefile, template_store=None, language_code=None,
                 is_template=False):
        """Create file format object, wrapping up translate-toolkit's store."""
        if (not isinstance(storefile, six.string_types)
                and not hasattr(storefile, 'mode')):
            storefile.mode = 'r'

        self.storefile = storefile

        # Load store
        self.store = self.load(storefile)

        # Remember template
        self.template_store = template_store
        self.is_template = is_template

    def check_valid(self):
        """Check store validity."""
        if not self.is_valid():
            raise ValueError(
                _('Failed to load strings from the file, try choosing other format.')
            )

    def get_filenames(self):
        if isinstance(self.storefile, six.string_types):
            return [self.storefile]
        return [self.storefile.name]

    @classmethod
    def load(cls, storefile):
        raise NotImplementedError()

    def get_plural(self, language):
        """Return matching plural object."""
        return language.plural

    @cached_property
    def has_template(self):
        """Check whether class is using template."""
        return (
            (self.monolingual or self.monolingual is None)
            and self.template_store is not None
        )

    @cached_property
    def _context_index(self):
        """ID based index for units."""
        return {unit.context: unit for unit in self.mono_units}

    def find_unit_mono(self, context):
        try:
            # The mono units always have only template set
            return self._context_index[context].template
        except KeyError:
            return None

    def _find_unit_template(self, context):
        # Need to create new unit based on template
        template_ttkit_unit = self.template_store.find_unit_mono(context)
        # We search by ID when using template
        ttkit_unit = self.find_unit_mono(context)

        # We always need new unit to translate
        if ttkit_unit is None:
            if template_ttkit_unit is None:
                raise UnitNotFound('Unit not found: {}'.format(context))
            ttkit_unit = deepcopy(template_ttkit_unit)
            add = True
        else:
            add = False

        return (self.unit_class(self, ttkit_unit, template_ttkit_unit), add)

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
            raise UnitNotFound('Unit not found: {}, {}'.format(context, source))

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
        raise NotImplementedError()

    def update_header(self, **kwargs):
        """Update store header if available."""
        return

    def save_atomic(self, filename, callback):
        dirname, basename = os.path.split(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        temp = tempfile.NamedTemporaryFile(
            prefix=basename, dir=dirname, delete=False
        )
        try:
            callback(temp)
            temp.close()
            move_atomic(temp.name, filename)
        finally:
            if os.path.exists(temp.name):
                os.unlink(temp.name)

    def save(self):
        """Save underlaying store to disk."""
        raise NotImplementedError()

    @cached_property
    def mono_units(self):
        return [self.unit_class(self, None, unit) for unit in self.store.units]

    @cached_property
    def all_units(self):
        """List of all units."""
        if not self.has_template:
            return [self.unit_class(self, unit) for unit in self.store.units]
        return [
            self.unit_class(
                self, self.find_unit_mono(unit.context), unit.template
            )
            for unit in self.template_store.mono_units
        ]

    @property
    def translatable_units(self):
        for unit in self.all_units:
            if not unit.is_translatable():
                continue
            yield unit

    @staticmethod
    def mimetype():
        """Return most common mime type for format."""
        return 'text/plain'

    @staticmethod
    def extension():
        """Return most common file extension for format."""
        return 'txt'

    def is_valid(self):
        """Check whether store seems to be valid."""
        return True

    @classmethod
    def is_valid_base_for_new(cls, base, monolingual):
        """Check whether base is valid."""
        raise NotImplementedError()

    @classmethod
    def get_language_code(cls, code, language_format=None):
        """Do any possible formatting needed for language code."""
        if not language_format:
            language_format = cls.language_format
        return getattr(cls, 'get_language_{}'.format(language_format))(code)

    @staticmethod
    def get_language_posix(code):
        return code

    @staticmethod
    def get_language_bcp(code):
        return code.replace('_', '-')

    @staticmethod
    def get_language_android(code):
        # Android doesn't use Hans/Hant, but rather TW/CN variants
        if code == 'zh_Hans':
            return 'zh-rCN'
        if code == 'zh_Hant':
            return 'zh-rTW'
        sanitized = code.replace('-', '_')
        if '_' in sanitized and len(sanitized.split('_')[1]) > 2:
            return 'b+{}'.format(sanitized.replace('_', '+'))
        return sanitized.replace('_', '-r')

    @classmethod
    def get_language_java(cls, code):
        # Java doesn't use Hans/Hant, but rather TW/CN variants
        if code == 'zh_Hans':
            return 'zh-CN'
        if code == 'zh_Hant':
            return 'zh-TW'
        if code == 'zh_Hans_SG':
            return 'zh-SG'
        if code == 'zh_Hant_HK':
            return 'zh-HK'
        return cls.get_language_bcp(code)

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
        raise NotImplementedError()

    def iterate_merge(self, fuzzy):
        """Iterate over units for merging.

        Note: This can change fuzzy state of units!
        """
        for unit in self.translatable_units:
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

    def create_unit(self, key, source):
        raise NotImplementedError()

    def new_unit(self, key, source):
        """Add new unit to monolingual store."""
        unit = self.create_unit(key, source)
        self.add_unit(unit)
        self.save()

    @classmethod
    def get_class(cls):
        raise NotImplementedError()


class EmptyFormat(TranslationFormat):
    """For testing purposes."""
    @classmethod
    def load(cls, storefile):
        return type(str(''), (object, ), {"units": []})()

    def save(self):
        return
