# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Component-wide source editing, preserving unit identity and pending writes."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.translation import gettext

from weblate.formats.base import UnitNotFoundError
from weblate.formats.source_edit import (
    clone_for_edit,
    edit_identity,
    editable_fields,
    find_identity,
)
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Unit
from weblate.trans.models.pending import PendingUnitChange
from weblate.trans.util import join_plural, split_plural
from weblate.utils.state import (
    FUZZY_STATES,
    STATE_APPROVED,
    STATE_NEEDS_REWRITING,
    STATE_READONLY,
    STATE_TRANSLATED,
)

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.trans.models import Component


def identity(unit: Unit) -> dict[str, str]:
    return {"source": unit.source, "context": unit.context}


def edit_source(
    unit: Unit,
    user: User,
    *,
    content_hash: int,
    source: list[str] | None = None,
    context: str | None = None,
    explanation: str | None = None,
) -> Unit:
    component = unit.translation.component
    with component.lock, transaction.atomic():
        source_unit = Unit.objects.select_for_update().get(
            pk=cast("int", unit.source_unit_id)
        )
        allowed = user.has_perm("meta:unit.edit_source", source_unit)
        if not allowed:
            raise PermissionDenied(getattr(allowed, "reason", ""))
        if source_unit.content_hash != content_hash:
            raise ValidationError(
                gettext("The source string has changed. Reload it before editing.")
            )
        old = identity(source_unit)
        new = {
            "source": old["source"] if source is None else join_plural(source),
            "context": old["context"] if context is None else context,
        }
        if (
            explanation is not None
            and explanation != source_unit.explanation
            and not user.has_perm("source.edit", source_unit.translation)
        ):
            raise PermissionDenied
        explanation = source_unit.explanation if explanation is None else explanation
        if old == new and explanation == source_unit.explanation:
            return source_unit
        _validate_request(component, old, new)
        unit_class = component.file_format_cls.get_unit_class(
            component.file_format_params
        )
        new_hash = unit_class.calculate_id_hash(
            component.has_template(), new["source"], new["context"]
        )
        units = list(source_unit.unit_set.select_for_update().prefetch().order_by("pk"))
        ids = [item.pk for item in units]
        others = Unit.objects.filter(translation__component=component).exclude(
            pk__in=ids
        )
        po_collision = (
            component.file_format == "po"
            and others.filter(
                *source_unit.translation._get_new_unit_duplicate_filters(  # ruff: ignore[private-member-access]
                    split_plural(new["source"])
                ),
                context=new["context"],
            ).exists()
        )
        if (
            po_collision
            or others.filter(id_hash=new_hash).exists()
            or source_unit.translation.has_reserved_identity(
                new["context"], new["source"], exclude_unit_ids=ids
            )
        ):
            raise ValidationError(
                {
                    "context": gettext(
                        "A string with this identity already exists or is awaiting a file update."
                    )
                }
            )
        physical_units = {item.pk: _validate_backend(item, new) for item in units}
        for item in units:
            _update_unit(
                item, new, new_hash, explanation, user, physical_units[item.pk]
            )
            if item.pk == source_unit.pk:
                source_unit = item
        component.unload_sources()
        component.invalidate_cache()
        return source_unit


def _validate_request(
    component: Component, old: dict[str, str], new: dict[str, str]
) -> None:
    fields = editable_fields(
        component.file_format,
        monolingual=component.has_template(),
        file_format_params=component.file_format_params,
    )
    for field in ("source", "context"):
        if old[field] != new[field] and field not in fields:
            raise ValidationError(
                {field: gettext("The file format does not support this edit.")}
            )
    texts = split_plural(new["source"])
    Unit.check_valid([*texts, new["context"]])
    if not any(texts) or len(texts) != len(split_plural(old["source"])):
        raise ValidationError(
            {"source": gettext("Keep the existing number of nonempty source forms.")}
        )
    if component.has_template() and not new["context"]:
        raise ValidationError({"context": gettext("A translation key is required.")})


def _validate_backend(item: Unit, new: dict[str, str]) -> bool:
    component = item.translation.component
    if not item.translation.filename:
        return False
    physical = True
    store = clone_for_edit(item.translation.store)
    disk = item.details.get("disk_identity", identity(item))
    try:
        backend = find_identity(store, disk)
    except UnitNotFoundError:
        physical = False
        if item.pending_changes.filter(add_unit=True).exists():
            backend = store.new_unit_from_unit(item)
        elif (
            component.has_template()
            and not item.is_source
            and "disk_identity" not in item.details
        ):
            if not item.pending_changes.exists():
                return False
            backend = store.new_unit_from_unit(item)
        else:
            raise ValidationError(
                gettext("Could not find the string in the translation file.")
            ) from None
    try:
        edit_identity(store, backend, new)
        store.serialize(store.store)
    except (ValueError, TypeError) as error:
        raise ValidationError(str(error)) from error
    return physical


def _update_unit(
    item: Unit,
    new: dict[str, str],
    new_hash: int,
    explanation: str,
    user: User,
    physical: bool,
) -> None:
    previous = identity(item)
    write_file = bool(item.translation.filename) and (
        physical or item.pending_changes.exists()
    )
    item.store_old_unit(item)
    if write_file:
        item.store_disk_state()
        item.details.setdefault("disk_identity", previous)
        # Freeze legacy queued writes before changing their lookup identity.
        for index, pending in enumerate(
            item.pending_changes.select_for_update().order_by("timestamp", "pk")
        ):
            if not physical and index == 0:
                pending.add_unit = True
            if "identity" not in pending.metadata:
                pending.metadata["identity"] = previous
                pending.save(update_fields=["metadata", "add_unit"])
    if "tbx_terms" in item.details:
        from weblate.utils.terminology import reconcile_terms  # ruff: ignore[import-outside-top-level]

        terms = item.details["tbx_terms"]
        terms["source"] = reconcile_terms(terms["source"], split_plural(new["source"]))
        if item.is_source:
            terms["target"] = deepcopy(terms["source"])
    item.source = new["source"]
    item.context = new["context"]
    item.id_hash = new_hash
    if item.is_source:
        if previous["source"] != new["source"] and item.state == STATE_APPROVED:
            item.state = STATE_TRANSLATED
        item.target = new["source"]
        item.explanation = explanation
    elif previous["source"] != new["source"]:
        _update_source_state(item, previous["source"])
    item.save()
    item.__dict__.pop("content_hash", None)
    if write_file:
        PendingUnitChange.store_unit_change(
            unit=item,
            author=user,
            source_unit_explanation=explanation,
            state=(
                STATE_TRANSLATED
                if item.is_source and item.state == STATE_READONLY
                else item.state
            ),
        )
    item.generate_change(
        user,
        user,
        ActionEvents.SOURCE_CHANGE,
        check_new=False,
        old=previous["source"],
        target=new["source"],
        change_details={
            "old_context": previous["context"],
            "context": new["context"],
        },
    )


def _update_source_state(unit: Unit, previous_source: str) -> None:
    """Match the review/reversion behavior of ordinary source-language edits."""
    if not unit.target:
        return
    if unit.previous_source == unit.source:
        if unit.state in FUZZY_STATES:
            unit.original_state = unit.state = STATE_TRANSLATED
            unit.previous_source = ""
            return
        if unit.original_state in FUZZY_STATES:
            unit.original_state = STATE_TRANSLATED
            unit.previous_source = ""
            return
    if unit.state >= STATE_TRANSLATED:
        unit.original_state = STATE_NEEDS_REWRITING
        if unit.state < STATE_READONLY:
            unit.state = STATE_NEEDS_REWRITING
        unit.previous_source = previous_source
