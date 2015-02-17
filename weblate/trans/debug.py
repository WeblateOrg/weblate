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
'''
Wrapper to include useful information in error mails.
'''

from django.views.debug import SafeExceptionReporterFilter
from weblate import get_versions_string


class WeblateExceptionReporterFilter(SafeExceptionReporterFilter):
    def get_request_repr(self, request):
        if request is None:
            return repr(None)

        result = super(WeblateExceptionReporterFilter, self).get_request_repr(
            request
        )

        if (hasattr(request, 'session') and
                'django_language' in request.session):
            lang = request.session['django_language']
        else:
            lang = None

        if (hasattr(request, 'user') and
                request.user.is_authenticated()):
            user = repr(request.user.username)
        else:
            user = None

        return '%s\n\nLanguage: %s\nUser: %s\n\nVersions:\n%s' % (
            result,
            lang,
            user,
            get_versions_string()
        )
