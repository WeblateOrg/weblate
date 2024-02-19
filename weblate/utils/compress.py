# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings

from weblate.accounts.models import Profile


def offline_context():
    for theme, _name in Profile.theme.field.choices:
        for bidi in (True, False):
            yield {
                "fonts_cdn_url": settings.FONTS_CDN_URL,
                "STATIC_URL": settings.STATIC_URL,
                "LANGUAGE_BIDI": bidi,
                "theme": theme,
            }
