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

from datetime import datetime

from django.utils.html import escape
from django.utils.http import is_safe_url
from django.utils.translation import ugettext as _
from django.utils.safestring import mark_safe
from django.conf import settings

import weblate
import weblate.screenshots.views
from weblate.utils.site import get_site_url
from weblate.wladmin.models import ConfigurationError

URL_BASE = 'https://weblate.org/?utm_source=weblate&utm_term=%s'
URL_DONATE = 'https://weblate.org/donate/?utm_source=weblate&utm_term=%s'


def weblate_context(request):
    """Context processor to inject various useful variables into context."""
    if is_safe_url(request.GET.get('next', ''), allowed_hosts=None):
        login_redirect_url = request.GET['next']
    else:
        login_redirect_url = request.get_full_path()

    # Load user translations if user is authenticated
    subscribed_projects = None
    if request.user.is_authenticated:
        subscribed_projects = request.user.profile.subscriptions.all()

    if settings.OFFER_HOSTING:
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

    weblate_url = URL_BASE % weblate.VERSION

    return {
        'cache_param': '?v={}'.format(weblate.GIT_VERSION),
        'version': weblate.VERSION,
        'description': description,

        'weblate_link': mark_safe(
            '<a href="{}">weblate.org</a>'.format(escape(weblate_url))
        ),
        'weblate_name_link': mark_safe(
            '<a href="{}">Weblate</a>'.format(escape(weblate_url))
        ),
        'weblate_version_link': mark_safe(
            '<a href="{}">Weblate {}</a>'.format(
                escape(weblate_url), weblate.VERSION
            )
        ),
        'donate_url': URL_DONATE % weblate.VERSION,

        'site_title': settings.SITE_TITLE,
        'site_url': get_site_url(),

        'offer_hosting': settings.OFFER_HOSTING,
        'demo_server': settings.DEMO_SERVER,
        'enable_avatars': settings.ENABLE_AVATARS,
        'enable_sharing': settings.ENABLE_SHARING,

        'piwik_site_id': settings.PIWIK_SITE_ID,
        'piwik_url': settings.PIWIK_URL,
        'google_analytics_id': settings.GOOGLE_ANALYTICS_ID,

        'current_date': datetime.utcnow().strftime('%Y-%m-%d'),
        'current_year': datetime.utcnow().strftime('%Y'),
        'current_month': datetime.utcnow().strftime('%m'),

        'login_redirect_url': login_redirect_url,

        'hooks_enabled': settings.ENABLE_HOOKS,
        'has_ocr': weblate.screenshots.views.HAS_OCR,

        'registration_open': settings.REGISTRATION_OPEN,
        'subscribed_projects': subscribed_projects,

        'rollbar_token': rollbar_token,
        'rollbar_environment': rollbar_environment,
        'allow_index': False,
        'legal': 'weblate.legal' in settings.INSTALLED_APPS,
        'status_url': settings.STATUS_URL,
        'configuration_errors': ConfigurationError.objects.filter(
            ignored=False
        ),
    }
