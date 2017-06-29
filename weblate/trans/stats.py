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

from django.db.models import Sum
from django.utils.encoding import force_text

from weblate.lang.models import Language
from weblate.trans.models import Translation
from weblate.trans.util import translation_percent


def get_per_language_stats(project, lang=None):
    """Calculate per language stats for project"""
    result = []

    language_objects = Language.objects.filter(
        translation__subproject__project=project
    )

    if lang:
        language_objects = language_objects.filter(pk=lang.pk)

    # List languages
    languages = {
        language.pk: language for language in language_objects
    }

    # Translated strings in language
    data = Translation.objects.filter(
        language__pk__in=languages.keys(),
        subproject__project=project
    ).values(
        'language'
    ).annotate(
        Sum('translated'),
        Sum('translated_words'),
        Sum('total'),
        Sum('total_words'),
    ).order_by()
    for item in data:
        translated = item['translated__sum']
        total = item['total__sum']
        if total == 0:
            percent = 0
        else:
            percent = int(100 * translated / total)

        # Insert sort
        pos = None
        for i, data in enumerate(result):
            if percent >= data[5]:
                pos = i
                break

        value = (
            languages[item['language']],
            translated,
            total,
            item['translated_words__sum'],
            item['total_words__sum'],
            percent,
        )
        if pos is not None:
            result.insert(pos, value)
        else:
            result.append(value)

    return result


def get_project_stats(project):
    """Return stats for project"""
    return [
        {
            'language': force_text(tup[0]),
            'code': tup[0].code,
            'total': tup[2],
            'translated': tup[1],
            'translated_percent': translation_percent(tup[1], tup[2]),
            'total_words': tup[4],
            'translated_words': tup[3],
            'words_percent': translation_percent(tup[3], tup[4])
        }
        for tup in get_per_language_stats(project)
    ]
