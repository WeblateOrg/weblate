# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.utils.translation import get_language
from weblate_language_data.docs import DOCUMENTATION_LANGUAGES

import weblate.utils.version

if TYPE_CHECKING:
    from weblate.auth.models import User


def get_doc_url(page: str, anchor: str = "", user: User | None = None) -> str:
    """Return URL to documentation."""
    version = weblate.utils.version.VERSION
    # Should we use tagged release or latest version
    if version.endswith(("-dev", "-rc")) or (
        settings.HIDE_VERSION and (user is None or not user.is_authenticated)
    ):
        doc_version = "latest"
    else:
        doc_version = f"weblate-{version}"
    # Language variant
    code = DOCUMENTATION_LANGUAGES.get(get_language(), "en")
    # Optionally append anchor
    if anchor:
        anchor = "#{}".format(anchor.replace("_", "-"))
    # Generate URL
    return f"https://docs.weblate.org/{code}/{doc_version}/{page}.html{anchor}"
