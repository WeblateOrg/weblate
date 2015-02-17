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

from social.strategies.django_strategy import DjangoStrategy
from importlib import import_module
from django.conf import settings


class WeblateStrategy(DjangoStrategy):
    def __init__(self, storage, request=None, tpl=None):
        """
        Restores session data based on passed ID.
        """
        super(WeblateStrategy, self).__init__(storage, request, tpl)
        if (request and
                self.session.session_key is None and
                'id' in request.GET):
            engine = import_module(settings.SESSION_ENGINE)
            self.session = engine.SessionStore(request.GET['id'])
