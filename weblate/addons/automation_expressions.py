# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext


def expressions(values: list[str], context: dict[str, Any] | None = None) -> list[bool]:
    """Compile/evaluate CEL using only JSON data across a process boundary."""
    if not values:
        return []
    payload = json.dumps({"expressions": values, "context": context}).encode()
    if len(payload) > 1024 * 1024:
        raise ValidationError(gettext("Automation context is too large."))
    try:
        result = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).with_name("automation_cel.py"))],
            input=payload,
            capture_output=True,
            timeout=5,
            check=True,
            env={"LANG": "C.UTF-8"},
        )
        response = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise ValidationError(
            gettext(
                "CEL validation or evaluation failed or exceeded its resource limit."
            )
        ) from error
    if "error" in response:
        raise ValidationError(gettext("Invalid CEL condition: %s") % response["error"])
    return response["results"]
