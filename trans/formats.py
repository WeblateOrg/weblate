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
from translate.storage import factory
import importlib
import __builtin__


class FileFormat(object):
    '''
    Simple object defining file format loader.
    '''
    def __init__(self, name, loader, monolingual=None, mark_fuzzy=False,
                 fixups=None):
        self.name = name
        self.loader = loader
        self.monolingual = monolingual
        self.mark_fuzzy = mark_fuzzy
        self.fixups = fixups

    def load(self, storefile):
        '''
        Loads file using defined loader.
        '''
        loader = self.loader

        # If loader is callable call it directly
        if callable(loader):
            return loader(storefile)

        # Tuple style loader, import from translate toolkit
        module_name, class_name = loader
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

        # Apply possible fixups
        if self.fixups is not None:
            for fix in self.fixups:
                setattr(store, fix, self.fixups[fix])

        return store


FILE_FORMATS = {
    'auto': FileFormat(
        _('Automatic detection'),
        factory.getobject,
    ),
    'po': FileFormat(
        _('Gettext PO file'),
        ('po', 'pofile'),
        False,
    ),
    'ts': FileFormat(
        _('Qt Linguist Translation File'),
        ('ts2', 'tsfile'),
    ),
    'xliff': FileFormat(
        _('XLIFF Translation File'),
        ('xliff', 'xlifffile'),
    ),
    'strings': FileFormat(
        _('OS X Strings'),
        ('properties', 'stringsfile'),
        False,
    ),
    'properties': FileFormat(
        _('Java Properties'),
        ('properties', 'javafile'),
        True,
        # Java properties need to be iso-8859-1, but
        # ttkit converts them to utf-8
        fixups={'encoding': 'iso-8859-1'},
    ),
    'properties-utf8': FileFormat(
        _('Java Properties (UTF-8)'),
        ('properties', 'javautf8file'),
        True,
    ),
    'php': FileFormat(
        _('PHP strings'),
        ('php', 'phpfile'),
    ),
    'aresource': FileFormat(
        _('Android String Resource'),
        ('aresource', 'AndroidResourceFile'),
        True,
        mark_fuzzy=True,
    )
}

FILE_FORMAT_CHOICES = [(fmt, FILE_FORMATS[fmt].name) for fmt in FILE_FORMATS]


def ttkit(storefile, file_format='auto'):
    '''
    Returns translate-toolkit storage for a path.
    '''

    # Workaround for _ created by interactive interpreter and
    # later used instead of gettext by ttkit
    if '_' in __builtin__.__dict__ and not callable(__builtin__.__dict__['_']):
        del __builtin__.__dict__['_']

    # Add missing mode attribute to Django file wrapper
    if not isinstance(storefile, basestring):
        storefile.mode = 'r'

    if not file_format in FILE_FORMATS:
        raise Exception('Not supported file format: %s' % file_format)

    # Get loader
    format_obj = FILE_FORMATS[file_format]

    return format_obj.load(storefile)
