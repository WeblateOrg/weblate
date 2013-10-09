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

from accounts.views import RegistrationTemplateView


urlpatterns = patterns(
    '',
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
        r'^email-sent/$',
        RegistrationTemplateView.as_view(
            template_name='accounts/email-sent.html',
        ),
        name='email-sent'
    ),
    url(r'^password/', 'accounts.views.password', name='password'),
    url(r'^logout/', 'accounts.views.weblate_logout', name='logout'),
    url(r'^profile/', 'accounts.views.user_profile', name='profile'),
    url(r'^login/$', 'accounts.views.weblate_login', name='login'),
    url(r'^register/$', 'accounts.views.register', name='register'),
    url(r'^email/$', 'accounts.views.email_login', name='email_login'),
    url(r'', include('social.apps.django_app.urls', namespace='social')),
)
