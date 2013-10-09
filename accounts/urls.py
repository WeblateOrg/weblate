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

from django.conf.urls import patterns, url, include
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth import views as auth_views
from django.conf import settings

from registration.views import activate, register

from accounts.forms import RegistrationForm
from accounts.views import RegistrationTemplateView


urlpatterns = patterns(
    '',
    url(
        r'^register/$', register, {
            'backend': 'registration.backends.default.DefaultBackend',
            'form_class': RegistrationForm,
            'extra_context': {'title': _('User registration')}
        },
        name='registration_register'
    ),
    url(
        r'^register/complete/$',
        RegistrationTemplateView.as_view(
            template_name='registration/registration_complete.html'
        ),
        name='registration_complete'
    ),
    url(
        r'^register/closed/$',
        RegistrationTemplateView.as_view(
            template_name='registration/registration_closed.html'
        ),
        name='registration_disallowed'
    ),
    url(
        r'^activate/complete/$',
        RegistrationTemplateView.as_view(
            template_name='registration/activation_complete.html',
        ),
        name='registration_activation_complete'
    ),
    url(
        r'^activate/(?P<activation_key>\w+)/$',
        activate,
        {
            'backend': 'registration.backends.default.DefaultBackend',
            'extra_context': {
                'title': _('Account activation'),
                'expiration_days': settings.ACCOUNT_ACTIVATION_DAYS,
            }
        },
        name='registration_activate'
    ),
    url(
        r'^login/$', 'accounts.views.weblate_login', name='login',
    ),
    url(
        r'^logout/$',
        auth_views.logout,
        {
            'template_name': 'registration/logout.html',
            'extra_context': {'title': _('Logged out'), 'skip_next': True},
        },
        name='auth_logout'
    ),
    url(
        r'^password/change/$',
        auth_views.password_change,
        {'extra_context': {'title': _('Change password')}},
        name='auth_password_change'
    ),
    url(
        r'^password/change/done/$',
        auth_views.password_change_done,
        {'extra_context': {'title': _('Password changed')}},
        name='auth_password_change_done'
    ),
    url(
        r'^password/reset/$',
        auth_views.password_reset,
        {'extra_context': {'title': _('Password reset')}},
        name='auth_password_reset'
    ),
    url(
        r'^password/reset/confirm/(?P<uidb36>[0-9A-Za-z]+)-(?P<token>.+)/$',
        auth_views.password_reset_confirm,
        {'extra_context': {'title': _('Password reset')}},
        name='auth_password_reset_confirm'
    ),
    url(
        r'^password/reset/complete/$',
        auth_views.password_reset_complete,
        {'extra_context': {'title': _('Password reset')}},
        name='auth_password_reset_complete'
    ),
    url(
        r'^password/reset/done/$',
        auth_views.password_reset_done,
        {'extra_context': {'title': _('Password reset')}},
        name='auth_password_reset_done'
    ),
    url(
        r'^profile/',
        'accounts.views.user_profile',
        name='profile',
    ),
    url(r'', include('social.apps.django_app.urls', namespace='social')),
)
