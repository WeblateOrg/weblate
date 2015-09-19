# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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
from translate.storage.xliff import xliffunit, xlifffile
from translate.storage.po import pounit, pofile
from translate.storage.php import phpunit
from translate.storage.ts2 import tsunit
from translate.storage import mo
from translate.storage import factory
from weblate.trans.util import get_string, join_plural, add_configuration_error
from translate.misc import quote
from weblate.trans.util import get_clean_env, calculate_checksum
import weblate
import subprocess
import os.path
import re
import csv
import traceback
import importlib
from StringIO import StringIO
import __builtin__


FILE_FORMATS = {}
FILE_DETECT = []
FLAGS_RE = re.compile(r'\b[-\w]+\b')
LOCATIONS_RE = re.compile(r'^([+-]|.*, [+-]|.*:[+-])')


class ParseError(Exception):
    """Generic error for parsing."""


class StringIOMode(StringIO):
    """
    StringIO with mode attribute to make ttkit happy.
    """
    def __init__(self, filename, data):
        StringIO.__init__(self, data)
        self.mode = 'r'
        self.name = filename


def register_fileformat(fileformat):
    '''
    Registers fileformat in dictionary.
    '''
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
        self.checksum = None
        self.contentsum = None

    def get_locations(self):
        '''
        Returns comma separated list of locations.
        '''
        # JSON, XLIFF and PHP are special in ttkit - it uses locations for what
        # is context in other formats
        if (isinstance(self.mainunit, xliffunit) or
                isinstance(self.mainunit, propunit) or
                isinstance(self.mainunit, phpunit)):
            return ''
        result = ', '.join(self.mainunit.getlocations())
        # Do not try to handle relative locations in Qt TS, see
        # http://qt-project.org/doc/qt-4.8/linguist-ts-file-format.html
        if LOCATIONS_RE.match(result):
            return ''
        return result

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
            hasattr(self.mainunit, 'name') and
            hasattr(self.mainunit, 'value') and
            hasattr(self.mainunit, 'translation')
        )

    def get_source(self):
        '''
        Returns source string from a ttkit unit.
        '''
        if (isinstance(self.mainunit, tsunit) and
                self.template is None and
                self.mainunit.hasplural()):
            # Need to apply special magic for plurals here
            # as there is no singlular/plural in the source string
            return join_plural([
                self.unit.source,
                self.unit.source,
            ])
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
        if (isinstance(self.unit, tsunit) and
                not self.unit.isreview() and
                not self.unit.istranslated()):
            # For Qt ts, empty translated string means source should be used
            return self.get_source()
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
            # Monolingual JSON files
            return self.template.getid()
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
        if self.checksum is None:
            if self.template is None:
                self.checksum = calculate_checksum(
                    self.get_source(), self.get_context()
                )
            else:
                self.checksum = calculate_checksum(
                    None, self.get_context()
                )

        return self.checksum

    def get_contentsum(self):
        '''
        Returns checksum of source string and context, used for quick lookup.

        We use MD5 as it is faster than SHA1.
        '''
        if self.template is None:
            return self.get_checksum()

        if self.contentsum is None:
            self.contentsum = calculate_checksum(
                self.get_source(), self.get_context()
            )

        return self.contentsum

    def is_translated(self):
        '''
        Checks whether unit is translated.
        '''
        if self.unit is None:
            return False
        if self.is_unit_key_value():
            return not self.unit.isfuzzy() and self.unit.value != ''
        elif isinstance(self.mainunit, tsunit):
            # For Qt ts, empty translated string means source should be used
            return not self.unit.isreview() or self.unit.istranslated()
        else:
            return self.unit.istranslated()

    def is_fuzzy(self):
        '''
        Checks whether unit is translated.
        '''
        if self.unit is None:
            return False
        return self.unit.isfuzzy()

    def is_obsolete(self):
        '''
        Checks whether unit is marked as obsolete in backend.
        '''
        return self.mainunit.isobsolete()

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


class JSONUnit(FileUnit):
    def get_locations(self):
        return ''

    def get_source(self):
        if self.template is None:
            return self.mainunit.getid().lstrip('.')
        return get_string(self.template.target)

    def get_context(self):
        if self.template is not None:
            # Monolingual JSON files
            return self.template.getid()
        else:
            return self.mainunit.getcontext()

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


