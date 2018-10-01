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
"""Exporter using translate-toolkit"""
from __future__ import unicode_literals

from django.http import HttpResponse
from django.utils.translation import ugettext_lazy as _

from translate.misc.multistring import multistring
from translate.storage.po import pofile
from translate.storage.mo import mofile, mounit
from translate.storage.poxliff import PoXliffFile
from translate.storage.xliff import xlifffile
from translate.storage.tbx import tbxfile
from translate.storage.tmx import tmxfile
from translate.storage.csvl10n import csvfile

import weblate
from weblate.formats.base import FileFormat
from weblate.formats.external import XlsxFormat
from weblate.utils.site import get_site_url

# Map to remove control chars except newlines and tabs
_CHARMAP = dict.fromkeys(
    x for x in range(32) if x not in (9, 10, 13)
)

EXPORTERS = {}


def register_exporter(exporter):
    """Register an exporter."""
    EXPORTERS[exporter.name] = exporter
    return exporter


def get_exporter(name):
    """Return registered exporter"""
    return EXPORTERS[name]


def list_exporters():
    return [
        {'name': x.name, 'verbose': x.verbose}
        for x in sorted(EXPORTERS.values(), key=lambda x: x.name)
    ]


class BaseExporter(object):
    content_type = 'text/plain'
    extension = 'txt'
    name = ''
    verbose = ''
    set_id = False

    def __init__(self, project=None, language=None, url=None,
                 translation=None, fieldnames=None):
        if translation is not None:
            self.project = translation.component.project
            self.language = translation.language
            self.url = get_site_url(translation.get_absolute_url())
        else:
            self.project = project
            self.language = language
            self.url = url
        self.fieldnames = fieldnames
        self.storage = self.get_storage()
        self.storage.setsourcelanguage(
            self.project.source_language.code
        )
        self.storage.settargetlanguage(
            self.language.code
        )

    def string_filter(self, text):
        return text

    def handle_plurals(self, plurals):
        if len(plurals) == 1:
            return self.string_filter(plurals[0])
        return multistring(
            [self.string_filter(plural) for plural in plurals]
        )

    def get_storage(self):
        raise NotImplementedError()

    def add(self, unit, word):
        unit.target = word

    def add_dictionary(self, word):
        """Add dictionary word"""
        unit = self.storage.UnitClass(self.string_filter(word.source))
        self.add(unit, self.string_filter(word.target))
        self.storage.addunit(unit)

    def add_units(self, units):
        for unit in units.iterator():
            self.add_unit(unit)

    def add_unit(self, unit):
        output = self.storage.UnitClass(
            self.handle_plurals(unit.get_source_plurals())
        )
        self.add(output, self.handle_plurals(unit.get_target_plurals()))
        # Location needs to be set prior to ID to avoid overwrite
        # on some formats (eg. xliff)
        for location in unit.location.split():
            if location:
                output.addlocation(location)

        # Store context as context and ID
        context = self.string_filter(unit.context)
        if context:
            output.setcontext(context)
            if isinstance(output, mounit):
                output.msgctxt = [context]
            if self.set_id:
                output.setid(context)
        elif self.set_id:
            # Use checksum based ID on formats requiring it
            output.setid(unit.checksum)

        # Store note
        note = self.string_filter(unit.comment)
        if note:
            output.addnote(note, origin='developer')

        # Set type comment (for Gettext)
        if hasattr(output, 'settypecomment'):
            for flag in unit.flags.split(','):
                if flag:
                    output.settypecomment(flag)

        # Store fuzzy flag
        if unit.fuzzy:
            output.markfuzzy(True)

        self.storage.addunit(output)

    def get_response(self, filetemplate='{project}-{language}.{extension}'):
        filename = filetemplate.format(
            project=self.project.slug,
            language=self.language.code,
            extension=self.extension
        )

        response = HttpResponse(
            content_type='{0}; charset=utf-8'.format(self.content_type)
        )
        response['Content-Disposition'] = 'attachment; filename={0}'.format(
            filename
        )

        # Save to response
        response.write(self.serialize())

        return response

    def serialize(self):
        """Return storage content"""
        return FileFormat.serialize(self.storage)


