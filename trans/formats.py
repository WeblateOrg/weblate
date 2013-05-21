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
from translate.storage.properties import propunit, propfile
from translate.storage.xliff import xliffunit
from translate.storage.po import pounit
from translate.storage import mo
from translate.storage import factory
from trans.util import get_string
from translate.misc import quote
import os.path
import re
import hashlib
import importlib
import __builtin__


FILE_FORMATS = {}
FLAGS_RE = re.compile(r'\b[-\w]+\b')


def register_fileformat(fileformat):
    '''
    Registers fileformat in dictionary.
    '''
    FILE_FORMATS[fileformat.format_id] = fileformat


class FileUnit(object):
    '''
    Wrapper for translate-toolkit unit to cope with ID/template based
    translations.
    '''

    def __init__(self, unit, template=None):
        '''
        Creates wrapper object.
        '''
        self.unit = unit
        self.template = template
        if template is not None:
            self.mainunit = template
        else:
            self.mainunit = unit

    def get_locations(self):
        '''
        Returns comma separated list of locations.
        '''
        # XLIFF is special in ttkit - it uses locations for what
        # is context in other formats
        if isinstance(self.mainunit, xliffunit):
            return ''
        return ', '.join(self.mainunit.getlocations())

    def reformat_flags(self, typecomments):
        '''
        Processes flags from PO file to nicer form.
        '''
        # Grab flags
        flags = set(FLAGS_RE.findall('\n'.join(typecomments)))

        # Discard fuzzy flag, we don't care about that one
        flags.discard('fuzzy')

        # Join into string
        return ', '.join(flags)

    def get_flags(self):
        '''
        Returns flags (typecomments) from units.

        This is Gettext (po) specific feature.
        '''
        # Merge flags
        if hasattr(self.unit, 'typecomments'):
            return self.reformat_flags(self.unit.typecomments)
        elif hasattr(self.template, 'typecomments'):
            return self.reformat_flags(self.template.typecomments)
        else:
            return ''

    def get_comments(self):
        '''
        Returns comments (notes) from units.
        '''
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
        '''
        Checks whether unit is key = value based rather than
        translation.

        These are some files like PHP or properties, which for some
        reason do not correctly set source/target attributes.
        '''
        return (
            hasattr(self.mainunit, 'name')
            and hasattr(self.mainunit, 'value')
            and hasattr(self.mainunit, 'translation')
        )

    def get_source(self):
        '''
        Returns source string from a ttkit unit.
        '''
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
        '''
        Returns target string from a ttkit unit.
        '''
        if self.unit is None:
            return ''
        if self.is_unit_key_value():
            # Need to decode property encoded string
            if isinstance(self.unit, propunit):
                # This is basically stolen from
                # translate.storage.properties.propunit.gettarget
                # which for some reason does not return translation
                value = quote.propertiesdecode(self.unit.value)
                value = re.sub(u"\\\\ ", u" ", value)
                return value
            return self.unit.value
        else:
            return get_string(self.unit.target)

    def get_context(self):
        '''
        Returns context of message. In some cases we have to use
        ID here to make all backends consistent.
        '''
        # XLIFF is special in ttkit - it uses locations for what
        # is context in other formats
        if isinstance(self.mainunit, xliffunit):
            context = self.mainunit.getlocations()
            if len(context) == 0:
                return ''
            else:
                return context[0]
        elif isinstance(self.mainunit, pounit) and self.template is not None:
            # Monolingual PO files
            return self.template.source
        else:
            context = self.mainunit.getcontext()
        if self.is_unit_key_value() and context == '':
            return self.mainunit.getid()
        return context

    def get_previous_source(self):
        '''
        Returns previous message source if there was any.
        '''
        if not self.is_fuzzy() or not hasattr(self.unit, 'prev_source'):
            return ''
        return get_string(self.unit.prev_source)

    def get_checksum(self):
        '''
        Returns checksum of source string, used for quick lookup.

        We use MD5 as it is faster than SHA1.
        '''
        md5 = hashlib.md5()
        if self.template is None:
            md5.update(self.get_source().encode('utf-8'))
        md5.update(self.get_context().encode('utf-8'))
        return md5.hexdigest()

    def is_translated(self):
        '''
        Checks whether unit is translated.
        '''
        if self.unit is None:
            return False
        if self.is_unit_key_value():
            return not self.unit.isfuzzy() and self.unit.value != ''
        else:
            return self.unit.istranslated()

    def is_fuzzy(self):
        '''
        Checks whether unit is translated.
        '''
        if self.unit is None:
            return False
        return self.unit.isfuzzy()

    def is_translatable(self):
        '''
        Checks whether unit is translatable.

        For some reason, blank string does not mean non translatable
        unit in some formats (XLIFF), so lets skip those as well.
        '''
        return self.mainunit.istranslatable() and not self.mainunit.isblank()

    def set_target(self, target):
        '''
        Sets translation unit target.
        '''
        self.unit.settarget(target)
        # Propagate to value so that is_translated works correctly
        if self.is_unit_key_value():
            self.unit.value = self.unit.translation

    def mark_fuzzy(self, fuzzy):
        '''
        Sets fuzzy flag on translated unit.
        '''
        self.unit.markfuzzy(fuzzy)


