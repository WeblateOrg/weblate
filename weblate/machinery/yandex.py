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
    MachineTranslation, MissingConfiguration, MachineTranslationError,
)


class YandexTranslation(MachineTranslation):
    """Yandex machine translation support."""
    name = 'Yandex'
    max_score = 90

    def __init__(self):
        """Check configuration."""
        super(YandexTranslation, self).__init__()
        if settings.MT_YANDEX_KEY is None:
            raise MissingConfiguration(
                'Yandex Translate requires API key'
            )

    def check_failure(self, response):
        if 'code' not in response or response['code'] == 200:
            return
        if 'message' in response:
            raise MachineTranslationError(response['message'])
        raise MachineTranslationError(
            'Error: {0}'.format(response['code'])
        )

    def download_languages(self):
        """Download list of supported languages from a service."""
        response = self.json_req(
            'https://translate.yandex.net/api/v1.5/tr.json/getLangs',
            key=settings.MT_YANDEX_KEY
        )
        self.check_failure(response)
        return [tuple(item.split('-')) for item in response['dirs']]

    def is_supported(self, source, language):
        """Check whether given language combination is supported."""
        return (source, language) in self.supported_languages

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        response = self.json_req(
            'https://translate.yandex.net/api/v1.5/tr.json/translate',
            key=settings.MT_YANDEX_KEY,
            text=text,
            lang='{0}-{1}'.format(source, language),
            target=language,
        )

        self.check_failure(response)

        return [
            (translation, self.max_score, self.name, text)
            for translation in response['text']
        ]
