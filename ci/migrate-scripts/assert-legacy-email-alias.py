# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import connection

from weblate.accounts.models import VerifiedEmail
from weblate.auth.models import User
from weblate.wladmin.models import SecurityFinding, SecurityScan

victim = User.objects.get(username="legacy-email-victim")
with connection.cursor() as cursor:
    cursor.execute("SELECT UPPER(%s) = UPPER(%s)", ["ı", "i"])
    locale_folds = cursor.fetchone()[0]
if locale_folds:
    finding = SecurityFinding.objects.get(
        user=victim, finding_type="legacy-email-alias"
    )
    assert finding.status == "open"
    assert finding.evidence["email"] == "victim@gıthub.com"
    assert finding.events.get(action="detected").actor.username == "weblate:alerts"
    assert (
        SecurityScan.objects.get(pk=finding.events.get().scan_id).state == "completed"
    )
else:
    assert not SecurityFinding.objects.filter(user=victim).exists()
assert VerifiedEmail.objects.filter(
    social__user=victim, email="victim@gıthub.com"
).exists()
assert not SecurityFinding.objects.filter(user__username="legacy-email-benign").exists()
