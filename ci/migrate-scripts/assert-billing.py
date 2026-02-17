# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Billing migration testing."""

from weblate.trans.models import Project

project = Project.objects.get(pk=1)

# Verify that two users were correctly migrated
assert set(project.billing.owners.values_list("username", flat=True)) == {
    "billingtest1",
    "billingtest2",
}
