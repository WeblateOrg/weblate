# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import subprocess

from django.conf import settings
from django.core.cache import cache
from siphashc import siphash

from weblate.trans.util import get_clean_env
from weblate.utils.errors import report_error

GPG_ERRORS: dict[str, str] = {}


def gpg_error(name: str, error: Exception, silent: bool = False) -> None:
    report_error(name)

    if not silent:
        GPG_ERRORS[name] = "{}\n{}\n{}".format(
            error, getattr(error, "stderr", ""), getattr(error, "stdout", "")
        )


def generate_gpg_key() -> str | None:
    try:
        subprocess.run(
            [
                "gpg",
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-generate-key",
                settings.WEBLATE_GPG_IDENTITY,
                settings.WEBLATE_GPG_ALGO,
                "default",
                "never",
            ],
            env=get_clean_env(),
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError) as error:
        gpg_error("GPG key generating", error)
        return None
    return get_gpg_key()


def get_gpg_key(silent=False) -> str | None:
    try:
        result = subprocess.run(
            [
                "gpg",
                "--batch",
                "--with-colons",
                "--list-secret-keys",
                settings.WEBLATE_GPG_IDENTITY,
            ],
            capture_output=True,
            env=get_clean_env(),
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError) as error:
        gpg_error("GPG key listing", error, silent)
        return None
    for line in result.stdout.splitlines():
        if not line.startswith("fpr:"):  # codespell:ignore fpr
            continue
        return line.split(":")[9]
    return None


def gpg_cache_key(suffix: str) -> str:
    return "gpg:{}:{}".format(
        siphash("Weblate GPG hash", settings.WEBLATE_GPG_IDENTITY), suffix
    )


def get_gpg_sign_key() -> str | None:
    """High level wrapper to cache key ID."""
    if not settings.WEBLATE_GPG_IDENTITY:
        return None
    cache_key = gpg_cache_key("id")
    keyid = cache.get(cache_key)
    if keyid is None:
        keyid = get_gpg_key(silent=True)
        if keyid is None:
            keyid = generate_gpg_key()
        if keyid:
            cache.set(cache_key, keyid, 7 * 86400)
    return keyid


def get_gpg_public_key() -> str | None:
    key = get_gpg_sign_key()
    if key is None:
        return None
    cache_key = gpg_cache_key("public")
    data = cache.get(cache_key)
    if not data:
        try:
            result = subprocess.run(
                ["gpg", "--batch", "-armor", "--export", key],
                env=get_clean_env(),
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.CalledProcessError, OSError) as error:
            gpg_error("GPG key public", error)
            return None
        data = result.stdout
        cache.set(cache_key, data, 7 * 86400)
    return data
