# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.test import SimpleTestCase

if TYPE_CHECKING:
    from types import ModuleType


def load_list_contributors_module() -> ModuleType:
    script = Path(__file__).resolve().parents[3] / "scripts" / "list-contributors.py"
    spec = importlib.util.spec_from_file_location("list_contributors", script)
    if spec is None or spec.loader is None:
        msg = "Could not load list-contributors.py"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ListContributorsTest(SimpleTestCase):
    def test_contributor_names_are_escaped(self) -> None:
        module = load_list_contributors_module()
        contributors = {
            "code": ["Jane *Doe*", "John_Doe", "Doe, Jane"],
            "translations": [],
            "docs": [],
        }

        with patch.object(module, "get_contributors", return_value=contributors):
            output = module.get_contributors_text()

        self.assertIn(r"Jane \*Doe\*, John\_Doe, Doe\, Jane", output)
