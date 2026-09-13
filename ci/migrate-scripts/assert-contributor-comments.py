# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify contributor settings and obsolete add-on removal after upgrading."""

from __future__ import annotations

from django.apps import apps

Project = apps.get_model("trans", "Project")
Component = apps.get_model("trans", "Component")
Addon = apps.get_model("addons", "Addon")

sitewide = Project.objects.get(slug="contributor-other").name == "sitewide"
for component in Component.objects.filter(
    project__slug__in=("contributor-project", "contributor-other")
):
    params = component.file_format_params
    assert params["po_line_wrap"] == -1
    if component.name == "unrelated" or (
        component.name == "uncovered" and not sitewide
    ):
        assert "po_contributor_comments" not in params
    elif component.name == "explicit":
        assert params["po_contributor_comments"] == "none"
    else:
        assert params["po_contributor_comments"] == "gettext"
assert not Addon.objects.filter(name="weblate.gettext.authors").exists()
