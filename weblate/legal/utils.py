# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.urls import reverse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy

if TYPE_CHECKING:
    from collections.abc import Sequence

MenuItem = tuple[str, str, Promise]

MENU = (
    ("index", "legal:index", gettext_lazy("Overview")),
    ("terms", "legal:terms", gettext_lazy("General Terms and Conditions")),
    ("cookies", "legal:cookies", gettext_lazy("Cookies")),
    ("privacy", "legal:privacy", gettext_lazy("Privacy Policy")),
    ("contracts", "legal:contracts", gettext_lazy("Subcontractors")),
)


def get_hidden_documents() -> set[str]:
    """Return legal documents hidden by configuration."""
    configured = settings.LEGAL_HIDDEN_DOCUMENTS
    documents = configured.split(",") if isinstance(configured, str) else configured

    hidden = set()
    for document in documents:
        document = document.strip()
        if document and document != "index":
            hidden.add(document)

    return hidden


def is_document_hidden(page: str) -> bool:
    return page in get_hidden_documents()


def get_legal_menu() -> Sequence[MenuItem]:
    hidden = get_hidden_documents()
    return tuple(item for item in MENU if item[0] not in hidden)


def get_document_url(page: str, fallback: str | None = None) -> str | None:
    if is_document_hidden(page):
        return fallback
    return reverse(f"legal:{page}")


def get_document_context() -> dict[str, bool | str | None]:
    return {
        "terms_document_hidden": is_document_hidden("terms"),
        "privacy_document_hidden": is_document_hidden("privacy"),
        "terms_url": get_document_url("terms", settings.LEGAL_URL),
        "privacy_url": get_document_url("privacy", settings.PRIVACY_URL),
    }
