# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from django.core.paginator import Paginator, EmptyPage

from weblate.trans.views.helper import get_component


def get_page_limit(request, default):
    """Return page and limit as integers."""
    try:
        limit = int(request.GET.get('limit', default))
    except ValueError:
        limit = default
    # Cap it to range 10 - 200
    limit = min(max(10, limit), 200)
    try:
        page = int(request.GET.get('page', 1))
    except ValueError:
        page = 1
    page = max(1, page)
    return page, limit


def get_paginator(request, object_list, default_page_limit=50):
    """Return paginator and current page."""
    page, limit = get_page_limit(request, default_page_limit)
    paginator = Paginator(object_list, limit)
    try:
        return paginator.page(page)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


class ComponentViewMixin(object):
    def get_component(self):
        return get_component(
            self.request,
            self.kwargs['project'],
            self.kwargs['component']
        )
