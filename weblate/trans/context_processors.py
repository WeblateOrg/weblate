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

import weblate
from weblate import appsettings
from datetime import datetime
from weblate.trans.util import get_site_url
from weblate.trans.models.project import Project
from weblate.trans.models.translation import Translation

URL_BASE = 'http://weblate.org/?utm_source=weblate&utm_term=%s'
URL_DONATE = 'http://weblate.org/donate/?utm_source=weblate&utm_term=%s'


def weblate_context(request):
    """
    Context processor to inject various useful variables into context.
    """
    if 'next' in request.GET:
        login_redirect_url = request.GET['next']
    else:
        login_redirect_url = request.get_full_path()

    projects = Project.objects.all_acl(request.user)

    # Load user translations if user is authenticated
    usertranslations = None
    if request.user.is_authenticated():
        usertranslations = Translation.objects.filter(
            language__in=request.user.profile.languages.all(),
            subproject__project__in=projects,
        ).order_by(
            'subproject__project__name', 'subproject__name'
        ).select_related()

    return {
        'version': weblate.VERSION,

        'weblate_url': URL_BASE % weblate.VERSION,
        'donate_url': URL_DONATE % weblate.VERSION,

        'site_title': appsettings.SITE_TITLE,
        'site_url': get_site_url(),

        'offer_hosting': appsettings.OFFER_HOSTING,
        'demo_server': appsettings.DEMO_SERVER,
        'enable_avatars': appsettings.ENABLE_AVATARS,
        'enable_sharing': appsettings.ENABLE_SHARING,

        'piwik_site_id': appsettings.PIWIK_SITE_ID,
        'piwik_url': appsettings.PIWIK_URL,
        'google_analytics_id': appsettings.GOOGLE_ANALYTICS_ID,

        'current_date': datetime.utcnow().strftime('%Y-%m-%d'),
        'current_year': datetime.utcnow().strftime('%Y'),
        'current_month': datetime.utcnow().strftime('%m'),

        'login_redirect_url': login_redirect_url,

        'mt_enabled': appsettings.MACHINE_TRANSLATION_ENABLED,
        'hooks_enabled': appsettings.ENABLE_HOOKS,
        'whiteboard_enabled': appsettings.ENABLE_WHITEBOARD,

        'registration_open': appsettings.REGISTRATION_OPEN,
        'acl_projects': projects,
        'usertranslations': usertranslations,
    }
