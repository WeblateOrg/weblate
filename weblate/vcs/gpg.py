#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#


import subprocess
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from siphashc import siphash

from weblate.trans.util import get_clean_env
from weblate.utils.errors import report_error

GPG_ERRORS = {}


def gpg_error(name: str, error: Exception, silent: bool = False):
    report_error(cause=name)

    if not silent:
        GPG_ERRORS[name] = "{}\n{}\n{}".format(
            error, getattr(error, "stderr", ""), getattr(error, "stdout", "")
        )


def generate_gpg_key() -> Optional[str]:
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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=True,
        )
        return get_gpg_key()
    except (subprocess.CalledProcessError, OSError) as error:
        gpg_error("GPG key generating", error)
        return None


def get_gpg_key(silent=False) -> Optional[str]:
    try:
        result = subprocess.run(
            [
                "gpg",
                "--batch",
                "--with-colons",
                "--list-secret-keys",
                settings.WEBLATE_GPG_IDENTITY,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=get_clean_env(),
            universal_newlines=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            if not line.startswith("fpr:"):
                continue
            return line.split(":")[9]
        return None
    except (subprocess.CalledProcessError, OSError) as error:
        gpg_error("GPG key listing", error, silent)
        return None


def gpg_cache_key(suffix: str) -> str:
    return "gpg:{}:{}".format(
        siphash("Weblate GPG hash", settings.WEBLATE_GPG_IDENTITY), suffix
    )


def get_gpg_sign_key() -> Optional[str]:
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


def get_gpg_public_key() -> Optional[str]:
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
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                check=True,
            )
            data = result.stdout
            cache.set(cache_key, data, 7 * 86400)
        except (subprocess.CalledProcessError, OSError) as error:
            gpg_error("GPG key public", error)
            return None
    return data
