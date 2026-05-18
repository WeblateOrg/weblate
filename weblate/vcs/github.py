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
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import jwt
import requests
from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

# Installation tokens are valid for 1 hour; cache for 50 minutes
TOKEN_CACHE_TTL = 50 * 60
# GitHub enforces a 10-minute maximum on App JWTs
JWT_MAX_LIFETIME = 9 * 60


def normalize_github_app_hostname(hostname: str) -> str:
    """Normalize GitHub hostnames to the web host used by installations."""
    normalized = hostname.strip().lower()
    if normalized == "api.github.com":
        return "github.com"
    return normalized


def get_github_app_configurations() -> dict[str, dict[str, str]]:
    """Return configured Weblate GitHub app settings keyed by normalized hostname."""
    raw_configs = getattr(settings, "GITHUB_APP_CREDENTIALS", {})
    if raw_configs:
        configs = {}
        for hostname, config in raw_configs.items():
            normalized = normalize_github_app_hostname(hostname)
            configs[normalized] = {
                "app_id": str(config.get("app_id", "")).strip(),
                "app_slug": str(config.get("app_slug", "")).strip(),
                "private_key": str(config.get("private_key", "")).strip(),
                "webhook_secret": str(config.get("webhook_secret", "")).strip(),
                "hostname": normalized,
            }
        return configs

    app_hostname = normalize_github_app_hostname(
        getattr(settings, "GITHUB_APP_HOSTNAME", "github.com")
    )
    app_id = str(getattr(settings, "GITHUB_APP_ID", "")).strip()
    app_slug = str(getattr(settings, "GITHUB_APP_SLUG", "")).strip()
    private_key = str(getattr(settings, "GITHUB_APP_PRIVATE_KEY", "")).strip()
    webhook_secret = str(getattr(settings, "GITHUB_APP_WEBHOOK_SECRET", "")).strip()
    if not app_id or not app_slug or not private_key:
        return {}

    return {
        app_hostname: {
            "app_id": app_id,
            "app_slug": app_slug,
            "private_key": private_key,
            "webhook_secret": webhook_secret,
            "hostname": app_hostname,
        }
    }


def get_github_app_settings(hostname: str | None = None) -> dict[str, str] | None:
    """Return the configured Weblate GitHub app settings for one host, if available."""
    configs = get_github_app_configurations()
    if hostname is not None:
        return configs.get(normalize_github_app_hostname(hostname))
    if len(configs) == 1:
        return next(iter(configs.values()))
    return None


def github_app_is_configured(hostname: str | None = None) -> bool:
    """Return whether the Weblate GitHub app is configured for installs on the host."""
    if hostname is not None:
        config = get_github_app_settings(hostname)
        return config is not None and bool(config["webhook_secret"])
    return any(
        config["webhook_secret"] for config in get_github_app_configurations().values()
    )


def get_github_app_install_url(state: str, hostname: str | None = None) -> str:
    """Build the Weblate GitHub app installation URL for the configured host."""
    config = get_github_app_settings(hostname)
    if config is None:
        msg = "Weblate GitHub app is not configured"
        raise ValueError(msg)

    return (
        f"https://{config['hostname']}/apps/{config['app_slug']}"
        f"/installations/new?{urlencode({'state': state})}"
    )


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
                "full_name": repo["full_name"],
                "clone_url": repo["clone_url"],
                "ssh_url": repo["ssh_url"],
                "html_url": repo["html_url"],
                "default_branch": repo.get("default_branch", "main"),
                "private": repo.get("private", False),
                "description": repo.get("description", ""),
            }
            for repo in data.get("repositories", [])
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


