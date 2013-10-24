# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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

#
# Django settings for running testsuite
#

from weblate.settings_example import *

# Different root for test repos
GIT_ROOT = '%s/test-repos/' % WEB_ROOT

# Avoid migrating during testsuite
SOUTH_TESTS_MIGRATE = False

# Fake access to Microsoft Translator
MT_MICROSOFT_ID = 'ID'
MT_MICROSOFT_SECRET = 'SECRET'

# Fake Google translate API key
MT_GOOGLE_KEY = 'KEY'

# To get higher limit for testing
MT_MYMEMORY_EMAIL = 'test@weblate.org'

# Enable some machine translations
MACHINE_TRANSLATION_SERVICES = (
    'trans.machine.microsoft.MicrosoftTranslation',
    'trans.machine.dummy.DummyTranslation',
)

# Silent logging setup
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
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
        }
    }
}
