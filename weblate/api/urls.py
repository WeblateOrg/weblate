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

from __future__ import unicode_literals

from django.conf.urls import url, include

from weblate.api.views import (
    ProjectViewSet, ComponentViewSet, TranslationViewSet, LanguageViewSet,
    UnitViewSet, ChangeViewSet, SourceViewSet, ScreenshotViewSet,
    Metrics
)
from weblate.api.routers import WeblateRouter

# Routers provide an easy way of automatically determining the URL conf.
router = WeblateRouter()
router.register(
    r'projects',
    ProjectViewSet
)
router.register(
    r'components',
    ComponentViewSet,
    'component',
)
router.register(
    r'translations',
    TranslationViewSet
)
router.register(
    r'languages',
    LanguageViewSet
)
router.register(
    r'changes',
    ChangeViewSet
)
router.register(
    r'units',
    UnitViewSet
)
router.register(
    r'sources',
    SourceViewSet
)
router.register(
    r'screenshots',
    ScreenshotViewSet
)


# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    url(
        r'^metrics/$',
        Metrics.as_view(),
        name='metrics',
    ),
    url(
        r'^',
        include(router.urls)
    ),
]
