# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check type annotations unavailable in the docs-only environment."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "annotation",
    ["tuple[URLPattern, ...]", "tuple[django.urls.resolvers.URLPattern, ...]"],
)
def test_addon_api_return_annotation(annotation: str) -> None:
    extension = runpy.run_path(
        str(Path(__file__).with_name("autodoc_signature_filter.py"))
    )
    filter_signature = extension["strip_problematic_autodoc_types"]
    args = (None, "method", "weblate.addons.base.BaseAddon.get_api_urls", None, None)
    assert filter_signature(*args, "()", annotation) == ("()", None)
    assert filter_signature(*args, "()", "tuple[str, ...]") == ("()", "tuple[str, ...]")