class FileFormat(object):
    '''
    Generic object defining file format loader.
    '''
    name = ''
    format_id = ''
    loader = None
    monolingual = None

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
        self.storefile = storefile
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

        Returns tuple (ttkit_unit, created) indicating whether returned
        unit is new one.
        '''
        if self.has_template:
            # Need to create new unit based on template
            template_ttkit_unit = self.template_store.findid(context)
            # We search by ID when using template
            ttkit_unit = self.store.findid(context)
            # We always need new unit to translate
            if ttkit_unit is None:
                ttkit_unit = template_ttkit_unit
                add = True
            else:
                add = False

            return (FileUnit(ttkit_unit, template_ttkit_unit), add)
        else:
            # Find all units with same source
            found_units = self.store.findunits(source)
            # Find is broken for propfile, ignore results
            if len(found_units) > 0 and not isinstance(self.store, propfile):
                for ttkit_unit in found_units:
                    # Does context match?
                    if ttkit_unit.getcontext() == context:
                        return (FileUnit(ttkit_unit), False)
            else:
                # Fallback to manual find for value based files
                for ttkit_unit in self.store.units:
                    ttkit_unit = FileUnit(ttkit_unit)
                    if ttkit_unit.get_source() == source:
                        return (ttkit_unit, False)

        return (None, False)

    def add_unit(self, ttkit_unit):
        '''
        Adds new unit to underlaying store.
        '''
        if isinstance(self.store, LISAfile):
            # LISA based stores need to know this
            self.store.addunit(ttkit_unit.unit, new=True)
        else:
            self.store.addunit(ttkit_unit.unit)

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

    def all_units(self):
        '''
        Generator of all units.
        '''
        if not self.has_template:
            for tt_unit in self.store.units:

                # Create wrapper object
                yield FileUnit(tt_unit)
        else:
            for template_unit in self.template_store.units:

                # Create wrapper object (not translated)
                yield FileUnit(
                    self.store.findid(template_unit.getid()),
                    template_unit
                )

    @property
    def mimetype(self):
        '''
        Returns most common mime type for format.
        '''
        if self.store.Mimetypes is None:
            # Properties files do not expose mimetype
            return 'text/plain'
        else:
            return self.store.Mimetypes[0]

    @property
    def extension(self):
        '''
        Returns most common file extension for format.
        '''
        if self.store.Extensions is None:
            # Typo in translate-toolkit 1.9, see
            # https://github.com/translate/translate/pull/10
            if hasattr(self.store, 'Exensions'):
                return self.store.Exensions[0]
            else:
                return 'txt'
        else:
            return self.store.Extensions[0]

    def supports_language_pack(self):
        '''
        Checks whether backend store supports generating language pack.
        '''
        return hasattr(self, 'get_language_pack')


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

    def get_language_pack(self):
        '''
        Generates compiled messages file.
        '''
        outputfile = mo.mofile()
        for unit in self.store.units:
            if not unit.istranslated() and not unit.isheader():
                continue
            mounit = mo.mounit()
            if unit.isheader():
                mounit.source = ""
            else:
                mounit.source = unit.source
                mounit.msgctxt = [unit.getcontext()]
            mounit.target = unit.target
            outputfile.addunit(mounit)
        return str(outputfile)

    def get_language_pack_meta(self):
        '''
        Returns language pack filename and mime type.
        '''

        basefile = os.path.splitext(
            os.path.basename(self.storefile)
        )[0]

        return (
            '%s.mo' % basefile,
            'application/x-gettext-catalog'
        )

register_fileformat(PoFormat)


class PoMonoFormat(PoFormat):
    name = _('Gettext PO file (monolingual)')
    format_id = 'po-mono'
    loader = ('po', 'pofile')
    monolingual = True

register_fileformat(PoMonoFormat)


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

register_fileformat(AndroidFormat)

FILE_FORMAT_CHOICES = [(fmt, FILE_FORMATS[fmt].name) for fmt in FILE_FORMATS]
