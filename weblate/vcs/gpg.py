#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

from django.conf import settings
from django.core.cache import cache
from django.utils.encoding import force_str

from weblate.trans.util import (
    add_configuration_error,
    delete_configuration_error,
    get_clean_env,
)
from weblate.utils.errors import report_error


def generate_gpg_key():
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
        )
        delete_configuration_error("GPG key generating")
        return get_gpg_key()
    except (subprocess.CalledProcessError, OSError) as exc:
        report_error(cause="GPG key generating")
        add_configuration_error("GPG key generating", force_str(exc))
        return None


def get_gpg_key(silent=False):
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
        )
        for line in result.stdout.splitlines():
            if not line.startswith("fpr:"):
                continue
            delete_configuration_error("GPG key listing")
            return line.split(":")[9]
        return None
    except (subprocess.CalledProcessError, OSError) as error:
        report_error(cause="GPG key listing")
        if not silent:
            add_configuration_error("GPG key listing", force_str(error))
        return None


def get_gpg_sign_key():
    """High level wrapper to cache key ID."""
    if not settings.WEBLATE_GPG_IDENTITY:
        return None
    keyid = cache.get("gpg-key-id")
    if keyid is None:
        keyid = get_gpg_key(silent=True)
        if keyid is None:
            keyid = generate_gpg_key()
        if keyid:
            cache.set("gpg-key-id", keyid, 7 * 86400)
    return keyid


def get_gpg_public_key():
    key = get_gpg_sign_key()
    if key is None:
        return None
    data = cache.get("gpg-key-public")
    if not data:
        try:
            result = subprocess.run(
                ["gpg", "--batch", "-armor", "--export", key],
                env=get_clean_env(),
                capture_output=True,
                text=True,
            )
            data = result.stdout
            cache.set("gpg-key-public", data, 7 * 86400)
            delete_configuration_error("GPG key public")
        except (subprocess.CalledProcessError, OSError) as error:
            report_error(cause="GPG key public")
            add_configuration_error("GPG key public", force_str(error))
            return None
    return data
