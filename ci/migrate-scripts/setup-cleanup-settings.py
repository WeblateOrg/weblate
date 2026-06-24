# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Add add-on for cleanup settings migration testing."""

from weblate.addons.models import Addon

Addon.objects.bulk_create(
    [
        Addon(name="weblate.removal.comments", configuration={"age": 3}),
    ]
)
