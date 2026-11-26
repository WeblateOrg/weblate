# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.test import SimpleTestCase

from weblate.checks.models import Check
from weblate.checks.save import SaveFailedCheck, save_failure_fingerprint
from weblate.trans.tests.factories import make_unit
from weblate.utils.state import (
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_READONLY,
    STATE_TRANSLATED,
)


class SaveFailedCheckTest(SimpleTestCase):
    def test_existing_diagnostic_applies_to_all_states(self) -> None:
        check = SaveFailedCheck()
        for source in (False, True):
            for state in (STATE_EMPTY, STATE_FUZZY, STATE_TRANSLATED, STATE_READONLY):
                with self.subTest(source=source, state=state):
                    unit = make_unit(
                        source="Source", target="Target", is_source=source, state=state
                    )
                    unit.__dict__["all_checks"] = [
                        Check(
                            name=check.check_id,
                            unit=unit,
                            metadata={
                                "fingerprint": save_failure_fingerprint(unit),
                                "error": "Cannot write",
                            },
                        )
                    ]
                    self.assertTrue(check.check_source([unit.source], unit))
                    self.assertTrue(
                        check.check_target([unit.source], [unit.target], unit)
                    )

    def test_content_changes_invalidate_diagnostic(self) -> None:
        check = SaveFailedCheck()
        for field in (
            "source",
            "context",
            "target",
            "explanation",
            "source_unit_explanation",
            "automatically_translated",
            "tbx_terms",
            "tbx_flags",
        ):
            with self.subTest(field=field):
                unit = make_unit(source="Source", target="Target")
                unit.__dict__["all_checks"] = [
                    Check(
                        name=check.check_id,
                        unit=unit,
                        metadata={
                            "fingerprint": save_failure_fingerprint(unit),
                        },
                    )
                ]
                match field:
                    case "source_unit_explanation":
                        unit.source_unit.explanation = "Changed"
                    case "automatically_translated":
                        unit.automatically_translated = True
                    case "tbx_terms":
                        unit.details[field] = {"target": [{"text": "Target"}]}
                    case "tbx_flags":
                        unit.details[field] = {"explicit": "", "read_only": True}
                    case _:
                        setattr(unit, field, "Changed")
                self.assertFalse(check.check_target([unit.source], [unit.target], unit))

    def test_rechecks_cannot_invent_diagnostics(self) -> None:
        unit = make_unit(source="Source", target="Target")
        self.assertFalse(
            SaveFailedCheck().check_target([unit.source], [unit.target], unit)
        )

    def test_description_is_escaped(self) -> None:
        check = SaveFailedCheck()
        stored = Check(
            name=check.check_id, metadata={"error": "<script>alert(1)</script>"}
        )
        self.assertEqual(
            check.get_description(stored), "&lt;script&gt;alert(1)&lt;/script&gt;"
        )
        self.assertEqual(
            check.get_plain_description(stored), "<script>alert(1)</script>"
        )
