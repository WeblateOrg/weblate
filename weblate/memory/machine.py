# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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
from weblate.machinery.base import MachineTranslation
from weblate.memory.storage import TranslationMemory, get_category_name


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

    def format_unit_match(self, text, target, similarity, category, origin):
        """Format match to translation service result."""
        return {
            'text': target,
            'quality': similarity,
            'service': self.name,
            'origin': get_category_name(category, origin),
            'source': text,
        }

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        memory = TranslationMemory.get_thread_instance()
        memory.refresh()
        results = memory.lookup(
            source.code, language.code, text,
            user,
            unit.translation.component.project,
            unit.translation.component.project.use_shared_tm,
        )
        return [self.format_unit_match(*result) for result in results]
