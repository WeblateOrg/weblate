# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

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
    service_name: str, configuration: str | dict
) -> tuple[BatchMachineTranslation | None, dict, list[str]]:
    """
    Validate given service configuration.

    :param service_name: Name of the service as defined in WEBLATE_MACHINERY
    :param configuration: JSON encoded configuration for the service
    :return: A tuple containing the validated service class, configuration
             and a list of errors
    :raises ValueError: When service is not found or configuration is invalid
    """
    try:
        service = MACHINERY[service_name]
    except KeyError:
        msg = f"Service not found: {service_name}"
        return None, {}, [msg]

    if isinstance(configuration, str):
        try:
            service_configuration = json.loads(configuration)
        except json.JSONDecodeError as error:
            msg = f"Invalid service configuration ({service_name}): {error}"
            return service, {}, [msg]
    else:
        service_configuration = configuration

    errors = []
    if service.settings_form is not None:
        form = service.settings_form(service, data=service_configuration)
        # validate form
        if not form.is_valid():
            errors.extend(list(form.non_field_errors()))

            for field in form:
                errors.extend(
                    [
                        f"Error in {field.name} ({service_name}): {error}"
                        for error in field.errors
                    ]
                )
    return service, service_configuration, errors
