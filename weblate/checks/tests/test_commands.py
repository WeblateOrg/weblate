# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for management commands."""

from io import StringIO

from django.core.management import call_command
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
