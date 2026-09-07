# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from urllib.parse import ParseResult


def strip_git_suffix(value: str) -> str:
    """Strip a trailing .git suffix from a repository path."""
    if value.endswith(".git"):
        return value[:-4]
    return value


def strip_vcs_wrapper(repo: str) -> str:
    """Strip VCS wrapper prefix from repository URL."""
    if repo.startswith("hg::"):
        return repo[4:]
    return repo


def normalize_full_name(full_name: str | None) -> str | None:
    """Normalize repository full name for matching helpers."""
    if not full_name:
        return None
    full_name = strip_git_suffix(full_name.strip("/"))
    parts = full_name.split("/")
    if len(parts) < 2 or any(not part for part in parts):
        return None
    return full_name


def validate_full_name(full_name: str | None) -> bool:
    """
    Validate that repository full name is suitable for repository URL templates.

    This is to avoid using too short expression with possibly too broad matches.
    """
    full_name = normalize_full_name(full_name)
    if full_name is None:
        return False
    name = strip_git_suffix(full_name.rsplit("/", 1)[-1])
    return len(name) >= 3


def parse_repo_url(repo: str) -> ParseResult | None:
    """Parse repository URL, returning None for malformed URL syntax."""
    repo = strip_vcs_wrapper(repo)
    try:
        return urlparse(repo)
    except ValueError:
        return None


def repo_connection(repo: str) -> tuple[str | None, str | None, int | None, bool]:
    """Extract hostname, username and SSH port from repository URL."""
    repo = strip_vcs_wrapper(repo)
    parsed = parse_repo_url(repo)
    if parsed is None:
        return None, None, None, False
    if parsed.hostname is not None:
        try:
            port = parsed.port
        except ValueError:
            port = None
        return parsed.hostname, parsed.username, port, parsed.scheme == "ssh"

    if ":" not in repo:
        return None, None, None, False

    host = repo.split(":", 1)[0]
    username = None
    if "@" in host:
        username, host = host.rsplit("@", 1)
    return host or None, username or None, None, False


def repo_is_scp_like(repo: str) -> bool:
    """Check whether repository URL uses scp-like Git syntax."""
    parsed = parse_repo_url(repo)
    return parsed is not None and parsed.hostname is None and ":" in repo


def repo_path(repo: str) -> str | None:
    """Extract repository path from URL or scp-like Git syntax."""
    repo = strip_vcs_wrapper(repo)
    parsed = parse_repo_url(repo)
    if parsed is None:
        return None
    if parsed.hostname is not None:
        return strip_git_suffix(parsed.path.lstrip("/")) or None
    if ":" not in repo:
        return None
    return strip_git_suffix(repo.split(":", 1)[1].lstrip("/")) or None
