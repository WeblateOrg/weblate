# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json

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
        "weblate.machinery.openai.AzureOpenAITranslation",
        "weblate.machinery.weblatetm.WeblateTranslation",
        "weblate.memory.machine.WeblateMemory",
        "weblate.machinery.cyrtranslit.CyrTranslitTranslation",
    )

    class Meta:
        prefix = ""


def validate_service_configuration(
    service_name: str, configuration_json: str
) -> tuple[BatchMachineTranslation, dict, list[str]]:
    try:
        service = MACHINERY[service_name]
    except KeyError as error:
        msg = f"Service not found: {service_name}"
        raise ValueError(msg) from error
    try:
        configuration = json.loads(configuration_json)
    except ValueError as error:
        msg = f"Invalid service configuration: {error}"
        raise ValueError(msg) from error

    errors = []
    if service.settings_form is not None:
        form = service.settings_form(service, data=configuration)
        # validate form
        if not form.is_valid():
            errors.extend(list(form.non_field_errors()))

            for field in form:
                errors.extend(
                    [f"Error in {field.name}: {error}" for error in field.errors]
                )
    return service, configuration, errors