class FileFormat(object):
    '''
    Generic object defining file format loader.
    '''
    name = ''
    format_id = ''
    loader = (None, None)
    monolingual = None
    check_flags = ()
    unit_class = FileUnit
    new_translation = None
    autoload = ()

    @classmethod
    def parse(cls, storefile, template_store=None, language_code=None):
        """Parses store and returns FileFormat instance."""
        return cls(storefile, template_store, language_code)

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
        if ('_' in __builtin__.__dict__ and
                not callable(__builtin__.__dict__['_'])):
            del __builtin__.__dict__['_']

        # Add missing mode attribute to Django file wrapper
        if (not isinstance(storefile, basestring) and
                not hasattr(storefile, 'mode')):
            storefile.mode = 'r'

        return cls.parse_store(storefile)

    @classmethod
    def get_class(cls):
        """
        Returns class for handling this module.
        """
        # Tuple style loader, import from translate toolkit
        module_name, class_name = cls.loader
        if '.' not in module_name:
            module_name = 'translate.storage.{0}'.format(module_name)
        module = importlib.import_module(module_name)

        # Get the class
        return getattr(module, class_name)

    @classmethod
    def parse_store(cls, storefile):
        """
        Parses the store.
        """
        storeclass = cls.get_class()

        # Parse file
        store = storeclass.parsefile(storefile)

        # Apply possible fixups and return
        return cls.fixup(store)

    def __init__(self, storefile, template_store=None, language_code=None):
        '''
        Creates file format object, wrapping up translate-toolkit's
        store.
        '''
        self.storefile = storefile
        # Load store
        self.store = self.load(storefile)
        # Check store validity
        if not self.is_valid(self.store):
            raise ValueError('Invalid file format')
        # Remember template
        self.template_store = template_store
        # Set language (needed for some which do not include this)
        if (language_code is not None and
                self.store.gettargetlanguage() is None):
            self.store.settargetlanguage(language_code)

    @property
    def has_template(self):
        '''
        Checks whether class is using template.
        '''
        return (
            (self.monolingual or self.monolingual is None) and
            self.template_store is not None
        )

    def _find_unit_template(self, context):
        # Need to create new unit based on template
        template_ttkit_unit = self.template_store.findid(context)
        # We search by ID when using template
        ttkit_unit = self.store.findid(context)
        # Do not use findid as it does not work for empty translations
        if ttkit_unit is None:
            for search_unit in self.store.units:
                if search_unit.getid() == context:
                    ttkit_unit = search_unit
        # We always need new unit to translate
        if ttkit_unit is None:
            ttkit_unit = template_ttkit_unit
            if template_ttkit_unit is None:
                raise Exception(
                    'Could not find template unit for new unit!'
                )
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
                # XLIFF is special in ttkit - it uses locations for what
                # is context in other formats
                if isinstance(ttkit_unit, xliffunit):
                    ttkit_unit_context = ttkit_unit.getlocations()
                    if len(ttkit_unit.getlocations()) == 0:
                        ttkit_unit_context = ''
                    else:
                        ttkit_unit_context = ttkit_unit.getlocations()[0]
                else:
                    ttkit_unit_context = ttkit_unit.getcontext()
                # Does context match?
                if ttkit_unit_context == context:
                    return (self.unit_class(ttkit_unit), False)
        else:
            # Fallback to manual find for value based files
            for ttkit_unit in self.store.units:
                ttkit_unit = self.unit_class(ttkit_unit)
                if ttkit_unit.get_source() == source:
                    return (ttkit_unit, False)
        return (None, False)

    def find_unit(self, context, source):
        '''
        Finds unit by context and source.

        Returns tuple (ttkit_unit, created) indicating whether returned
        unit is new one.
        '''
        if self.has_template:
            return self._find_unit_template(context)
        else:
            return self._find_unit_bilingual(context, source)

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

        kwargs['x_generator'] = 'Weblate %s' % weblate.VERSION

        # Adjust Content-Type header if needed
        header = self.store.parseheader()
        if ('Content-Type' not in header or
                'charset=CHARSET' in header['Content-Type'] or
                'charset=ASCII' in header['Content-Type']):
            kwargs['Content_Type'] = 'text/plain; charset=UTF-8'

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
                yield self.unit_class(tt_unit)
        else:
            for template_unit in self.template_store.units:

                # Create wrapper object (not translated)
                yield self.unit_class(
                    self.store.findid(template_unit.getid()),
                    template_unit
                )

    def count_units(self):
        '''
        Returns count of units.
        '''
        if not self.has_template:
            return len(self.store.units)
        else:
            return len(self.template_store.units)

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

    @classmethod
    def supports_language_pack(cls):
        '''
        Checks whether backend store supports generating language pack.
        '''
        return hasattr(cls, 'get_language_pack')

    @classmethod
    def is_valid(cls, store):
        '''
        Checks whether store seems to be valid.

        In some cases ttkit happily "parses" the file, even though it
        really did not do so (eg. Gettext parser on random text file).
        '''
        if store is None:
            return False

        if cls.monolingual is False and str(store) == '':
            return False

        return True

    @classmethod
    def supports_new_language(cls):
        '''
        Whether it supports creating new translation.
        '''
        return cls.new_translation is not None

    @staticmethod
    def is_valid_base_for_new(base):
        '''
        Checks whether base is valid.
        '''
        return True

    @staticmethod
    def get_language_code(code):
        """
        Does any possible formatting needed for language code.
        """
        return code

    @classmethod
    def get_language_filename(cls, mask, code):
        """
        Return full filename of a language file for given
        path, filemask and language code.
        """
        return mask.replace('*', cls.get_language_code(code))

    @classmethod
    def add_language(cls, filename, code, base):
        '''
        Adds new language file.
        '''
        # Create directory for a translation
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        cls.create_new_file(filename, code, base)

    @classmethod
    def create_new_file(cls, filename, code, base):
        """Handles creation of new translation file."""
        if cls.new_translation is None:
            raise ValueError('Not supported')

        with open(filename, 'w') as output:
            output.write(cls.new_translation)

    def iterate_merge(self, fuzzy, header=False):
        """Iterates over units for merging.

        Note: This can change fuzzy state of units!
        """
        for unit in self.all_units():
            # Handle header
            if unit.unit and unit.unit.isheader():
                if header:
                    yield False, unit
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


