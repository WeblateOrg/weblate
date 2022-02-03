#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

from weblate.utils.classloader import ClassLoader

MACHINERY = ClassLoader("WEBLATE_MACHINERY", construct=False)


class WeblateConf(AppConf):
    """
    Machine-translation settings.

    TODO: Drop all MT_* settings in Weblate 5.1.

    These are deprecated and should be dropped once migration
    from Weblate 4.11 is no longer supported.
    """

    # URL of the Apertium APy server
    MT_APERTIUM_APY = None

    # Amazon Translate settings
    MT_AWS_ACCESS_KEY_ID = None
    MT_AWS_SECRET_ACCESS_KEY = None
    MT_AWS_REGION = None

    # Microsoft Conginite Services Translator
    MT_MICROSOFT_COGNITIVE_KEY = None
    MT_MICROSOFT_BASE_URL = "api.cognitive.microsofttranslator.com"
    MT_MICROSOFT_ENDPOINT_URL = "api.cognitive.microsoft.com"

    # Microsoft Azure services region identification code
    MT_MICROSOFT_REGION = None

    # MyMemory identification email, see
    # https://mymemory.translated.net/doc/spec.php
    MT_MYMEMORY_EMAIL = None

    # Optional MyMemory credentials to access private translation memory
    MT_MYMEMORY_USER = None
    MT_MYMEMORY_KEY = None

    # Google API key for Google Translate API
    MT_GOOGLE_KEY = None

    # Google Translate API3 credentials and project id
    MT_GOOGLE_CREDENTIALS = None
    MT_GOOGLE_PROJECT = None
    MT_GOOGLE_LOCATION = "global"

    # ModernMT
    MT_MODERNMT_KEY = None
    MT_MODERNMT_URL = "https://api.modernmt.com/"

    # API key for Yandex Translate API
    MT_YANDEX_KEY = None

    # tmserver URL
    MT_TMSERVER = None

    # API key for DeepL API
    MT_DEEPL_KEY = None
    MT_DEEPL_API_URL = "https://api.deepl.com/v2/"

    # API key for LibreTranslate
    MT_LIBRETRANSLATE_KEY = None
    MT_LIBRETRANSLATE_API_URL = None

    # SAP Translation Hub
    MT_SAP_BASE_URL = None
    MT_SAP_SANDBOX_APIKEY = None
    MT_SAP_USERNAME = None
    MT_SAP_PASSWORD = None
    MT_SAP_USE_MT = True

    # Youdao
    MT_YOUDAO_ID = None
    MT_YOUDAO_SECRET = None

    # Netease
    MT_NETEASE_KEY = None
    MT_NETEASE_SECRET = None

    # List of machine translations
    MT_SERVICES = (
        "weblate.machinery.weblatetm.WeblateTranslation",
        "weblate.memory.machine.WeblateMemory",
    )

    # List of machinery classes
    WEBLATE_MACHINERY = (
        "weblate.machinery.apertium.ApertiumAPYTranslation",
        "weblate.machinery.aws.AWSTranslation",
        "weblate.machinery.baidu.BaiduTranslation",
        "weblate.machinery.deepl.DeepLTranslation",
        "weblate.machinery.glosbe.GlosbeTranslation",
        "weblate.machinery.google.GoogleTranslation",
        "weblate.machinery.googlev3.GoogleV3Translation",
        "weblate.machinery.libretranslate.LibreTranslateTranslation",
        "weblate.machinery.microsoft.MicrosoftCognitiveTranslation",
        "weblate.machinery.microsoftterminology.MicrosoftTerminologyService",
        "weblate.machinery.modernmt.ModernMTTranslation",
        "weblate.machinery.mymemory.MyMemoryTranslation",
        "weblate.machinery.netease.NeteaseSightTranslation",
        "weblate.machinery.tmserver.AmagamaTranslation",
        "weblate.machinery.tmserver.TMServerTranslation",
        "weblate.machinery.yandex.YandexTranslation",
        "weblate.machinery.saptranslationhub.SAPTranslationHub",
        "weblate.machinery.youdao.YoudaoTranslation",
        "weblate.machinery.weblatetm.WeblateTranslation",
        "weblate.memory.machine.WeblateMemory",
    )

    class Meta:
        prefix = ""
