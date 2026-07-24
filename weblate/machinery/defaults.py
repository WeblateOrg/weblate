# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

DEFAULT_WEBLATE_MACHINERY: tuple[str, ...] = (
    "weblate.machinery.apertium.ApertiumAPYTranslation",
    "weblate.machinery.aws.AWSTranslation",
    "weblate.machinery.alibaba.AlibabaTranslation",
    "weblate.machinery.anthropic.AnthropicTranslation",
    "weblate.machinery.baidu.BaiduTranslation",
    "weblate.machinery.deepl.DeepLTranslation",
    "weblate.machinery.glosbe.GlosbeTranslation",
    "weblate.machinery.google.GoogleTranslation",
    "weblate.machinery.googlev3.GoogleV3Translation",
    "weblate.machinery.libretranslate.LTEngineTranslation",
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
    "weblate.machinery.systran.SystranTranslation",
    "weblate.machinery.openai.OpenAITranslation",
    "weblate.machinery.mistral.MistralTranslation",
    "weblate.machinery.ollama.OllamaTranslation",
    "weblate.machinery.openai.AzureOpenAITranslation",
    "weblate.machinery.weblatetm.WeblateTranslation",
    "weblate.memory.machine.WeblateMemory",
    "weblate.machinery.cyrtranslit.CyrTranslitTranslation",
)

DEFAULT_MACHINERY_ERROR_KEEP_DAYS = 30
