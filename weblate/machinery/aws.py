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

import boto3

from django.conf import settings

from weblate.machinery.base import MachineTranslation


class AWSTranslation(MachineTranslation):
    '''AWS machine translation'''
    name = 'AWS'
    max_score = 88

    def __init__(self):
        super(AWSTranslation, self).__init__()
        self.client = boto3.client(
            'translate',
            region_name=settings.MT_AWS_REGION,
            aws_access_key_id=settings.MT_AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.MT_AWS_SECRET_ACCESS_KEY,
        )

    def download_languages(self):
        return (
            'en', 'ar', 'zh', 'fr', 'de', 'pt', 'es',
            'ja', 'ru', 'it', 'zh-TW', 'tr', 'cs',
        )

    def download_translations(self, source, language, text, unit, user):
        response = self.client.translate_text(
            Text=text, SourceLanguageCode=source, TargetLanguageCode=language
        )
        return [
            (response['TranslatedText'], self.max_score, self.name, text)
        ]
