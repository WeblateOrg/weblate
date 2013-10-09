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

from django.shortcuts import redirect
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _

from social.pipeline.partial import partial
from social.exceptions import AuthException, AuthForbidden

from accounts.models import send_notification_email
from weblate import appsettings


@partial
def require_email(strategy, details, user=None, is_new=False,
                  *args, **kwargs):
    '''
    Forces entering email for backends which don't provide it.
    '''
    if user and user.email:
        return

    elif is_new and not details.get('email'):

        if strategy.session_get('saved_email'):
            details['email'] = strategy.session_pop('saved_email')
        else:
            return redirect('register')


def send_validation(strategy, code):
    '''
    Sends verification email.
    '''
    url = '%s?verification_code=%s' % (
        reverse('social:complete', args=(strategy.backend_name,)),
        code.code
    )

    send_notification_email(
        None,
        code.email,
        'activation',
        info=code.code,
        context={
            'url': url
        }
    )


def verify_open(strategy, user, *args, **kwargs):
    '''
    Checks whether it is possible to create new user.
    '''

    if not user and not appsettings.REGISTRATION_OPEN:
        raise AuthForbidden(strategy.backend)
