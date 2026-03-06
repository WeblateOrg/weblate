# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING, ClassVar

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
        anchor = f"#{anchor}"
    # Generate URL
    return f"https://docs.weblate.org/{code}/{doc_version}/{page}.html{anchor}"


class DocVersionsMixin:
    """
    Mixin for classes that document version metadata in RST.

    Set version_added and/or versions_changed on subclasses; get_versions_output()
    renders them as .. versionadded:: and .. versionchanged:: directives.
    """

    version_added: ClassVar[str | None] = None
    versions_changed: ClassVar[tuple[tuple[str, str], ...]] = ()

    @classmethod
    def get_versions_output(cls) -> list[str]:
        parts: list[str] = []
        if cls.version_added is not None:
            parts.extend(("\n", f".. versionadded:: {cls.version_added}", "\n"))
        for version, description in cls.versions_changed:
            normalized = description.replace("\r\n", "\n").replace("\r", "\n")
            body = textwrap.indent(normalized, "   ")
            parts.extend(("\n", f".. versionchanged:: {version}", "\n\n", body, "\n"))
        return parts
