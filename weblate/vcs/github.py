# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Weblate GitHub app authentication and API utilities."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
import uuid
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import urlencode, urlparse

import jwt
import requests
from django.core.cache import cache
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy

from weblate.utils.errors import report_error
from weblate.vcs.base import RepositoryError
from weblate.vcs.git import GithubRepository, GitRepository
from weblate.vcs.models import Installation, InstallationProvider

if TYPE_CHECKING:
    from collections.abc import Iterator

    from django_stubs_ext import StrOrPromise

    from weblate.workspaces.models import Workspace

logger = logging.getLogger(__name__)

# Installation tokens are valid for 1 hour; cache for 50 minutes
TOKEN_CACHE_TTL = 50 * 60
# GitHub enforces a 10-minute maximum on App JWTs
JWT_MAX_LIFETIME = 9 * 60

# Permissions and events Weblate needs when registering a GitHub App via
# the manifest flow. Keep aligned with the documented manual setup.
GITHUB_APP_MANIFEST_PERMISSIONS: dict[str, str] = {
    "contents": "write",
    "metadata": "read",
    "pull_requests": "write",
    "workflows": "write",
}
GITHUB_APP_MANIFEST_EVENTS: tuple[str, ...] = (
    "installation",
    "installation_repositories",
    "installation_target",
    "meta",
    "push",
)
# GitHub rejects App names longer than this; mirror the limit on our side so
# users see the constraint up front and the manifest is always accepted.
GITHUB_APP_NAME_MAX_LENGTH = 34


def normalize_github_app_hostname(hostname: str) -> str:
    """Normalize GitHub hostnames to the web host used by installations."""
    normalized = hostname.strip().lower()
    if normalized == "api.github.com":
        return "github.com"
    return normalized


def get_github_app_configurations() -> dict[str, GitHubAppCredentials]:
    """
    Return configured Weblate GitHub app credentials keyed by normalized hostname.

    GitHub Apps are registered through the manifest flow and stored in the
    database (:class:`GitHubAppCredentials`); there is no settings-based
    configuration.
    """
    try:
        rows = list(GitHubAppCredentials.objects.all())
    except Exception:
        # Database may not be migrated yet (e.g. during initial setup or
        # when this is called outside a request).
        return {}
    return {row.hostname: row for row in rows}


def get_github_app_settings(hostname: str | None = None) -> GitHubAppCredentials | None:
    """Return the configured Weblate GitHub app credentials for one host, if any."""
    configs = get_github_app_configurations()
    if hostname is not None:
        return configs.get(normalize_github_app_hostname(hostname))
    if len(configs) == 1:
        return next(iter(configs.values()))
    return None


def github_app_is_configured(hostname: str | None = None) -> bool:
    """Return whether the Weblate GitHub app is configured for installs on the host."""
    if hostname is not None:
        return get_github_app_settings(hostname) is not None
    return bool(get_github_app_configurations())


def get_github_app_install_url(state: str, hostname: str | None = None) -> str:
    """Build the Weblate GitHub app installation URL for the configured host."""
    config = get_github_app_settings(hostname)
    if config is None:
        msg = "Weblate GitHub app is not configured"
        raise ValueError(msg)

    # The documented ``installations/new`` URL can send returning users straight
    # to an existing installation settings page. ``select_target`` keeps the
    # account or organization picker in the connect flow.
    app_path = "apps" if config.hostname == "github.com" else "github-apps"
    return (
        f"https://{config.hostname}/{app_path}/{config.app_slug}"
        f"/installations/select_target?{urlencode({'state': state})}"
    )


def get_github_repository_import_url(
    repo: dict,
    *,
    project_id: str | int | None = None,
    category_id: str | int | None = None,
) -> str:
    """Return the component creation URL pre-filled from a GitHub repository."""
    name = repo["name"]
    params = {
        "repo": repo["clone_url"],
        "branch": repo.get("default_branch", "main"),
        "vcs": "github-app",
        "name": name,
        "slug": slugify(name),
    }
    if project_id:
        params["project"] = str(project_id)
    if category_id:
        params["category"] = str(category_id)
    return f"{reverse('create-component-vcs')}?{urlencode(params)}"


