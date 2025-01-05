# Copyright © Michal Čihař <michal@weblate.org>
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
        "DESCRIPTION": api_description,
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
    }
    if "weblate.legal" in installed_apps:
        settings["TOS"] = "/legal/terms/"

    return settings


api_description = f"""
This OpenAPI specification is offered as a feature preview, your feedback is welcome!

---

Weblate's REST API is based on [Django REST framework](https://www.django-rest-framework.org).
You can interact with it on the `/api/` URL path by using the [Weblate Client]({get_doc_url(page='wlc')}) or any third-party REST client of your choice.

## Authentication

Authentication works with tokens placed in the `Authorization` HTTP request header:

- Each user has a personal access token which they can get from their respective user profile. These tokens have the `wlu_` prefix.
- It is possible to create project tokens whose access to the API is limited to operations to their associated project. These tokens have the `wlp_` prefix.

Although some of the API operations are available without authentication,
it is still recommended to authenticate your requests:

- Operations such as `GET /api/users/` return an incomplete representation of the
requested resources if the request has not been authenticated and authorized.
- Anonymous requests are heavily rate limited, by default, to 100
requests per day. On the other hand, authenticated requests are rate limited
to 5000 requests per hour by default.

## API rate limiting

Rate limiting can be adjusted in the `settings.py` file; see [Throttling in Django REST framework documentation](https://www.django-rest-framework.org/api-guide/throttling/)
for more details on how to configure it.

In the Docker container, this can be configured with the [WEBLATE_API_RATELIMIT_ANON]({get_doc_url(page='admin/install/docker', anchor='envvar-WEBLATE_API_RATELIMIT_ANON')}) and the [WEBLATE_API_RATELIMIT_USER]({get_doc_url(page='admin/install/docker', anchor='envvar-WEBLATE_API_RATELIMIT_USER')}) environment variables.

**Added in version 4.1:**
HTTP response headers indicating status of rate-limiting.

Those HTTP headers are:

<table>
    <thead>
        <tr>
            <td>Header name</td>
            <td>Description</td>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>X-RateLimit-Limit</td>
            <td>The maximum number of client requests allowed for a certain period of time, depending on whether the request is anonymous or authenticated.</td>
        </tr>
        <tr>
            <td>X-RateLimit-Remaining</td>
            <td>The remaining number of client requests allowed for the current timeframe.</td>
        </tr>
        <tr>
            <td>X-RateLimit-Reset</td>
            <td>The number of seconds until the rate limit is reset by the server.</td>
        </tr
    </tbody>
</table>

## Components and categories

To access a component which is nested inside a [Category]({get_doc_url(page='admin/projects', anchor='category')}),
you need to URL encode the category name into a component name separated with a slash.

For example, usage placed in a `docs` category needs to be used as `docs%252Fusage`.
In this case, the full URL could be:

`https://weblate.example.com/api/components/hello/docs%252Fusage/repository/`
"""
