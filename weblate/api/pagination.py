# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import cast

from rest_framework.pagination import PageNumberPagination
from rest_framework.settings import api_settings


class StandardPagination(PageNumberPagination):
    page_size = cast("int", api_settings.PAGE_SIZE)
    page_size_query_param = "page_size"
    max_page_size = 1000

    def get_paginated_response_schema(self, data):
        """
        Make the response schema compatible with OpenAPI 3.1 specification.

        As of drf-spectacular[sidecar]>=0.28.0,<0.29, pagination schemas are not
        compatible by default with OpenAPI 3.1. This method overrides the default.
        Later updates might fix this issue.

        https://github.com/tfranzel/drf-spectacular/issues/1360
        """
        schema = super().get_paginated_response_schema(data)
        schema["properties"]["next"].pop("nullable")
        schema["properties"]["previous"].pop("nullable")
        return schema


class LargePagination(StandardPagination):
    page_size = StandardPagination.page_size * 4
    max_page_size = 10000
