# Copyright © Michal Čihař <michal@weblate.org>
# SPDX-FileCopyrightText: 2025 Javier Pérez <jdbp@protonmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.utils.functional import lazy
from django.utils.translation import gettext_lazy

if TYPE_CHECKING:
    from collections.abc import Sequence


def get_doc_url_wrapper(page: str, anchor: str = "") -> str:
    """
    Wrap get_doc_url to delay get_doc_url import.

    It cannot be imported directly, because get_spectacular_settings is used
    from settings.
    """
    # ruff: ignore[import-outside-top-level]
    from weblate.utils.docs import get_doc_url

    return get_doc_url(page, anchor, doc_version="latest")


def get_legal_terms_url(
    legal_hidden_documents: Sequence[str] | str = (), legal_url: str | None = None
) -> str | None:
    hidden_documents: Sequence[str]
    if isinstance(legal_hidden_documents, str):
        hidden_documents = legal_hidden_documents.split(",")
    else:
        hidden_documents = legal_hidden_documents

    for document in hidden_documents:
        if document.strip() == "terms":
            return legal_url
    return "/legal/terms/"


def get_spectacular_settings(
    installed_apps: list[str],
    site_url: str,
    site_title: str,
    *,
    static_url: str = "/static/",
    legal_hidden_documents: Sequence[str] | str = (),
    legal_url: str | None = None,
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
        "SWAGGER_UI_DIST": "SIDECAR",
        "DEFAULT_GENERATOR_CLASS": "weblate.api.generators.WeblateSchemaGenerator",
        # OpenAPI Specification version: 'webhooks' field is supported from 3.1.0
        "OAS_VERSION": "3.1.1",
        "SERVERS": [
            {"url": site_url.rstrip("/"), "description": site_title},
        ],
        "SERVE_URLCONF": "weblate.urls",
        "TITLE": gettext_lazy("Weblate's REST API"),
        "LICENSE": {
            "name": "GNU General Public License v3 or later",
            "url": lazy(get_doc_url_wrapper, str)("contributing/license"),
        },
        "DESCRIPTION": """
The API is accessible on the ``/api/`` URL and it is based on [Django REST framework](https://www.django-rest-framework.org/).

Read-only requests can be made without authentication unless the site requires login.
Authenticate using a personal or project token in the `Authorization` header with
the `Token` or `Bearer` scheme. API requests are rate limited.

## Authorization

<!-- Redoc-Inject: <security-definitions> -->


    """,
        "EXTENSIONS_INFO": {
            "x-logo": {
                "url": f"{static_url.rstrip('/')}/weblate.svg",
            }
        },
        # Do not use API versioning
        "VERSION": None,
        # Flatten enum definitions
        "ENUM_NAME_OVERRIDES": {
            "ActionEnum": "weblate.trans.actions.ActionEvents.choices",
            "AlertSeverityEnum": "weblate.trans.alerts.base.AlertSeverity.choices",
            "SeverityEnum": "weblate.trans.models.announcement.ANNOUNCEMENT_SEVERITY_CHOICES",
            "ColorEnum": "weblate.utils.colors.ColorChoices.choices",
            "StringStateEnum": "weblate.utils.state.StringState.choices",
            "ReportKindEnum": "weblate.trans.models.report.REPORT_KIND_CHOICES",
            "NewUnitStateEnum": "weblate.api.serializers.NEW_UNIT_STATE_CHOICES",
            "ErrorResponse400TypeEnum": "weblate.api.serializers.ErrorResponse400TypeEnum.choices",
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
            "weblate.api.docs.strip_field_choice_descriptions",
            "weblate.api.docs.document_change_actions",
            "weblate.api.docs.document_all_static_vcs_choices",
            "weblate.api.docs.add_middleware_headers",
            "weblate.api.docs.simplify_license_schema",
            "weblate.api.docs.document_delete_bodies",
            "weblate.api.docs.simplify_media_types",
            "weblate.api.docs.document_response_descriptions",
        ],
        "EXTERNAL_DOCS": {
            "url": lazy(get_doc_url_wrapper, str)("index"),
            "description": "Official Weblate documentation",
        },
        "TAGS": [
            {
                "name": "users",
                "description": "User accounts, profiles, and related data.",
            },
            {
                "name": "groups",
                "description": "Teams and their access permissions.",
            },
            {
                "name": "roles",
                "description": "Permission roles available to teams.",
            },
            {
                "name": "languages",
                "description": "Languages available for translation.",
            },
            {
                "name": "projects",
                "description": "Translation projects and their configuration.",
            },
            {
                "name": "components",
                "description": "Translation components, their files, and repository operations.",
            },
            {
                "name": "translations",
                "description": "Translations of components into individual languages.",
            },
            {
                "name": "memory",
                "description": "Translation memory entries and matches.",
            },
            {
                "name": "units",
                "description": "A unit is a single piece of a translation which pairs a source string with a corresponding translated string and also contains some related metadata. The term is derived from the Translate Toolkit and XLIFF.",
            },
            {
                "name": "changes",
                "description": "Recorded changes to translations and other objects.",
            },
            {
                "name": "screenshots",
                "description": "Screenshots and their associations with source strings.",
            },
            {
                "name": "addons",
                "description": "Installed add-ons and their configuration.",
            },
            {
                "name": "component-lists",
                "description": "Lists of translation components.",
            },
            {
                "name": "tasks",
                "description": "Background task status and cancellation. Listing tasks is not available.",
            },
            {
                "name": "statistics",
                "description": "Many endpoints support displaying statistics for their objects.",
            },
            {
                "name": "metrics",
                "description": "Translation metrics in CSV and OpenMetrics formats.",
            },
            {
                "name": "search",
                "description": "Search across projects, components, languages, and users.",
            },
            {
                "name": "categories",
                "description": "Categories that group translation components.",
            },
            {
                "name": "contributions",
                "description": "Contributions made by a user.",
            },
            {
                "name": "reports",
                "description": "Stored reports and report generation.",
            },
            {
                "name": "schema",
                "description": "The OpenAPI schema for this API.",
            },
            {
                "name": "suggestions",
                "description": "Suggestions for translating strings.",
            },
            {
                "name": "hooks",
                "description": """Notification hooks allow external applications to notify Weblate that the VCS repository has been updated."""
                """\n\nYou can use repository endpoints for projects, components and translations to update individual repositories.""",
            },
            {
                "name": "webhooks",
                "description": "Notifications sent by Weblate.",
            },
        ],
        "WEBHOOKS": ["weblate.addons.webhooks.change_event_webhook"],
    }
    if "weblate.legal" in installed_apps:
        terms_url = get_legal_terms_url(legal_hidden_documents, legal_url)
        if terms_url:
            settings["TOS"] = terms_url

    return settings


def get_drf_standardized_errors_settings() -> dict[str, Any]:
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
            "400": "weblate.api.serializers.ErrorResponse400Serializer",
            "423": "weblate.api.serializers.ErrorResponse423Serializer",
        },
        "EXCEPTION_HANDLER_CLASS": "weblate.api.views.WeblateExceptionHandler",
    }


def get_drf_settings(*, require_login: bool) -> dict[str, Any]:
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
            # Reject unhandled headers before a browser session can authenticate them.
            "weblate.api.authentication.RejectAuthorizationAuthentication",
            "rest_framework.authentication.SessionAuthentication",
        ),
        "DEFAULT_THROTTLE_CLASSES": (
            "weblate.api.throttling.UserRateThrottle",
            "weblate.api.throttling.AnonRateThrottle",
        ),
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
        "DEFAULT_SCHEMA_CLASS": "weblate.api.generators.WeblateAutoSchema",
    }
