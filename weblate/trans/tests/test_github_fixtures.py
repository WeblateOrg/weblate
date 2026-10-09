# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify offline GitHub transports and isolated screenshot discovery data."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase
from translation_finder import discover

from weblate.trans.tests.github import DEMO_URL, TEST_URL, github_fixture_repositories
from weblate.utils.data import data_dir
from weblate.vcs.git import GitRepository


class GitHubFixtureTest(SimpleTestCase):
    def test_offline_clone_fetch_and_branches(self) -> None:
        original_getenv = GitRepository._getenv  # ruff: ignore[private-member-access]

        def offline_git_environment(
            environment: dict[str, str] | None = None, *, cwd: str | None = None
        ) -> dict[str, str]:
            result = original_getenv(environment, cwd=cwd)
            index = int(result.get("GIT_CONFIG_COUNT", "0"))
            result["GIT_CONFIG_COUNT"] = str(index + 1)
            result[f"GIT_CONFIG_KEY_{index}"] = "protocol.https.allow"
            result[f"GIT_CONFIG_VALUE_{index}"] = "never"
            return result

        with (
            github_fixture_repositories(),
            TemporaryDirectory() as root,
            patch.object(GitRepository, "_getenv", side_effect=offline_git_environment),
            patch("socket.getaddrinfo", side_effect=AssertionError("Unexpected DNS")),
        ):
            for url, name, branches, expected_path, absent_path in (
                (
                    DEMO_URL,
                    "demo",
                    ["main"],
                    "weblate/langdata/locale/django.pot",
                    "po-duplicates",
                ),
                (
                    TEST_URL,
                    "test",
                    ["main", "translations"],
                    "po-duplicates/hello.pot",
                    "weblate",
                ),
            ):
                with self.subTest(url=url):
                    self.assertEqual(GitRepository.get_remote_branch(url), "main")
                    path = Path(root, name)
                    repository = GitRepository.clone(url, str(path), "main")
                    self.assertEqual(repository.list_remote_branches(), branches)
                    self.assertEqual(repository.get_config("remote.origin.url"), url)
                    self.assertTrue((path / expected_path).is_file())
                    self.assertFalse((path / absent_path).exists())
                    with repository.lock:
                        repository.update_remote()

    def test_demo_discovery(self) -> None:
        with github_fixture_repositories(), TemporaryDirectory() as root:
            GitRepository.clone(DEMO_URL, root, "main")
            results = discover(root, source_language="en")
            self.assertEqual(
                {result["filemask"] for result in results},
                {
                    "weblate/langdata/locale/*/LC_MESSAGES/django.po",
                    "weblate/locale/*/LC_MESSAGES/django.po",
                    "weblate/locale/*/LC_MESSAGES/djangojs.po",
                    "app/src/main/res/values-*/strings.xml",
                },
            )

    def test_config_restored_after_failure(self) -> None:
        config = Path(data_dir("home"), ".config", "git", "config")
        config.parent.mkdir(parents=True, exist_ok=True)
        original = config.read_bytes() if config.exists() else None
        if original is None:
            self.addCleanup(config.unlink, missing_ok=True)
        else:
            self.addCleanup(config.write_bytes, original)
        for content in (None, b'[user]\n\tname = "Existing configuration"\n'):
            with self.subTest(existing_config=content is not None):
                if content is None:
                    config.unlink(missing_ok=True)
                else:
                    config.write_bytes(content)
                with (
                    self.assertRaisesRegex(RuntimeError, "Test failure"),
                    github_fixture_repositories() as repositories,
                ):
                    paths = list(repositories.values())
                    msg = "Test failure"
                    raise RuntimeError(msg)
                self.assertEqual(
                    config.read_bytes() if config.exists() else None, content
                )
                self.assertTrue(all(not path.exists() for path in paths))
