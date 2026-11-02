# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Billing migration testing."""

from weblate.auth.models import Group
from weblate.trans.models import Project

project = Project.objects.get(pk=1)

# Billing owners are subsequently migrated to the workspace Owners team.
assert project.workspace_id is not None
owners = Group.objects.get(defining_workspace=project.workspace, name="Owners")
# Other fixtures can legitimately migrate additional owners, such as custom bots.
# Check both granted and withheld ownership for the users seeded by setup-billing.
migrated_users = set(
    owners.user_set.filter(
        username__in=("billingtest1", "billingtest2", "billingtest3")
    ).values_list("username", flat=True)
)
assert migrated_users == {
    "billingtest1",
    "billingtest2",
}, f"Unexpected migrated billing fixture owners: {sorted(migrated_users)}"
