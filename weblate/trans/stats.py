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

from __future__ import unicode_literals

from django.utils.encoding import force_text


def get_project_stats(project):
    """Return stats for project"""
    return [
        {
            'language': force_text(tup.language.name),
            'code': tup.language.code,
            'total': tup.all,
            'translated': tup.translated,
            'translated_percent': tup.translated_percent,
            'total_words': tup.all_words,
            'translated_words': tup.translated_words,
            'words_percent': tup.translated_words_percent,
        }
        for tup in project.stats.get_language_stats()
    ]