@register_fileformat
class AutoFormat(FileFormat):
    name = _('Automatic detection')
    format_id = 'auto'

    @classmethod
    def parse(cls, storefile, template_store=None, language_code=None):
        """Parses store and returns FileFormat instance.

        First attempt own autodetection, then fallback to ttkit.
        """
        filename = getattr(storefile, 'name', None)
        if filename is not None:
            name = os.path.basename(filename)
            for autoload, storeclass in FILE_DETECT:
                if not isinstance(autoload, tuple) and name.endswith(autoload):
                    return storeclass(storefile, template_store, language_code)
                elif (name.startswith(autoload[0]) and
                      name.endswith(autoload[1])):
                    return storeclass(storefile, template_store, language_code)
        return cls(storefile, template_store, language_code)

    @classmethod
    def parse_store(cls, storefile):
        '''
        Directly loads using translate-toolkit.
        '''
        return factory.getobject(storefile)

    @classmethod
    def get_class(cls):
        return None


@register_fileformat
class PoFormat(FileFormat):
    name = _('Gettext PO file')
    format_id = 'po'
    loader = ('po', 'pofile')
    monolingual = False
    msginit_found = None
    autoload = ('.po', '.pot')

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
                context = unit.getcontext()
                if context:
                    mounit.msgctxt = [context]
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

    @classmethod
    def supports_new_language(cls):
        '''
        Checks whether we can create new language file.
        '''
        if cls.msginit_found is None:
            try:
                ret = subprocess.check_call(
                    ['msginit', '--help'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=get_clean_env(),
                )
                cls.msginit_found = (ret == 0)
            except subprocess.CalledProcessError:
                cls.msginit_found = False
        return cls.msginit_found

    @staticmethod
    def is_valid_base_for_new(base):
        '''
        Checks whether base is valid.
        '''
        try:
            pofile.parsefile(base)
            return True
        except Exception:
            return False

    @classmethod
    def create_new_file(cls, filename, code, base):
        """Handles creation of new translation file."""
        with open(base, 'r') as handle:
            data = handle.read()
        # Assume input is UTF-8 if not specified
        if 'Content-Type: text/plain; charset=CHARSET' in data:
            data = data.replace(
                'Content-Type: text/plain; charset=CHARSET',
                'Content-Type: text/plain; charset=UTF-8'
            )
        process = subprocess.Popen(
            [
                'msginit',
                '--input', '-',
                '--output', filename,
                '--no-translator',
                '--locale', code
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=get_clean_env(),
        )
        output, output_err = process.communicate(input=data)
        retcode = process.poll()
        if retcode:
            raise ValueError(output_err if output_err else output)


@register_fileformat
class PoMonoFormat(PoFormat):
    name = _('Gettext PO file (monolingual)')
    format_id = 'po-mono'
    loader = ('po', 'pofile')
    monolingual = True


@register_fileformat
class TSFormat(FileFormat):
    name = _('Qt Linguist Translation File')
    format_id = 'ts'
    loader = ('ts2', 'tsfile')
    autoload = ('.ts',)


@register_fileformat
class XliffFormat(FileFormat):
    name = _('XLIFF Translation File')
    format_id = 'xliff'
    loader = ('xliff', 'xlifffile')
    autoload = ('.xlf', '.xliff')

    @classmethod
    def supports_new_language(cls):
        '''
        Checks whether we can create new language file.
        '''
        return True

    @staticmethod
    def is_valid_base_for_new(base):
        '''
        Checks whether base is valid.
        '''
        try:
            xlifffile.parsefile(base)
            return True
        except Exception:
            return False

    @classmethod
    def create_new_file(cls, filename, code, base):
        """Handles creation of new translation file."""
        content = xlifffile.parsefile(base)
        content.settargetlanguage(code)
        content.savefile(filename)


@register_fileformat
class StringsFormat(FileFormat):
    name = _('OS X Strings')
    format_id = 'strings'
    loader = ('properties', 'stringsfile')
    new_translation = '\n'
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
        '''
        Java properties need to be iso-8859-1, but
        ttkit converts them to utf-8.

        This will be fixed in translate-toolkit 1.14.0, we could then
        merge utf-16 and this one as the encoding detection should do
        the correct magic then.
        '''
        store.encoding = 'iso-8859-1'
        return store


@register_fileformat
class PhpFormat(FileFormat):
    name = _('PHP strings')
    format_id = 'php'
    loader = ('php', 'phpfile')
    new_translation = '<?php\n'
    autoload = ('.php',)

    @property
    def mimetype(self):
        '''
        Returns most common mime type for format.
        '''
        return 'text/x-php'

    @property
    def extension(self):
        '''
        Returns most common file extension for format.
        '''
        return 'php'


@register_fileformat
class RESXFormat(FileFormat):
    name = _('.Net resource file')
    format_id = 'resx'
    loader = ('resx', 'RESXFile')
    monolingual = True
    unit_class = RESXUnit
    new_translation = (
        '<?xml version="1.0" encoding="utf-8"?>\n<root></root>'
    )
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
    new_translation = (
        '<?xml version="1.0" encoding="utf-8"?>\n<resources></resources>'
    )
    autoload = (('strings', '.xml'),)

    @staticmethod
    def get_language_code(code):
        """
        Does any possible formatting needed for language code.
        """
        return code.replace('_', '-r')


@register_fileformat
class JSONFormat(FileFormat):
    name = _('JSON file')
    format_id = 'json'
    loader = ('weblate.trans.aresource', 'JsonFile')
    unit_class = JSONUnit
    autoload = ('.json',)

    @classmethod
    def supports_new_language(cls):
        '''
        Checks whether we can create new language file.
        '''
        return True

    @classmethod
    def create_new_file(cls, filename, code, base):
        """Handles creation of new translation file."""
        content = '{}\n'
        if base:
            with open(base, 'r') as handle:
                content = handle.read()
        with open(filename, 'w') as output:
            output.write(content)

    @property
    def mimetype(self):
        '''
        Returns most common mime type for format.
        '''
        return 'application/json'

    @property
    def extension(self):
        '''
        Returns most common file extension for format.
        '''
        return 'json'


@register_fileformat
class CSVFormat(FileFormat):
    name = _('CSV file')
    format_id = 'csv'
    loader = ('csvl10n', 'csvfile')
    unit_class = JSONUnit
    autoload = ('.csv',)

    @property
    def mimetype(self):
        '''
        Returns most common mime type for format.
        '''
        return 'text/csv'

    @property
    def extension(self):
        '''
        Returns most common file extension for format.
        '''
        return 'csv'

    @classmethod
    def parse_store(cls, storefile):
        """
        Parses the store.
        """
        storeclass = cls.get_class()

        # Read content for fixups
        content = storefile.read()
        storefile.seek(0)

        # Parse file
        store = storeclass.parsefile(storefile)

        # Did headers detection work?
        if store.fieldnames != ['location', 'source', 'target']:
            return store

        fileobj = StringIOMode(storefile.name, content)

        # Try reading header
        reader = csv.reader(fileobj, store.dialect)
        header = reader.next()

        # We seem to have match
        if len(header) != 2:
            fileobj.close()
            return store

        fileobj.seek(0)
        return storeclass(fileobj, ['source', 'target'])


FILE_FORMAT_CHOICES = [
    (fmt, FILE_FORMATS[fmt].name) for fmt in sorted(FILE_FORMATS)
]
