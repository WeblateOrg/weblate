# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from ssl import CertificateError

from django.conf import settings

from weblate.accounts.avatar import download_avatar_image
from weblate.utils.checks import weblate_check


def check_avatars(app_configs, **kwargs):
    if not settings.ENABLE_AVATARS:
        return []
    try:
        download_avatar_image("noreply@weblate.org", 32)
    except (OSError, CertificateError) as error:
        return [weblate_check("weblate.E018", f"Could not download avatar: {error}")]
    return []
