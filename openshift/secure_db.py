#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright © 2014 Daniel Tschan <tschan@puzzle.ch>
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

from django.conf import settings

import os
import sqlite3
from openshift.openshiftlibs import make_secure_key, get_openshift_secret_token
from hashlib import sha256
from django.contrib.auth.hashers import make_password


def secure_db():
    # Use default Django settings
    settings.configure()

    new_pass = make_secure_key({
        'hash': sha256(get_openshift_secret_token()).hexdigest(),
        'original': '0' * 12,
        'variable': ''
    })
    new_hash = make_password(new_pass)

    # Update admin password in database
    conn = sqlite3.connect(os.environ['OPENSHIFT_DATA_DIR'] + '/weblate.db')
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE AUTH_USER SET password = ? WHERE username = ?',
        [new_hash, 'admin']
    )
    conn.commit()
    cursor.close()
    conn.close()

    # Print the new password info
    print "Weblate admin credentials:\n\tuser: admin\n\tpassword: " + new_pass

if __name__ == "__main__":
    secure_db()
