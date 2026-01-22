# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Billing migration testing."""

from weblate.auth.data import SELECTION_ALL
from weblate.auth.models import Group, Permission, User, setup_project_groups
from weblate.billing.models import Billing, Plan
from weblate.trans.models import Project

# Create test users
user1 = User.objects.create(username="billingtest1")
user2 = User.objects.create(username="billingtest2")
user3 = User.objects.create(username="billingtest3")

# Create test billing
plan = Plan.objects.create(name="Basic plan", price=19, yearly_price=199)
billing = Billing.objects.create(plan=plan)
project = Project.objects.get(pk=1)
setup_project_groups(sender=Project, instance=project, created=True)
billing.projects.add(project)

# Add user to per-project group
project.add_user(user1, "Billing")

# Create site-wide group and add both users
billing_group = Group.objects.create(
    name="Global Billing", project_selection=SELECTION_ALL
)
billing_role = billing_group.roles.create(name="Test Role")
billing_role.permissions.add(Permission.objects.get(codename="billing.view"))
user1.groups.add(billing_group)
user2.groups.add(billing_group)
