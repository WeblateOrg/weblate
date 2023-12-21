# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from rest_framework import routers


class WeblateRouter(routers.DefaultRouter):
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
