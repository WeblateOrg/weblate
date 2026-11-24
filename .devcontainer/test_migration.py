# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify migration isolation without running Docker or external VCS requests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from environment import git
from migration import configure_migration, migration_test, snapshot


class SnapshotTests(unittest.TestCase):
    def test_dirty_worktree_is_copied_without_changing_source(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            git(source, "init")
            git(source, "config", "user.name", "Verification")
            git(source, "config", "user.email", "test@example.com")
            (source / ".gitignore").write_text("ignored\n")
            (source / "tracked").write_text("before")
            (source / "deleted").write_text("remove")
            git(source, "add", ".")
            git(source, "commit", "-m", "test: original")
            # Exercise a linked worktree with separate staged and unstaged edits.
            worktree = root / "worktree $with spaces"
            git(source, "worktree", "add", "--detach", str(worktree))
            (worktree / "tracked").write_text("staged")
            git(worktree, "add", "tracked")
            (worktree / "tracked").write_text("unstaged")
            (worktree / "deleted").unlink()
            (worktree / "binary").write_bytes(b"\0\xff")
            (worktree / "link").symlink_to("tracked")
            (worktree / "ignored").write_text("do not copy")
            before = (
                git(worktree, "status", "--porcelain=v1"),
                git(worktree, "rev-parse", "HEAD"),
                git(worktree, "diff", "--cached"),
            )
            destination = root / "snapshot"
            snapshot(worktree, destination)
            self.assertEqual((destination / "tracked").read_text(), "unstaged")
            self.assertFalse((destination / "deleted").exists())
            self.assertEqual((destination / "binary").read_bytes(), b"\0\xff")
            self.assertTrue((destination / "link").is_symlink())
            self.assertFalse((destination / "ignored").exists())
            self.assertTrue((destination / ".git").is_dir())
            self.assertFalse((destination / ".git/objects/info/alternates").exists())
            self.assertEqual(git(destination, "status", "--porcelain=v1"), "")
            self.assertEqual(
                before,
                (
                    git(worktree, "status", "--porcelain=v1"),
                    git(worktree, "rev-parse", "HEAD"),
                    git(worktree, "diff", "--cached"),
                ),
            )
            (destination / ".devcontainer").mkdir()
            env = configure_migration(destination)
            config = json.loads(
                (destination / ".devcontainer/compose.local.json").read_text()
            )
            self.assertEqual(
                config["services"]["database"]["environment"]["POSTGRES_USER"],
                "postgres",
            )
            self.assertEqual(
                config["services"]["developer"]["build"]["target"], "migration"
            )
            self.assertEqual(env.backend, "compose")

    def test_cleanup_on_startup_failure_test_failure_and_interrupt(self) -> None:
        for startup, outcome in ((1, 0), (0, 2), (0, KeyboardInterrupt())):
            with self.subTest(startup=startup, outcome=outcome):
                env = Mock()
                env.services = ["developer", "database", "cache"]
                env.up.return_value = startup
                env.call.return_value = 0
                if isinstance(outcome, BaseException):
                    env.execute.side_effect = outcome
                else:
                    env.execute.return_value = outcome
                with (
                    patch("migration.snapshot"),
                    patch("migration.configure_migration", return_value=env),
                ):
                    if isinstance(outcome, BaseException):
                        with self.assertRaises(KeyboardInterrupt):
                            migration_test(Path.cwd(), "5.10")
                    else:
                        self.assertEqual(
                            migration_test(Path.cwd(), "5.10"), startup or outcome
                        )
                self.assertEqual(
                    env.call.call_args.args, ("down", "--volumes", "--remove-orphans")
                )
                if startup:
                    env.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
