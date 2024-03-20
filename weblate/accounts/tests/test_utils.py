# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for various helper utilities."""

from django.test import SimpleTestCase, TestCase

from weblate.accounts.pipeline import slugify_username
from weblate.accounts.tasks import cleanup_auditlog, cleanup_social_auth


class PipelineTest(SimpleTestCase):
    def test_slugify(self) -> None:
        self.assertEqual(slugify_username("zkouska"), "zkouska")
        self.assertEqual(slugify_username("Zkouska"), "Zkouska")
        self.assertEqual(slugify_username("zkouška"), "zkouska")
        self.assertEqual(slugify_username(" zkouska "), "zkouska")
        self.assertEqual(slugify_username("ahoj - ahoj"), "ahoj-ahoj")
        self.assertEqual(slugify_username("..test"), "test")


class TasksTest(TestCase):
    def test_cleanup_social_auth(self) -> None:
        cleanup_social_auth()

    def test_cleanup_auditlog(self) -> None:
        cleanup_auditlog()
