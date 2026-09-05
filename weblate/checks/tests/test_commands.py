# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for management commands."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from weblate.checks.chars import EscapedNewlineCountingCheck, KabyleCharactersCheck
from weblate.checks.management.commands.list_checks import Command
from weblate.checks.source import EllipsisCheck, OptionalPluralCheck
from weblate.trans.tests.test_commands import WeblateComponentCommandTestCase
from weblate.trans.tests.test_models import RepoTestCase


class ListSameCommandTest(RepoTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.component = self.create_component()

    def test_list_same_checks(self) -> None:
        output = StringIO()
        call_command("list_same_checks", stdout=output)
        self.assertEqual(1, len(output.getvalue().splitlines()))


class UpdateChecksTest(WeblateComponentCommandTestCase):
    command_name = "updatechecks"
    expected_string = "Processing"


class ListTestCase(SimpleTestCase):
    def test_character_summaries(self) -> None:
        for check, summary in (
            (
                EscapedNewlineCountingCheck(),
                r":Summary: Number of ``\n`` literals in translation does not match source.",
            ),
            (
                KabyleCharactersCheck(),
                ":Summary: Use standardized Latin Kabyle characters (e.g. ``ɣ`` instead of Greek ``γ``; ``ɛ`` instead of ``ε``).",
            ),
        ):
            with self.subTest(check=check.check_id):
                self.assertIn(summary, Command().build_check_section(check))

    def test_ellipsis_summary(self) -> None:
        self.assertIn(
            ":Summary: The string uses three dots ``...`` instead of an ellipsis character ``…``.",
            Command().build_check_section(EllipsisCheck()),
        )

    def test_summary_escaping(self) -> None:
        check = OptionalPluralCheck()
        for description, expected in (
            ("Plain description.", "Plain description."),
            (r"Use \n.", r"Use \\n."),
        ):
            with (
                self.subTest(description=description),
                patch.object(check, "description", description),
            ):
                self.assertIn(
                    f":Summary: {expected}", Command().build_check_section(check)
                )

    def test_list_checks(self) -> None:
        output = StringIO()
        call_command("list_checks", stdout=output)
        self.assertIn(".. _check-same:", output.getvalue())

    def test_list_checks_includes_auto_flag_notes(self) -> None:
        output = StringIO()
        call_command("list_checks", "--sections", "checks", stdout=output)
        value = output.getvalue()
        self.assertIn(":Automatic flag behavior:", value)
        self.assertIn(
            "``auto-java-messageformat``: Treat a text as conditional Java MessageFormat",
            value,
        )
        self.assertIn(
            "``auto-safe-html``: Treat a text as conditional HTML",
            value,
        )

    def test_list_checks_includes_dual_scope(self) -> None:
        output = StringIO()
        call_command("list_checks", "--sections", "checks", stdout=output)
        value = output.getvalue()
        self.assertIn(".. _check-max-size:", value)
        self.assertIn(":Scope: source and translated strings", value)

    def test_list_checks_requires_sections_with_output(self) -> None:
        with self.assertRaisesRegex(CommandError, "requires exactly one"):
            call_command("list_checks", "-o", "checks.rst")

    def test_list_checks_requires_single_section_with_output(self) -> None:
        with self.assertRaisesRegex(CommandError, "requires exactly one"):
            call_command(
                "list_checks", "--sections", "checks", "flags", "-o", "checks.rst"
            )
