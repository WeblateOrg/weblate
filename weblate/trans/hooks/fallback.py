# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from ipaddress import ip_address
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from django.db.models import Q

if TYPE_CHECKING:
    from urllib.parse import ParseResult

    from django.db.models import QuerySet

    from weblate.trans.models import Component

type FallbackRepositoryEvidence = frozenset[tuple[str, int | None, str]]


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
    Validate that repository full name is suitable for endswith matching.

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


def normalize_repo_path(path: str | None) -> str | None:
    """Normalize repository path for host-bound fallback matching."""
    if not path:
        return None
    path = strip_git_suffix(path.strip("/"))
    if not path:
        return None
    return path.lower()


def repo_hostname(repo: str) -> str | None:
    """Extract hostname from repository URL or scp-like Git URL."""
    return repo_connection(repo)[0]


def repo_is_loopback(repo: str) -> bool:
    """Check whether repository URL points to a loopback host."""
    hostname = repo_hostname(repo)
    if hostname is None:
        return False
    if hostname == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


def normalize_repo_port(repo: str) -> int | None:
    """Extract non-default repository URL port for fallback matching."""
    parsed = parse_repo_url(repo)
    if parsed is None or parsed.hostname is None:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        return None
    if parsed.scheme == "http" and port == 80:
        return None
    if parsed.scheme == "https" and port == 443:
        return None
    if parsed.scheme == "ssh" and port == 22:
        return None
    return port


def repo_fallback_key(repo: str) -> tuple[str, int | None, str] | None:
    """Return host, port and path evidence for repository fallback matching."""
    if repo_is_loopback(repo):
        return None
    hostname = repo_hostname(repo)
    port = normalize_repo_port(repo)
    path = normalize_repo_path(repo_path(repo))
    if hostname is None or path is None:
        return None
    return hostname.lower(), port, path


def fallback_repository_evidence(
    repos: list[str], full_name: str | None
) -> FallbackRepositoryEvidence:
    """
    Collect trusted host/path evidence for suffix fallback matching.

    The public webhook payload controls both repository URLs and full_name. Do
    not use full_name alone to select components; require a non-loopback
    repository URL whose normalized path agrees with full_name.
    """
    normalized_full_name = normalize_full_name(full_name)
    normalized_path = normalize_repo_path(normalized_full_name)
    if normalized_path is None or not validate_full_name(normalized_full_name):
        return frozenset()

    evidence = set()
    for repo in repos:
        key = repo_fallback_key(repo)
        if key is not None and key[2] == normalized_path:
            evidence.add(key)
    return frozenset(evidence)


def repo_matches_fallback_evidence(
    repo: str, evidence: FallbackRepositoryEvidence
) -> bool:
    """Check whether a configured repository matches fallback host/path evidence."""
    key = repo_fallback_key(repo)
    return key is not None and key in evidence


def fallback_repositories_filter(full_name: str) -> Q:
    """Build a repository suffix filter for fallback hook matching."""
    return (
        Q(repo__iendswith=full_name)
        | Q(repo__iendswith=f"{full_name}/")
        | Q(repo__iendswith=f"{full_name}.git")
    )


def get_fallback_components(
    components: QuerySet[Component], repos: list[str], full_name: str | None
) -> QuerySet[Component] | None:
    """Return components matched by repository suffix fallback evidence."""
    fallback_full_name = normalize_full_name(full_name)
    fallback_evidence = fallback_repository_evidence(repos, fallback_full_name)
    if fallback_full_name is None or not fallback_evidence:
        return None

    fallback_candidates = (
        components.filter(fallback_repositories_filter(fallback_full_name))
        .values_list("pk", "repo")
        .iterator()
    )
    fallback_pks = [
        pk
        for pk, repo in fallback_candidates
        if repo_matches_fallback_evidence(repo, fallback_evidence)
    ]
    return components.filter(pk__in=fallback_pks)
