# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

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
        except (OSError, AkismetServerError):
            report_error()
            return True
        if result:
            report_error(cause="Akismet reported spam", level="info", message=True)
        return result == SpamStatus.DefiniteSpam
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
