# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

from importlib import import_module

from django.conf import settings
from django.utils.http import is_safe_url

from social_django.strategy import DjangoStrategy


class WeblateStrategy(DjangoStrategy):
    def __init__(self, storage, request=None, tpl=None):
        """
        Restores session data based on passed ID.
        """
        super(WeblateStrategy, self).__init__(storage, request, tpl)
        if (request and
                'verification_code' in request.GET and
                'id' in request.GET):
            engine = import_module(settings.SESSION_ENGINE)
            self.session = engine.SessionStore(request.GET['id'])

    def request_data(self, merge=True):
        if not self.request:
            return {}
        if merge:
            data = self.request.GET.copy()
            data.update(self.request.POST)
        elif self.request.method == 'POST':
            data = self.request.POST.copy()
        else:
            data = self.request.GET.copy()
        # This is mostly fix for lack of next validation in Python Social Auth
        # - https://github.com/python-social-auth/social-core/pull/92
        # - https://github.com/python-social-auth/social-core/issues/62
        if 'next' in data and not is_safe_url(data['next']):
            data['next'] = '/accounts/profile/#auth'
        return data
