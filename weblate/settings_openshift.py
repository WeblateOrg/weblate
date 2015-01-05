# -*- coding: utf-8 -*-
#
# Copyright © 2015 Daniel Tschan <tschan@puzzle.ch>
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

import os
import sys
import re
import ast
from string import Template
from openshift.openshiftlibs import openshift_secure

# Import example settings file to get default values for Weblate settings.
from weblate.settings_example import *

DEBUG = False

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(os.environ['OPENSHIFT_DATA_DIR'], 'weblate.db'),
        'ATOMIC_REQUESTS': True,
    }
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.environ['OPENSHIFT_DATA_DIR']

TIME_ZONE = None

STATIC_ROOT = os.path.join(BASE_DIR, '..', 'wsgi', 'static')

default_keys = {'SECRET_KEY': SECRET_KEY}

# Replace default keys with dynamic values if we are in OpenShift
use_keys = default_keys
use_keys = openshift_secure(default_keys)

SECRET_KEY = use_keys['SECRET_KEY']

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

GIT_ROOT = os.path.join(os.environ['OPENSHIFT_DATA_DIR'], 'repos')

# Offload indexing: if the cron cartridge is installed the preconfigured job
# in .openshift/cron/minutely/update_index updates the index.
if os.environ.get('OPENSHIFT_CRON_DIR', False):
    OFFLOAD_INDEXING = True
else:
    OFFLOAD_INDEXING = False

# Where to put Whoosh index
WHOOSH_INDEX = os.path.join(os.environ['OPENSHIFT_DATA_DIR'], 'whoosh-index')

SOURCE_LANGUAGE = 'en-us'

# List of machine translations
MACHINE_TRANSLATION_SERVICES = (
    'weblate.trans.machine.weblatetm.WeblateSimilarTranslation',
    'weblate.trans.machine.weblatetm.WeblateTranslation',
)

if os.environ.get('OPENSHIFT_CLOUD_DOMAIN', False):
    SERVER_EMAIL = 'no-reply@%s' % os.environ['OPENSHIFT_CLOUD_DOMAIN']
    DEFAULT_FROM_EMAIL = 'no-reply@%s' % os.environ['OPENSHIFT_CLOUD_DOMAIN']

ALLOWED_HOSTS = [os.environ['OPENSHIFT_APP_DNS']]

TTF_PATH = os.path.join(os.environ['OPENSHIFT_REPO_DIR'], 'weblate', 'ttf')

os.environ['HOME'] = os.environ['OPENSHIFT_DATA_DIR']


# Import environment variables prefixed with WEBLATE_ as weblate settings
_this_module = sys.modules[__name__]

weblate_var = re.compile('^WEBLATE_[A-Za-z0-9_]+$')
for name, value in os.environ.items():
    if weblate_var.match(name):
        try:
            setattr(_this_module, name[8:],
                    ast.literal_eval(Template(value).substitute(os.environ)))
        except ValueError as e:
            if not e.args:
                e.args = ('',)
                e.args = (
                    "Error parsing %s = '%s': %s" % (name, value, e.args[0]),
                ) + e.args[1:]
            raise
