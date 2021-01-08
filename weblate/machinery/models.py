#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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


from appconf import AppConf


class WeblateConf(AppConf):
    """Machine translation settings."""

    # URL of the Apertium APy server
    APERTIUM_APY = None

    # Amazon Translate settings
    AWS_ACCESS_KEY_ID = None
    AWS_SECRET_ACCESS_KEY = None
    AWS_REGION = None

    # Microsoft Conginite Services Translator
    MICROSOFT_COGNITIVE_KEY = None
    MICROSOFT_BASE_URL = "api.cognitive.microsofttranslator.com"
    MICROSOFT_ENDPOINT_URL = "api.cognitive.microsoft.com"

    # Microsoft Azure services region identification code
    MICROSOFT_REGION = None

    # MyMemory identification email, see
    # https://mymemory.translated.net/doc/spec.php
    MYMEMORY_EMAIL = None

    # Optional MyMemory credentials to access private translation memory
    MYMEMORY_USER = None
    MYMEMORY_KEY = None

    # Google API key for Google Translate API
    GOOGLE_KEY = None

    # Google Translate API3 credentials and project id
    GOOGLE_CREDENTIALS = None
    GOOGLE_PROJECT = None
    GOOGLE_LOCATION = "global"

    # ModernMT
    MT_MODERNMT_KEY = None
    MT_MODERNMT_URL = "https://api.modernmt.com/"

    # API key for Yandex Translate API
    YANDEX_KEY = None

    # tmserver URL
    TMSERVER = None

    # API key for DeepL API
    DEEPL_KEY = None
    DEEPL_API_VERSION = "v2"

    # SAP Translation Hub
    SAP_BASE_URL = None
    SAP_SANDBOX_APIKEY = None
    SAP_USERNAME = None
    SAP_PASSWORD = None
    SAP_USE_MT = True

    # Youdao
    YOUDAO_ID = None
    YOUDAO_SECRET = None

    # Netease
    NETEASE_KEY = None
    NETEASE_SECRET = None

    # List of machine translations
    SERVICES = (
        "weblate.machinery.weblatetm.WeblateTranslation",
        "weblate.memory.machine.WeblateMemory",
    )

    class Meta:
        prefix = "MT"
