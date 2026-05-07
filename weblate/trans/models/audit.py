# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from django.db import models

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable

    from weblate.auth.models import User
    from weblate.trans.actions import ActionEvents


class ChangeSetModel(Protocol):
    change_set: models.Manager[models.Model]


type AuditValue = str | int | float | bool | list[str] | None
type AuditInputValue = AuditValue | models.Model


def should_track_field(
    instance: models.Model, attribute: str, update_fields: Collection[str] | None
) -> bool:
    """Check whether a changed field is included in a partial model save."""
    if update_fields is None:
        return True
    field = cast("models.Field", instance._meta.get_field(attribute))  # noqa: SLF001
    return attribute in update_fields or field.attname in update_fields


def get_audit_value(value: AuditInputValue) -> AuditValue:
    """Return JSON-serializable value for storing in change details."""
    if isinstance(value, models.Model):
        return cast("AuditValue", value.pk)
    return value


def log_setting_changes(
    instance: models.Model,
    old: models.Model,
    fields: Iterable[str],
    action: ActionEvents,
    user: User | None,
    update_fields: Collection[str] | None = None,
) -> None:
    """Create history entries for changed audit-sensitive settings."""
    for attribute in fields:
        if not should_track_field(instance, attribute, update_fields):
            continue

        old_value = cast("AuditInputValue", getattr(old, attribute))
        current_value = cast("AuditInputValue", getattr(instance, attribute))
        if old_value == current_value:
            continue

        change_set = cast("ChangeSetModel", instance).change_set
        change_set.create(
            action=action,
            target=attribute,
            user=user,
            details={
                "field": attribute,
                "old": get_audit_value(old_value),
                "target": get_audit_value(current_value),
            },
        )
