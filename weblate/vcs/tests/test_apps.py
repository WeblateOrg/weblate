# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.vcs.apps import check_vcs, check_vcs_versions
from weblate.vcs.base import Repository
from weblate.vcs.git import (
    GitRepository,
    GitWithGerritRepository,
    SubversionRepository,
)
from weblate.vcs.mercurial import HgRepository
from weblate.vcs.models import VCS_REGISTRY


class OptionalRepository(Repository):
    name = "Optional"
    identifier = "optional"
    _cmd = "optional-vcs"
    req_version = "2"

    @classmethod
    def _get_version(cls) -> str:
        return cls._popen(["--version"])


class SharedVersionRepository(Repository):
    name = "Shared"
    identifier = "shared"
    _cmd = "shared-vcs"
    req_version = "2"

    @classmethod
    def _get_version(cls) -> str:
        return cls._popen(["--version"])


class OtherSharedVersionRepository(SharedVersionRepository):
    name = "Other shared"
    identifier = "other-shared"


OPTIONAL_BACKENDS = ("weblate.vcs.tests.test_apps.OptionalRepository",)
SHARED_BACKENDS = (
    "weblate.vcs.tests.test_apps.SharedVersionRepository",
    "weblate.vcs.tests.test_apps.OtherSharedVersionRepository",
)


class VCSChecksTest(SimpleTestCase):
    def setUp(self) -> None:
        Repository.clear_version_cache()
        VCS_REGISTRY.clear_cache()

    def tearDown(self) -> None:
        Repository.clear_version_cache()
        VCS_REGISTRY.clear_cache()

    def test_builtin_required_commands(self) -> None:
        with patch("weblate.vcs.base.find_runtime_command", return_value=None):
            self.assertEqual(GitRepository.get_missing_commands(), ("git",))
            self.assertEqual(
                GitWithGerritRepository.get_missing_commands(),
                ("git", "git-review"),
            )
            self.assertEqual(
                SubversionRepository.get_missing_commands(),
                ("git", "svn"),
            )
            self.assertIn(HgRepository.get_missing_commands(), (("hg",), ("rhg",)))

    def test_subversion_availability_does_not_execute_git(self) -> None:
        with (
            patch(
                "weblate.vcs.base.find_runtime_command",
                return_value="/usr/bin/command",
            ),
            patch.object(SubversionRepository, "_popen") as popen,
        ):
            self.assertEqual(SubversionRepository.get_missing_commands(), ())

        popen.assert_not_called()

    def test_registry_invalidated_on_credentials_change(self) -> None:
        backends = {
            "AZURE_DEVOPS_CREDENTIALS": "azure_devops",
            "BITBUCKETCLOUD_CREDENTIALS": "bitbucketcloud",
            "BITBUCKETSERVER_CREDENTIALS": "bitbucketserver",
            "GITEA_CREDENTIALS": "gitea",
            "GITHUB_CREDENTIALS": "github",
            "GITLAB_CREDENTIALS": "gitlab",
            "PAGURE_CREDENTIALS": "pagure",
        }
        for setting_name, backend in backends.items():
            with self.subTest(setting=setting_name):
                self.assertNotIn(backend, VCS_REGISTRY)
                with override_settings(**{setting_name: {"example.com": {}}}):
                    self.assertIn(backend, VCS_REGISTRY)
                self.assertNotIn(backend, VCS_REGISTRY)

    @override_settings(VCS_BACKENDS=OPTIONAL_BACKENDS)
    def test_registry_checks_availability_without_version_probe(self) -> None:
        with (
            patch("weblate.vcs.base.find_runtime_command", return_value=None),
            patch.object(OptionalRepository, "_get_version") as get_version,
        ):
            self.assertEqual(list(VCS_REGISTRY), [])

        get_version.assert_not_called()
        self.assertEqual(
            VCS_REGISTRY.errors,
            {"Optional": "Command not found: optional-vcs"},
        )

    @override_settings(VCS_BACKENDS=OPTIONAL_BACKENDS)
    def test_standard_check_does_not_probe_version(self) -> None:
        with (
            patch(
                "weblate.vcs.base.find_runtime_command",
                return_value="/usr/bin/optional-vcs",
            ),
            patch.object(OptionalRepository, "_get_version") as get_version,
        ):
            self.assertEqual(
                list(check_vcs(app_configs=None, databases=None)),
                [],
            )

        get_version.assert_not_called()

    @override_settings(VCS_BACKENDS=OPTIONAL_BACKENDS)
    def test_deployment_check_reports_outdated_version(self) -> None:
        with (
            patch(
                "weblate.vcs.base.find_runtime_command",
                return_value="/usr/bin/optional-vcs",
            ),
            patch.object(OptionalRepository, "_get_version", return_value="1"),
        ):
            errors = list(check_vcs_versions(app_configs=None, databases=None))

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].id, "weblate.W033.Optional")
        self.assertIn("Outdated version: 1", errors[0].msg)

    @override_settings(VCS_BACKENDS=OPTIONAL_BACKENDS)
    def test_deployment_check_reports_invalid_version(self) -> None:
        with (
            patch(
                "weblate.vcs.base.find_runtime_command",
                return_value="/usr/bin/optional-vcs",
            ),
            patch.object(
                OptionalRepository,
                "_get_version",
                return_value="invalid-version",
            ),
        ):
            errors = list(check_vcs_versions(app_configs=None, databases=None))

        self.assertEqual(len(errors), 1)
        self.assertIn("Invalid version", errors[0].msg)

    @override_settings(VCS_BACKENDS=OPTIONAL_BACKENDS)
    def test_deployment_check_reports_version_probe_failure(self) -> None:
        with (
            patch(
                "weblate.vcs.base.find_runtime_command",
                return_value="/usr/bin/optional-vcs",
            ),
            patch.object(
                OptionalRepository,
                "_get_version",
                side_effect=OSError("probe failed"),
            ),
        ):
            errors = list(check_vcs_versions(app_configs=None, databases=None))

        self.assertEqual(len(errors), 1)
        self.assertIn("probe failed", errors[0].msg)

    @override_settings(VCS_BACKENDS=SHARED_BACKENDS)
    def test_deployment_check_shares_version_probe(self) -> None:
        with (
            patch(
                "weblate.vcs.base.find_runtime_command",
                return_value="/usr/bin/shared-vcs",
            ),
            patch.object(
                SharedVersionRepository,
                "_popen",
                return_value="2",
            ) as popen,
        ):
            errors = list(check_vcs_versions(app_configs=None, databases=None))

        self.assertEqual(errors, [])
        popen.assert_called_once_with(["--version"])
