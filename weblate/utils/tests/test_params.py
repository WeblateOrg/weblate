# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validation of serialized component parameters."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from django.core.exceptions import ValidationError

from weblate.trans.file_format_params import (
    FlatXMLRootName,
    GettextPoLineWrap,
    JSONOutputIndentation,
)
from weblate.vcs.params import GitForcePush, MergeRequestMergeMethod

if TYPE_CHECKING:
    from weblate.utils.params import BaseParam


@pytest.mark.parametrize(
    ("param", "value"),
    [
        (GitForcePush, True),
        (GitForcePush, False),
        (JSONOutputIndentation, 0),
        (JSONOutputIndentation, 4),
        (FlatXMLRootName, "root"),
        (FlatXMLRootName, ""),
        (GettextPoLineWrap, 77),
        (GettextPoLineWrap, "77"),
        (GettextPoLineWrap, -1),
        (GettextPoLineWrap, "-1"),
        (GettextPoLineWrap, ""),
        (MergeRequestMergeMethod, "merge"),
        (MergeRequestMergeMethod, "squash"),
        (MergeRequestMergeMethod, "rebase"),
        (MergeRequestMergeMethod, ""),
    ],
)
def test_valid_stored_values(param: type[BaseParam], value: str | int | bool) -> None:
    param().validate_stored_value(value)


@pytest.mark.parametrize(
    ("param", "value"),
    [
        (GitForcePush, "true"),
        (GitForcePush, "false"),
        (GitForcePush, ""),
        (GitForcePush, 0),
        (GitForcePush, 1),
        (GitForcePush, None),
        (GitForcePush, []),
        (GitForcePush, {}),
        (JSONOutputIndentation, "4"),
        (JSONOutputIndentation, True),
        (JSONOutputIndentation, False),
        (JSONOutputIndentation, 4.0),
        (JSONOutputIndentation, -1),
        (JSONOutputIndentation, None),
        (JSONOutputIndentation, []),
        (JSONOutputIndentation, {}),
        (FlatXMLRootName, 1),
        (FlatXMLRootName, False),
        (FlatXMLRootName, None),
        (FlatXMLRootName, []),
        (FlatXMLRootName, {}),
        (GettextPoLineWrap, True),
        (GettextPoLineWrap, 77.0),
        (GettextPoLineWrap, "077"),
        (GettextPoLineWrap, " 77"),
        (GettextPoLineWrap, 42),
        (GettextPoLineWrap, None),
        (GettextPoLineWrap, []),
        (GettextPoLineWrap, {}),
        (MergeRequestMergeMethod, "invalid"),
        (MergeRequestMergeMethod, 1),
        (MergeRequestMergeMethod, True),
        (MergeRequestMergeMethod, None),
        (MergeRequestMergeMethod, []),
        (MergeRequestMergeMethod, {}),
    ],
)
def test_invalid_stored_values(
    param: type[BaseParam],
    value: str | float | bool | list[object] | dict[str, object] | None,
) -> None:
    with pytest.raises(ValidationError):
        param().validate_stored_value(value)
