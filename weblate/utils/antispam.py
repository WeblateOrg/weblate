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

from django.conf import settings

from weblate.utils.errors import report_error
from weblate.utils.request import get_ip_address, get_user_agent_raw
from weblate.utils.site import get_site_url


def is_spam(text, request):
    """Generic spam checker interface."""
    if settings.AKISMET_API_KEY:
        from akismet import Akismet

        akismet = Akismet(settings.AKISMET_API_KEY, get_site_url())
        try:
            return akismet.comment_check(
                get_ip_address(request),
                get_user_agent_raw(request),
                comment_content=text,
                comment_type="comment",
            )
        except OSError:
            report_error()
            return True
    return False


def report_spam(text, user_ip, user_agent):
    if not settings.AKISMET_API_KEY:
        return
    from akismet import Akismet, ProtocolError

    akismet = Akismet(settings.AKISMET_API_KEY, get_site_url())
    try:
        akismet.submit_spam(
            user_ip, user_agent, comment_content=text, comment_type="comment"
        )
    except (ProtocolError, OSError):
        report_error()
