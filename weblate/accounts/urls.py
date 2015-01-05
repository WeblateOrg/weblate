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

from django.conf.urls import patterns, url, include

from weblate.accounts.views import RegistrationTemplateView


urlpatterns = patterns(
    '',
    url(
        r'^email-sent/$',
        RegistrationTemplateView.as_view(
            template_name='accounts/email-sent.html',
        ),
        name='email-sent'
    ),
    url(r'^password/', 'weblate.accounts.views.password', name='password'),
    url(
        r'^reset/', 'weblate.accounts.views.reset_password',
        name='password_reset'
    ),
    url(r'^logout/', 'weblate.accounts.views.weblate_logout', name='logout'),
    url(r'^profile/', 'weblate.accounts.views.user_profile', name='profile'),
    url(r'^remove/', 'weblate.accounts.views.user_remove', name='remove'),
    url(r'^login/$', 'weblate.accounts.views.weblate_login', name='login'),
    url(r'^register/$', 'weblate.accounts.views.register', name='register'),
    url(r'^email/$', 'weblate.accounts.views.email_login', name='email_login'),
    url(r'', include('social.apps.django_app.urls', namespace='social')),
)
