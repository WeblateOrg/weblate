# Copyright © Michal Čihař <michal@weblate.org>
# SPDX-FileCopyrightText: 2025 Javier Pérez <jdbp@protonmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy

from weblate.utils.docs import get_doc_url


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
        "SERVERS": [
            {"url": site_url.rstrip("/"), "description": site_title},
        ],
        # Document only API (not webauthn and other drf endpoints)
        "SERVE_URLCONF": "weblate.api.urls",
        "TITLE": gettext_lazy("Weblate's REST API"),
        "LICENSE": {
            "name": "GNU General Public License v3 or later",
            "url": "https://docs.weblate.org/en/latest/contributing/license.html",
        },
        "DESCRIPTION": """
The API is accessible on the ``/api/`` URL and it is based on [Django REST framework](https://www.django-rest-framework.org/).

The OpenAPI specification is available as feature preview, feedback welcome!
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
        },
        "POSTPROCESSING_HOOKS": [
            "drf_spectacular.hooks.postprocess_schema_enums",
            "weblate.api.docs.add_middleware_headers",
        ],
        "EXTERNAL_DOCS": {
            "url": get_doc_url(),
            "description": "Official Weblate documentation",
        },
    }
    if "weblate.legal" in installed_apps:
        settings["TOS"] = "/legal/terms/"

    return settings
