# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""Exporter using translate-toolkit"""
from __future__ import unicode_literals

import string

from django.http import HttpResponse

import six

from translate.misc.multistring import multistring
from translate.storage.po import pofile
from translate.storage.mo import mofile
from translate.storage.poxliff import PoXliffFile
from translate.storage.xliff import xlifffile
from translate.storage.tbx import tbxfile

import weblate
from weblate.trans.formats import FileFormat
from weblate.trans.site import get_site_url

if six.PY2:
    _CHARMAP2 = string.maketrans('', '')[:32]
_CHARMAP = dict.fromkeys(range(32))

EXPORTERS = {}


def register_exporter(exporter):
    """Registerss exporter"""
    EXPORTERS[exporter.name] = exporter
    return exporter


def get_exporter(name):
    """Returns registered exporter"""
    return EXPORTERS[name]


class BaseExporter(object):
    content_type = 'text/plain'
    extension = 'txt'
    name = ''
    has_lang = False

    def __init__(self, project=None, language=None, url=None,
                 translation=None):
        if translation is not None:
            self.project = translation.subproject.project
            self.language = translation.language
            self.url = get_site_url(translation.get_absolute_url())
        else:
            self.project = project
            self.language = language
            self.url = url
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
        else:
            return multistring(
                [self.string_filter(plural) for plural in plurals]
            )

    def get_storage(self):
        raise NotImplementedError()

    def add_dictionary(self, word):
        """Adds dictionary word"""
        unit = self.storage.UnitClass(self.string_filter(word.source))
        if self.has_lang:
            unit.settarget(self.string_filter(word.target), self.language.code)
        else:
            unit.target = word.target
        self.storage.addunit(unit)

    def add_units(self, translation):
        for unit in translation.unit_set.iterator():
            self.add_unit(unit)

    def add_unit(self, unit):
        output = self.storage.UnitClass(
            self.handle_plurals(unit.get_source_plurals())
        )
        output.target = multistring(
            self.handle_plurals(unit.get_target_plurals())
        )
        output.setcontext(self.string_filter(unit.context))
        if hasattr(output, 'msgctxt'):
            output.msgctxt = [self.string_filter(unit.context)]
        for location in unit.location.split():
            if location:
                output.addlocation(location)
        output.addnote(self.string_filter(unit.comment))
        if hasattr(output, 'settypecomment'):
            for flag in unit.flags.split(','):
                output.settypecomment(flag)
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
        response.write(FileFormat.serialize(self.storage))

        return response

    def serialize(self):
        """Returns storage content"""
        return FileFormat.serialize(self.storage)


@register_exporter
class PoExporter(BaseExporter):
    name = 'po'
    content_type = 'text/x-po'
    extension = 'po'
    has_lang = False

    def get_storage(self):
        store = pofile()

        # Set po file header
        store.updateheader(
            add=True,
            language=self.language.code,
            x_generator='Weblate %s' % weblate.VERSION,
            project_id_version='%s (%s)' % (
                self.language.name, self.project.name
            ),
            plural_forms=self.language.get_plural_form(),
            language_team='%s <%s>' % (
                self.language.name,
                self.url,
            )
        )
        return store


class XMLExporter(BaseExporter):
    """Wrapper for XML based exporters to strip control chars"""

    def string_filter(self, text):
        if six.PY2 and not isinstance(text, six.text_type):
            return text.translate(None, _CHARMAP2)
        else:
            return text.translate(_CHARMAP)

    def get_storage(self):
        raise NotImplementedError()


@register_exporter
class PoXliffExporter(XMLExporter):
    name = 'xliff'
    content_type = 'application/x-xliff+xml'
    extension = 'xlf'
    has_lang = True

    def get_storage(self):
        return PoXliffFile()


@register_exporter
class XliffExporter(XMLExporter):
    name = 'xliff12'
    content_type = 'application/x-xliff+xml'
    extension = 'xlf'
    has_lang = True

    def get_storage(self):
        return xlifffile()


@register_exporter
class TBXExporter(XMLExporter):
    name = 'tbx'
    content_type = 'application/x-tbx'
    extension = 'tbx'
    has_lang = True

    def get_storage(self):
        return tbxfile()


@register_exporter
class MoExporter(BaseExporter):
    name = 'mo'
    content_type = 'application/x-gettext-catalog'
    extension = 'mo'
    has_lang = False

    def get_storage(self):
        store = mofile()

        # Set po file header
        store.updateheader(
            add=True,
            language=self.language.code,
            x_generator='Weblate %s' % weblate.VERSION,
            project_id_version='%s (%s)' % (
                self.language.name, self.project.name
            ),
            plural_forms=self.language.get_plural_form(),
            language_team='%s <%s>' % (
                self.language.name,
                self.url,
            )
        )
        return store

    def add_unit(self, unit):
        if not unit.translated:
            return
        super(MoExporter, self).add_unit(unit)
