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

from weblate.machinery.base import (
    MachineTranslation, MachineTranslationError, MissingConfiguration
)


GOOGLE_API_ROOT = 'https://translation.googleapis.com/language/translate/v2/'


class GoogleTranslation(MachineTranslation):
    """Google Translate API v2 machine translation support."""
    name = 'Google Translate'
    max_score = 90

    # Map old codes used by Google to new ones used by Weblate
    language_map = {
        'he': 'iw',
        'jv': 'jw',
        'nb': 'no',
    }


    def __init__(self):
        """Check configuration."""
        super(GoogleTranslation, self).__init__()
        if settings.MT_GOOGLE_KEY is None:
            raise MissingConfiguration(
                'Google Translate requires API key'
            )

    def convert_language(self, language):
        """Convert language to service specific code."""
        return super(GoogleTranslation, self).convert_language(
            language.replace('_', '-').split('@')[0]
        )

    def download_languages(self):
        """List of supported languages."""
        response = self.json_req(
            GOOGLE_API_ROOT + 'languages',
            key=settings.MT_GOOGLE_KEY
        )

        if 'error' in response:
            raise MachineTranslationError(response['error']['message'])

        return [d['language'] for d in response['data']['languages']]

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        response = self.json_req(
            GOOGLE_API_ROOT,
            key=settings.MT_GOOGLE_KEY,
            q=text,
            source=source,
            target=language,
            format='text',
        )

        if 'error' in response:
            raise MachineTranslationError(response['error']['message'])

        translation = response['data']['translations'][0]['translatedText']

        return [(translation, self.max_score, self.name, text)]
