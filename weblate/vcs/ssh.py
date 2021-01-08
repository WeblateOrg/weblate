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

import hashlib
import os
import stat
import subprocess
from base64 import b64decode, b64encode
from distutils.spawn import find_executable

from django.utils.functional import cached_property
from django.utils.translation import gettext as _

from weblate.trans.util import get_clean_env
from weblate.utils import messages
from weblate.utils.data import data_dir
from weblate.utils.hash import calculate_checksum

# SSH key files
KNOWN_HOSTS = "known_hosts"
RSA_KEY = "id_rsa"
RSA_KEY_PUB = "id_rsa.pub"


def ssh_file(filename):
    """Generate full path to SSH configuration file."""
    return os.path.join(data_dir("ssh"), filename)


def is_key_line(key):
    """Check whether this line looks like a valid known_hosts line."""
    if not key:
        return False
    # Comment
    if key[0] == "#":
        return False
    # Special entry like @cert-authority
    if key[0] == "@":
        return False
    return (
        " ssh-rsa " in key or " ecdsa-sha2-nistp256 " in key or " ssh-ed25519 " in key
    )


def parse_hosts_line(line):
    """Parse single hosts line into tuple host, key fingerprint."""
    host, keytype, key = line.strip().split(None, 3)[:3]
    digest = hashlib.sha256(b64decode(key)).digest()
    fingerprint = b64encode(digest).rstrip(b"=").decode()
    if host.startswith("|1|"):
        # Translators: placeholder SSH hashed hostname
        host = _("[hostname hashed]")
    return host, keytype, fingerprint


def get_host_keys():
    """Return list of host keys."""
    try:
        result = []
        with open(ssh_file(KNOWN_HOSTS)) as handle:
            for line in handle:
                line = line.strip()
                if is_key_line(line):
                    result.append(parse_hosts_line(line))
    except OSError:
        return []

    return result


def get_key_data():
    """Parse host key and returns it."""
    # Read key data if it exists
    if os.path.exists(ssh_file(RSA_KEY_PUB)):
        with open(ssh_file(RSA_KEY_PUB)) as handle:
            key_data = handle.read()
        key_type, key_fingerprint, key_id = key_data.strip().split(None, 2)
        return {
            "key": key_data,
            "type": key_type,
            "fingerprint": key_fingerprint,
            "id": key_id,
        }
    return None


def generate_ssh_key(request):
    """Generate SSH key."""
    keyfile = ssh_file(RSA_KEY)
    pubkeyfile = ssh_file(RSA_KEY_PUB)
    try:
        # Actually generate the key
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-b",
                "4096",
                "-N",
                "",
                "-C",
                "Weblate",
                "-t",
                "rsa",
                "-f",
                keyfile,
            ],
            universal_newlines=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=get_clean_env(),
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        messages.error(
            request, _("Failed to generate key: %s") % getattr(exc, "output", str(exc))
        )
        return

    # Fix key permissions
    os.chmod(keyfile, stat.S_IWUSR | stat.S_IRUSR)
    os.chmod(pubkeyfile, stat.S_IWUSR | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    messages.success(request, _("Created new SSH key."))


def add_host_key(request, host, port=""):
    """Add host key for a host."""
    if not host:
        messages.error(request, _("Invalid host name given!"))
    else:
        cmdline = ["ssh-keyscan"]
        if port:
            cmdline.extend(["-p", str(port)])
        cmdline.append(host)
        try:
            result = subprocess.run(
                cmdline,
                env=get_clean_env(),
                check=True,
                universal_newlines=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            keys = []
            for key in result.stdout.splitlines():
                key = key.strip()
                if not is_key_line(key):
                    continue
                keys.append(key)
                host, keytype, fingerprint = parse_hosts_line(key)
                messages.warning(
                    request,
                    _(
                        "Added host key for %(host)s with fingerprint "
                        "%(fingerprint)s (%(keytype)s), "
                        "please verify that it is correct."
                    )
                    % {"host": host, "fingerprint": fingerprint, "keytype": keytype},
                )
            if not keys:
                messages.error(request, _("Failed to fetch public key for a host!"))
            with open(ssh_file(KNOWN_HOSTS), "a") as handle:
                for key in keys:
                    handle.write(f"{key}\n")
        except subprocess.CalledProcessError as exc:
            messages.error(
                request, _("Failed to get host key: %s") % exc.stderr or exc.stdout
            )
        except OSError as exc:
            messages.error(request, _("Failed to get host key: %s") % str(exc))


def can_generate_key():
    """Check whether we can generate key."""
    return find_executable("ssh-keygen") is not None


class SSHWrapper:
    # Custom ssh wrapper
    # - use custom location for known hosts and key
    # - do not hash it
    # - strict hosk key checking
    # - force not using system configuration (to avoid evil things as SendEnv)
    SSH_WRAPPER_TEMPLATE = r"""#!/bin/sh
    exec ssh \
        -o "UserKnownHostsFile={known_hosts}" \
        -o "IdentityFile={identity}" \
        -o StrictHostKeyChecking=yes \
        -o HashKnownHosts=no \
        -F /dev/null \
        "$@"
    """

    @cached_property
    def filename(self):
        """Calculates unique wrapper filename.

        It is based on template and DATA_DIR settings.
        """
        digest = calculate_checksum(self.SSH_WRAPPER_TEMPLATE, data_dir("ssh"))
        return ssh_file(f"ssh-weblate-wrapper-{digest}")

    def create(self):
        """Create wrapper for SSH to pass custom known hosts and key."""
        if os.path.exists(self.filename):
            return

        with open(self.filename, "w") as handle:
            handle.write(
                self.SSH_WRAPPER_TEMPLATE.format(
                    known_hosts=ssh_file(KNOWN_HOSTS), identity=ssh_file(RSA_KEY)
                )
            )

        os.chmod(self.filename, 0o755)  # nosec


SSH_WRAPPER = SSHWrapper()
