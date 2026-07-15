# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from appconf import AppConf

from weblate.utils.classloader import ClassRegistry

from .base import BatchMachineTranslation
from .defaults import DEFAULT_WEBLATE_MACHINERY

if TYPE_CHECKING:
    from .types import SettingsDict

MACHINERY = ClassRegistry(
    "WEBLATE_MACHINERY",
    collect_errors=True,
    base_class=BatchMachineTranslation,
)


class WeblateConf(AppConf):
    """Machine-translation settings."""

    # List of machinery classes
    WEBLATE_MACHINERY = DEFAULT_WEBLATE_MACHINERY

    class Meta:
        prefix = ""


def validate_service_configuration(
    service_name: str,
    configuration: str | SettingsDict,
    *,
    allow_private_targets: bool = True,
) -> tuple[type[BatchMachineTranslation] | None, SettingsDict, list[str]]:
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

    service_configuration: SettingsDict

    if isinstance(configuration, str):
        try:
            service_configuration = cast("SettingsDict", json.loads(configuration))
        except json.JSONDecodeError as error:
            msg = f"Invalid service configuration ({service_name}): {error}"
            return service, {}, [msg]
    else:
        service_configuration = configuration

    errors = []
    if service.settings_form is not None:
        form = service.settings_form(
            service,
            data=service_configuration,
            allow_private_targets=allow_private_targets,
        )
        # validate form
        if not form.is_valid():
            errors.extend([str(error) for error in form.non_field_errors()])

            for field in form:
                errors.extend(
                    [
                        f"Error in {field.name} ({service_name}): {error}"
                        for error in field.errors
                    ]
                )
    return service, service_configuration, errors
