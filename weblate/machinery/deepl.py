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

from django.conf import settings

from weblate.machinery.base import MachineTranslation, MissingConfiguration

DEEPL_API = 'https://api.deepl.com/v1/translate'


class DeepLTranslation(MachineTranslation):
    """DeepL (Linguee) machine translation support."""
    name = 'DeepL'
    # This seems to be currently best MT service, so score it a bit
    # better than other ones.
    max_score = 91

    def __init__(self):
        """Check configuration."""
        super(DeepLTranslation, self).__init__()
        if settings.MT_DEEPL_KEY is None:
            raise MissingConfiguration('DeepL requires API key')

    def download_languages(self):
        """List of supported languages is currently hardcoded."""
        return ('en', 'de', 'fr', 'es', 'it', 'nl', 'pl')

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        response = self.json_req(
            DEEPL_API,
            http_post=True,
            auth_key=settings.MT_DEEPL_KEY,
            text=text,
            source_lang=source,
            target_lang=language,
        )

        return [
            (translation['text'], self.max_score, self.name, text)
            for translation in response['translations']
        ]
