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
"""OpenShift integration support"""

import os
import hashlib
import sys


def get_openshift_secret_key():
    """Tries to get secred token from OpenShift environment"""

    # Use actual secret token
    token = os.getenv('OPENSHIFT_SECRET_TOKEN')
    if token is not None:
        return token

    # Generate token from UUID
    name = os.getenv('OPENSHIFT_APP_NAME')
    uuid = os.getenv('OPENSHIFT_APP_UUID')
    if name is not None and uuid is not None:
        return hashlib.sha256(name + '-' + uuid).hexdigest()

    sys.stderr.write(
        "OPENSHIFT WARNING: Using default values for secure variables, " +
        "please set OPENSHIFT_SECRET_TOKEN!"
    )
    raise ValueError('No key available')
