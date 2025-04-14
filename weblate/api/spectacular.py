# Copyright © Michal Čihař <michal@weblate.org>
# SPDX-FileCopyrightText: 2025 Javier Pérez <jdbp@protonmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Any

from django.utils.functional import lazy
from django.utils.translation import gettext_lazy


def get_doc_url_wrapper(page: str, anchor: str = "") -> str:
    """
    Wrap get_doc_url to delay get_doc_url import.

    It cannot be imported directly, because get_spectacular_settings is used
    from settings and get_doc_url needs settings to determine if it should hide t
    he version info.
    """
    from weblate.utils.docs import get_doc_url

    return get_doc_url(page, anchor)


def get_spectacular_settings(
    installed_apps: list[str], site_url: str, site_title: str
) -> dict[str, Any]:
    settings = {
        # Use redoc from sidecar
        # TODO: Should bundle it internally
        "REDOC_DIST": "SIDECAR",
        "REDOC_UI_SETTINGS": {
            "theme": {
                "typography": {
                    "fontFamily": '"Source Sans 3", sans-serif',
                    "headings": {
                        "fontFamily": '"Source Sans 3", sans-serif',
                    },
                    "code": {
                        "fontFamily": '"Source Code Pro", monospace',
                    },
                },
                "logo": {
                    "maxWidth": "150px",
                    "maxHeight": "50vh",
                    "margin": "auto",
                },
            },
        },
        # OpenAPI Specification version: 'webhooks' field is supported from 3.1.0
        "OAS_VERSION": "3.1.1",
        "SERVERS": [
            {"url": site_url.rstrip("/"), "description": site_title},
        ],
        # Document only API (not webauthn and other drf endpoints)
        "SERVE_URLCONF": "weblate.api.urls",
        "TITLE": gettext_lazy("Weblate's REST API"),
        "LICENSE": {
            "name": "GNU General Public License v3 or later",
            "url": lazy(get_doc_url_wrapper, str)("contributing/license"),
        },
        "DESCRIPTION": """
The API is accessible on the ``/api/`` URL and it is based on [Django REST framework](https://www.django-rest-framework.org/).

The OpenAPI specification is available as feature preview, feedback welcome!

## Authorization

<!-- Redoc-Inject: <security-definitions> -->


    """,
        "EXTENSIONS_INFO": {
            "x-logo": {
                "url": "/static/weblate.svg",
            }
        },
        # Do not use API versioning
        "VERSION": None,
        # Flatten enum definitions
        "ENUM_NAME_OVERRIDES": {
            "ColorEnum": "weblate.utils.colors.ColorChoices.choices",
            "ValidationErrorEnum": "drf_standardized_errors.openapi_serializers.ValidationErrorEnum.choices",
            "ClientErrorEnum": "drf_standardized_errors.openapi_serializers.ClientErrorEnum.choices",
            "ServerErrorEnum": "drf_standardized_errors.openapi_serializers.ServerErrorEnum.choices",
            "ErrorCode401Enum": "drf_standardized_errors.openapi_serializers.ErrorCode401Enum.choices",
            "ErrorCode403Enum": "drf_standardized_errors.openapi_serializers.ErrorCode403Enum.choices",
            "ErrorCode404Enum": "drf_standardized_errors.openapi_serializers.ErrorCode404Enum.choices",
            "ErrorCode405Enum": "drf_standardized_errors.openapi_serializers.ErrorCode405Enum.choices",
            "ErrorCode406Enum": "drf_standardized_errors.openapi_serializers.ErrorCode406Enum.choices",
            "ErrorCode415Enum": "drf_standardized_errors.openapi_serializers.ErrorCode415Enum.choices",
            "ErrorCode429Enum": "drf_standardized_errors.openapi_serializers.ErrorCode429Enum.choices",
            "ErrorCode500Enum": "drf_standardized_errors.openapi_serializers.ErrorCode500Enum.choices",
            "ErrorCode423Enum": "weblate.api.serializers.ErrorCode423Enum.choices",
        },
        "POSTPROCESSING_HOOKS": [
            "drf_standardized_errors.openapi_hooks.postprocess_schema_enums",
            "weblate.api.docs.add_middleware_headers",
        ],
        "EXTERNAL_DOCS": {
            "url": lazy(get_doc_url_wrapper, str)("index"),
            "description": "Official Weblate documentation",
        },
        "TAGS": [
            {
                "name": "root",
                "description": "The API root entry point.",
            },
            {
                "name": "users",
                "description": "Added in version 4.0.",
            },
            {
                "name": "groups",
                "description": "Added in version 4.0.",
            },
            {
                "name": "roles",
            },
            {
                "name": "languages",
            },
            {
                "name": "projects",
            },
            {
                "name": "components",
            },
            {
                "name": "translations",
            },
            {
                "name": "memory",
                "description": "Added in version 4.14.",
            },
            {
                "name": "units",
                "description": "A unit is a single piece of a translation which pairs a source string with a corresponding translated string and also contains some related metadata. The term is derived from the Translate Toolkit and XLIFF.",
            },
            {
                "name": "changes",
            },
            {
                "name": "screenshots",
            },
            {
                "name": "addons",
                "description": "Added in version 4.4.1.",
            },
            {
                "name": "component-lists",
                "description": "Added in version 4.0.",
            },
            {
                "name": "glossary",
                "description": "**Changed in version 4.5:** Glossaries are now stored as regular components, translations and strings, please use respective API instead.",
            },
            {
                "name": "tasks",
                "description": "Added in version 4.4.\n\nListing of the tasks is currently not available.",
            },
            {
                "name": "statistics",
                "description": "Many endpoints support displaying statistics for their objects.",
            },
            {
                "name": "metrics",
            },
            {
                "name": "search",
                "description": "Added in version 4.18.",
            },
            {
                "name": "categories",
            },
            {
                "name": "hooks",
                "description": """Notification hooks allow external applications to notify Weblate that the VCS repository has been updated."""
                """\n\nYou can use repository endpoints for projects, components and translations to update individual repositories.""",
            },
            {
                "name": "exports",
                "description": "Weblate provides various exports to allow you to further process the data.",
            },
            {
                "name": "rssFeeds",
                "description": "Changes in translations are exported in RSS feeds.",
            },
            {
                "name": "webhooks",
                "description": "Notifications sent by Weblate.",
            },
        ],
        "WEBHOOKS": ["weblate.addons.webhooks.change_event_webhook"],
    }
    if "weblate.legal" in installed_apps:
        settings["TOS"] = "/legal/terms/"

    return settings


