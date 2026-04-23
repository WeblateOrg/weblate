# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for management commands."""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

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

    def test_list_checks_requires_sections_with_output(self) -> None:
        with self.assertRaisesRegex(CommandError, "requires exactly one"):
            call_command("list_checks", "-o", "checks.rst")

    def test_list_checks_requires_single_section_with_output(self) -> None:
        with self.assertRaisesRegex(CommandError, "requires exactly one"):
            call_command(
                "list_checks", "--sections", "checks", "flags", "-o", "checks.rst"
            )
