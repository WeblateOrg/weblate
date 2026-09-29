# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from django.utils.html import format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy

from weblate.checks.base import BaseCheck

if TYPE_CHECKING:
    from weblate.checks.models import Check
    from weblate.trans.models import Unit

AI_CATEGORIES = ("accuracy", "fluency", "terminology", "style", "formatting")
AI_CHECKS = tuple(f"ai_{category}" for category in AI_CATEGORIES)


def evaluation_fingerprint(unit: Unit) -> str:
    """Identify the content to which persisted diagnostics apply."""
    content = [unit.source, unit.target, unit.context, unit.translation.language_id]
    return hashlib.sha256(json.dumps(content).encode()).hexdigest()


class AICheck(BaseCheck):
    target = True

    def check_target_unit(
        self, sources: list[str], targets: list[str], unit: Unit
    ) -> bool:
        if self.check_id not in unit.all_checks_names:
            return False
        fingerprint = evaluation_fingerprint(unit)
        return any(
            check.name == self.check_id
            and check.metadata.get("fingerprint") == fingerprint
            and bool(check.metadata.get("issues"))
            for check in unit.all_checks
        )

    def get_plain_description(self, check_obj: Check) -> str:
        return "\n".join(
            f"{self.severity_label(issue['severity'])}: {issue['explanation']}"
            for issue in check_obj.metadata.get("issues", [])
        )

    def get_description(self, check_obj: Check) -> str:
        return format_html_join(
            mark_safe("<br />"),
            "{}: {}",
            (
                (self.severity_label(issue["severity"]), issue["explanation"])
                for issue in check_obj.metadata.get("issues", [])
            ),
        )

    @staticmethod
    def severity_label(severity: str) -> str:
        return {
            "minor": gettext("Minor"),
            "major": gettext("Major"),
            "critical": gettext("Critical"),
        }[severity]


class AIAccuracyCheck(AICheck):
    check_id = "ai_accuracy"
    name = gettext_lazy("AI: Accuracy")
    description = gettext_lazy("The evaluation detected a change in meaning.")


class AIFluencyCheck(AICheck):
    check_id = "ai_fluency"
    name = gettext_lazy("AI: Fluency")
    description = gettext_lazy("The evaluation detected a language quality issue.")


class AITerminologyCheck(AICheck):
    check_id = "ai_terminology"
    name = gettext_lazy("AI: Terminology")
    description = gettext_lazy("The evaluation detected incorrect terminology.")


class AIStyleCheck(AICheck):
    check_id = "ai_style"
    name = gettext_lazy("AI: Style")
    description = gettext_lazy(
        "The evaluation detected a style or instruction mismatch."
    )


class AIFormattingCheck(AICheck):
    check_id = "ai_formatting"
    name = gettext_lazy("AI: Formatting")
    description = gettext_lazy(
        "The evaluation detected a formatting or placeholder issue."
    )
