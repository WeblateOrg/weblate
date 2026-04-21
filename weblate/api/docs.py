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

LICENSE_ENUM_REF = "#/components/schemas/LicenseEnum"
LICENSE_SCHEMA_EXAMPLES = (
    "MIT",
    "GPL-3.0-or-later",
    "Apache-2.0",
    "BSD-3-Clause",
    "proprietary",
)
HTTP_METHODS = {"delete", "get", "patch", "post", "put"}
JSON_MEDIA_TYPE = "application/json"
FORM_MEDIA_TYPE = "application/x-www-form-urlencoded"
MULTIPART_MEDIA_TYPE = "multipart/form-data"
WILDCARD_MEDIA_TYPE = "*/*"
CSV_MEDIA_TYPE = "text/csv"
OPENMETRICS_MEDIA_TYPE = "application/openmetrics-text"
METRICS_PATH = "/api/metrics/"
FILE_UPLOAD_REQUEST_MEDIA_TYPES = {
    ("post", "/api/projects/{slug}/components/"): {
        JSON_MEDIA_TYPE,
        MULTIPART_MEDIA_TYPE,
    },
    ("post", "/api/screenshots/"): {MULTIPART_MEDIA_TYPE},
    ("post", "/api/screenshots/{id}/file/"): {MULTIPART_MEDIA_TYPE},
    ("put", "/api/screenshots/{id}/file/"): {MULTIPART_MEDIA_TYPE},
    (
        "post",
        "/api/translations/{component__project__slug}/{component__slug}/{language__code}/file/",
    ): {MULTIPART_MEDIA_TYPE},
    (
        "put",
        "/api/translations/{component__project__slug}/{component__slug}/{language__code}/file/",
    ): {MULTIPART_MEDIA_TYPE},
}


def _license_string_schema() -> dict[str, object]:
    return {
        "type": "string",
        "maxLength": 150,
        "examples": list(LICENSE_SCHEMA_EXAMPLES),
    }


def _is_license_enum_ref(schema: object) -> bool:
    return isinstance(schema, dict) and schema.get("$ref") == LICENSE_ENUM_REF


def _replace_license_schema(schema: object) -> None:
    if isinstance(schema, dict):
        if _is_license_enum_ref(schema):
            schema.clear()
            schema.update(_license_string_schema())
            return

        for combinator in ("oneOf", "anyOf", "allOf"):
            options = schema.get(combinator)
            if isinstance(options, list) and any(
                _is_license_enum_ref(item) for item in options
            ):
                schema.pop(combinator)
                schema.update(_license_string_schema())
                break

        for value in schema.values():
            _replace_license_schema(value)

    elif isinstance(schema, list):
        for item in schema:
            _replace_license_schema(item)


def simplify_license_schema(result, generator, request, public):
    """Document component licenses as strings instead of a huge enum."""
    result.get("components", {}).get("schemas", {}).pop("LicenseEnum", None)
    _replace_license_schema(result)
    return result


def _keep_content_media_types(content: dict, allowed: set[str]) -> None:
    for media_type in list(content):
        if media_type not in allowed:
            content.pop(media_type)


def _simplify_request_media_types(path: str, method: str, operation: dict) -> None:
    request_body = operation.get("requestBody")
    if not isinstance(request_body, dict):
        return

    content = request_body.get("content")
    if not isinstance(content, dict):
        return

    allowed = FILE_UPLOAD_REQUEST_MEDIA_TYPES.get((method, path))
    if allowed is None:
        allowed = {JSON_MEDIA_TYPE} if JSON_MEDIA_TYPE in content else set(content)
        allowed.discard(FORM_MEDIA_TYPE)
        allowed.discard(MULTIPART_MEDIA_TYPE)
        allowed.discard(WILDCARD_MEDIA_TYPE)

    _keep_content_media_types(content, allowed)


def _simplify_response_media_types(path: str, method: str, operation: dict) -> None:
    for status_code, response in operation.get("responses", {}).items():
        if not isinstance(response, dict):
            continue

        content = response.get("content")
        if not isinstance(content, dict):
            continue

        if path == METRICS_PATH and method == "get" and status_code == "200":
            if CSV_MEDIA_TYPE in content:
                content[CSV_MEDIA_TYPE]["schema"] = {"type": "string"}
            if OPENMETRICS_MEDIA_TYPE in content:
                content[OPENMETRICS_MEDIA_TYPE]["schema"] = {"type": "string"}
            continue

        content.pop(CSV_MEDIA_TYPE, None)
        content.pop(OPENMETRICS_MEDIA_TYPE, None)


def _simplify_format_parameter(path: str, method: str, operation: dict) -> None:
    if path == METRICS_PATH and method == "get":
        return

    parameters = operation.get("parameters")
    if not isinstance(parameters, list):
        return

    filtered_parameters = [
        parameter
        for parameter in parameters
        if parameter.get("in") != "query" or parameter.get("name") != "format"
    ]
    if filtered_parameters:
        operation["parameters"] = filtered_parameters
    else:
        operation.pop("parameters")


def simplify_media_types(result, generator, request, public):
    """Remove renderer and parser noise from generated media types."""
    for path, path_item in result.get("paths", {}).items():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue

            _simplify_request_media_types(path, method, operation)
            _simplify_response_media_types(path, method, operation)
            _simplify_format_parameter(path, method, operation)

    return result


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
