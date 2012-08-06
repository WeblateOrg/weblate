# -*- coding: utf-8 -*-
#
# Copyright © 2012 Michal Čihař <michal@cihar.com>
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

import weblate
from django.conf import settings
from datetime import datetime

def version(request):
    return {'version': weblate.VERSION}

def title(request):
    return {'site_title': settings.SITE_TITLE}

def date(request):
    return {
        'current_date': datetime.utcnow().strftime('%Y-%m-%d'),
        'current_year': datetime.utcnow().strftime('%Y'),
        'current_month': datetime.utcnow().strftime('%m'),
        }

def url(request):
    return {
        'current_url': request.get_full_path(),
    }

def mt(request):
    return {
        'apertium_api_key': settings.MT_APERTIUM_KEY,
        'microsoft_api_key': settings.MT_MICROSOFT_KEY,
    }
