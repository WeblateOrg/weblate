#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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
from weblate.utils.version import USER_AGENT


def get_akismet():
    if not settings.AKISMET_API_KEY:
        return None

    from akismet import Akismet

    return Akismet(
        api_key=settings.AKISMET_API_KEY,
        blog=get_site_url(),
        application_user_agent=USER_AGENT,
    )


def is_spam(text, request):
    """Generic spam checker interface."""
    if not text:
        return False
    akismet = get_akismet()
    if akismet is not None:
        from akismet import AkismetServerError, SpamStatus

        user_ip = get_ip_address(request)
        user_agent = get_user_agent_raw(request)

        try:
            result = akismet.check(
                user_ip=user_ip,
                user_agent=user_agent,
                comment_content=text,
                comment_type="comment",
            )
            if result:
                try:
                    raise Exception(
                        f"Akismet reported spam: {user_ip} / {user_agent} / {text!r}"
                    )
                except Exception:
                    report_error(cause="Akismet reported spam")
            return result == SpamStatus.DefiniteSpam
        except (OSError, AkismetServerError):
            report_error()
            return True
    return False


def report_spam(text, user_ip, user_agent):
    akismet = get_akismet()
    if akismet is None:
        return
    from akismet import AkismetServerError

    try:
        akismet.submit_spam(
            user_ip=user_ip,
            user_agent=user_agent,
            comment_content=text,
            comment_type="comment",
        )
    except (OSError, AkismetServerError):
        report_error()
