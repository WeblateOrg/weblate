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
    TEAM_ASSIGNMENT = ("weblate", "team-assignment", "Automatic team assignment")
    ALERTS = ("weblate", "alerts", "Automatic alerts")
    BACKUP = ("weblate", "backup", "Automatic backups")
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


def internal_bot_names() -> dict[str, str]:
    """Names whose inactive authorship account can be reconstructed locally."""
    # ruff: ignore[import-outside-top-level]
    from weblate.addons.models import ADDONS
    from weblate.machinery.models import MACHINERY  # ruff: ignore[import-outside-top-level]

    names = {
        f"{scope}:{name}": verbose
        for scope, name, verbose in (bot.value for bot in InternalBot)
    }
    names.update({f"mt:{name}": engine.name for name, engine in MACHINERY.items()})
    names.update(
        {
            f"addon:{addon.user_name}": addon.user_verbose
            for addon in ADDONS.values()
            if addon.user_name and addon.user_verbose
        }
    )
    return names
