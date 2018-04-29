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

from weblate.lang.models import Language
from weblate.memory.storage import TranslationMemory
from weblate.machinery.base import MachineTranslation


class WeblateMemory(MachineTranslation):
    """Translation service using strings already translated in Weblate."""
    name = 'Weblate Translation Memory'
    rank_boost = 2
    cache_translations = False

    def convert_language(self, language):
        return Language.objects.get(code=language)

    def is_supported(self, source, language):
        """Any language is supported."""
        return True

    def format_unit_match(self, text, target, similarity, origin):
        """Format match to translation service result."""
        return (
            target,
            similarity,
            '{0} ({1})'.format(
                self.name,
                origin,
            ),
            text,
        )

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        memory = TranslationMemory()
        return [
            self.format_unit_match(*result)
            for result in memory.lookup(source.code, language.code, text)
        ]
