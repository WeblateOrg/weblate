# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mercurial subrepository and nested-metadata isolation."""

from __future__ import annotations

import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory
from unittest import skipUnless
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from weblate.vcs.base import RepositoryError
from weblate.vcs.mercurial import HgRepository


class MercurialSubrepositoryTest(SimpleTestCase):
    def test_all_commands_disable_subrepositories(self) -> None:
        with TemporaryDirectory() as directory:
            repository = HgRepository(directory, local=True)
            for command in ("init", "clone", "update", "pull", "commit", "version"):
                with (
                    self.subTest(command=command),
                    patch(
                        "weblate.vcs.base.subprocess.run",
                        return_value=subprocess.CompletedProcess([], 0, "", ""),
                    ) as run,
                ):
                    repository.execute([command], remote_op="none", needs_lock=False)
                    self.assertEqual(
                        run.call_args.kwargs["args"][1:4],
                        ["--config", "subrepos.allowed=false", command],
                    )

    def test_cleanup_preserves_working_files_and_primary_metadata(self) -> None:
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            root = Path(directory)
            metadata = root / ".hg"
            metadata.mkdir()
            (metadata / "requires").write_text("revlogv1\n", encoding="utf-8")
            (metadata / "keep").write_bytes(b"primary history")
            nested = root / "child" / ".hg" / "store"
            nested.mkdir(parents=True)
            (nested / "private.i").write_bytes(b"copied history")
            translation = root / "child" / "translation.po"
            translation.write_bytes(b"translated content")
            (root / "child" / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
            (root / ".gitignore").write_bytes(b"ignored")
            external = Path(outside) / ".hg"
            external.mkdir()
            (external / "keep").write_bytes(b"external history")
            (root / "linked").symlink_to(outside, target_is_directory=True)
            (root / "metadata-link").mkdir()
            (root / "metadata-link" / ".hg").symlink_to(
                external, target_is_directory=True
            )
            (root / ".git").mkdir()
            (root / ".git" / "HEAD").write_bytes(b"nested git history")

            repository = HgRepository(directory, local=True)
            with repository.lock:
                self.assertFalse((root / "child" / ".hg").exists())
                self.assertFalse((root / "child" / ".git").exists())
                self.assertFalse((root / ".git").exists())
                self.assertFalse((root / "metadata-link" / ".hg").is_symlink())
                self.assertEqual(translation.read_bytes(), b"translated content")
                self.assertEqual((metadata / "keep").read_bytes(), b"primary history")
                self.assertEqual((external / "keep").read_bytes(), b"external history")
                self.assertEqual((root / ".gitignore").read_bytes(), b"ignored")

    def test_cleanup_requires_repository_lock(self) -> None:
        with TemporaryDirectory() as directory:
            repository = HgRepository(directory, local=True)
            with self.assertRaisesRegex(RuntimeError, "without lock"):
                repository.cleanup_nested_metadata()

    def test_cleanup_failure_stops_operation(self) -> None:
        with TemporaryDirectory() as directory:
            (Path(directory) / ".hg").mkdir()
            (Path(directory) / "child" / ".hg").mkdir(parents=True)
            repository = HgRepository(directory, local=True)
            with (
                patch(
                    "weblate.vcs.mercurial.shutil.rmtree", side_effect=PermissionError
                ),
                self.assertRaisesRegex(RepositoryError, "nested repository metadata"),
                repository.lock,
            ):
                self.fail("Recovery must reject the operation")

    def test_cleanup_skips_non_mercurial_checkout(self) -> None:
        with TemporaryDirectory() as directory:
            metadata = Path(directory) / ".git"
            metadata.mkdir()
            (metadata / "HEAD").write_bytes(b"primary git history")
            repository = HgRepository(directory, local=True)

            with repository.lock:
                self.assertEqual(
                    (metadata / "HEAD").read_bytes(), b"primary git history"
                )

    @staticmethod
    def run_hg(path: Path, *args: str) -> str:
        """Build local test fixtures with subrepositories deliberately enabled."""
        command = which("hg")
        if command is None:
            msg = "Mercurial is not installed"
            raise FileNotFoundError(msg)
        return subprocess.run(
            [
                command,
                "--config",
                "subrepos.allowed=true",
                "--config",
                "ui.username=Fixture <fixture@example.com>",
                *args,
            ],
            cwd=path,
            env={**os.environ, "HGPLAIN": "1", "HGRCPATH": ""},
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    @skipUnless(which("hg"), "Mercurial is not installed")
    @override_settings(VCS_ALLOW_SCHEMES=["file"], VCS_RESTRICT_PRIVATE=False)
    def test_native_clone_does_not_copy_subrepository(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            secret = root / "secret"
            upstream = root / "upstream"
            secret.mkdir()
            upstream.mkdir()
            self.run_hg(secret, "init")
            (secret / "private.txt").write_bytes(b"private translation")
            self.run_hg(secret, "add", "private.txt")
            self.run_hg(secret, "commit", "-m", "Private history")
            revision = self.run_hg(secret, "log", "-r", ".", "--template", "{node}")
            self.run_hg(upstream, "init")
            self.run_hg(upstream, "clone", str(secret), "nested")
            (upstream / ".hgsub").write_text(f"nested = {secret}\n", encoding="utf-8")
            (upstream / ".hgsubstate").write_text(
                f"{revision} nested\n", encoding="utf-8"
            )
            self.run_hg(upstream, "add", ".hgsub", ".hgsubstate")
            self.run_hg(upstream, "commit", "-m", "Subrepository revision")

            target = root / "checkout"
            with self.assertRaisesRegex(RepositoryError, "subrepos not enabled"):
                HgRepository.clone(str(upstream), str(target), "default")

            self.assertFalse((target / "nested" / ".hg").exists())
            self.assertFalse((target / "nested" / "private.txt").exists())
