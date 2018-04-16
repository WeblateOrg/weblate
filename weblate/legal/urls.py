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

from django.conf.urls import url

from weblate.legal.views import (
    LegalView, TermsView, CookiesView, SecurityView, PrivacyView,
    tos_confirm,
)

urlpatterns = [
    url(
        r'^$',
        LegalView.as_view(),
        name='index',
    ),
    url(
        r'^terms/$',
        TermsView.as_view(),
        name='terms',
    ),
    url(
        r'^cookies/$',
        CookiesView.as_view(),
        name='cookies',
    ),
    url(
        r'^security/$',
        SecurityView.as_view(),
        name='security',
    ),
    url(
        r'^privacy/$',
        PrivacyView.as_view(),
        name='privacy',
    ),
    url(
        r'^confirm/$',
        tos_confirm,
        name='confirm',
    ),
]
