# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Isolation of component fixtures shared within a test class."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.cache import cache
from django.test import TransactionTestCase
from django.test.utils import override_settings

from weblate.api.tests import APIBaseTest
from weblate.lang.models import Language
from weblate.trans.models import Component, Project
from weblate.trans.tests.test_views import (
    ComponentTestCase,
    ReusableComponentTestCase,
    ReusableViewTestCase,
)
from weblate.trans.tests.utils import clear_users_cache
from weblate.utils.data import data_path
from weblate.utils.files import remove_tree
from weblate.utils.state import STATE_TRANSLATED


class ReusableFixtureTest(TransactionTestCase):
    def setUp(self) -> None:
        super().setUp()
        # The inner suites close their connections at class teardown, so these
        # lifecycle tests must not hold an outer TestCase transaction open.
        Language.objects.flush_object_cache()
        self.addCleanup(Language.objects.flush_object_cache)
        clear_users_cache()
        self.addCleanup(clear_users_cache)

    def test_api_database_repositories_and_authentication_are_restored(self) -> None:
        constructions = []

        class APIIsolationTest(APIBaseTest):
            initial_revision: str
            initial_token: str

            @classmethod
            def build_fixture(cls, builder: ComponentTestCase) -> None:
                super().build_fixture(builder)
                constructions.append(builder.component.pk)
                cls.initial_revision = builder.component.repository.last_revision
                cls.initial_token = builder.user.auth_token.key

            def mutate(self) -> None:
                self.authenticate(superuser=True)
                self.client.force_authenticate(user=self.user)
                self.user.full_name = "Changed API user"
                self.user.save()
                self.user.profile.languages.clear()
                self.user.groups.clear()
                self.user.auth_token.delete()
                self.project.name = "Changed API project"
                self.project.save()
                self.get_unit().translate(self.user, "Changed target", STATE_TRANSLATED)
                self.create_po(project=self.create_project(name="Extra", slug="extra"))
                Path(self.git_repo_path, "fixture-probe.txt").write_bytes(
                    b"Changed repo"
                )
                remove_tree(self.project.full_path)
                cache.set("api-fixture-probe", "Changed cache")
                self.fail("Intentional failure after API fixture mutation")

            def verify(self) -> None:
                self.assertEqual(self.user.username, "apitest")
                self.assertEqual(self.user.email, "apitest@example.org")
                self.assertNotEqual(self.user.full_name, "Changed API user")
                self.assertFalse(self.user.is_superuser)
                self.assertTrue(self.user.profile.languages.filter(code="cs").exists())
                self.assertTrue(self.user.groups.filter(name="Users").exists())
                self.assertEqual(self.user.auth_token.key, self.initial_token)
                self.assertIs(self.component.project, self.project)
                self.assertEqual(self.project.name, "Test")
                self.assertEqual(Component.objects.count(), 2)
                self.assertTrue(
                    self.project.component_set.filter(slug="glossary").exists()
                )
                self.assertFalse(Project.objects.filter(slug="extra").exists())
                self.assertNotEqual(self.get_unit().target, "Changed target")
                self.assertEqual(
                    self.component.repository.last_revision, self.initial_revision
                )
                self.assertFalse(Path(self.git_repo_path, "fixture-probe.txt").exists())
                self.assertIsNone(cache.get("api-fixture-probe"))
                response = self.do_request("api:user-list", authenticated=False)
                self.assertEqual(response.data["count"], 0)

        result = unittest.TestResult()
        unittest.TestSuite(
            [APIIsolationTest("mutate"), APIIsolationTest("verify")]
        ).run(result)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.testsRun, 2)
        self.assertEqual(len(result.failures), 1, result.failures)
        self.assertIn("Intentional failure", result.failures[0][1])
        self.assertEqual(len(constructions), 1)

    def test_database_and_repositories_are_restored(self) -> None:
        constructions = []
        configurations = []

        class IsolationTest(ReusableViewTestCase):
            initial_revision: str

            @classmethod
            def build_fixture(cls, builder: ComponentTestCase) -> None:
                super().build_fixture(builder)
                constructions.append(builder.component.pk)
                configurations.append((data_path("home") / ".gitconfig").read_bytes())
                cls.initial_revision = builder.component.repository.last_revision

            def mutate(self) -> None:
                unit = self.get_unit()
                unit.translate(self.user, "Changed target", STATE_TRANSLATED)
                self.user.full_name = "Changed name"
                self.user.save()
                self.create_po(project=self.create_project(name="Extra", slug="extra"))
                filename = Path(self.component.full_path, "fixture-probe.txt")
                filename.write_text("Changed repository", encoding="utf-8")
                with self.component.repository.lock:
                    self.component.repository.commit(
                        "Fixture mutation", files=[str(filename)]
                    )
                    self.component.repository.push(self.component.branch)
                self.assertNotEqual(
                    self.component.repository.last_revision, self.initial_revision
                )
                # Cover restoration after a test removes the working checkout.
                remove_tree(self.project.full_path)
                config = data_path("home") / ".gitconfig"
                config.write_text("[user]\nname = Changed name\n", encoding="utf-8")
                cache.set("fixture-probe", "Changed cache")
                self.component.unload_sources()
                self.fail("Intentional failure after fixture mutation")

            def verify(self) -> None:
                self.assertEqual(self.user.full_name, "Weblate Test")
                self.assertNotEqual(self.get_unit().target, "Changed target")
                self.assertEqual(Component.objects.count(), 1)
                self.assertFalse(Project.objects.filter(slug="extra").exists())
                self.assertFalse((data_path("vcs") / "extra").exists())
                self.assertIsNone(cache.get("fixture-probe"))
                self.assertNotIn("repository", self.component.__dict__)
                self.assertEqual(
                    self.component.repository.last_revision, self.initial_revision
                )
                self.assertFalse(
                    Path(self.component.full_path, "fixture-probe.txt").exists()
                )
                with self.component.repository.lock:
                    self.assertEqual(
                        self.component.repository.execute(
                            ["--git-dir", self.git_repo_path, "rev-parse", "main"],
                            remote_op="none",
                        ).strip(),
                        self.initial_revision,
                    )
                self.assertEqual(self.client.get(self.translation_url).status_code, 200)

        result = unittest.TestResult()
        unittest.TestSuite(
            [IsolationTest("mutate"), IsolationTest("verify"), IsolationTest("mutate")]
        ).run(result)
        self.maxDiff = None
        self.assertEqual(result.errors, [])
        self.assertEqual(result.testsRun, 3)
        self.assertEqual(len(result.failures), 2, result.failures)
        for _, failure in result.failures:
            self.assertIn("Intentional failure", failure)
        self.assertEqual(len(constructions), 1)
        self.assertEqual(
            (data_path("home") / ".gitconfig").read_bytes(), configurations[0]
        )

    def test_class_setup_failure_cleans_files(self) -> None:
        snapshots_before = set(data_path("").glob("component-fixture-*"))
        project_paths = []

        class BrokenFixtureTest(ReusableComponentTestCase):
            @classmethod
            def build_fixture(cls, builder: ComponentTestCase) -> None:
                super().build_fixture(builder)
                project_paths.append(Path(builder.project.full_path))
                msg = "Intentional fixture construction failure"
                raise RuntimeError(msg)

            def unused(self) -> None:
                self.fail("Class setup should fail before this runs")

        result = unittest.TestResult()
        unittest.TestSuite([BrokenFixtureTest("unused")]).run(result)
        self.assertEqual(result.testsRun, 0)
        self.assertEqual(result.failures, [])
        self.assertEqual(len(result.errors), 1)
        self.assertIn("Intentional fixture construction failure", result.errors[0][1])
        self.assertEqual(len(project_paths), 1)
        self.assertFalse(project_paths[0].exists())
        self.assertEqual(
            set(data_path("").glob("component-fixture-*")), snapshots_before
        )

    def test_class_setup_failure_restores_repository_inputs(self) -> None:
        paths = ("home", "test-repo.git", "test-repo.hg", "test-repo.svn")

        class BrokenFixtureTest(ReusableComponentTestCase):
            @classmethod
            def build_fixture(cls, builder: ComponentTestCase) -> None:
                for name in paths:
                    path = Path(builder.get_repo_path(name))
                    remove_tree(path, True)
                    path.mkdir(parents=True)
                    (path / "probe").write_bytes(b"Changed input")
                (data_path("home") / ".gitconfig").write_bytes(b"Changed config")
                msg = "Intentional fixture construction failure"
                raise RuntimeError(msg)

            def unused(self) -> None:
                self.fail("Class setup should fail before this runs")

        for existing in (False, True):
            with (
                self.subTest(existing=existing),
                TemporaryDirectory() as directory,
                override_settings(DATA_DIR=directory),
            ):
                if existing:
                    for name in paths:
                        data_path(name).mkdir()
                        (data_path(name) / "probe").write_bytes(b"Original input")
                    (data_path("home") / ".gitconfig").write_bytes(b"Original config")
                result = unittest.TestResult()
                unittest.TestSuite([BrokenFixtureTest("unused")]).run(result)
                self.assertEqual(result.testsRun, 0)
                self.assertEqual(result.failures, [])
                self.assertEqual(len(result.errors), 1)
                self.assertIn(
                    "Intentional fixture construction failure", result.errors[0][1]
                )
                for name in paths:
                    if existing:
                        self.assertEqual(
                            (data_path(name) / "probe").read_bytes(), b"Original input"
                        )
                    else:
                        self.assertFalse(data_path(name).exists())
                if existing:
                    self.assertEqual(
                        (data_path("home") / ".gitconfig").read_bytes(),
                        b"Original config",
                    )
                self.assertEqual(list(Path(directory).glob("component-fixture-*")), [])

    def test_each_class_builds_its_own_format(self) -> None:
        formats = []

        class BilingualFixtureTest(ReusableComponentTestCase):
            def verify(self) -> None:
                formats.append(self.component.file_format)
                self.assertEqual(self.component.file_format, "po")

        class MonolingualFixtureTest(BilingualFixtureTest):
            def create_component(self) -> Component:
                return self.create_po_mono()

            def verify(self) -> None:
                formats.append(self.component.file_format)
                self.assertEqual(self.component.file_format, "po-mono")

        result = unittest.TestResult()
        unittest.TestSuite(
            [BilingualFixtureTest("verify"), MonolingualFixtureTest("verify")]
        ).run(result)
        self.maxDiff = None
        self.assertEqual(result.errors, [])
        self.assertEqual(result.testsRun, 2)
        self.assertEqual(result.failures, [])
        self.assertEqual(formats, ["po", "po-mono"])
