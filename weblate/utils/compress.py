# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings

from weblate.accounts.types import ThemeChoices


def offline_context():
    for theme in ThemeChoices.values:
        for bidi in (True, False):
            for bootstrap_5 in (True, False):
                yield {
                    "fonts_cdn_url": settings.FONTS_CDN_URL,
                    "STATIC_URL": settings.STATIC_URL,
                    "LANGUAGE_BIDI": bidi,
                    "theme": theme,
                    "bootstrap_5": bootstrap_5,
                }
