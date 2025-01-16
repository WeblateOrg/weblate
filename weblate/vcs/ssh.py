# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from base64 import b64decode, b64encode
from typing import TYPE_CHECKING, Literal, TypedDict

from django.conf import settings
from django.core.management.utils import find_command
from django.utils.functional import cached_property
from django.utils.translation import gettext, pgettext_lazy

from weblate.trans.util import get_clean_env
from weblate.utils import messages
from weblate.utils.data import data_path
from weblate.utils.hash import calculate_checksum

if TYPE_CHECKING:
    from pathlib import Path

    from django_stubs_ext import StrOrPromise

    from weblate.auth.models import AuthenticatedHttpRequest

# SSH key files
KNOWN_HOSTS = "known_hosts"
CONFIG = "config"


class KeyInfo(TypedDict):
    private: str
    public: str
    name: StrOrPromise
    keygen: list[str]


KeyType = Literal["rsa", "ed25519"]

KEYS: dict[KeyType, KeyInfo] = {
    "rsa": {
        "private": "id_rsa",
        "public": "id_rsa.pub",
        "name": pgettext_lazy("SSH key type", "RSA"),
        "keygen": ["-b", "4096", "-t", "rsa"],
    },
    "ed25519": {
        "private": "id_ed25519",
        "public": "id_ed25519.pub",
        "name": pgettext_lazy("SSH key type", "Ed25519"),
        "keygen": ["-t", "ed25519"],
    },
}


def ssh_file(filename: str) -> Path:
    """Generate full path to SSH configuration file."""
    return data_path("ssh") / filename


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
        host = gettext("[hostname hashed]")
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


def get_key_data_raw(
    key_type: KeyType = "rsa", kind: Literal["public", "private"] = "public"
) -> tuple[str, str | None]:
    """Return raw public key data."""
    # Read key data if it exists
    filename = KEYS[key_type][kind]
    key_file = ssh_file(filename)
    if os.path.exists(key_file):
        with open(key_file) as handle:
            return filename, handle.read()
    return filename, None


def get_key_data(key_type: KeyType = "rsa") -> dict[str, StrOrPromise | None]:
    """Parse host key and returns it."""
    filename, key_data = get_key_data_raw(key_type)
    if key_data is not None:
        _key_type_parsed, key_fingerprint, key_id = key_data.strip().split(None, 2)
        return {
            "key": key_data,
            "fingerprint": key_fingerprint,
            "id": key_id,
            "filename": filename,
            "type": key_type,
            "name": KEYS[key_type]["name"],
        }
    return {
        "key": None,
        "type": key_type,
        "name": KEYS[key_type]["name"],
    }


def get_all_key_data() -> dict[str, dict[str, StrOrPromise | None]]:
    """Return all supported SSH keys."""
    return {key_type: get_key_data(key_type) for key_type in KEYS}


def ensure_ssh_key():
    """Ensure SSH key is existing."""
    result = None
    for key_type in KEYS:
        ssh_key = get_key_data(key_type)
        if not ssh_key["key"]:
            generate_ssh_key(None, key_type)
            ssh_key = get_key_data()
        if key_type == "rsa":
            result = ssh_key
    return result


def generate_ssh_key(
    request: AuthenticatedHttpRequest | None, key_type: KeyType = "rsa"
) -> None:
    """Generate SSH key."""
    key_info = KEYS[key_type]
    keyfile = ssh_file(key_info["private"])
    pubkeyfile = ssh_file(key_info["public"])
    try:
        # Actually generate the key
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                *key_info["keygen"],
                "-N",
                "",
                "-C",
                settings.SITE_TITLE,
                "-f",
                keyfile,
            ],
            text=True,
            check=True,
            capture_output=True,
            env=get_clean_env(),
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        error = getattr(exc, "output", "").strip()
        if not error:
            error = str(exc)
        messages.error(request, gettext("Could not generate key: %s") % error)
        return

    # Fix key permissions
    os.chmod(keyfile, stat.S_IWUSR | stat.S_IRUSR)
    os.chmod(pubkeyfile, stat.S_IWUSR | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    messages.success(request, gettext("Created new SSH key."))


def add_host_key(request: AuthenticatedHttpRequest | None, host, port="") -> None:
    """Add host key for a host."""
    if not host:
        messages.error(request, gettext("Invalid host name given!"))
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
                text=True,
                capture_output=True,
            )
            keys = set()
            for key in result.stdout.splitlines():
                key = key.strip()
                if not is_key_line(key):
                    continue
                keys.add(key)
                host, keytype, fingerprint = parse_hosts_line(key)
                messages.warning(
                    request,
                    gettext(
                        "Added host key for %(host)s with fingerprint "
                        "%(fingerprint)s (%(keytype)s), "
                        "please verify that it is correct."
                    )
                    % {"host": host, "fingerprint": fingerprint, "keytype": keytype},
                )
            if keys:
                known_hosts_file = ssh_file(KNOWN_HOSTS)
                # Remove existing key entries
                if known_hosts_file.exists():
                    with known_hosts_file.open() as handle:
                        keys.difference_update(line.strip() for line in handle)
                # Write any new keys
                if keys:
                    with known_hosts_file.open(mode="a") as handle:
                        for key in keys:
                            handle.write(key)
                            handle.write("\n")
            else:
                messages.error(
                    request,
                    gettext("Could not fetch public key for a host: %s") % result.stderr
                    or result.stdout,
                )
        except subprocess.CalledProcessError as exc:
            messages.error(
                request,
                gettext("Could not fetch public key for a host: %s") % exc.stderr
                or exc.stdout,
            )
        except OSError as exc:
            messages.error(request, gettext("Could not get host key: %s") % str(exc))


