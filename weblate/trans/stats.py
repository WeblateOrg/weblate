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

from __future__ import unicode_literals

from django.db.models import Sum

from weblate.lang.models import Language
from weblate.trans.models import Translation


def get_per_language_stats(project):
    """Calculates per language stats for project"""
    result = []

    # List languages
    languages = Translation.objects.filter(
        subproject__project=project
    ).values_list(
        'language',
        flat=True
    ).distinct()

    # Calculates total strings in project
    total = 0
    total_words = 0
    for component in project.subproject_set.all():
        try:
            translation = component.translation_set.all()[0]
            total += translation.total
            total_words += translation.total_words
        except IndexError:
            pass

    # Translated strings in language
    for language in Language.objects.filter(pk__in=languages):
        data = Translation.objects.filter(
            language=language,
            subproject__project=project
        ).aggregate(
            Sum('translated'),
            Sum('translated_words'),
        )

        translated = data['translated__sum']
        translated_words = data['translated_words__sum']

        # Insert sort
        pos = None
        for i in range(len(result)):
            if translated >= result[i][1]:
                pos = i
                break
        value = (language, translated, total, translated_words, total_words)
        if pos is not None:
            result.insert(pos, value)
        else:
            result.append(value)

    return result
