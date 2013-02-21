# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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

from south.signals import post_migrate
from django.db.models.signals import post_syncdb
from django.dispatch import receiver


@receiver(post_migrate)
def create_permissions_compat(app, **kwargs):
    '''
    Creates permissions like syncdb would if we were not using South

    See http://south.aeracode.org/ticket/211
    '''
    from django.db.models import get_app
    from django.contrib.auth.management import create_permissions
    create_permissions(get_app(app), (), 0)


@receiver(post_syncdb)
@receiver(post_migrate)
def check_versions(sender, app, **kwargs):
    '''
    Check required versions.
    '''
    appname = 'trans.models'
    if app == 'trans' or getattr(app, '__name__', '') == appname:
        from trans.requirements import get_versions, check_version
        versions = get_versions()
        failure = False

        for version in versions:
            failure |= check_version(*version)

        if failure:
            raise Exception(
                'Some of required modules are missing or too old! '
                'Check above output for details.'
            )
