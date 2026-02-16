# Copyright © Boost Orgnaization <boost@boost.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig


class BoostEndpointConfig(AppConfig):
    name = "weblate.boost_endpoint"
    label = "boost_endpoint"
    verbose_name = "Boost documentation translation API"
