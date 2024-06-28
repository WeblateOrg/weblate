# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WSGI config for weblate project.

This module contains the WSGI application used by Django's development server
and any production WSGI deployments. It should expose a module-level variable
named ``application``. Django's ``runserver`` and ``runfcgi`` commands discover
this application via the ``WSGI_APPLICATION`` setting.

Usually you will have the standard Django WSGI application here, but it also
might make sense to replace the whole Django WSGI application with a custom one
that later delegates to the Django one. For example, you could introduce WSGI
middleware here, or combine a Django application with an application of another
framework.
"""

import os

from django.core.wsgi import get_wsgi_application


def preload_url_patterns():
    """
    Ensure Django URL resolver is loaded.

    This avoids expensive load with a first request and makes memory sharing work
    better between uwsgi workers.
    """
    from django.conf import settings
    from django.urls import get_resolver

    return get_resolver(settings.ROOT_URLCONF).url_patterns


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "weblate.settings")

# This application object is used by any WSGI server configured to use this
# file. This includes Django's development server, if the WSGI_APPLICATION
# setting points here.
application = get_wsgi_application()
preload_url_patterns()
