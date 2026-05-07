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
from weblate.utils.version_display import hide_detailed_version

if TYPE_CHECKING:
    from weblate.auth.models import User


def build_doc_url(page: str, doc_version: str, anchor: str = "") -> str:
    """Build a documentation URL for the given docs version."""
    code = DOCUMENTATION_LANGUAGES.get(get_language(), "en")
    if anchor:
        anchor = f"#{anchor}"
    return f"https://docs.weblate.org/{code}/{doc_version}/{page}.html{anchor}"


def get_doc_url(
    page: str,
    anchor: str = "",
    user: User | None = None,
    *,
    doc_version: str | None = None,
) -> str:
    """Return URL to documentation."""
    if doc_version is None:
        version = weblate.utils.version.VERSION
        if version.endswith(("-dev", "-rc")) or (
            hide_detailed_version(settings.VERSION_DISPLAY)
            and (user is None or not user.is_authenticated)
        ):
            doc_version = "latest"
        else:
            doc_version = f"weblate-{version}"
    return build_doc_url(page, doc_version, anchor)


class DocVersionsMixin:
    """
    Mixin for classes that document version metadata in RST.

    Set version_added and/or versions_changed on subclasses; get_versions_output()
    renders them as .. versionadded:: and .. versionchanged:: directives.
    """

    version_added: ClassVar[str | None] = None
    versions_changed: ClassVar[tuple[tuple[str, str], ...]] = ()

    @classmethod
    def get_versions_rst_lines(cls) -> list[str]:
        parts: list[str] = []
        if cls.version_added is not None:
            parts.extend(["", f".. versionadded:: {cls.version_added}"])
        for version, description in cls.versions_changed:
            normalized = description.replace("\r\n", "\n").replace("\r", "\n")
            body = textwrap.indent(normalized, "   ")
            parts.extend(("", f".. versionchanged:: {version}", "", body))
        return parts
