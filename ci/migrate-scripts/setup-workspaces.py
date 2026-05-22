# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Set up billing projects for workspace migration testing."""

from weblate.billing.models import Billing, Plan
from weblate.trans.models import Project

plan_kwargs = {"name": "Workspace migration plan", "price": 29, "yearly_price": 299}
if hasattr(Plan, "slug"):
    plan_kwargs["slug"] = "workspace-migration"

plan = Plan.objects.create(**plan_kwargs)
billing = Billing.objects.create(plan=plan)
project = Project.objects.create(name="Workspace Migration", slug="workspace-migration")

# This script runs before migration, against the older checked-out Weblate version.
billing.projects.add(project)
