# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

import os.path

from django.db import models
from django.utils.encoding import python_2_unicode_compatible

from translate.misc.xml_helpers import getXMLlang, getXMLspace
from translate.storage.tmx import tmxfile

from weblate.lang.models import Language


def get_node_data(unit, node):
    """Generic implementation of LISAUnit.gettarget."""
    return (
        getXMLlang(node),
        unit.getNodeText(
            node, getXMLspace(unit.xmlelement, unit._default_xml_space)
        )
    )


class MemoryManager(models.Manager):
    def import_tmx(self, fileobj):
        origin = os.path.basename(fileobj.name)
        storage = tmxfile.parsefile(fileobj)
        header = next(
            storage.document.getroot().iterchildren(storage.namespaced("header"))
        )
        source_language_code = header.get('srclang')
        source_language = Language.objects.auto_get_or_create(
            source_language_code
        )

        languages = {}

        for unit in storage.units:
            # Parse translations (translate-toolkit does not care about
            # languages here, it just picks first and second XML elements)
            translations = {}
            for node in unit.getlanguageNodes():
                lang, text = get_node_data(unit, node)
                translations[lang] = text
                if lang not in languages:
                    languages[lang] = Language.objects.auto_get_or_create(lang)

            try:
                source = translations.pop(source_language_code)
            except KeyError:
                # Skip if source language is not present
                continue

            for lang, text in translations.items():
                self.get_or_create(
                    source_language=source_language,
                    target_language=languages[lang],
                    source=source,
                    target=text,
                    origin=origin,
                )


@python_2_unicode_compatible
class Memory(models.Model):
    source_language = models.ForeignKey(
        Language,
        related_name='memory_source',
    )
    target_language = models.ForeignKey(
        Language,
        related_name='memory_target',
    )
    source = models.TextField()
    target = models.TextField()
    origin = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    objects = MemoryManager()

    class Meta(object):
        ordering = ['source']
        index_together = [
            ('source_language', 'source'),
        ]

    def __str__(self):
        return '{} ({}): {} ({})'.format(
            self.source,
            self.source_language,
            self.target,
            self.target_language,
        )
