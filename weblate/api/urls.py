#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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


from django.urls import include, path

from weblate.api.routers import WeblateRouter
from weblate.api.views import (
    AddonViewSet,
    ChangeViewSet,
    ComponentListViewSet,
    ComponentViewSet,
    GroupViewSet,
    LanguageViewSet,
    Metrics,
    ProjectViewSet,
    RoleViewSet,
    ScreenshotViewSet,
    TasksViewSet,
    TranslationViewSet,
    UnitViewSet,
    UserViewSet,
)

# Routers provide an easy way of automatically determining the URL conf.
router = WeblateRouter()
router.register("users", UserViewSet)
router.register("groups", GroupViewSet)
router.register("roles", RoleViewSet)
router.register("projects", ProjectViewSet)
router.register("components", ComponentViewSet)
router.register("translations", TranslationViewSet)
router.register("languages", LanguageViewSet)
router.register("component-lists", ComponentListViewSet)
router.register("changes", ChangeViewSet)
router.register("units", UnitViewSet)
router.register("screenshots", ScreenshotViewSet)
router.register("tasks", TasksViewSet, "task")
router.register("addons", AddonViewSet)

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path("metrics/", Metrics.as_view(), name="metrics"),
    path("", include(router.urls)),
]
