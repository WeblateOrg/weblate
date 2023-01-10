# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings
from django.utils.translation import get_language
from weblate_language_data.docs import DOCUMENTATION_LANGUAGES

import weblate.utils.version


def get_doc_url(page, anchor="", user=None):
    """Return URL to documentation."""
    # Should we use tagged release or latest version
    if "-dev" in weblate.utils.version.VERSION or (
        (user is None or not user.is_authenticated) and settings.HIDE_VERSION
    ):
        version = "latest"
    else:
        version = f"weblate-{weblate.utils.version.VERSION}"
    # Language variant
    code = DOCUMENTATION_LANGUAGES.get(get_language(), "en")
    # Generate URL
    url = f"https://docs.weblate.org/{code}/{version}/{page}.html"
    # Optionally append anchor
    if anchor != "":
        url += "#{}".format(anchor.replace("_", "-"))

    return url
