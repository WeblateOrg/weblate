# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Extract Android resource values using the source file's representation."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, cast
from xml.sax.saxutils import escape

from arsc_writer import ResourceValue, Text, android_text
from lxml import etree

from weblate.utils.state import STATE_READONLY, STATE_TRANSLATED

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from weblate.formats.ttkit import AndroidUnit
    from weblate.trans.models import Component, Translation


class LocaleValues(NamedTuple):
    locale: str
    entries: Iterable[tuple[tuple[str, str], ResourceValue]]


class LocaleSnapshot(NamedTuple):
    language: str
    values: LocaleValues


def get_resource_references(wrapper: AndroidUnit) -> dict[str | None, str]:
    """Preserve imported references before target serialization escapes them."""
    if not wrapper.has_unit():
        return {}
    original = wrapper.unit.xmlelement
    elements = original if original.tag == "plurals" else [original]
    return {
        element.get("quantity"): wrapper.unit.get_xml_text_value(element)
        for element in elements
        if (element.text or "").startswith(("@", "?"))
    }


def extract_translations(
    component: Component, resource_keys: set[tuple[str, str]] | None = None
) -> Generator[LocaleSnapshot]:
    """Yield one locale at a time using the Android exporter for text semantics."""
    for translation in (
        component.translation_set.select_related("language", "plural")
        .order_by("language__code")
        .iterator()
    ):
        if translation.filename:
            yield LocaleSnapshot(
                translation.language.code,
                LocaleValues(
                    translation.language_code,
                    extract_locale(component, translation, resource_keys),
                ),
            )


def extract_locale(
    component: Component,
    translation: Translation,
    resource_keys: set[tuple[str, str]] | None,
) -> Generator[tuple[tuple[str, str], ResourceValue]]:
    from weblate.trans.models import Unit  # ruff: ignore[import-outside-top-level]

    with component.repository.lock:
        store = translation.load_store()
        for unit in (
            Unit.objects.filter(translation=translation, state__gte=STATE_TRANSLATED)
            .exclude(state=STATE_READONLY)
            .iterator()
        ):
            unit.translation = translation
            targets = unit.get_target_plurals()
            if not all(targets):
                continue
            wrapper, _ = store.find_unit(unit.context, unit.source)
            if not wrapper:
                continue
            reference = wrapper.get_markup_reference_unit().xmlelement
            kind = "plurals" if reference.tag == "plurals" else "strings"
            name = reference.get("name")
            if resource_keys is not None and (kind, name) not in resource_keys:
                continue
            # Importing decodes escaped literals and references to the same text.
            # Preserve the original distinction before set_target escapes both.
            resource_references = get_resource_references(wrapper)
            wrapper.set_target(targets if unit.is_plural else targets[0])
            node = wrapper.unit.xmlelement
            kind = "plurals" if node.tag == "plurals" else "strings"
            name = node.get("name")
            if name is None:
                msg = "Missing Android resource name"
                raise ValueError(msg)

            def text(
                element: etree._Element,
                references: dict[str | None, str],
                resource_name: str = name,
            ) -> Text | None:
                raw = (
                    escape(element.text or "") if len(element) else element.text or ""
                ) + "".join(
                    etree.tostring(child, encoding="unicode") for child in element
                )
                decoded = android_text(raw, markup=bool(len(element)))
                if raw.startswith(("@", "?")) or decoded.value == references.get(
                    element.get("quantity")
                ):
                    component.log_warning(
                        "Kotlin SDK CDN skipped resource reference: %s",
                        resource_name,
                    )
                    return None
                return decoded

            value: ResourceValue
            if kind == "plurals":
                plural_values = {
                    child.get("quantity"): text(child, resource_references)
                    for child in node
                }
                if "other" not in plural_values or any(
                    item is None for item in plural_values.values()
                ):
                    continue
                value = cast("dict[str, Text]", plural_values)
            else:
                singular = text(node, resource_references)
                if singular is None:
                    continue
                value = singular
            yield (kind, name), value