class GitHubInstallationManager(models.Manager["GitHubInstallation"]):
    def get_for_installation(
        self, hostname: str, installation_id: str | int
    ) -> GitHubInstallation | None:
        """Return one installation by host and installation ID."""
        hostname = normalize_github_app_hostname(hostname)
        return self.filter(
            hostname=hostname,
            installation_id=str(installation_id),
        ).first()

    def get_for_repo(self, hostname: str, full_name: str) -> GitHubInstallation | None:
        """Return an enabled installation on ``hostname`` that owns ``full_name``."""
        hostname = normalize_github_app_hostname(hostname)
        for installation in self.filter(hostname=hostname, enabled=True).order_by(
            "-created"
        ):
            if installation.has_repository(full_name):
                return installation
        return None

    def upsert_from_data(
        self,
        hostname: str,
        installation_id: str | int,
        data: dict,
        *,
        created_by=None,
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
        if created_by is not None:
            defaults["created_by"] = created_by

        installation, _created = self.update_or_create(
            hostname=hostname,
            installation_id=installation_id,
            defaults=defaults,
        )
        return installation

    def sync_from_api(
        self,
        hostname: str,
        installation_id: str | int,
        *,
        created_by=None,
        enabled: bool = True,
    ) -> GitHubInstallation:
        """Fetch installation metadata from GitHub and persist it."""
        hostname = normalize_github_app_hostname(hostname)
        config = get_github_app_settings(hostname)
        if config is None:
            msg = f"Weblate GitHub app is not configured for {hostname}"
            raise GitHubAppNotConfiguredError(msg)

        data = get_app_installation(
            config["app_id"],
            config["private_key"],
            installation_id,
            hostname,
        )
        return self.upsert_from_data(
            hostname,
            installation_id,
            data,
            created_by=created_by,
            enabled=enabled,
        )


class GitHubInstallation(models.Model):
    """
    Tracks a connected GitHub account for the Weblate GitHub app.

    Per-account rows store only what is unique to one install: the
    GitHub-issued ``installation_id``, the account it was installed on, and a
    cached repository list. App-level credentials (App ID, private key,
    webhook secret) live in ``settings.GITHUB_APP_CREDENTIALS`` and are
    looked up by hostname so a single configured App can serve every
    connected account on that host.
    """

    installation_id = models.CharField(
        max_length=50,
        verbose_name=gettext_lazy("GitHub installation ID"),
    )

    target_type = models.CharField(
        max_length=20,
        verbose_name=gettext_lazy("Target type"),
        help_text=gettext_lazy("Organization or User"),
    )
    target_login = models.CharField(
        max_length=255,
        verbose_name=gettext_lazy("Target login"),
        help_text=gettext_lazy("GitHub organization or user login"),
    )

    created_by = models.ForeignKey(
        "weblate_auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    hostname = models.CharField(
        max_length=255,
        default="github.com",
        verbose_name=gettext_lazy("GitHub hostname"),
        help_text=gettext_lazy(
            "github.com for GitHub.com, or your GitHub Enterprise hostname"
        ),
    )

    enabled = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    repositories = models.JSONField(
        default=list,
        blank=True,
        verbose_name=gettext_lazy("Available repositories"),
    )
    repositories_updated = models.DateTimeField(null=True, blank=True)

    objects = GitHubInstallationManager()

    class Meta:
        verbose_name = gettext_lazy("connected GitHub account")
        verbose_name_plural = gettext_lazy("connected GitHub accounts")
        unique_together = (("hostname", "installation_id"),)

    def __str__(self) -> str:
        return f"{self.target_login} ({self.hostname}/{self.installation_id})"

    def save(self, *args, **kwargs) -> None:
        self.hostname = normalize_github_app_hostname(self.hostname)
        super().save(*args, **kwargs)

    @property
    def api_base(self) -> str:
        return get_github_api_base(self.hostname)

    def _require_app_settings(self) -> dict[str, str]:
        config = get_github_app_settings(self.hostname)
        if config is None:
            msg = f"Weblate GitHub app is not configured for {self.hostname}"
            raise GitHubAppNotConfiguredError(msg)
        return config

    @property
    def app_id(self) -> str:
        config = get_github_app_settings(self.hostname)
        return config["app_id"] if config is not None else ""

    def get_access_token(self) -> str:
        config = self._require_app_settings()
        return get_installation_token(
            config["app_id"],
            config["private_key"],
            self.installation_id,
            self.hostname,
        )

    def refresh_repositories(self) -> list[dict]:
        config = self._require_app_settings()
        repos = get_app_repositories(
            config["app_id"],
            config["private_key"],
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
        return config["webhook_secret"]
