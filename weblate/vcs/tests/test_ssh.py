# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import shutil
from pathlib import Path
from time import time

from django.conf import settings
from django.test import TestCase
from django.test.utils import override_settings

from weblate.trans.tests.utils import get_test_file
from weblate.utils.apps import check_data_writable
from weblate.utils.unittest import tempdir_setting
from weblate.vcs.ssh import (
    STALE_WRAPPER_SECONDS,
    SSHWrapper,
    cleanup_legacy_wrapper_dirs,
    cleanup_stale_wrapper_dirs,
    extract_url_host_port,
    get_host_key_entries,
    get_host_keys,
    remove_host_key,
    ssh_file,
    ssh_wrapper_path,
)

TEST_HOSTS = get_test_file("known_hosts")


class SSHTest(TestCase):
    """Test for customized admin interface."""

    @tempdir_setting("DATA_DIR")
    def test_parse(self) -> None:
        self.assertEqual(check_data_writable(app_configs=None, databases=None), [])
        shutil.copy(TEST_HOSTS, os.path.join(settings.DATA_DIR, "ssh"))
        hosts = get_host_keys()
        self.assertEqual(len(hosts), 50)

    @tempdir_setting("DATA_DIR")
    def test_remove_host_key(self) -> None:
        known_hosts = ssh_file("known_hosts")
        known_hosts.parent.mkdir(parents=True, exist_ok=True)
        known_hosts.write_text(
            "\n".join(Path(TEST_HOSTS).read_text(encoding="utf-8").splitlines()[:2])
            + "\n",
            encoding="utf-8",
        )

        host_keys = get_host_key_entries()
        self.assertEqual(len(host_keys), 2)

        self.assertTrue(remove_host_key(None, host_keys[0]["id"]))

        remaining = get_host_key_entries()
        self.assertEqual(len(remaining), 1)
        self.assertNotEqual(remaining[0]["id"], host_keys[0]["id"])

    @tempdir_setting("CACHE_DIR")
    @tempdir_setting("DATA_DIR")
    def test_create_ssh_wrapper(self) -> None:
        self.assertEqual(check_data_writable(app_configs=None, databases=None), [])
        wrapper = SSHWrapper()
        filename = wrapper.filename
        wrapper.create()
        data = filename.read_text()
        self.assertEqual(filename.parent.parent, ssh_wrapper_path())
        self.assertTrue(filename.is_relative_to(Path(settings.CACHE_DIR)))
        self.assertIn(ssh_file("known_hosts").as_posix(), data)
        self.assertIn(ssh_file("id_rsa").as_posix(), data)
        self.assertIn(settings.DATA_DIR, data)
        self.assertTrue(os.access(filename, os.X_OK))
        # Second run should not touch the file
        timestamp = os.stat(filename).st_mtime
        wrapper.create()
        self.assertEqual(timestamp, os.stat(filename).st_mtime)

    @tempdir_setting("CACHE_DIR")
    @tempdir_setting("DATA_DIR")
    @override_settings(SSH_EXTRA_ARGS="-oKexAlgorithms=+diffie-hellman-group1-sha1")
    def test_ssh_args(self) -> None:
        wrapper = SSHWrapper()
        filename = wrapper.filename
        wrapper.create()
        data = filename.read_text()
        self.assertIn(settings.SSH_EXTRA_ARGS, data)
        self.assertTrue(os.access(filename, os.X_OK))
        # Second run should not touch the file
        timestamp = os.stat(filename).st_mtime
        wrapper.create()
        self.assertEqual(timestamp, os.stat(filename).st_mtime)

    @tempdir_setting("DATA_DIR")
    def test_cleanup_legacy_wrappers(self) -> None:
        legacy_wrapper_dir = ssh_file("bin-legacy-dir")
        legacy_wrapper_file = ssh_file("bin-legacy-file")
        persistent_file = ssh_file("known_hosts")

        legacy_wrapper_dir.mkdir(parents=True)
        legacy_wrapper_file.write_text("#!/bin/sh\n")
        persistent_file.write_text("example ssh-ed25519 AAAA\n")

        cleanup_legacy_wrapper_dirs()

        self.assertFalse(legacy_wrapper_dir.exists())
        self.assertFalse(legacy_wrapper_file.exists())
        self.assertTrue(persistent_file.exists())

    @tempdir_setting("CACHE_DIR")
    @tempdir_setting("DATA_DIR")
    def test_cleanup_stale_cached_wrappers(self) -> None:
        wrapper = SSHWrapper()
        wrapper.create()

        stale_wrapper_dir = ssh_wrapper_path("bin-stale")
        active_wrapper_dir = ssh_wrapper_path("bin-active")
        recent_wrapper_dir = ssh_wrapper_path("bin-recent")
        stale_wrapper_dir.mkdir(parents=True)
        active_wrapper_dir.mkdir(parents=True)
        recent_wrapper_dir.mkdir(parents=True)
        stale_wrapper_file = stale_wrapper_dir / "ssh"
        active_wrapper_file = active_wrapper_dir / "ssh"
        stale_wrapper_file.write_text("#!/bin/sh\n")
        active_wrapper_file.write_text("#!/bin/sh\n")

        expired_atime = time() - STALE_WRAPPER_SECONDS - 1
        os.utime(wrapper.path, (expired_atime, expired_atime))
        os.utime(stale_wrapper_dir, (expired_atime, expired_atime))
        os.utime(stale_wrapper_file, (expired_atime, expired_atime))
        os.utime(active_wrapper_dir, (expired_atime, expired_atime))

        cleanup_stale_wrapper_dirs()

        self.assertTrue(wrapper.path.exists())
        self.assertFalse(stale_wrapper_dir.exists())
        self.assertTrue(active_wrapper_dir.exists())
        self.assertTrue(recent_wrapper_dir.exists())

    def test_extract_url_host_port(self) -> None:
        self.assertEqual((None, None), extract_url_host_port(""))
        self.assertEqual((None, None), extract_url_host_port("http://"))
        self.assertEqual((None, None), extract_url_host_port("http:// invalid/url"))
        self.assertEqual(
            ("github.com", None), extract_url_host_port("git@github.com:repo")
        )
        self.assertEqual(
            ("github.com", 1234), extract_url_host_port("git://github.com:1234/repo")
        )
