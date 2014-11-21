# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
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

from django.conf import settings


def create_permissions_compat(app, **kwargs):
    '''
    Creates permissions like syncdb would if we were not using South

    See http://south.aeracode.org/ticket/211
    '''
    # This fails with Django 1.7, but the code is used only for 1.6
    # pylint: disable=E0611
    from django.db.models import get_app, get_models
    from django.contrib.auth.management import create_permissions
    if app in ('trans', 'lang', 'accounts'):
        try:
            create_permissions(
                get_app(app), get_models(), 2 if settings.DEBUG else 0
            )
        except AttributeError as error:
            # See https://code.djangoproject.com/ticket/20442
            print 'Failed to create permission objects: {0}'.format(error)

if 'south' in settings.INSTALLED_APPS:
    from south.signals import post_migrate
    post_migrate.connect(create_permissions_compat)
