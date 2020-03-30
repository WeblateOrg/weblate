#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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


from django.utils.encoding import force_str

from weblate.machinery.base import MachineTranslation
from weblate.trans.models import Unit
from weblate.utils.state import STATE_TRANSLATED


class WeblateTranslation(MachineTranslation):
    """Translation service using strings already translated in Weblate."""

    name = "Weblate"
    rank_boost = 1
    cache_translations = False

    def convert_language(self, language):
        """No conversion of language object."""
        return language

    def is_supported(self, source, language):
        """Any language is supported."""
        return True

    def download_translations(self, source, language, text, unit, user, search):
        """Download list of possible translations from a service."""
        if user:
            kwargs = {
                "translation__component__project_id__in": user.allowed_project_ids
            }
        else:
            kwargs = {
                "translation__component__project": unit.translation.component.project
            }
        matching_units = Unit.objects.prefetch().filter(
            source__search=text,
            translation__language=language,
            state__gte=STATE_TRANSLATED,
            **kwargs
        )

        for munit in matching_units:
            source = munit.get_source_plurals()[0]
            quality = self.comparer.similarity(text, source)
            if quality < 10 or (quality < 75 and not search):
                continue
            yield {
                "text": munit.get_target_plurals()[0],
                "quality": quality,
                "service": self.name,
                "origin": force_str(munit.translation.component),
                "origin_url": munit.get_absolute_url(),
                "source": source,
            }
