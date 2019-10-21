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

from django.conf import settings

from weblate.machinery.base import MachineTranslation, MissingConfiguration

DEEPL_API_BASE = 'https://api.deepl.com/v2'


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
        """Download list of supported languages from DeepL."""
        response = self.json_req(
            DEEPL_API_BASE + '/languages',
            http_post=True,
            auth_key=settings.MT_DEEPL_KEY
        )

        return [item['language'] for item in response]

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        response = self.json_req(
            DEEPL_API_BASE + '/translate',
            http_post=True,
            auth_key=settings.MT_DEEPL_KEY,
            text=text,
            source_lang=source,
            target_lang=language,
        )

        translations = {
            trans['detected_source_language'].lower(): trans['text']
            for trans in response.get('translations', [])
        }

        translation = translations.get(source.lower())
        if translation is None:
            return []

        return [
            {
                'text': translation,
                'quality': self.max_score,
                'service': self.name,
                'source': text,
            }
        ]
