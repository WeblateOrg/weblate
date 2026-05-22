# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Assertion for billing workspace migration."""

from weblate.billing.models import Billing
from weblate.trans.models import Project

project = Project.objects.get(slug="workspace-migration")
billing = Billing.objects.get(plan__name="Workspace migration plan")

assert project.workspace_id is not None, "Project workspace was not migrated"
assert billing.workspace_id == project.workspace_id, (
    f"Billing workspace {billing.workspace_id} does not match "
    f"project workspace {project.workspace_id}"
)
assert project.workspace.name == "Workspace Migration", (
    f"Unexpected workspace name: {project.workspace.name}"
)
