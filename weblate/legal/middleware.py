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

import re

from django.urls import reverse
from django.shortcuts import redirect
from django.utils.http import urlencode
from django.utils.translation import ugettext as _

from weblate.legal.models import Agreement
from weblate.utils import messages


class RequireTOSMiddleware(object):
    """
    Middleware to enforce TOS confirmation on certain requests.
    """
    def __init__(self, get_response=None):
        self.get_response = get_response
        # Ignored paths regexp, mostly covers API and legal pages
        self.matcher = re.compile(
            r'^/(legal|about|contact|api|static|widgets|data|hooks)/'
        )

    def process_view(self, request, view_func, view_args, view_kwargs):
        """Check request whether user has agreed to TOS."""
        # We intercept only GET requests for authenticated users
        if request.method != 'GET' or not request.user.is_authenticated:
            return None

        # Some paths are ignored
        if self.matcher.match(request.path):
            return None

        # Check TOS agreement
        agreement = Agreement.objects.get_or_create(user=request.user)[0]
        if not agreement.is_current():
            messages.info(
                request,
                _(
                    'We have new version of the Terms of Service document, '
                    'please read it and confirm that you agree with it.'
                )
            )
            return redirect(
                '{0}?{1}'.format(
                    reverse('legal:confirm'),
                    urlencode({'next': request.get_full_path()})
                )
            )

        # Explicitly return None for all non-matching requests
        return None

    def __call__(self, request):
        return self.get_response(request)
