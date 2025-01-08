# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy


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
                "description": '**Changed in version 4.5:** Glossaries are now stored as regular components, translations and strings, please use respective API instead.',
            },
            {
                "name": "tasks",
                "description": "Added in version 4.4.",
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
                               """\n\nYou can use repository endpoints for projects, components and translations to update individual repositories."""
            },
            {
                "name": "exports",
                "description": "Weblate provides various exports to allow you to further process the data.",
            },
            {
                "name": "rssFeeds",
                "description": "Changes in translations are exported in RSS feeds.",
            }
        ],
    }
    if "weblate.legal" in installed_apps:
        settings["TOS"] = "/legal/terms/"

    return settings
