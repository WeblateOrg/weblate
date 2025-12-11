# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


import binascii
import os


def get_random_identifier(length: int = 4) -> str:
    return binascii.hexlify(os.urandom(length)).decode()
