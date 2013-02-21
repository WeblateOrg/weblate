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
'''
Cleanup task for Jenkins CI
'''

from django_jenkins.tasks import BaseTask
from django.conf import settings
import os
import shutil


class Task(BaseTask):
    def teardown_test_environment(self, **kwargs):
        '''
        Remove test repos before collecting code stats.

        The test-repos just pollute stats.
        '''
        if 'test-repos' in settings.GIT_ROOT:
            if os.path.exists(settings.GIT_ROOT):
                shutil.rmtree(settings.GIT_ROOT)
