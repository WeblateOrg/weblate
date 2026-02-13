# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Add a pending unit for migration testing."""

from weblate.auth.models import User
from weblate.trans.models import Change, Unit
from weblate.utils.state import STATE_TRANSLATED

user = User.objects.create(username="migratetest")
unit = Unit.objects.all()[0]
unit.target = "Test Target"
unit.explanation = "Test Explanation"
unit.state = STATE_TRANSLATED
unit.save()
Change.objects.create(
    translation=unit.translation, user=user, action=1, unit=unit, target=unit.target
)
# This flag is to be migrated
unit.pending = True  # type: ignore[attr-defined]
unit.save()
