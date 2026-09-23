# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fixed internal bot identities."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from weblate.auth.models import User


class InternalBot(Enum):
    COMMIT = ("weblate", "commit", "Background commit")
    UPDATE = ("weblate", "update", "Background update")
    PUSH = ("weblate", "push", "Background push")
    REPOSITORY = ("weblate", "repository", "Repository maintenance")
    SCREENSHOTS = ("weblate", "screenshots", "Screenshots from repository")
    GLOSSARY_SYNC = ("glossary", "sync", "Glossary sync")

    def get_user(self) -> User:
        """Resolve the bot using the configured internal bot account settings."""
        from weblate.auth.models import User  # ruff: ignore[import-outside-top-level]

        scope, name, verbose = self.value
        return User.objects.get_or_create_bot(scope=scope, name=name, verbose=verbose)
