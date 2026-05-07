# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Strip local type annotations that Sphinx can not reliably resolve."""

from __future__ import annotations

import re

PROBLEMATIC_AUTODOC_TYPES = {
    "Addon",
    "AddonActivityLog",
    "BaseAddonForm",
    "AddonT",
    "AuthenticatedHttpRequest",
    "Category",
    "Change",
    "ConfigurationT",
    "Component",
    "Project",
    "Self",
    "StoredConfigurationT",
    "Translation",
    "TranslationFormat",
    "Unit",
    "User",
}

PROBLEMATIC_AUTODOC_TYPE_RE = re.compile(
    r"\b(" + "|".join(sorted(PROBLEMATIC_AUTODOC_TYPES)) + r")\b"
)


def has_problematic_autodoc_type(annotation: str) -> bool:
    return bool(PROBLEMATIC_AUTODOC_TYPE_RE.search(annotation))


def split_top_level(text: str, delimiter: str) -> list[str]:
    result: list[str] = []
    current: list[str] = []
    depth = 0
    quote = ""
    escaped = False

    for char in text:
        if quote:
            current.append(char)
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == quote:
                quote = ""
            continue

        if char in {'"', "'"}:
            quote = char
            current.append(char)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == delimiter and depth == 0:
            result.append("".join(current).strip())
            current = []
            continue
        current.append(char)

    result.append("".join(current).strip())
    return result


def find_top_level(text: str, target: str) -> int | None:
    depth = 0
    quote = ""
    escaped = False

    for index, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == quote:
                quote = ""
            continue

        if char in {'"', "'"}:
            quote = char
            continue
        if char in "([{":
            depth += 1
            continue
        if char in ")]}":
            depth -= 1
            continue
        if char == target and depth == 0:
            return index

    return None


def strip_problematic_parameter_annotation(parameter: str) -> str:
    colon = find_top_level(parameter, ":")
    if colon is None:
        return parameter

    equals = find_top_level(parameter, "=")
    annotation_end = equals if equals is not None else len(parameter)
    annotation = parameter[colon + 1 : annotation_end].strip()
    if not has_problematic_autodoc_type(annotation):
        return parameter

    parameter_name = parameter[:colon].rstrip()
    if equals is None:
        return parameter_name
    default_value = parameter[equals + 1 :].lstrip()
    return f"{parameter_name}={default_value}"


def strip_problematic_autodoc_types(
    app,
    what: str,
    name: str,
    obj,
    options,
    signature: str | None,
    return_annotation: str | None,
) -> tuple[str | None, str | None]:
    del app, what, name, obj, options

    if signature and signature.startswith("(") and signature.endswith(")"):
        parameters = split_top_level(signature[1:-1], ",")
        signature = (
            "("
            + ", ".join(
                strip_problematic_parameter_annotation(parameter)
                for parameter in parameters
                if parameter
            )
            + ")"
        )

    if return_annotation and has_problematic_autodoc_type(return_annotation):
        return_annotation = None

    return signature, return_annotation


def setup(app) -> dict[str, bool]:
    app.connect("autodoc-process-signature", strip_problematic_autodoc_types)
    return {
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