@register_exporter
class PoExporter(BaseExporter):
    name = 'po'
    content_type = 'text/x-po'
    extension = 'po'
    verbose = _('gettext PO')

    def get_storage(self):
        store = pofile()
        plural = self.language.plural

        # Set po file header
        store.updateheader(
            add=True,
            language=self.language.code,
            x_generator='Weblate {0}'.format(weblate.VERSION),
            project_id_version='{0} ({1})'.format(
                self.language.name, self.project.name
            ),
            plural_forms=plural.plural_form,
            language_team='{0} <{1}>'.format(
                self.language.name,
                self.url
            )
        )
        return store


class XMLExporter(BaseExporter):
    """Wrapper for XML based exporters to strip control chars"""

    def string_filter(self, text):
        return text.translate(_CHARMAP)

    def get_storage(self):
        raise NotImplementedError()

    def add(self, unit, word):
        unit.settarget(word, self.language.code)


@register_exporter
class PoXliffExporter(XMLExporter):
    name = 'xliff'
    content_type = 'application/x-xliff+xml'
    extension = 'xlf'
    set_id = True
    verbose = _('XLIFF with gettext extensions')

    def get_storage(self):
        return PoXliffFile()


@register_exporter
class XliffExporter(XMLExporter):
    name = 'xliff11'
    content_type = 'application/x-xliff+xml'
    extension = 'xlf'
    set_id = True
    verbose = _('XLIFF 1.1')

    def get_storage(self):
        return xlifffile()


@register_exporter
class TBXExporter(XMLExporter):
    name = 'tbx'
    content_type = 'application/x-tbx'
    extension = 'tbx'
    verbose = _('TBX')

    def get_storage(self):
        return tbxfile()


@register_exporter
class TMXExporter(XMLExporter):
    name = 'tmx'
    content_type = 'application/x-tmx'
    extension = 'tmx'
    verbose = _('TMX')

    def get_storage(self):
        return tmxfile()


@register_exporter
class MoExporter(BaseExporter):
    name = 'mo'
    content_type = 'application/x-gettext-catalog'
    extension = 'mo'
    verbose = _('gettext MO')

    def get_storage(self):
        store = mofile()
        plural = self.language.plural

        # Set po file header
        store.updateheader(
            add=True,
            language=self.language.code,
            x_generator='Weblate {0}'.format(weblate.VERSION),
            project_id_version='{0} ({1})'.format(
                self.language.name, self.project.name
            ),
            plural_forms=plural.plural_form,
            language_team='{0} <{1}>'.format(
                self.language.name,
                self.url
            )
        )
        return store

    def add_unit(self, unit):
        if not unit.translated:
            return
        super(MoExporter, self).add_unit(unit)


@register_exporter
class CSVExporter(BaseExporter):
    name = 'csv'
    content_type = 'text/csv'
    extension = 'csv'
    verbose = _('CSV')

    def get_storage(self):
        return csvfile(fieldnames=self.fieldnames)

    def string_filter(self, text):
        """Avoid Excel interpreting text as formula.

        This is really bad idea, implemented in Excel, as this change leads
        to displaying additional ' in all other tools, but this seems to be
        what most people have gotten used to. Hopefully these chars are not
        widely used at first position of translatable strings, so that harm is
        reduced.
        """
        if text and text[0] in ('=', '+', '-', '@', '|', '%'):
            return "'{0}'".format(text.replace('|', '\\|'))
        return text


@register_exporter
class XlsxExporter(BaseExporter):
    name = 'xlsx'
    content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    extension = 'xlsx'
    verbose = _('Excel Open XML')

    def get_storage(self):
        return csvfile(fieldnames=self.fieldnames)

    def serialize(self):
        """Return storage content"""
        return XlsxFormat.serialize(self.storage)