def build_github_app_manifest(
    *,
    name: str,
    base_url: str,
    redirect_url: str,
    setup_url: str,
    webhook_url: str,
    public: bool = True,
) -> dict[str, object]:
    """
    Return a GitHub App manifest pre-filled with Weblate's requirements.

    ``public=True`` lets the App be installed on any account the maintainer
    administrates (without it, GitHub's install URL skips the account picker
    and forces a single-target install on the owner). This is *not* the same
    as "Marketplace listed"; the App still has to be submitted separately to
    show up in the Marketplace.

    ``request_oauth_on_install=True`` sends users through user authorization during
     installation so the post-install redirect carries an OAuth ``code`` Weblate can
     exchange to confirm the user controls the installation they are connecting.
    """
    return {
        "name": name,
        "url": base_url,
        "hook_attributes": {"url": webhook_url, "active": True},
        "redirect_url": redirect_url,
        "callback_urls": [setup_url],
        "setup_url": setup_url,
        "setup_on_update": True,
        "request_oauth_on_install": True,
        "public": public,
        "default_permissions": dict(GITHUB_APP_MANIFEST_PERMISSIONS),
        "default_events": list(GITHUB_APP_MANIFEST_EVENTS),
    }


def get_github_app_manifest_new_url(hostname: str, org: str | None = None) -> str:
    """Return the GitHub URL where the manifest form should be POSTed."""
    hostname = normalize_github_app_hostname(hostname)
    if org:
        return f"https://{hostname}/organizations/{org}/settings/apps/new"
    return f"https://{hostname}/settings/apps/new"


