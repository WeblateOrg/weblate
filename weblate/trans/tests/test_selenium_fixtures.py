# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Committed Selenium fixture isolation without starting a browser."""

from __future__ import annotations

import math
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from weblate.auth.models import User
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Change, Project
from weblate.trans.tests import test_selenium as selenium_tests
from weblate.trans.tests.github import DEMO_URL
from weblate.trans.tests.selenium_fixtures import (
    ReusableSeleniumDemoMixin,
    reuse_demo_fixture,
)
from weblate.utils.files import remove_tree


class SeleniumFixtureTest(TransactionTestCase):
    def test_demo_is_committed_and_restored_after_failure(self) -> None:
        constructions = []

        def committed_project_name() -> str:
            try:
                return Project.objects.get(slug="weblateorg").name
            finally:
                connection.close()

        class DemoIsolationTest(ReusableSeleniumDemoMixin, TransactionTestCase):
            github_fixtures: dict[str, Path]
            use_github_fixtures = selenium_tests.SeleniumTests.use_github_fixtures
            clear_weblateorg_fixture_path = (
                selenium_tests.SeleniumTests.clear_weblateorg_fixture_path
            )
            clear_project_stats_cache = (
                selenium_tests.SeleniumTests.clear_project_stats_cache
            )

            def setUp(self) -> None:
                super().setUp()
                ContentType.objects.get_for_model(Project)

            def _build_demo_component(self) -> Project:
                # Supply the factory's helpers without starting a browser.
                project = selenium_tests.SeleniumTests._build_demo_component(  # ruff: ignore[private-member-access]
                    cast("selenium_tests.SeleniumTests", self)
                )
                constructions.append(project.pk)
                return project

            @reuse_demo_fixture
            def mutate(self) -> None:
                project = self.get_demo_fixture()
                project.name = "Mutated demo"
                project.save()
                project.component_set.get(slug="language-names").translation_set.get(
                    language_code="cs"
                ).unit_set.update(target="Mutated translation")
                User.objects.create(username="fixture-mutator")
                Path(self.github_fixtures[DEMO_URL], "fixture-probe").touch()
                remove_tree(project.full_path)
                cache.set("selenium-fixture-probe", "Mutated cache")
                self.fail("Intentional fixture mutation failure")

            @reuse_demo_fixture
            def verify(self) -> None:
                project = self.get_demo_fixture()
                self.assertEqual(project.name, "WeblateOrg")
                self.assertEqual(
                    ContentType.objects.get_for_model(Project).pk,
                    ContentType.objects.get(app_label="trans", model="project").pk,
                )
                self.assertEqual(project.pk, constructions[0])
                self.assertTrue(Path(project.full_path).is_dir())
                component = project.component_set.get(slug="language-names")
                self.assertTrue(Path(component.full_path, ".git").is_dir())
                self.assertFalse(
                    component.translation_set.get(language_code="cs")
                    .unit_set.filter(target="Mutated translation")
                    .exists()
                )
                self.assertFalse(
                    User.objects.filter(username="fixture-mutator").exists()
                )
                self.assertFalse(
                    Path(self.github_fixtures[DEMO_URL], "fixture-probe").exists()
                )
                self.assertIsNone(cache.get("selenium-fixture-probe"))
                with ThreadPoolExecutor(max_workers=1) as executor:
                    self.assertEqual(
                        executor.submit(committed_project_name).result(), "WeblateOrg"
                    )
                # Restoring explicit primary keys must leave sequences usable.
                extra = Project.objects.create(name="Extra", slug="extra")
                self.assertNotEqual(extra.pk, project.pk)

            def opt_out(self) -> None:
                self.assertFalse(Project.objects.filter(slug="weblateorg").exists())

        result = unittest.TestResult()
        unittest.TestSuite(
            [
                DemoIsolationTest("mutate"),
                DemoIsolationTest("verify"),
                DemoIsolationTest("opt_out"),
            ]
        ).run(result)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.testsRun, 3)
        self.assertEqual(len(result.failures), 1, result.failures)
        self.assertIn("Intentional fixture mutation failure", result.failures[0][1])
        self.assertEqual(len(constructions), 1)

    def test_dashboard_activity_distribution(self) -> None:
        now = timezone.now().replace(microsecond=0)
        with patch("django.utils.timezone.now", return_value=now):
            selenium_tests.SeleniumTests.populate_dashboard_activity(
                cast("selenium_tests.SeleniumTests", self)
            )
        expected = Counter(
            {day: int(10 + 10 * math.sin(2 * math.pi * day / 30)) for day in range(365)}
        )
        actual = Counter(
            (now - timestamp).days
            for timestamp in Change.objects.filter(
                action=ActionEvents.CREATE_PROJECT
            ).values_list("timestamp", flat=True)
        )
        self.assertEqual(actual, +expected)

    def test_absent_element_search_restores_wait_after_error(self) -> None:
        driver = Mock()
        driver.timeouts.implicit_wait = 5
        driver.find_elements.side_effect = RuntimeError("Search failed")
        test = Mock(driver=driver)
        with self.assertRaisesMessage(RuntimeError, "Search failed"):
            selenium_tests.SeleniumTests.find_elements_now(
                test, "css selector", ".missing"
            )
        self.assertEqual(
            driver.implicitly_wait.call_args_list,
            [unittest.mock.call(0), unittest.mock.call(5)],
        )
