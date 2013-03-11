# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
'''
File format specific behavior.
'''
from django.utils.translation import ugettext_lazy as _
from translate.storage.lisa import LISAfile
from translate.storage import factory
import importlib
import __builtin__


FILE_FORMATS = {}


def register_fileformat(fileformat):
    '''
    Registers fileformat in dictionary.
    '''
    FILE_FORMATS[fileformat.format_id] = fileformat


class FileFormat(object):
    '''
    Generic object defining file format loader.
    '''
    name = ''
    format_id = ''
    loader = None
    monolingual = None
    mark_fuzzy = None

    @classmethod
    def fixup(cls, store):
        '''
        Performs optional fixups on store.
        '''
        return store

    @classmethod
    def load(cls, storefile):
        '''
        Loads file using defined loader.
        '''
        # Workaround for _ created by interactive interpreter and
        # later used instead of gettext by ttkit
        if ('_' in __builtin__.__dict__
                and not callable(__builtin__.__dict__['_'])):
            del __builtin__.__dict__['_']

        # Add missing mode attribute to Django file wrapper
        if not isinstance(storefile, basestring):
            storefile.mode = 'r'

        return cls.parse_store(storefile)

    @classmethod
    def parse_store(cls, storefile):
        # Tuple style loader, import from translate toolkit
        module_name, class_name = cls.loader
        if '.' in module_name:
            module = importlib.import_module(module_name)
        else:
            try:
                module = importlib.import_module(
                    'translate.storage.%s' % module_name
                )
            except ImportError:
                # Fallback to bultin ttkit copy
                # (only valid for aresource)
                module = importlib.import_module(
                    'ttkit.%s' % module_name
                )

        # Get the class
        storeclass = getattr(module, class_name)

        # Parse file
        store = storeclass.parsefile(storefile)

        # Apply possible fixups and return
        return cls.fixup(store)

    def __init__(self, storefile, template_store=None):
        '''
        Creates file format object, wrapping up translate-toolkit's
        store.
        '''
        # Load store
        self.store = self.load(storefile)
        # Remember template
        self.template_store = template_store

    @property
    def has_template(self):
        '''
        Checks whether class is using template.
        '''
        return (
            (self.monolingual or self.monolingual is None)
            and not self.template_store is None
        )

    def find_unit(self, context, source):
        '''
        Finds unit by context and source.

        Returns tuple (pounit, created) indicating whether returned
        unit is new one.
        '''
        if self.has_template:
            # We search by ID when using template
            pounit = self.store.findid(context)

            if pounit is not None:
                return (pounit, False)

            # Need to create new unit based on template
            pounit = self.template_store.findid(context)

            if pounit is not None:
                return (pounit, True)
            add = True
            found = pounit is not None
        else:
            # Find all units with same source
            found_units = self.store.findunits(source)
            if len(found_units) > 0:
                for pounit in found_units:
                    # Does context match?
                    if pounit.getcontext() == context:
                        return (pounit, False)
            else:
                # Fallback to manual find for value based files
                for pounit in store.units:
                    if get_source(pounit) == src:
                        return (pounit, False)

        return (None, False)

    def add_unit(self, pounit):
        '''
        Adds new unit to underlaying store.
        '''
        if isinstance(self.store, LISAfile):
            # LISA based stores need to know this
            self.store.addunit(pounit, new=True)
        else:
            self.store.addunit(pounit)

    def update_header(self, **kwargs):
        '''
        Updates store header if available.
        '''
        if not hasattr(self.store, 'updateheader'):
            return
        self.store.updateheader(**kwargs)

    def save(self):
        '''
        Saves underlaying store to disk.
        '''
        self.store.save()


class AutoFormat(FileFormat):
    name = _('Automatic detection')
    format_id = 'auto'

    @classmethod
    def parse_store(cls, storefile):
        '''
        Directly loads using translate-toolkit.
        '''
        return factory.getobject(storefile)

register_fileformat(AutoFormat)


class PoFormat(FileFormat):
    name = _('Gettext PO file')
    format_id = 'po'
    loader = ('po', 'pofile')
    monolingual = False

register_fileformat(PoFormat)


class TSFormat(FileFormat):
    name = _('Qt Linguist Translation File')
    format_id = 'ts'
    loader = ('ts2', 'tsfile')

register_fileformat(TSFormat)


class XliffFormat(FileFormat):
    name = _('XLIFF Translation File')
    format_id = 'xliff'
    loader = ('xliff', 'xlifffile')

register_fileformat(XliffFormat)


class StringsFormat(FileFormat):
    name = _('OS X Strings')
    format_id = 'strings'
    loader = ('properties', 'stringsfile')
    monolingual = False

register_fileformat(StringsFormat)


class PropertiesFormat(FileFormat):
    name = _('Java Properties')
    format_id = 'properties'
    loader = ('properties', 'javafile')
    monolingual = True

    @classmethod
    def fixup(cls, store):
        '''
        Java properties need to be iso-8859-1, but
        ttkit converts them to utf-8.
        '''
        store.encoding = 'iso-8859-1'
        return store

register_fileformat(PropertiesFormat)


class PropertiesUtf8Format(FileFormat):
    name = _('Java Properties (UTF-8)')
    format_id = 'properties-utf8'
    loader = ('properties', 'javautf8file')
    monolingual = True

register_fileformat(PropertiesUtf8Format)


class PhpFormat(FileFormat):
    name = _('PHP strings')
    format_id = 'php'
    loader = ('php', 'phpfile')

register_fileformat(PhpFormat)


class AndroidFormat(FileFormat):
    name = _('Android String Resource')
    format_id = 'aresource'
    loader = ('aresource', 'AndroidResourceFile')
    monolingual = True
    mark_fuzzy = True

register_fileformat(AndroidFormat)

FILE_FORMAT_CHOICES = [(fmt, FILE_FORMATS[fmt].name) for fmt in FILE_FORMATS]
