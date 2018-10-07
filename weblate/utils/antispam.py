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

from django.conf import settings

from weblate.utils.errors import report_error
from weblate.utils.site import get_site_url
from weblate.utils.request import get_ip_address


def is_spam(text, request):
    """Generic spam checker interface."""
    if settings.AKISMET_API_KEY:
        from akismet import Akismet
        akismet = Akismet(
            settings.AKISMET_API_KEY,
            get_site_url()
        )
        return akismet.comment_check(
            get_ip_address(request),
            request.META.get('HTTP_USER_AGENT', ''),
            comment_content=text,
            comment_type='comment'
        )
    return False


def report_spam(text, user_ip, user_agent):
    if not settings.AKISMET_API_KEY:
        return
    from akismet import Akismet, ProtocolError
    akismet = Akismet(
        settings.AKISMET_API_KEY,
        get_site_url()
    )
    try:
        akismet.submit_spam(
            user_ip,
            user_agent,
            comment_content=text,
            comment_type='comment'
        )
    except ProtocolError as error:
        report_error(error)
