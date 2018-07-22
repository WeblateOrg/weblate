# -*- coding: utf-8 -*-
#
# Copyright © 2015 Daniel Tschan <tschan@puzzle.ch>
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

import os
import sys
from weblate.openshiftlib import get_openshift_secret_key, import_env_vars

# Import example settings file to get default values for Weblate settings.
from weblate.settings_example import *  # noqa

DEBUG = False

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(os.environ['OPENSHIFT_DATA_DIR'], 'weblate.db'),
        'ATOMIC_REQUESTS': True,
    }
}

# if mysql is available,  use that as our database by default
if 'OPENSHIFT_MYSQL_DB_URL' in os.environ:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ['OPENSHIFT_APP_NAME'],
            'USER': os.environ['OPENSHIFT_MYSQL_DB_USERNAME'],
            'PASSWORD': os.environ['OPENSHIFT_MYSQL_DB_PASSWORD'],
            'HOST': os.environ['OPENSHIFT_MYSQL_DB_HOST'],
            'PORT': os.environ['OPENSHIFT_MYSQL_DB_PORT'],
        }
    }

# if postgresql is available,  use that as our database by default
if 'OPENSHIFT_POSTGRESQL_DB_URL' in os.environ:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ['OPENSHIFT_APP_NAME'],
            'USER': os.environ['OPENSHIFT_POSTGRESQL_DB_USERNAME'],
            'PASSWORD': os.environ['OPENSHIFT_POSTGRESQL_DB_PASSWORD'],
            'HOST': os.environ['OPENSHIFT_POSTGRESQL_DB_HOST'],
            'PORT': os.environ['OPENSHIFT_POSTGRESQL_DB_PORT'],
        }
    }


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.environ['OPENSHIFT_DATA_DIR']

STATIC_ROOT = os.path.join(BASE_DIR, 'wsgi', 'static')

# Replace default keys with dynamic values if we are in OpenShift
try:
    SECRET_KEY = get_openshift_secret_key()
except ValueError:
    # We keep the default value if nothing better is available
    pass

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    },
    'avatar': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': os.path.join(
            os.environ['OPENSHIFT_DATA_DIR'], 'avatar-cache'
        ),
        'TIMEOUT': 604800,
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
        },
    }
}

# Offload indexing: if the cron cartridge is installed the preconfigured job
# in .openshift/cron/minutely/update_index updates the index.
if os.environ.get('OPENSHIFT_CRON_DIR', False):
    OFFLOAD_INDEXING = True
else:
    OFFLOAD_INDEXING = False

# List of machine translations
MACHINE_TRANSLATION_SERVICES = (
    'weblate.machinery.weblatetm.WeblateTranslation',
    'weblate.memory.machine.WeblateMemory',
)

if os.environ.get('OPENSHIFT_CLOUD_DOMAIN', False):
    SERVER_EMAIL = 'no-reply@{0}'.format(
        os.environ['OPENSHIFT_CLOUD_DOMAIN']
    )
    DEFAULT_FROM_EMAIL = 'no-reply@{0}'.format(
        os.environ['OPENSHIFT_CLOUD_DOMAIN']
    )

ALLOWED_HOSTS = [os.environ['OPENSHIFT_APP_DNS']]

TTF_PATH = os.path.join(os.environ['OPENSHIFT_REPO_DIR'], 'weblate', 'ttf')

# Import environment variables prefixed with WEBLATE_ as weblate settings
import_env_vars(os.environ, sys.modules[__name__])
