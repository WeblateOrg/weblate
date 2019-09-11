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

import random
import time
from hashlib import sha1

from django.conf import settings

from weblate.machinery.base import (
    MachineTranslation,
    MachineTranslationError,
    MissingConfiguration,
)

NETEASE_API_ROOT = 'https://jianwai.netease.com/api/text/trans'


class NeteaseSightTranslation(MachineTranslation):
    """Netease Sight API machine translation support."""

    name = 'Netease Sight'
    max_score = 90

    # Map codes used by Netease Sight to codes used by Weblate
    language_map = {'zh_Hans': 'zh'}

    def __init__(self):
        """Check configuration."""
        super(NeteaseSightTranslation, self).__init__()
        if settings.MT_NETEASE_KEY is None:
            raise MissingConfiguration('Netease Sight Translate requires app key')
        if settings.MT_NETEASE_SECRET is None:
            raise MissingConfiguration('Netease Sight Translate requires app secret')

    def download_languages(self):
        """List of supported languages."""
        return ['zh', 'en']

    def authenticate(self, request):
        """Hook for backends to allow add authentication headers to request."""
        # Override to add required headers.

        nonce = str(random.randint(1000, 99999999))
        timestamp = str(int(1000 * time.time()))

        sign = settings.MT_NETEASE_SECRET + nonce + timestamp
        sign = sign.encode('utf-8')
        sign = sha1(sign).hexdigest()

        request.add_header('Content-Type', 'application/json')
        request.add_header('appkey', settings.MT_NETEASE_KEY)
        request.add_header('nonce', nonce)
        request.add_header('timestamp', timestamp)
        request.add_header('signature', sign)

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        response = self.json_req(
            NETEASE_API_ROOT, http_post=True, json_body=True, lang=source, content=text
        )

        if not response['success']:
            raise MachineTranslationError(response['message'])

        translation = response['relatedObject']['content'][0]['transContent']

        return [
            {
                'text': translation,
                'quality': self.max_score,
                'service': self.name,
                'source': text,
            }
        ]