GITHUB_RSA_KEY = (
    "AAAAB3NzaC1yc2EAAAABIwAAAQEAq2A7hRGmdnm9tUDbO9IDSwBK6TbQa+PXYPCPy6rbTrTtw7"
    "PHkccKrpp0yVhp5HdEIcKr6pLlVDBfOLX9QUsyCOV0wzfjIJNlGEYsdlLJizHhbn2mUjvSAHQq"
    "ZETYP81eFzLQNnPHt4EVVUh7VfDESU84KezmD5QlWpXLmvU31/yMf+Se8xhHTvKSCZIFImWwoG"
    "6mbUoWf9nzpIoaSjB+weqqUUmpaaasXVal72J+UX2B+2RPW3RcT0eOzQgqlJL3RKrTJvdsjE3J"
    "EAvGq3lGHSZXy28G3skua2SmVi/w4yCE6gbODqnTWlg7+wC604ydGXA8VJiS5ap43JXiUFFAaQ=="
)


def cleanup_host_keys(*args, **kwargs) -> None:
    known_hosts_file = ssh_file(KNOWN_HOSTS)
    if not known_hosts_file.exists():
        return
    logger = kwargs.get("logger", print)
    keys = []
    with known_hosts_file.open() as handle:
        for line in handle:
            # Ignore IP address based RSA keys for GitHub, these
            # are duplicate to hostname based and cause problems on
            # migration to ECDSA.
            # See https://github.com/WeblateOrg/weblate/issues/6830
            if line[0].isdigit() and GITHUB_RSA_KEY in line:
                logger(f"Removing deprecated RSA key for GitHub: {line.strip()}")
                continue

            # Avoid duplicates
            if line in keys:
                logger(f"Skipping duplicate key: {line.strip()}")
                continue

            keys.append(line)

    with known_hosts_file.open(mode="w") as handle:
        handle.writelines(keys)


def can_generate_key():
    """Check whether we can generate key."""
    return find_command("ssh-keygen") is not None


SSH_WRAPPER_TEMPLATE = r"""#!/bin/sh
exec {command} \
    -o "UserKnownHostsFile={known_hosts}" \
    -o "IdentityFile={identity_rsa}" \
    -o "IdentityFile={identity_ed25519}" \
    -o StrictHostKeyChecking=yes \
    -o HashKnownHosts=no \
    -o UpdateHostKeys=yes \
    -F {config_file} \
    {extra_args} \
    "$@"
"""


class SSHWrapper:
    # Custom ssh wrapper
    # - use custom location for known hosts and key
    # - do not hash it
    # - strict hosk key checking
    # - force not using system configuration (to avoid evil things as SendEnv)

    @cached_property
    def digest(self):
        return calculate_checksum(self.get_content())

    @property
    def path(self) -> Path:
        """
        Calculates unique wrapper path.

        It is based on template and DATA_DIR settings.
        """
        return ssh_file(f"bin-{self.digest}")

    def get_content(self, command="ssh"):
        return SSH_WRAPPER_TEMPLATE.format(
            command=command,
            known_hosts=ssh_file(KNOWN_HOSTS).as_posix(),
            config_file=ssh_file(CONFIG).as_posix(),
            identity_rsa=ssh_file(KEYS["rsa"]["private"]).as_posix(),
            identity_ed25519=ssh_file(KEYS["ed25519"]["private"]).as_posix(),
            extra_args=settings.SSH_EXTRA_ARGS,
        )

    @property
    def filename(self) -> Path:
        """Calculate unique wrapper filename."""
        return self.path / "ssh"

    def create(self) -> None:
        """Create wrapper for SSH to pass custom known hosts and key."""
        self.path.mkdir(parents=True, exist_ok=True)

        ssh_config = ssh_file(CONFIG)
        if not ssh_config.exists():
            try:
                with ssh_config.open(mode="x") as handle:
                    handle.write(
                        "# SSH configuration for customising SSH client in Weblate\n"
                    )
            except OSError:
                pass

        for command in ("ssh", "scp"):
            filename = self.path / command

            if not filename.exists():
                filename.write_text(self.get_content(find_command(command)))

            if not os.access(filename, os.X_OK):
                filename.chmod(0o755)


SSH_WRAPPER = SSHWrapper()
