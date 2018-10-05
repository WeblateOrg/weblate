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
from weblate.utils.site import get_site_url, get_site_domain
from weblate.wladmin.models import ConfigurationError

URL_BASE = 'https://weblate.org/?utm_source=weblate&utm_term=%s'
URL_DONATE = 'https://weblate.org/donate/?utm_source=weblate&utm_term=%s'

CONTEXT_SETTINGS = [
    'SITE_TITLE',
    'OFFER_HOSTING',
    'DEMO_SERVER',
    'ENABLE_AVATARS',
    'ENABLE_SHARING',
    'PIWIK_SITE_ID',
    'PIWIK_URL',
    'GOOGLE_ANALYTICS_ID',
    'ENABLE_HOOKS',
    'REGISTRATION_OPEN',
    'STATUS_URL',
]

CONTEXT_APPS = ['billing', 'legal', 'gitexport']


def add_error_logging_context(context):
    if (hasattr(settings, 'ROLLBAR') and
            'client_token' in settings.ROLLBAR and
            'environment' in settings.ROLLBAR):
        context['rollbar_token'] = settings.ROLLBAR['client_token']
        context['rollbar_environment'] = settings.ROLLBAR['environment']
    else:
        context['rollbar_token'] = None
        context['rollbar_environment'] = None

    if (hasattr(settings, 'RAVEN_CONFIG') and
            'public_dsn' in settings.RAVEN_CONFIG):
        context['sentry_dsn'] = settings.RAVEN_CONFIG['public_dsn']
    else:
        context['sentry_dsn'] = None


def add_settings_context(context):
    for name in CONTEXT_SETTINGS:
        context[name.lower()] = getattr(settings, name)


def add_optional_context(context):
    for name in CONTEXT_APPS:
        appname = 'weblate.{}'.format(name)
        context['has_{}'.format(name)] = appname in settings.INSTALLED_APPS


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

    weblate_url = URL_BASE % weblate.VERSION

    context = {
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

        'site_url': get_site_url(),
        'site_domain': get_site_domain(),

        'current_date': datetime.utcnow().strftime('%Y-%m-%d'),
        'current_year': datetime.utcnow().strftime('%Y'),
        'current_month': datetime.utcnow().strftime('%m'),

        'login_redirect_url': login_redirect_url,

        'has_ocr': weblate.screenshots.views.HAS_OCR,
        'has_antispam': bool(settings.AKISMET_API_KEY),

        'subscribed_projects': subscribed_projects,

        'allow_index': False,
        'configuration_errors': ConfigurationError.objects.filter(
            ignored=False
        ),
    }

    add_error_logging_context(context)
    add_settings_context(context)
    add_optional_context(context)

    return context
