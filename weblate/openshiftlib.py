# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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
"""OpenShift integration support"""

import os
import hashlib
import sys
import re
import ast
from string import Template


def get_openshift_secret_key():
    """Try to get secred token from OpenShift environment"""

    # Use actual secret token
    token = os.getenv('OPENSHIFT_SECRET_TOKEN')
    if token is not None:
        return token

    # Generate token from UUID
    name = os.getenv('OPENSHIFT_APP_NAME')
    uuid = os.getenv('OPENSHIFT_APP_UUID')
    if name is not None and uuid is not None:
        nameuuid = '-'.join((name, uuid))
        return hashlib.sha256(nameuuid.encode('utf-8')).hexdigest()

    sys.stderr.write(
        "OPENSHIFT WARNING: Using default values for secure variables, " +
        "please set OPENSHIFT_SECRET_TOKEN!"
    )
    raise ValueError('No key available')


def import_env_vars(environ, target):
    """Import WEBLATE_* variables into given object.

    This is used for importing settings from environment into settings module.
    """
    weblate_var = re.compile('^WEBLATE_[A-Za-z0-9_]+$')
    for name, value in environ.items():
        if weblate_var.match(name):
            try:
                setattr(target, name[8:],
                        ast.literal_eval(Template(value).substitute(environ)))
            except ValueError as err:
                if not err.args:
                    err.args = (
                        "Error parsing {0} = '{1}': {2}".format(
                            name, value, err
                        ),
                    )
                raise
