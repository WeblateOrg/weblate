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

from django.shortcuts import redirect
from django.core.urlresolvers import reverse

from social.pipeline.partial import partial
from social.exceptions import AuthForbidden, AuthMissingParameter

from weblate.accounts.models import send_notification_email, VerifiedEmail
from weblate import appsettings


@partial
def require_email(strategy, backend, details, user=None, is_new=False,
                  **kwargs):
    '''
    Forces entering email for backends which don't provide it.
    '''
    if user and user.email:
        # Force validation of new email address
        if backend.name == 'email':
            return {'is_new': True}

        return

    elif is_new and not details.get('email'):

        if strategy.session_get('saved_email'):
            details['email'] = strategy.session_pop('saved_email')
        else:
            return redirect('register')


def send_validation(strategy, backend, code):
    '''
    Sends verification email.
    '''

    # We need to have existing session
    if not strategy.request.session.session_key:
        strategy.request.session.create()

    template = 'activation'
    if strategy.request.session.pop('password_reset', False):
        template = 'reset'

    url = '{}?verification_code={}&id={}'.format(
        reverse('social:complete', args=(backend.name,)),
        code.code,
        strategy.request.session.session_key
    )

    send_notification_email(
        None,
        code.email,
        template,
        info=code.code,
        context={
            'url': url
        }
    )


def verify_open(backend, user, **kwargs):
    '''
    Checks whether it is possible to create new user.
    '''

    if not user and not appsettings.REGISTRATION_OPEN:
        raise AuthForbidden(backend)


def store_email(strategy, backend, user, social, details, **kwargs):
    '''
    Stores verified email.
    '''
    if details['email'] is None:
        raise AuthMissingParameter(backend, 'email')
    if 'email' in details:
        verified, dummy = VerifiedEmail.objects.get_or_create(social=social)
        if verified.email != details['email']:
            verified.email = details['email']
            verified.save()


def user_full_name(strategy, details, user=None, **kwargs):
    """
    Update user full name using data from provider.
    """
    if user:
        full_name = details.get('fullname', '').strip()

        if (not full_name and
                ('first_name' in details or 'last_name' in details)):
            first_name = details.get('first_name', '')
            last_name = details.get('last_name', '')

            if first_name and first_name not in last_name:
                full_name = u'{0} {1}'.format(first_name, last_name)
            elif first_name:
                full_name = first_name
            else:
                full_name = last_name

        full_name = full_name.strip()

        if full_name and full_name != user.first_name:
            user.first_name = full_name
            strategy.storage.user.changed(user)
