# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from weblate.billing.models import Billing, Plan

for label, price, state in (
    ("pending", 0, Billing.STATE_TRIAL),
    ("approved", 0, Billing.STATE_ACTIVE),
    ("paid", 10, Billing.STATE_TRIAL),
):
    name = f"Libre migration {label}"
    plan_fields = {"name": name, "price": price}
    if hasattr(Plan, "slug"):
        plan_fields["slug"] = f"migration-{label}"
    plan = Plan.objects.create(**plan_fields)
    Billing.objects.create(
        plan=plan, state=state, payment={"libre_request": True, "keep": label}
    )
