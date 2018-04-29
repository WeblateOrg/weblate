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

from weblate.machinery.base import MachineTranslation


class DummyTranslation(MachineTranslation):
    """Dummy machine translation for testing purposes."""
    name = 'Dummy'

    def download_languages(self):
        """Dummy translation supports just Czech language."""
        return ('en', 'cs')

    def download_translations(self, source, language, text, unit, user):
        """Dummy translation supports just single phrase."""
        if source == 'en' and text.strip() == 'Hello, world!':
            return [
                ('Nazdar světe!', self.max_score, 'Dummy', text),
                ('Ahoj světe!', self.max_score, 'Dummy', text),
            ]
        return []
