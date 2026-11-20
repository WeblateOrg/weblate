# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from weblate.billing.models import Billing

for label in ("pending", "approved", "paid"):
    billing = Billing.objects.get(plan__name=f"Libre migration {label}")
    assert billing.libre_request_pending == (label == "pending")
    assert billing.payment == {"keep": label}
    assert billing.libre_cleanup_warned_at is None
    assert billing.libre_cleanup_empty_since is None
