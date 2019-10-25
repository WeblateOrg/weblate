# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

#
# Django settings for running testsuite
#

import os
import warnings

from weblate.settings_example import *  # noqa

CI_DATABASE = os.environ.get('CI_DATABASE', '')

DATABASES['default']['HOST'] = os.environ.get('CI_DB_HOST', '')
if CI_DATABASE == 'mysql':
    DATABASES['default']['ENGINE'] = 'django.db.backends.mysql'
    DATABASES['default']['NAME'] = 'weblate'
    DATABASES['default']['USER'] = 'root'
    DATABASES['default']['PASSWORD'] = ''
    DATABASES['default']['OPTIONS'] = {
        'init_command': (
            'SET NAMES utf8, '
            'wait_timeout=28800, '
            'default_storage_engine=INNODB, '
            'sql_mode="STRICT_TRANS_TABLES"'
        ),
        'charset': 'utf8',
        'isolation_level': 'read committed',
    }
elif CI_DATABASE == 'postgresql':
    DATABASES['default']['ENGINE'] = 'django.db.backends.postgresql'
    DATABASES['default']['NAME'] = 'weblate'
    DATABASES['default']['USER'] = 'postgres'
    DATABASES['default']['PASSWORD'] = ''
else:
    DATABASES['default']['ENGINE'] = 'django.db.backends.sqlite3'
    DATABASES['default']['NAME'] = 'weblate.db'
    # Workaround for
    # https://github.com/travis-ci/travis-ci/issues/7873
    if 'TRAVIS' in os.environ:
        DATABASES['default']['TEST'] = {'NAME': 'weblate_test.db'}


# Configure admins
ADMINS = (('Weblate test', 'noreply@weblate.org'), )

# Different root for test repos
DATA_DIR = os.path.join(BASE_DIR, 'data-test')
MEDIA_ROOT = os.path.join(DATA_DIR, 'media')
STATIC_ROOT = os.path.join(DATA_DIR, 'static')
CELERY_BEAT_SCHEDULE_FILENAME = os.path.join(
    DATA_DIR, 'celery', 'beat-schedule'
)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = 'memory://'
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_RESULT_BACKEND = None

# Silent logging setup
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'formatters': {
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
        'weblate': {
            'handlers': [],
            'level': 'ERROR',
        },
        'social': {
            'handlers': [],
            'level': 'ERROR',
        },
    }
}

# Reset caches
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Selenium can not clear HttpOnly cookies in MSIE
SESSION_COOKIE_HTTPONLY = False

# Use database backed sessions for transaction consistency in tests
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# Test optional apps as well
INSTALLED_APPS += (
    'weblate.billing',
    'weblate.legal',
)

# Test GitHub auth
AUTHENTICATION_BACKENDS = (
    'social_core.backends.email.EmailAuth',
    'social_core.backends.github.GithubOAuth2',
    'weblate.accounts.auth.WeblateUserBackend',
)

AUTH_VALIDATE_PERMS = True

warnings.filterwarnings(
    'error', r"DateTimeField .* received a naive datetime",
    RuntimeWarning, r'django\.db\.models\.fields'
)

# Generate junit compatible XML for AppVeyor
if 'APPVEYOR' in os.environ:
    TEST_RUNNER = 'xmlrunner.extra.djangotestrunner.XMLTestRunner'
    TEST_OUTPUT_FILE_NAME = 'junit.xml'
