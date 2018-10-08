# -*- coding: utf-8 -*-
#
# Copyright ©2018 Sun Zhigang <hzsunzhigang@corp.netease.com>
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

YOUDAO_API_ROOT = 'https://openapi.youdao.com/api'


class YoudaoTranslation(MachineTranslation):
    """Youdao Zhiyun API machine translation support."""
    name = 'Youdao Zhiyun'
    max_score = 90

    # Map codes used by Youdao to codes used by Weblate
    language_map = {
        'zh_Hans': 'zh-CHS',
        'zh': 'zh-CHS',
        'en': 'EN',
    }

    def __init__(self):
        """Check configuration."""
        super(YoudaoTranslation, self).__init__()
        if settings.MT_YOUDAO_ID is None:
            raise MissingConfiguration(
                'Youdao Translate requires app key'
            )
        if settings.MT_YOUDAO_SECRET is None:
            raise MissingConfiguration(
                'Youdao Translate requires app secret'
            )

    def download_languages(self):
        """List of supported languages."""
        return [
            'zh-CHS',
            'ja',
            'EN',  # Officially youdao uses uppercase for en
            'ko',
            'fr',
            'ru',
            'pt',
            'es',
            'vi',
            'de',
            'ar',
            'id'
        ]

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        salt, sign = self.signed_salt(
            settings.MT_YOUDAO_ID, settings.MT_YOUDAO_SECRET, text
        )

        response = self.json_req(
            YOUDAO_API_ROOT,
            q=text,
            _from=source,
            to=language,
            appKey=settings.MT_YOUDAO_ID,
            salt=salt,
            sign=sign,
        )

        if int(response['errorCode']) != 0:
            raise MachineTranslationError(
                'Error code: {}'.format(response['errorCode'])
            )

        translation = response['translation'][0]

        return [(translation, self.max_score, self.name, text)]
