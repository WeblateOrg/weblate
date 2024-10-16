# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Custom filters tests."""

import pytest

from weblate.accounts.templatetags.custom_filters import split


@pytest.mark.parametrize(
    "value, key, expected",
    [
        ("a,b,c", ",", ["a", "b", "c"]),
        ("a b c", " ", ["a", "b", "c"]),
        ("a-b-c", "-", ["a", "b", "c"]),
        ("abc", "x", ["abc"]),
        ("", ",", [""]),
    ],
)
def test_split(value, key, expected):
    assert split(value, key) == expected  # noqa: S101
