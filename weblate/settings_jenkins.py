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
# Django settings for run inside Jenkins
#

from weblate.settings_test import *
import os

INSTALLED_APPS += ('django_jenkins', )

JENKINS_TASKS = (
    'weblate.jenkins_cleanup',
    'django_jenkins.tasks.run_pylint',
    'django_jenkins.tasks.run_pyflakes',
    'django_jenkins.tasks.run_sloccount',
    'django_jenkins.tasks.with_coverage',
    'django_jenkins.tasks.run_pep8',
    'django_jenkins.tasks.run_csslint',
    'django_jenkins.tasks.run_jshint',
    'django_jenkins.tasks.django_tests',
)

CSSLINT_CHECKED_FILES = (
    os.path.join(WEB_ROOT, 'media/style.css'),
)

JSHINT_CHECKED_FILES = (
    os.path.join(WEB_ROOT, 'media/loader.js'),
)

PROJECT_APPS = (
    'trans',
    'lang',
    'accounts',
    'weblate',
)

PYLINT_RCFILE = os.path.join(WEB_ROOT, '..', 'pylint.rc')

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
