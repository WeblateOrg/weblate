# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from django.utils.html import format_html
from django.utils.translation import gettext_lazy

from weblate.checks.base import BaseCheck

if TYPE_CHECKING:
    from weblate.checks.models import Check
    from weblate.trans.models import Unit


def save_failure_fingerprint(unit: Unit) -> str:
    """Identify serialized content without the state demotion after a failed save."""
    content = [
        unit.source,
        unit.context,
        unit.target,
        unit.explanation,
        unit.source_unit.explanation,
        unit.automatically_translated,
        unit.details.get("tbx_terms"),
        unit.details.get("tbx_flags"),
    ]
    return hashlib.sha256(json.dumps(content).encode()).hexdigest()


class SaveFailedCheck(BaseCheck):
    version_added = "2026.12"
    check_id = "save_failed"
    name = gettext_lazy("Saving string failed")
    description = gettext_lazy(
        "The string could not be written to the translation file."
    )
    source = True
    target = True
    glossary = True
    ignore_untranslated = False
    ignore_readonly = False

    def check_source_unit(self, sources: list[str], unit: Unit) -> bool:
        return self.check_target_unit(sources, [], unit)

    def check_target_unit(
        self, sources: list[str], targets: list[str], unit: Unit
    ) -> bool:
        if self.check_id not in unit.all_checks_names:
            return False
        fingerprint = save_failure_fingerprint(unit)
        return any(
            check.name == self.check_id
            and check.metadata.get("fingerprint") == fingerprint
            for check in unit.all_checks
        )

    def get_plain_description(self, check_obj: Check) -> str:
        return check_obj.metadata.get("error", "")

    def get_description(self, check_obj: Check) -> str:
        return format_html("{}", self.get_plain_description(check_obj))
