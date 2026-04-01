# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import transaction

from weblate.checks.base import BatchCheckMixin
from weblate.checks.models import CHECKS
from weblate.trans.models import Component
from weblate.utils.celery import app
from weblate.utils.lock import WeblateLockTimeoutError


def _perform_batched_checks(component: Component, checks: list[str]) -> None:
    for check in sorted(checks, key=lambda check_id: check_id in CHECKS.source):
        check_obj = CHECKS[check]
        if not isinstance(check_obj, BatchCheckMixin):
            msg = (
                f"Check {check!r} with type {type(check_obj).__name__} "
                "does not support batch updates"
            )
            raise TypeError(msg)
        component.log_info("batch updating check %s", check)
        check_obj.perform_batch(component)


@app.task(
    trail=False,
    autoretry_for=(WeblateLockTimeoutError,),
    retry_backoff=60,
)
def finalize_component_checks(
    component_id: int,
    unit_ids: list[int],
    checks: list[str],
    *,
    batch_mode: bool,
    component: Component | None = None,
) -> None:
    if not unit_ids and not checks:
        return
    if component is None:
        try:
            component = Component.objects.get(pk=component_id)
        except Component.DoesNotExist:
            return
    with component.checks_lock:
        component.batch_checks = batch_mode
        component.batched_checks = set(checks)
        try:
            with transaction.atomic():
                if unit_ids:
                    units = component.source_translation.unit_set.filter(
                        pk__in=unit_ids
                    )
                    unit_count = units.count()
                    component.log_info(
                        "running source checks for %d strings", unit_count
                    )
                    for unit in units.iterator(chunk_size=500):
                        unit.translation.component = component
                        unit.is_batch_update = True
                        unit.run_checks()
                if component.batched_checks:
                    _perform_batched_checks(component, list(component.batched_checks))
        finally:
            component.batch_checks = False
            component.batched_checks = set()
        component.invalidate_cache()
