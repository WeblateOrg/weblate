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

from django.http import HttpResponse

from translate.misc.multistring import multistring
from translate.storage.po import pofile
from translate.storage.xliff import xlifffile
from translate.storage.tbx import tbxfile

import weblate
from weblate.trans.formats import FileFormat


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

    def __init__(self, project, language, url):
        self.project = project
        self.language = language
        self.url = url
        self.storage = self.get_storage()
        self.storage.setsourcelanguage(project.source_language.code)
        self.storage.settargetlanguage(language.code)

    def get_storage(self):
        raise NotImplementedError()

    def add_dictionary(self, word):
        """Adds dictionary word"""
        unit = self.storage.UnitClass(word.source)
        if self.has_lang:
            unit.settarget(word.target, self.language.code)
        else:
            unit.target = word.target
        self.storage.addunit(unit)

    def add_unit(self, unit):
        if unit.is_plural():
            output = self.storage.UnitClass(
                multistring(unit.get_source_plurals())
            )
            output.target = multistring(unit.get_target_plurals())
        else:
            output = self.storage.UnitClass(unit.source)
            output.target = unit.target
        output.context = unit.context
        for location in unit.location.split():
            if location:
                output.addlocation(location)
        output.addnote(unit.comment)
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


@register_exporter
class XliffExporter(BaseExporter):
    name = 'xliff'
    content_type = 'application/x-xliff+xml'
    extension = 'xlf'
    has_lang = True

    def get_storage(self):
        return xlifffile()


@register_exporter
class TBXExporter(BaseExporter):
    name = 'tbx'
    content_type = 'application/x-tbx'
    extension = 'tbx'
    has_lang = True

    def get_storage(self):
        return tbxfile()
