# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Local Git transport for tests displaying real GitHub repository URLs."""

from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.conf import settings
from django.test.utils import override_settings

from weblate.trans.tests.utils import RepoTestMixin
from weblate.utils.data import data_dir
from weblate.utils.validators import resolve_runtime_hostname
from weblate.vcs.git import GitRepository

if TYPE_CHECKING:
    from collections.abc import Generator

DEMO_URL = "https://github.com/WeblateOrg/demo.git"
TEST_URL = "https://github.com/WeblateOrg/test.git"
DEMO_REF = "refs/fixtures/screenshot-demo"


@contextmanager
def github_fixture_repositories() -> Generator[dict[str, Path], None, None]:
    """Route GitHub URLs to isolated local copies without changing their display."""
    fixture = RepoTestMixin()
    base = fixture.git_base_repo_path
    with TemporaryDirectory(prefix="github-fixtures-", dir=settings.DATA_DIR) as root:
        repositories = {
            DEMO_URL: Path(root, "demo.git"),
            TEST_URL: Path(root, "test.git"),
        }
        # Use the backend runner so Git shares Weblate's isolated test HOME.
        execute = GitRepository._popen  # ruff: ignore[private-member-access]
        for url, repository in repositories.items():
            shutil.copytree(base, repository)
            git_dir = f"--git-dir={repository}"
            if url == DEMO_URL:
                revision = execute([git_dir, "rev-parse", DEMO_REF]).strip()
                references = execute(
                    [git_dir, "for-each-ref", "--format=%(refname)"]
                ).splitlines()
                for reference in references:
                    execute([git_dir, "update-ref", "-d", reference])
                execute([git_dir, "update-ref", "refs/heads/main", revision])
                execute([git_dir, "symbolic-ref", "HEAD", "refs/heads/main"])
            else:
                execute([git_dir, "update-ref", "-d", DEMO_REF])

        # Weblate rewrites ~/.gitconfig during global_setup(), so keep the
        # transport-only rewrites in the test home's XDG configuration instead.
        config = Path(data_dir("home"), ".config", "git", "config")
        config.parent.mkdir(parents=True, exist_ok=True)
        original = config.read_bytes() if config.exists() else None

        def resolve_fixture_hostname(
            hostname: str, *, allow_private_targets: bool = True
        ) -> tuple[str, ...]:
            if hostname == "github.com":
                # Git never connects here: insteadOf routes the request locally.
                return ("192.0.2.1",)
            return resolve_runtime_hostname(
                hostname, allow_private_targets=allow_private_targets
            )

        try:
            GitRepository.git_config_update(
                config,
                *(
                    (f'url "{repository.as_uri()}"', "insteadOf", url)
                    for url, repository in repositories.items()
                ),
            )
            with (
                override_settings(VCS_ALLOW_HOSTS={"github.com"}),
                patch(
                    "weblate.utils.validators.resolve_runtime_hostname",
                    side_effect=resolve_fixture_hostname,
                ),
            ):
                yield repositories
        finally:
            if original is None:
                config.unlink(missing_ok=True)
            else:
                config.write_bytes(original)
