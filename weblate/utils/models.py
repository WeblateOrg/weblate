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

from __future__ import unicode_literals

from appconf import AppConf


class WeblateConf(AppConf):
    WEBLATE_GPG_IDENTITY = None
    WEBLATE_GPG_ALGO = 'default'

    RATELIMIT_ATTEMPTS = 5
    RATELIMIT_WINDOW = 300
    RATELIMIT_LOCKOUT = 600

    RATELIMIT_SEARCH_ATTEMPTS = 6
    RATELIMIT_SEARCH_WINDOW = 60
    RATELIMIT_SEARCH_LOCKOUT = 60

    class Meta(object):
        prefix = ''


class CeleryConf(AppConf):
    """Defaults for Celery settings."""
    TASK_ALWAYS_EAGER = True
    BROKER_URL = 'memory://'

    # List Celery beats (scheduled tasks)
    BEAT_SCHEDULE = {}

    CELERY_IMPORTS = [
        'weblate.accounts.notifications',
        'weblate.trans.discovery',
        'weblate.trans.models',
        'weblate.trans.search',
        'weblate.trans.views.api',
    ]

    class Meta(object):
        prefix = 'CELERY'
