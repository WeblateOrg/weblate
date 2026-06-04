# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

HOOK_MATCH_EXACT = "exact"
HOOK_MATCH_FALLBACK = "fallback"


def repo_matches_exact_repos(repo: str, repos: list[str]) -> bool:
    """Check whether a repository URL would match the exact hook URL filter."""
    for candidate in repos:
        if repo in {candidate, f"{candidate}/"}:
            return True
        if (
            repo.startswith("http://")
            and candidate.startswith("http://")
            and repo.endswith(f"@{candidate[7:]}")
        ):
            return True
        if (
            repo.startswith("https://")
            and candidate.startswith("https://")
            and repo.endswith(f"@{candidate[8:]}")
        ):
            return True
    return False
