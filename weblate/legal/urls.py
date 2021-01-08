#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from django.urls import path

from weblate.legal.views import (
    ContractsView,
    CookiesView,
    LegalView,
    PrivacyView,
    SecurityView,
    TermsView,
    tos_confirm,
)

urlpatterns = [
    path("", LegalView.as_view(), name="index"),
    path("terms/", TermsView.as_view(), name="terms"),
    path("cookies/", CookiesView.as_view(), name="cookies"),
    path("security/", SecurityView.as_view(), name="security"),
    path("privacy/", PrivacyView.as_view(), name="privacy"),
    path("contracts/", ContractsView.as_view(), name="contracts"),
    path("confirm/", tos_confirm, name="confirm"),
]
