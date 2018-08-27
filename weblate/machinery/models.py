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

from appconf import AppConf


class WeblateConf(AppConf):
    """Machine translation settings."""

    # URL of the Apertium APy server
    APERTIUM_APY = None

    # Amazon Translate settings
    AWS_ACCESS_KEY_ID = None
    AWS_SECRET_ACCESS_KEY = None
    AWS_REGION = None

    # Microsoft Translator service, register at
    # https://datamarket.azure.com/developer/applications/
    MICROSOFT_ID = None
    MICROSOFT_SECRET = None

    # Microsoft Conginite Services Translator, register at
    # https://portal.azure.com/
    MICROSOFT_COGNITIVE_KEY = None

    # MyMemory identification email, see
    # https://mymemory.translated.net/doc/spec.php
    MYMEMORY_EMAIL = None

    # Optional MyMemory credentials to access private translation memory
    MYMEMORY_USER = None
    MYMEMORY_KEY = None

    # Google API key for Google Translate API
    GOOGLE_KEY = None

    # API key for Yandex Translate API
    YANDEX_KEY = None

    # tmserver URL
    TMSERVER = None

    # API key for DeepL API
    DEEPL_KEY = None

    # SAP Translation Hub
    SAP_BASE_URL = None
    SAP_SANDBOX_APIKEY = None
    SAP_USERNAME = None
    SAP_PASSWORD = None
    SAP_USE_MT = True

    # Youdao
    YOUDAO_ID = None
    YOUDAO_SECRET = None

    # List of machine translations
    SERVICES = (
        'weblate.machinery.weblatetm.WeblateTranslation',
        'weblate.memory.machine.WeblateMemory',
    )

    class Meta(object):
        prefix = 'MT'
