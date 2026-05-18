# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Set up team membership for through-model migration testing."""

from weblate.auth.models import User
from weblate.trans.models import Project

project = Project.objects.get(slug="test")
group = project.defined_groups.get(name="Translate")
user = User.objects.create_user(
    "membership-migrate", "membership-migrate@example.org", "testpassword"
)
user.groups.add(group)
