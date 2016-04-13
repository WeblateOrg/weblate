# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from datetime import datetime

from django.utils.translation import ugettext as _
from django.conf import settings

import weblate
from weblate import appsettings
from weblate.trans.site import get_site_url
from weblate.trans.models.project import Project

URL_BASE = 'https://weblate.org/?utm_source=weblate&utm_term=%s'
URL_DONATE = 'https://weblate.org/donate/?utm_source=weblate&utm_term=%s'


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
    subscribed_projects = None
    if request.user.is_authenticated():
        subscribed_projects = request.user.profile.subscriptions.all()

    if appsettings.OFFER_HOSTING:
        description = _(
            'Hosted Weblate, the place to translate your software project.'
        )
    else:
        description = _(
            'This site runs Weblate for translating various software projects.'
        )

    if (hasattr(settings, 'ROLLBAR') and
            'client_token' in settings.ROLLBAR and
            'environment' in settings.ROLLBAR):
        rollbar_token = settings.ROLLBAR['client_token']
        rollbar_environment = settings.ROLLBAR['environment']
    else:
        rollbar_token = None
        rollbar_environment = None

    return {
        'version': weblate.VERSION,
        'description': description,

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

        'hooks_enabled': appsettings.ENABLE_HOOKS,

        'registration_open': appsettings.REGISTRATION_OPEN,
        'acl_projects': projects,
        'subscribed_projects': subscribed_projects,

        'rollbar_token': rollbar_token,
        'rollbar_environment': rollbar_environment,
    }
