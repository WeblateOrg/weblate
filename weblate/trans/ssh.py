# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import subprocess
import hashlib
import os
from django.utils.translation import ugettext as _
from django.contrib import messages

from weblate.trans.util import get_clean_env
from weblate.trans.data import data_dir

# SSH key files
KNOWN_HOSTS = 'known_hosts'
RSA_KEY = 'id_rsa'
RSA_KEY_PUB = 'id_rsa.pub'
SSH_WRAPPER = 'ssh-weblate-wrapper'

SSH_WRAPPER_TEMPLATE = r'''#!/bin/sh
ssh \
    -o "UserKnownHostsFile={known_hosts}" \
    -o "IdentityFile={identity}" \
    -o StrictHostKeyChecking=yes \
    -o HashKnownHosts=no \
    "$@"
'''


def ensure_ssh_dir():
    """
    Ensures the ssh configuration directory exists.
    """
    ssh_dir = data_dir('ssh')
    if not os.path.exists(ssh_dir):
        os.makedirs(ssh_dir)


def ssh_file(filename):
    """
    Generates full path to SSH configuration file.
    """
    return os.path.join(
        data_dir('ssh'),
        filename
    )


def is_key_line(key):
    """
    Checks whether this line looks like a valid known_hosts line.
    """
    if not key:
        return False
    if key[0] == '#':
        return False
    return (
        ' ssh-rsa ' in key or
        ' ecdsa-sha2-nistp256 ' in key or
        ' ssh-ed25519 ' in key
    )


def parse_hosts_line(line):
    """
    Parses single hosts line into tuple host, key fingerprint.
    """
    host, keytype, key = line.strip().split(None, 3)[:3]
    fp_plain = hashlib.md5(key.decode('base64')).hexdigest()
    fingerprint = ':'.join(
        [a + b for a, b in zip(fp_plain[::2], fp_plain[1::2])]
    )
    if host.startswith('|1|'):
        # Translators: placeholder SSH hashed hostname
        host = _('[hostname hashed]')
    return host, keytype, fingerprint


def get_host_keys():
    """
    Returns list of host keys.
    """
    try:
        result = []
        with open(ssh_file(KNOWN_HOSTS), 'r') as handle:
            for line in handle:
                line = line.strip()
                if is_key_line(line):
                    result.append(parse_hosts_line(line))
    except IOError:
        return []

    return result


def get_key_data():
    """
    Parses host key and returns it.
    """
    # Read key data if it exists
    if os.path.exists(ssh_file(RSA_KEY_PUB)):
        with open(ssh_file(RSA_KEY_PUB)) as handle:
            key_data = handle.read()
        key_type, key_fingerprint, key_id = key_data.strip().split(None, 2)
        return {
            'key': key_data,
            'type': key_type,
            'fingerprint': key_fingerprint,
            'id': key_id,
        }
    return None


def generate_ssh_key(request):
    """
    Generates SSH key.
    """
    try:
        # Create directory if it does not exist
        ensure_ssh_dir()

        # Actually generate the key
        subprocess.check_output(
            [
                'ssh-keygen', '-q',
                '-N', '',
                '-C', 'Weblate',
                '-t', 'rsa',
                '-f', ssh_file(RSA_KEY)
            ],
            stderr=subprocess.STDOUT,
            env=get_clean_env(),
        )
        messages.success(request, _('Created new SSH key.'))
    except (subprocess.CalledProcessError, OSError) as exc:
        messages.error(
            request,
            _('Failed to generate key: %s') %
            getattr(exc, 'output', str(exc))
        )


def add_host_key(request):
    """
    Adds host key for a host.
    """
    ensure_ssh_dir()
    host = request.POST.get('host', '')
    port = request.POST.get('port', '')
    if len(host) == 0:
        messages.error(request, _('Invalid host name given!'))
    else:
        cmdline = ['ssh-keyscan']
        if port:
            cmdline.extend(['-p', port])
        cmdline.append(host)
        try:
            output = subprocess.check_output(
                cmdline,
                stderr=subprocess.STDOUT,
                env=get_clean_env(),
            )
            keys = []
            for key in output.splitlines():
                key = key.strip()
                if not is_key_line(key):
                    continue
                keys.append(key)
                host, keytype, fingerprint = parse_hosts_line(key)
                messages.warning(
                    request,
                    _(
                        'Added host key for %(host)s with fingerprint '
                        '%(fingerprint)s (%(keytype)s), '
                        'please verify that it is correct.'
                    ) % {
                        'host': host,
                        'fingerprint': fingerprint,
                        'keytype': keytype,
                    }
                )
            if len(keys) == 0:
                messages.error(
                    request,
                    _('Failed to fetch public key for a host!')
                )
            with open(ssh_file(KNOWN_HOSTS), 'a') as handle:
                for key in keys:
                    handle.write('%s\n' % key)
        except (subprocess.CalledProcessError, OSError) as exc:
            messages.error(
                request,
                _('Failed to get host key: %s') % exc.output
            )


def can_generate_key():
    """
    Checks whether we can generate key.
    """
    try:
        ensure_ssh_dir()
    except OSError:
        return False

    try:
        ret = subprocess.check_call(
            ['which', 'ssh-keygen'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=get_clean_env(),
        )
        return ret == 0
    except subprocess.CalledProcessError:
        return False


def create_ssh_wrapper():
    """
    Creates wrapper for SSH to pass custom known hosts and key.
    """
    ensure_ssh_dir()

    ssh_wrapper = ssh_file(SSH_WRAPPER)

    with open(ssh_wrapper, 'w') as handle:
        handle.write(SSH_WRAPPER_TEMPLATE.format(
            known_hosts=ssh_file(KNOWN_HOSTS),
            identity=ssh_file(RSA_KEY),
        ))

    os.chmod(ssh_wrapper, 0755)
