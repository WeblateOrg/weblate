# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Explicitly supported, in-place source identity edits."""

from __future__ import annotations

from copy import copy
from io import BytesIO
from typing import TYPE_CHECKING, cast

from django.core.exceptions import ValidationError
from django.utils.translation import gettext
from translate.misc.multistring import multistring

from weblate.formats.base import UnitNotFoundError
from weblate.trans.util import split_plural

if TYPE_CHECKING:
    from weblate.formats.base import TranslationFormat, TranslationUnit
    from weblate.formats.ttkit import BaseTTKitFormat

# Capabilities deliberately do not inherit from a related format's implementation.
KEY_FORMATS = frozenset(
    {
        "json",
        "json-nested",
        "arb",
        "webextension",
        "i18next",
        "i18nextv4",
        "yaml",
        "ruby-yaml",
        "toml",
        "go-i18n-toml",
        "properties",
        "gwt",
        "php",
        "dtd",
        "aresource",
        "resx",
        "fluent",
    }
)
SOURCE_FORMATS = frozenset({"po", "tbx", "plainxliff", "xliff2", "apple-xliff"})
CONTEXT_FORMATS = KEY_FORMATS | {"po", "tbx"}


def editable_fields(format_id: str, *, monolingual: bool) -> set[str]:
    fields = set()
    if format_id in (KEY_FORMATS if monolingual else SOURCE_FORMATS):
        fields.add("source")
    if format_id in CONTEXT_FORMATS and (monolingual or format_id in SOURCE_FORMATS):
        fields.add("context")
    return fields


def clone_for_edit(store: TranslationFormat) -> BaseTTKitFormat:
    """Copy only document state, not the adapter's application configuration."""
    scratch = cast("BaseTTKitFormat", copy(store))
    # XML element deepcopy can separate unit nodes from the serialized tree.
    scratch.store = scratch.load(
        BytesIO(scratch.serialize(store.store)), scratch.template_store
    )
    scratch._invalidate_units()  # ruff: ignore[private-member-access]
    return scratch


def find_identity(
    store: TranslationFormat, identity: dict[str, str]
) -> TranslationUnit:
    """Find physical entries even when their template has already been renamed."""
    if not (store.has_template or store.is_template):
        return store.find_unit(identity["context"], identity["source"])[0]
    for raw in store.all_store_units:
        unit = store.unit_class(store, raw, raw)
        if unit.context == identity["context"]:
            return unit
    raise UnitNotFoundError(identity["context"], identity["source"])


def edit_identity(
    store: TranslationFormat,
    unit: TranslationUnit,
    identity: dict[str, str],
) -> None:
    """Mutate an existing toolkit entry without reconstructing its metadata."""
    monolingual = store.has_template or store.is_template
    fields = editable_fields(store.format_id, monolingual=monolingual)
    context = identity["context"]
    if store.format_id == "fluent" and any(
        part.name or part.top_branch.child_nodes for part in unit.unit.get_parts() or []
    ):
        raise ValidationError(
            gettext(
                "Editing Fluent messages with attributes or selectors is not supported."
            )
        )
    if context != unit.context:
        store.validate_new_context(context)
        if "context" not in fields:
            raise ValidationError(
                {
                    "context": gettext(
                        "This file format does not support editing keys or context."
                    )
                }
            )
        for raw in store.all_store_units:
            other = (
                store.unit_class(store, raw, raw)
                if monolingual
                else store.unit_class(store, raw)
            )
            if (
                raw is not unit.unit
                and other.context == context
                and (
                    monolingual
                    or store.format_id == "tbx"
                    or other.source == identity["source"]
                )
            ):
                raise ValidationError(
                    {"context": gettext("A string with this identity already exists.")}
                )
        if store.format_id == "po":
            unit.unit.setcontext(context)
        else:
            unit.unit.setid(context)
    # Monolingual translations contain values, not the source language text.
    if (not monolingual or store.is_template) and identity["source"] != unit.source:
        if "source" not in fields:
            raise ValidationError(
                {
                    "source": gettext(
                        "This file format does not support editing source strings."
                    )
                }
            )
        raw = unit.unit
        source_dom = getattr(raw, "source_dom", None)
        if store.format_id != "tbx" and source_dom is not None and len(source_dom):
            raise ValidationError(
                {
                    "source": gettext(
                        "Editing source strings with inline markup is not supported."
                    )
                }
            )
        source = split_plural(identity["source"])
        if monolingual:
            unit.set_target(source)
        elif store.format_id == "tbx":
            raw.set_source_terms(source)
        else:
            raw.source = source[0] if len(source) == 1 else multistring(source)
    unit.invalidate_all_caches()
    unit.__dict__.pop("id_hash", None)
    store._invalidate_units()  # ruff: ignore[private-member-access]
    if unit.context != context:
        raise ValidationError(
            {"context": gettext("The key cannot be represented in this file format.")}
        )
