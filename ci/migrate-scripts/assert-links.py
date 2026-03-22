# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Assertion for component links migration."""

from weblate.trans.models import ComponentLink, Project

project = Project.objects.get(slug="link-target")

# Verify the link survived the migration to the explicit through model
link = ComponentLink.objects.get(project=project)
assert link.component is not None, "ComponentLink.component is None"
assert link.category is None, (
    f"ComponentLink.category should be None, got {link.category}"
)
