# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.core.checks import (
    CheckMessage,
    Critical,
    Debug,
    Error,
    Info,
    Warning,  # noqa: A004
)

from weblate.utils.docs import get_doc_url

DOC_LINKS: dict[str, tuple[str] | tuple[str, str]] = {
    "security.W001": ("admin/upgdade", "up-3-1"),
    "security.W002": ("admin/upgdade", "up-3-1"),
    "security.W003": ("admin/upgdade", "up-3-1"),
    "security.W004": ("admin/install", "production-ssl"),
    "security.W005": ("admin/install", "production-ssl"),
    "security.W006": ("admin/upgdade", "up-3-1"),
    "security.W007": ("admin/upgdade", "up-3-1"),
    "security.W008": ("admin/install", "production-ssl"),
    "security.W009": ("admin/install", "production-secret"),
    "security.W010": ("admin/install", "production-ssl"),
    "security.W011": ("admin/install", "production-ssl"),
    "security.W012": ("admin/install", "production-ssl"),
    "security.W018": ("admin/install", "production-debug"),
    "security.W019": ("admin/upgdade", "up-3-1"),
    "security.W020": ("admin/install", "production-hosts"),
    "security.W021": ("admin/install", "production-ssl"),
    "weblate.E002": ("admin/install", "file-permissions"),
    "weblate.E003": ("admin/install", "out-mail"),
    "weblate.E005": ("admin/install", "celery"),
    "weblate.E006": ("admin/install", "production-database"),
    "weblate.E007": ("admin/install", "production-cache"),
    "weblate.E008": ("admin/install", "production-cache-avatar"),
    "weblate.E009": ("admin/install", "celery"),
    "weblate.E011": ("admin/install", "production-admins"),
    "weblate.E012": ("admin/install", "production-email"),
    "weblate.E013": ("admin/install", "production-email"),
    "weblate.E014": ("admin/install", "production-secret"),
    "weblate.E015": ("admin/install", "production-hosts"),
    "weblate.E017": ("admin/install", "production-site"),
    "weblate.E018": ("admin/optionals", "avatars"),
    "weblate.E019": ("admin/install", "celery"),
    "weblate.E020": ("admin/install", "celery"),
    "weblate.I021": ("admin/install", "collecting-errors"),
    "weblate.E022": ("admin/optionals", "git-exporter"),
    "weblate.C023": ("admin/install", "production-encoding"),
    "weblate.C024": ("admin/install", "pangocairo"),
    "weblate.W025": ("admin/install", "optional-deps"),
    "weblate.E026": ("admin/install", "celery"),
    "weblate.E027": ("admin/install", "file-permissions"),
    "weblate.E028": ("admin/config",),
    "weblate.I028": ("admin/backup",),
    "weblate.C029": ("admin/backup",),
    "weblate.C030": ("admin/install", "celery"),
    "weblate.I031": ("admin/upgrade",),
    "weblate.C031": ("admin/upgrade",),
    "weblate.C032": ("admin/install",),
    "weblate.W033": ("vcs",),
    "weblate.E034": ("admin/install", "celery"),
    "weblate.C035": ("vcs",),
    "weblate.C036": ("admin/optionals", "gpg-sign"),
    "weblate.C037": ("admin/install", "production-database"),
    "weblate.C038": ("admin/install", "production-database"),
    "weblate.W039": ("admin/machine",),
    "weblate.C040": ("vcs",),
}


def check_doc_link(docid: str, strict: bool = False) -> str | None:
    while docid.count(".") > 1:
        docid = docid.rsplit(".", 1)[0]
    try:
        return get_doc_url(*DOC_LINKS[docid])
    except KeyError:
        if strict:
            raise
        return None


def weblate_check(
    check_id: str,
    message: str,
    cls: type[Critical | Debug | Error | Info | Warning] = Critical,
) -> CheckMessage:
    """Return Django check instance."""
    return cls(message, hint=check_doc_link(check_id), id=check_id)
