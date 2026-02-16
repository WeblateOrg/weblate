# Copyright © Boost Orgnaization <boost@boost.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.urls import path

from weblate.boost_endpoint.views import AddOrUpdateView, BoostEndpointInfo

urlpatterns = [
    path("", BoostEndpointInfo.as_view(), name="info"),
    path("add-or-update/", AddOrUpdateView.as_view(), name="add-or-update"),
]
