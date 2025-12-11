# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.utils.translation import gettext
from drf_spectacular.plumbing import (
    ResolvedComponent,
    build_basic_type,
    build_parameter_type,
)
from drf_spectacular.settings import spectacular_settings
from drf_spectacular.utils import OpenApiParameter

from .middleware import (
    RATELIMIT_LIMIT_HEADER,
    RATELIMIT_REMAINING_HEADER,
    RATELIMIT_RESET_HEADER,
)


def build_response_header_parameter(
    name: str,
    description: str,
    schema_type: type = str,
    required: bool = True,
    **kwargs,
):
    parameter = build_parameter_type(
        name=name,
        schema=build_basic_type(schema_type),
        location=OpenApiParameter.HEADER,
        description=description,
        required=required,
        **kwargs,
    )

    # following drf_spectacular.openapi.AutoSchema._get_response_headers_for_code, this is
    # not present in header objects
    del parameter["in"]
    del parameter["name"]

    return parameter


def build_response_header_component(
    name: str,
    description: str,
    schema_type: type = str,
    required: bool = True,
    **kwargs,
) -> ResolvedComponent:
    parameter = build_response_header_parameter(
        name=name,
        description=description,
        schema_type=schema_type,
        required=required,
        **kwargs,
    )
    return ResolvedComponent(
        name=name,
        type=ResolvedComponent.HEADER,
        schema=parameter,
        object=name,
    )


RATELIMIT_LIMIT_COMPONENT = build_response_header_component(
    name=RATELIMIT_LIMIT_HEADER,
    schema_type=int,
    description=gettext("Allowed number of requests to perform"),
)
RATELIMIT_REMAINING_COMPONENT = build_response_header_component(
    name=RATELIMIT_REMAINING_HEADER,
    schema_type=int,
    description=gettext("Remaining number of requests to perform"),
)
RATELIMIT_RESET_COMPONENT = build_response_header_component(
    name=RATELIMIT_RESET_HEADER,
    schema_type=int,
    description=gettext("Number of seconds until the rate-limit window resets"),
)


def add_middleware_headers(result, generator, request, public):
    """Add headers to responses set by middleware."""
    generator.registry.register_on_missing(RATELIMIT_LIMIT_COMPONENT)
    generator.registry.register_on_missing(RATELIMIT_REMAINING_COMPONENT)
    generator.registry.register_on_missing(RATELIMIT_RESET_COMPONENT)

    for path in result["paths"].values():
        for operation in path.values():
            # the paths object may be extended with custom, non-standard extensions
            if "responses" not in operation:  # pragma: no cover
                continue

            for code, response in operation["responses"].items():
                if code != "200":
                    continue
                # spec: https://swagger.io/specification/#response-object
                response.setdefault("headers", {})
                response["headers"].update(
                    {
                        RATELIMIT_LIMIT_HEADER: RATELIMIT_LIMIT_COMPONENT.ref,
                        RATELIMIT_REMAINING_HEADER: RATELIMIT_REMAINING_COMPONENT.ref,
                        RATELIMIT_RESET_HEADER: RATELIMIT_RESET_COMPONENT.ref,
                    }
                )

        result["components"] = generator.registry.build(
            spectacular_settings.APPEND_COMPONENTS
        )

    return result
