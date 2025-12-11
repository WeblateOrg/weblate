# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from drf_spectacular.generators import SchemaGenerator
from drf_standardized_errors.openapi import AutoSchema


class WeblateSchemaGenerator(SchemaGenerator):
    def _should_include_path(self, path: str) -> bool:
        return (
            # Our API endpoints, exclude third-party one such
            # as django_otp_webauthn
            path.startswith(("/api/", "/hooks/"))
            and
            # Exclude legacy URL for webhook
            path != "/hooks/{service}"
        )

    def _get_paths_and_endpoints(self):
        paths = super()._get_paths_and_endpoints()
        return [
            (path, path_regex, method, view)
            for path, path_regex, method, view in paths
            if self._should_include_path(path)
        ]


class WeblateAutoSchema(AutoSchema):
    def get_tags(self) -> list[str]:
        """Override this for custom behaviour."""
        tokenized_path = self._tokenize_path()
        # use first non-parameter path part as tag
        if tokenized_path[0] == "api":
            return tokenized_path[1:2]
        return tokenized_path[:1]

    def get_operation_id(self) -> str:
        result = super().get_operation_id()
        if result == "hooks_create":
            return "hooks_incoming"
        return result
