# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Add add-ons for file format params migration testing."""

from weblate.addons.models import Addon

Addon.objects.bulk_create(
    [
        Addon(name="weblate.gettext.msgmerge", configuration={"previous": False}),
        Addon(
            project_id=1, name="weblate.gettext.customize", configuration={"width": -1}
        ),
        Addon(
            component_id=1,
            name="weblate.gettext.msgmerge",
            configuration={"no_location": True},
        ),
        Addon(name="weblate.yaml.customize", configuration={"line_break": "dos"}),
        Addon(project_id=1, name="weblate.yaml.customize", configuration={"indent": 2}),
        Addon(
            component_id=1,
            name="weblate.json.customize",
            configuration={"style": "spaces"},
        ),
    ]
)
