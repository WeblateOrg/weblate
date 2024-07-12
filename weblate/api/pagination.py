# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import cast

from rest_framework.pagination import PageNumberPagination
from rest_framework.settings import api_settings


class StandardPagination(PageNumberPagination):
    page_size = cast(int, api_settings.PAGE_SIZE)
    page_size_query_param = "page_size"
    max_page_size = 1000


class LargePagination(StandardPagination):
    page_size = StandardPagination.page_size * 2
    max_page_size = 10000
