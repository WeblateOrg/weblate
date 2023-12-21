# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.urls import include, path

from weblate.api.routers import WeblateRouter
from weblate.api.views import (
    AddonViewSet,
    CategoryViewSet,
    ChangeViewSet,
    ComponentListViewSet,
    ComponentViewSet,
    GroupViewSet,
    LanguageViewSet,
    MemoryViewSet,
    Metrics,
    ProjectViewSet,
    RoleViewSet,
    ScreenshotViewSet,
    Search,
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
router.register("memory", MemoryViewSet)
router.register("languages", LanguageViewSet)
router.register("component-lists", ComponentListViewSet)
router.register("changes", ChangeViewSet)
router.register("units", UnitViewSet)
router.register("screenshots", ScreenshotViewSet)
router.register("tasks", TasksViewSet, "task")
router.register("addons", AddonViewSet)
router.register("categories", CategoryViewSet)

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path("metrics/", Metrics.as_view(), name="metrics"),
    path("search/", Search.as_view(), name="search"),
    path("", include(router.urls)),
]
