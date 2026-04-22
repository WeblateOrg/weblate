# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Migrate project set language team settings to file format params."""

from weblate.trans.models import Component, Project

project1, project2 = Project.objects.bulk_create(
    [
        Project(
            name="set-language_team-off",
            slug="set-language_team-off",
            set_language_team=False,
        ),
        Project(
            name="set-language_team-on",
            slug="set-language_team-on",
            set_language_team=True,
        ),
    ]
)
Component.objects.bulk_create(
    [
        Component(
            name="Gettext headers settings component 1",
            slug="gettext-header-settings-component-1",
            project=project1,
            file_format="po",
        ),
        Component(
            name="Gettext headers settings component 2",
            slug="gettext-header-settings-component-2",
            project=project2,
            file_format="po",
        ),
    ]
)
