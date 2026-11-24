# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import routers

from weblate.api.generators import WeblateAutoSchema


@extend_schema_view(
    get=extend_schema(
        operation_id="api_root",
        tags=["api"],
        summary="Discover API resource URLs",
        description=(
            "Return a map of resource names to their list URLs. The keys depend "
            "on which resources provide list endpoints."
        ),
        responses={
            "200": {
                "type": "object",
                "additionalProperties": {"type": "string", "format": "uri"},
            }
        },
        examples=[
            OpenApiExample(
                "Resource links",
                value={
                    "projects": "https://example.com/api/projects/",
                    "components": "https://example.com/api/components/",
                    "translations": "https://example.com/api/translations/",
                    "languages": "https://example.com/api/languages/",
                },
                response_only=True,
            )
        ],
    )
)
class WeblateAPIRootView(routers.APIRootView):
    schema = WeblateAutoSchema()


class WeblateRouter(routers.DefaultRouter):
    APIRootView = WeblateAPIRootView

    def get_lookup_regex(self, viewset, lookup_prefix=""):
        """
        Get lookup regex for a viewset.

        Given a viewset, return the portion of URL regex that is used
        to match against a single instance.

        Note that lookup_prefix is not used directly inside REST rest_framework
        itself, but is required in order to nicely support nested router
        implementations, such as drf-nested-routers.

        https://github.com/alanjds/drf-nested-routers
        """
        base_regex = "(?P<{lookup_prefix}{lookup_url_kwarg}>{lookup_value})"
        # Use `pk` as default field, unset set.  Default regex should not
        # consume `.json` style suffixes and should break at '/' boundaries.
        lookup_field = getattr(viewset, "lookup_field", "pk")
        lookup_fields = getattr(viewset, "lookup_fields", None)
        if lookup_fields is None:
            lookup_fields = [lookup_field]

        lookup_value = getattr(viewset, "lookup_value_regex", "[^/]+")

        return "/".join(
            base_regex.format(
                lookup_prefix=lookup_prefix,
                lookup_url_kwarg=field,
                lookup_value=lookup_value,
            )
            for field in lookup_fields
        )
