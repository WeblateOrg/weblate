# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check that upgraded slugs retain their casing and project scope."""

from __future__ import annotations

from weblate.trans.models import Component, Project

assert Project.objects.filter(slug="slug-upgrade-repaired").exists()
assert Component.objects.filter(
    project__slug="Slug-Upgrade", slug="component-repaired"
).exists()
assert set(
    Component.objects.filter(
        project__slug__in=["Slug-Upgrade", "slug-upgrade-duplicate"],
        slug="Shared-Component",
    ).values_list("project__slug", flat=True)
) == {"Slug-Upgrade", "slug-upgrade-duplicate"}
