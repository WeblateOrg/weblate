# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from appconf import AppConf

from weblate.utils.classloader import ClassLoader

from .base import BatchMachineTranslation

MACHINERY = ClassLoader(
    "WEBLATE_MACHINERY",
    construct=False,
    collect_errors=True,
    base_class=BatchMachineTranslation,
)


class WeblateConf(AppConf):
    """Machine-translation settings."""

    # List of machinery classes
    WEBLATE_MACHINERY = (
        "weblate.machinery.apertium.ApertiumAPYTranslation",
        "weblate.machinery.aws.AWSTranslation",
        "weblate.machinery.alibaba.AlibabaTranslation",
        "weblate.machinery.baidu.BaiduTranslation",
        "weblate.machinery.deepl.DeepLTranslation",
        "weblate.machinery.glosbe.GlosbeTranslation",
        "weblate.machinery.google.GoogleTranslation",
        "weblate.machinery.googlev3.GoogleV3Translation",
        "weblate.machinery.libretranslate.LibreTranslateTranslation",
        "weblate.machinery.microsoft.MicrosoftCognitiveTranslation",
        "weblate.machinery.modernmt.ModernMTTranslation",
        "weblate.machinery.mymemory.MyMemoryTranslation",
        "weblate.machinery.netease.NeteaseSightTranslation",
        "weblate.machinery.tmserver.TMServerTranslation",
        "weblate.machinery.yandex.YandexTranslation",
        "weblate.machinery.yandexv2.YandexV2Translation",
        "weblate.machinery.saptranslationhub.SAPTranslationHub",
        "weblate.machinery.youdao.YoudaoTranslation",
        "weblate.machinery.ibm.IBMTranslation",
        "weblate.machinery.systran.SystranTranslation",
        "weblate.machinery.openai.OpenAITranslation",
        "weblate.machinery.weblatetm.WeblateTranslation",
        "weblate.memory.machine.WeblateMemory",
        "weblate.machinery.cyrtranslit.CyrTranslitTranslation",
    )

    class Meta:
        prefix = ""
