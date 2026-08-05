# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for Weblate documentation Sphinx plugins."""

from unittest.mock import Mock

import pytest
from djangodocs import GHSSA_URL, ghsa_link
from docutils import nodes


def test_ghsa_link() -> None:
    identifier = "r52j-4vjp-q949"

    result, messages = ghsa_link("ghsa", f":ghsa:`{identifier}`", identifier, 1, Mock())

    assert messages == []
    assert len(result) == 1
    assert isinstance(result[0], nodes.reference)
    assert result[0].astext() == f"GHSA-{identifier}"
    assert result[0]["refuri"] == GHSSA_URL.format(f"GHSA-{identifier}")


@pytest.mark.parametrize(
    "identifier",
    [
        "",
        "r52j-4vjp",
        "r52j-4vjp-q94",
        "r52j-4vjp-q949-extra",
        "R52J-4VJP-Q949",
        "abcd-1234-efgh",
    ],
)
def test_ghsa_link_invalid(identifier: str) -> None:
    rawtext = f":ghsa:`{identifier}`"
    message = object()
    problematic = object()
    inliner = Mock()
    inliner.reporter.error.return_value = message
    inliner.problematic.return_value = problematic

    result, messages = ghsa_link("ghsa", rawtext, identifier, 42, inliner)

    assert result == [problematic]
    assert messages == [message]
    inliner.reporter.error.assert_called_once_with(
        f"Invalid GitHub Security Advisory identifier: GHSA-{identifier}", line=42
    )
    inliner.problematic.assert_called_once_with(rawtext, rawtext, message)