def get_drf_standardized_errors_sertings() -> dict[str, Any]:
    return {
        "ALLOWED_ERROR_STATUS_CODES": [
            "400",
            "401",
            "403",
            "404",
            "405",
            "406",
            "415",
            "423",  # Added by Weblate
            "429",
            "500",
        ],
        "ERROR_SCHEMAS": {
            "423": "weblate.api.serializers.ErrorResponse423Serializer",
        },
        "EXCEPTION_HANDLER_CLASS": "weblate.api.views.WeblateExceptionHandler",
    }


def get_drf_settings(
    *, require_login: bool, anon_throttle: str, user_throttle: str
) -> dict[str, Any]:
    return {
        # Use Django's standard `django.contrib.auth` permissions,
        # or allow read-only access for unauthenticated users.
        "DEFAULT_PERMISSION_CLASSES": [
            # Require authentication for login required sites
            "rest_framework.permissions.IsAuthenticated"
            if require_login
            else "rest_framework.permissions.IsAuthenticatedOrReadOnly"
        ],
        "DEFAULT_AUTHENTICATION_CLASSES": (
            "rest_framework.authentication.TokenAuthentication",
            "weblate.api.authentication.BearerAuthentication",
            "rest_framework.authentication.SessionAuthentication",
        ),
        "DEFAULT_THROTTLE_CLASSES": (
            "weblate.api.throttling.UserRateThrottle",
            "weblate.api.throttling.AnonRateThrottle",
        ),
        "DEFAULT_THROTTLE_RATES": {
            "anon": anon_throttle,
            "user": user_throttle,
        },
        "DEFAULT_RENDERER_CLASSES": [
            "rest_framework.renderers.JSONRenderer",
            "rest_framework.renderers.BrowsableAPIRenderer",
            "weblate.api.renderers.AutoCSVRenderer",
        ],
        "DEFAULT_PAGINATION_CLASS": "weblate.api.pagination.StandardPagination",
        "PAGE_SIZE": 50,
        "VIEW_DESCRIPTION_FUNCTION": "weblate.api.views.get_view_description",
        "EXCEPTION_HANDLER": "drf_standardized_errors.handler.exception_handler",
        "UNAUTHENTICATED_USER": "weblate.auth.models.get_anonymous",
        "DEFAULT_SCHEMA_CLASS": "drf_standardized_errors.openapi.AutoSchema",
    }
