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

from social.pipeline.partial import partial
from social.exceptions import AuthException

from accounts.models import send_notification_email


@partial
def require_email(strategy, details, user=None, is_new=False,
                  *args, **kwargs):
    if user and user.email:
        return

    elif is_new and not details.get('email'):

        if strategy.session_get('saved_email'):
            details['email'] = strategy.session_pop('saved_email')
        else:
            return redirect('require_email')


def user_password(strategy, user, is_new=False, *args, **kwargs):
    '''
    Password validation/storing for email based auth.
    '''
    if strategy.backend_name != 'email':
        return

    password = strategy.request_data()['password']

    if is_new:
        user.set_password(password)
        user.save()
    elif not user.check_password(password):
        raise AuthException(strategy.backend)


def send_validation(strategy, code):
    '''
    Sends verification email.
    '''
    url = '%s?verification_code=%s' % (
        reverse('social:complete', args=(strategy.backend_name,)),
        code.code
    )

    send_notification_email(
        'en', # FIXME: should probably stay same
        code.email,
        'activation',
        info=code.code,
        context={
            'url': url
        }
    )