def exchange_github_app_manifest_code(
    code: str, hostname: str = "github.com"
) -> dict[str, object]:
    """Exchange a temporary manifest code for the created app's credentials."""
    api_base = get_github_api_base(normalize_github_app_hostname(hostname))
    response = requests.post(
        f"{api_base}/app-manifests/{code}/conversions",
        headers={"Accept": "application/vnd.github.v3+json"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def validate_private_key(value: str) -> str:
    """Return the PEM string, stripped, rejecting anything that isn't a PEM block."""
    value = value.strip()
    if (
        not value.startswith("-----BEGIN")
        or "PRIVATE KEY" not in value.split("\n", 1)[0]
    ):
        msg = "Private key must be an inline PEM block"
        raise ValueError(msg)
    return value


def generate_jwt(app_id: str | int, private_key_pem: str) -> str:
    """Generate a short-lived JWT for Weblate GitHub app authentication (RS256)."""
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + JWT_MAX_LIFETIME,
        "iss": str(app_id),
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


def get_github_basic_auth_header(username: str, token: str) -> str:
    """Return an HTTP Basic auth header value for GitHub HTTPS operations."""
    auth = base64.b64encode(f"{username}:{token}".encode()).decode("ascii")
    return f"Authorization: Basic {auth}"


def get_github_git_auth_args(username: str, token: str) -> Iterator[str]:
    """
    Yield git CLI flags that inject GitHub HTTPS auth for one command.

    ``http.extraHeader`` is sent on every request, which is enough for the
    initial smart-protocol probe to succeed. Combining it with
    ``http.proactiveAuth=auto`` is counter-productive: proactive auth makes
    Git skip the unauthenticated probe and instead look for credentials it
    knows about (URL, credential helper) — it does not consume
    ``extraHeader`` — so Git falls back to prompting and the clone fails
    with "terminal prompts disabled".
    """
    yield "-c"
    yield f"http.extraHeader={get_github_basic_auth_header(username, token)}"


def get_github_api_base(hostname: str) -> str:
    """Return the API base for github.com or a GHE host."""
    if hostname == "github.com":
        return "https://api.github.com"
    return f"https://{hostname}/api/v3"


def get_installation_token(
    app_id: str | int,
    private_key: str,
    installation_id: str | int,
    hostname: str,
) -> str:
    """Return a cached installation access token for the given installation."""
    cache_key = f"github-app-token:{hostname}:{installation_id}"
    cached_token = cache.get(cache_key)
    if cached_token is not None:
        return cached_token

    private_key_pem = validate_private_key(private_key)
    token = generate_jwt(app_id, private_key_pem)

    api_base = get_github_api_base(hostname)
    response = requests.post(
        f"{api_base}/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    access_token = data["token"]
    cache.set(cache_key, access_token, TOKEN_CACHE_TTL)
    logger.info(
        "Obtained Weblate GitHub app token for connected account %s/%s",
        hostname,
        installation_id,
    )
    return access_token


def get_app_installation(
    app_id: str | int,
    private_key: str,
    installation_id: str | int,
    hostname: str,
) -> dict:
    """Fetch metadata for one installation using app authentication."""
    private_key_pem = validate_private_key(private_key)
    token = generate_jwt(app_id, private_key_pem)
    api_base = get_github_api_base(hostname)
    response = requests.get(
        f"{api_base}/app/installations/{installation_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_app_repositories(
    app_id: str | int,
    private_key: str,
    installation_id: str | int,
    hostname: str,
) -> list[dict]:
    """List repositories accessible to the installation, paginated."""
    access_token = get_installation_token(
        app_id, private_key, installation_id, hostname
    )
    api_base = get_github_api_base(hostname)

    repositories: list[dict] = []
    url: str | None = f"{api_base}/installation/repositories?per_page=100"
    headers = {
        "Authorization": f"token {access_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    while url:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        repositories.extend(
            {
                "name": repo["name"],
                "full_name": repo["full_name"],
                "clone_url": repo["clone_url"],
                "ssh_url": repo["ssh_url"],
                "html_url": repo["html_url"],
                "default_branch": repo.get("default_branch", "main"),
                "private": repo.get("private", False),
                "description": repo.get("description", ""),
            }
            for repo in data.get("repositories", [])
            if not repo.get("archived", False)
        )

        url = None
        for part in response.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break

    return repositories


def verify_webhook_signature(
    payload_body: bytes, signature_header: str, secret: str
) -> bool:
    """Verify a GitHub X-Hub-Signature-256 header using HMAC-SHA256."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected_signature = (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"),
            payload_body,
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected_signature, signature_header)


class GitHubAppNotConfiguredError(RuntimeError):
    """Raised when Weblate GitHub app credentials are not configured for a host."""


class GitHubAppCredentials(models.Model):
    """
    Per-host Weblate GitHub App credentials stored in the database.

    Rows in this table are created by the manifest registration flow in
    :mod:`weblate.vcs.views`; this is the only way GitHub Apps are configured.
    """

    hostname = models.CharField(
        max_length=255,
        unique=True,
        verbose_name=gettext_lazy("GitHub hostname"),
    )
    app_id = models.CharField(max_length=50, verbose_name=gettext_lazy("App ID"))
    app_slug = models.CharField(max_length=255, verbose_name=gettext_lazy("App slug"))
    private_key = models.TextField(verbose_name=gettext_lazy("Private key (PEM)"))
    client_id = models.CharField(
        max_length=255, verbose_name=gettext_lazy("OAuth client ID")
    )
    client_secret = models.CharField(
        max_length=255, verbose_name=gettext_lazy("OAuth client secret")
    )
    webhook_secret = models.CharField(
        max_length=255, verbose_name=gettext_lazy("Webhook secret")
    )
    # Opaque identifier embedded in the App's webhook URL
    # (``/hooks/integrations/<webhook_token>/``). It lets an incoming delivery be
    # tied to exactly one integration so its secret can be verified without
    # guessing the host from the payload.
    webhook_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name=gettext_lazy("Webhook token"),
    )
    html_url = models.URLField(blank=True, verbose_name=gettext_lazy("App URL"))
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Weblate GitHub App credentials")
        verbose_name_plural = gettext_lazy("Weblate GitHub App credentials")

    def __str__(self) -> str:
        return f"{self.app_slug} ({self.hostname})"

    def save(self, *args, **kwargs) -> None:
        self.hostname = normalize_github_app_hostname(self.hostname)
        super().save(*args, **kwargs)


class GitHubAppOAuthError(Exception):
    """Raised when the user-authorization step of the install flow fails."""


def get_github_oauth_base(hostname: str) -> str:
    """Return the base URL hosting the OAuth ``login/oauth`` endpoints."""
    hostname = normalize_github_app_hostname(hostname)
    return "https://github.com" if hostname == "github.com" else f"https://{hostname}"


def exchange_github_user_code(config: GitHubAppCredentials, code: str) -> str:
    """Exchange an install-time OAuth ``code`` for a user-to-server access token."""
    response = requests.post(
        f"{get_github_oauth_base(config.hostname)}/login/oauth/access_token",
        data={
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code": code,
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        msg = f"GitHub did not return a user access token: {payload.get('error')}"
        raise GitHubAppOAuthError(msg)
    return token


def user_can_access_installation(
    config: GitHubAppCredentials, user_token: str, installation_id: str | int
) -> bool:
    """Return whether the authenticated user can access ``installation_id``."""
    installation_id = str(installation_id)
    api_base = get_github_api_base(normalize_github_app_hostname(config.hostname))
    url: str | None = f"{api_base}/user/installations?per_page=100"
    headers = {
        "Authorization": f"Bearer {user_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    while url:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        for installation in response.json().get("installations", []):
            if str(installation.get("id")) == installation_id:
                return True
        url = response.links.get("next", {}).get("url")
    return False


class GitHubInstallationManager(models.Manager["GitHubInstallation"]):
    def get_queryset(self) -> models.QuerySet[GitHubInstallation]:
        # Scope the proxy to GitHub-owned rows so the shared installations table
        # does not leak rows belonging to other providers.
        return super().get_queryset().filter(provider=InstallationProvider.GITHUB)

    def filter_for_installation(
        self, hostname: str, installation_id: str | int
    ) -> models.QuerySet[GitHubInstallation]:
        """Return installations by host and installation ID."""
        hostname = normalize_github_app_hostname(hostname)
        return self.filter(
            hostname=hostname,
            installation_id=str(installation_id),
        )

    def get_for_installation(
        self,
        hostname: str,
        installation_id: str | int,
        *,
        workspace: Workspace | None = None,
    ) -> GitHubInstallation | None:
        """Return one installation by host and installation ID."""
        queryset = self.filter_for_installation(hostname, installation_id)
        if workspace is not None:
            queryset = queryset.filter(workspace=workspace)
        return queryset.order_by("workspace_id", "-created").first()

    def get_for_repo(
        self,
        hostname: str,
        full_name: str,
        *,
        workspace: Workspace | None = None,
    ) -> GitHubInstallation | None:
        """Return an enabled installation on ``hostname`` that owns ``full_name``."""
        hostname = normalize_github_app_hostname(hostname)
        queryset = self.filter(hostname=hostname, enabled=True)
        if workspace is not None:
            queryset = queryset.filter(workspace=workspace)
        for installation in queryset.order_by("-created"):
            if installation.has_repository(full_name):
                return installation
        return None

    def upsert_from_data(
        self,
        hostname: str,
        installation_id: str | int,
        data: dict,
        *,
        workspace: Workspace,
        enabled: bool = True,
    ) -> GitHubInstallation:
        """Create or update an installation using trusted GitHub metadata."""
        hostname = normalize_github_app_hostname(hostname)
        installation_id = str(installation_id)
        account = data.get("account") or {}
        defaults: dict[str, object] = {"enabled": enabled}
        if login := account.get("login"):
            defaults["target_login"] = login
        if target_type := account.get("type"):
            defaults["target_type"] = target_type

        installation = self.filter(
            hostname=hostname,
            installation_id=installation_id,
            workspace=workspace,
        ).first()
        if installation is None:
            installation = self.model(
                hostname=hostname,
                installation_id=installation_id,
                workspace=workspace,
            )
        for name, value in defaults.items():
            setattr(installation, name, value)
        installation.save()
        return installation

    def sync_from_api(
        self,
        hostname: str,
        installation_id: str | int,
        *,
        workspace: Workspace,
        enabled: bool = True,
    ) -> GitHubInstallation:
        """Fetch installation metadata from GitHub and persist it."""
        hostname = normalize_github_app_hostname(hostname)
        config = get_github_app_settings(hostname)
        if config is None:
            msg = f"Weblate GitHub app is not configured for {hostname}"
            raise GitHubAppNotConfiguredError(msg)

        data = get_app_installation(
            config.app_id,
            config.private_key,
            installation_id,
            hostname,
        )
        return self.upsert_from_data(
            hostname,
            installation_id,
            data,
            workspace=workspace,
            enabled=enabled,
        )

    def connect_workspace(
        self, hostname: str, installation_id: str | int, workspace: Workspace
    ) -> tuple[GitHubInstallation, bool]:
        """Connect an existing GitHub installation to a Weblate workspace."""
        hostname = normalize_github_app_hostname(hostname)
        installation_id = str(installation_id)

        installation = self.get_for_installation(
            hostname, installation_id, workspace=workspace
        )
        if installation is not None:
            return installation, False

        return (
            self.sync_from_api(hostname, installation_id, workspace=workspace),
            True,
        )


class GitHubInstallation(Installation):
    """
    Workspace-scoped connected GitHub account for the Weblate GitHub app.

    Per-workspace rows store the GitHub-issued ``installation_id``, the account
    it was installed on, and a cached repository list. App-level credentials
    (App ID, private key, webhook secret) live in
    :class:`GitHubAppCredentials` and are looked up by hostname so a single
    registered App can serve every connected account on that host.
    """

    objects = GitHubInstallationManager()

    class Meta:
        proxy = True
        verbose_name = gettext_lazy("connected GitHub account")
        verbose_name_plural = gettext_lazy("connected GitHub accounts")

    def save(self, *args, **kwargs) -> None:
        self.provider = InstallationProvider.GITHUB
        self.hostname = normalize_github_app_hostname(self.hostname)
        super().save(*args, **kwargs)

    @property
    def api_base(self) -> str:
        return get_github_api_base(self.hostname)

    def _require_app_settings(self) -> GitHubAppCredentials:
        config = get_github_app_settings(self.hostname)
        if config is None:
            msg = f"Weblate GitHub app is not configured for {self.hostname}"
            raise GitHubAppNotConfiguredError(msg)
        return config

    @property
    def app_id(self) -> str:
        config = get_github_app_settings(self.hostname)
        return config.app_id if config is not None else ""

    def get_access_token(self) -> str:
        config = self._require_app_settings()
        return get_installation_token(
            config.app_id,
            config.private_key,
            self.installation_id,
            self.hostname,
        )

    def refresh_repositories(self) -> list[dict]:
        config = self._require_app_settings()
        repos = get_app_repositories(
            config.app_id,
            config.private_key,
            self.installation_id,
            self.hostname,
        )
        self.repositories = repos
        self.repositories_updated = timezone.now()
        self.save(update_fields=["repositories", "repositories_updated"])
        logger.info(
            "Refreshed %d repositories for connected GitHub account %s/%s",
            len(repos),
            self.hostname,
            self.installation_id,
        )
        return repos

    def has_repository(self, full_name: str) -> bool:
        return any(repo.get("full_name") == full_name for repo in self.repositories)

    def get_webhook_secret(self) -> str:
        config = get_github_app_settings(self.hostname)
        if config is None:
            return ""
        return config.webhook_secret


class GithubAppRepository(GithubRepository):
    """
    GitHub backend that authenticates exclusively via the Weblate GitHub app.

    Components imported through the GitHub App flow use this backend so the
    settings UI can prevent editing the repository URL — changing it would
    silently switch the App-issued token to a different repository (or break
    auth entirely, leaking PAT-style credentials embedded in the new URL).
    """

    name: ClassVar[StrOrPromise] = gettext_lazy("GitHub (via Weblate GitHub app)")
    identifier: ClassVar[str] = "github-app"
    push_label: ClassVar[StrOrPromise] = gettext_lazy(
        "This will push changes and create a GitHub pull request "
        "via the Weblate GitHub app."
    )

    @classmethod
    def is_configured(cls) -> bool:
        # Always register this backend. App availability is configured in the
        # database (per host/installation) and resolved per repository at clone
        # time, so it must not be gated by the process-wide cached VCS registry
        # (which would otherwise hide it until a worker restart). Whether to
        # offer it in the UI is decided dynamically via github_app_is_configured.
        return True

    @classmethod
    def get_credentials_configuration(cls):
        # The App backend authenticates per-installation rather than through
        # a static settings dict; satisfy the base API with an empty mapping.
        return {}

    def should_use_fork(self, branch: str | None = None) -> bool:
        # Apps push branches directly to the source repo; forking is both
        # unnecessary (the App already has write access) and unsupported
        # (Apps cannot fork without an explicit organization target).
        return False

    def push(self, branch: str) -> None:
        # Translations must not push onto the pull branch — there's no fork
        # to absorb them. Substitute a dedicated weblate-* branch on the
        # source repo when no explicit push branch is configured (or when
        # it equals the pull branch).
        if not branch or branch == self.branch:
            branch = self.get_fork_branch_name()
        return super().push(branch)

    @classmethod
    def _resolve_github_app_credentials_for_repo(
        cls, repo: str, *, workspace: Workspace | None = None
    ) -> dict[str, str] | None:
        """Resolve an installation access token for a GitHub HTTPS repo URL."""
        if workspace is None:
            return None

        parsed = urlparse(repo)
        if parsed.scheme != "https" or not parsed.hostname:
            return None
        if parsed.username or parsed.password:
            return None

        path = parsed.path.strip("/").removesuffix(".git")
        if path.count("/") != 1:
            return None

        installation = GitHubInstallation.objects.get_for_repo(
            parsed.hostname.lower(), path, workspace=workspace
        )
        if installation is None:
            return None

        try:
            token = installation.get_access_token()
        except GitHubAppNotConfiguredError:
            return None

        return {
            "username": "x-access-token",
            "token": token,
            "github_app": "1",
        }

    @classmethod
    def _get_auth_args(cls, repo: str, *, workspace: Workspace | None = None):
        yield from GitRepository._get_auth_args(repo)  # noqa: SLF001

        app_creds = cls._resolve_github_app_credentials_for_repo(
            repo, workspace=workspace
        )
        if app_creds is not None:
            yield from get_github_git_auth_args(
                app_creds["username"], app_creds["token"]
            )

    def get_auth_args(self) -> list[str]:
        if (
            self.component is None
            or self.component.project_id is None
            or self.component.project.workspace_id is None
        ):
            return []
        return list(
            self._get_auth_args(
                self.component.repo, workspace=self.component.project.workspace
            )
        )

    @classmethod
    def get_remote_branch(cls, repo: str):
        if not repo:
            return super().get_remote_branch(repo)

        cls.validate_remote_url(repo)
        try:
            result = cls._popen(
                [*cls._get_auth_args(repo), "ls-remote", "--symref", "--", repo, "HEAD"]
            )
        except RepositoryError:
            report_error("Listing remote branch")
            return super().get_remote_branch(repo)

        for line in result.splitlines():
            if not line.startswith("ref: "):
                continue
            return line.split("\t")[0].split("refs/heads/")[1]

        report_error("Could not figure out remote branch", message=True)
        raise RepositoryError(0, "Could not figure out remote branch")

    def _resolve_github_app_token(self, hostname: str) -> dict[str, str] | None:
        """Resolve an installation access token for the parsed repository."""
        if (
            self.component is None
            or self.component.project_id is None
            or self.component.project.workspace_id is None
        ):
            return None

        # ``hostname`` arrives as the API host (``api.github.com`` for
        # github.com). Map it back to the user-facing hostname used by
        # installations.
        raw_hostname = "github.com" if hostname == "api.github.com" else hostname

        _, _, _, _, owner, slug = self.parse_repo_url()
        full_name = f"{owner}/{slug}"
        workspace = self.component.project.workspace
        installation = GitHubInstallation.objects.get_for_repo(
            raw_hostname, full_name, workspace=workspace
        )
        if installation is None:
            return None
        try:
            token = installation.get_access_token()
        except GitHubAppNotConfiguredError:
            return None
        return {
            "username": "x-access-token",
            "token": token,
            "github_app": "1",
        }

    def get_credentials_by_hostname(self, hostname: str) -> dict[str, str]:
        app_creds = self._resolve_github_app_token(hostname)
        if app_creds is None:
            raise RepositoryError(
                0, f"No Weblate GitHub app installation available for {hostname}"
            )
        return app_creds
