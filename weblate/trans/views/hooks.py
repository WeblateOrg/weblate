# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from functools import partial
from typing import TYPE_CHECKING, ClassVar, NotRequired, TypedDict, cast
from urllib.parse import quote, urlparse

from django.conf import settings
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import parsers, serializers
from rest_framework.exceptions import (
    APIException,
    MethodNotAllowed,
    NotFound,
    ParseError,
    PermissionDenied,
    ValidationError,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from weblate.api.serializers import MultiFieldHyperlinkedIdentityField
from weblate.auth.models import User
from weblate.logger import LOGGER
from weblate.trans.actions import ActionEvents
from weblate.trans.hooks.fallback import (
    get_fallback_components,
    normalize_full_name,
    repo_connection,
    repo_is_scp_like,
    repo_path,
    validate_full_name,
)
from weblate.trans.hooks.matching import HOOK_MATCH_EXACT, HOOK_MATCH_FALLBACK
from weblate.trans.models import Component
from weblate.trans.tasks import perform_update
from weblate.utils.errors import report_error
from weblate.vcs.github import (
    GitHubAppCredentials,
    GitHubInstallation,
    get_github_app_settings,
    verify_webhook_signature,
)
from weblate.vcs.models import InstallationProvider, PendingInstallation

if TYPE_CHECKING:
    import uuid
    from collections.abc import Generator

    from django.db.models import QuerySet
    from django_stubs_ext import StrOrPromise

BITBUCKET_GIT_REPOS = (
    "ssh://git@{server}/{full_name}.git",
    "ssh://git@{server}/{full_name}",
    "git@{server}:{full_name}.git",
    "git@{server}:{full_name}",
    "https://{server}/{full_name}.git",
    "https://{server}/{full_name}",
)

BITBUCKET_HG_REPOS = (
    "https://{server}/{full_name}",
    "ssh://hg@{server}/{full_name}",
    "hg::ssh://hg@{server}/{full_name}",
    "hg::https://{server}/{full_name}",
)

GITHUB_REPOS = (
    "git://github.com/%(owner)s/%(slug)s.git",
    "git://github.com/%(owner)s/%(slug)s",
    "https://github.com/%(owner)s/%(slug)s.git",
    "https://github.com/%(owner)s/%(slug)s",
    "git@github.com:%(owner)s/%(slug)s.git",
    "git@github.com:%(owner)s/%(slug)s",
)

PAGURE_REPOS = (
    "https://{server}/{project}",
    "https://{server}/{project}.git",
    "ssh://git@{server}/{project}",
    "ssh://git@{server}/{project}.git",
)

AZURE_REPOS = (
    "https://dev.azure.com/{organization}/{project}/_git/{repository}",
    "https://dev.azure.com/{organization}/{projectId}/_git/{repositoryId}",
    "git@ssh.dev.azure.com:v3/{organization}/{project}/{repository}",
    "https://{organization}.visualstudio.com/{project}/_git/{repository}",
    "{organization}@vs-ssh.visualstudio.com:v3/{organization}/{project}/{repository}",
)

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type JSONDict = dict[str, JSONValue]
type JSONMapping = Mapping[str, JSONValue]
type FormData = Mapping[str, str | bytes]


class HandlerResponse(TypedDict):
    service_long_name: str
    repo_url: str
    repos: list[str]
    branch: str | None
    full_name: str | None
    exact_match: NotRequired[bool]
    project_ids: NotRequired[list[int]]
    component_vcs: NotRequired[str]
    exclude_component_vcs: NotRequired[list[str]]


HandlerType = Callable[[dict, Request | None], HandlerResponse | None]


HOOK_HANDLERS: dict[str, HandlerType] = {}


class HookPayloadError(Exception):
    """Raised for malformed but expected webhook payload problems."""


def exact_repositories_filter(repos: list[str], *, include_variants: bool = True) -> Q:
    """Build a filter for exact repository URL matching."""
    spfilter = Q(repo__in=repos)
    if not include_variants:
        return spfilter
    for repo in repos:
        # We need to match also URLs which include username and password
        if repo.startswith("http://"):
            spfilter |= Q(repo__startswith="http://") & Q(repo__endswith=f"@{repo[7:]}")
        elif repo.startswith("https://"):
            spfilter |= Q(repo__startswith="https://") & Q(
                repo__endswith=f"@{repo[8:]}"
            )
        # Include URLs with trailing slash
        spfilter |= Q(repo=f"{repo}/")
    return spfilter


def inexact_hook_alert_details(details: Mapping[str, object]) -> dict[str, str]:
    """Extract details stored with inexact hook match alerts."""
    return {
        "service_long_name": str(details.get("service_long_name") or ""),
        "repo_url": str(details.get("repo_url") or ""),
        "branch": str(details.get("branch") or ""),
        "full_name": str(details.get("full_name") or ""),
    }


def get_hook_components(
    repos: list[str],
    full_name: str | None,
    *,
    exact_match: bool = False,
    project_ids: list[int] | None = None,
    component_vcs: str | None = None,
    exclude_component_vcs: list[str] | None = None,
) -> tuple[QuerySet[Component], str]:
    """Return hook target components and repository match method."""
    components = Component.objects.all()
    if project_ids is not None:
        components = components.filter(project_id__in=project_ids)
    if component_vcs is not None:
        components = components.filter(vcs=component_vcs)
    if exclude_component_vcs is not None:
        components = components.exclude(vcs__in=exclude_component_vcs)

    repo_components = components.filter(
        exact_repositories_filter(repos, include_variants=not exact_match)
    )
    if exact_match:
        return repo_components, HOOK_MATCH_EXACT
    if repo_components.exists():
        return repo_components, HOOK_MATCH_EXACT

    fallback_components = get_fallback_components(components, repos, full_name)
    if fallback_components is None:
        return repo_components, HOOK_MATCH_EXACT

    return fallback_components, HOOK_MATCH_FALLBACK


def url_host(hostname: str) -> str:
    """Format a hostname for use in a URL."""
    if ":" in hostname and not hostname.startswith("["):
        return f"[{hostname}]"
    return hostname


def gitea_like_repo_variants(
    clone_url: str, ssh_url: str, html_url: str, full_name: str | None
) -> list[str]:
    """Return exact repository URL variants for Gitea-like payloads."""
    payload_repos = [clone_url, ssh_url, html_url]
    repos = payload_repos.copy()
    normalized_full_name = normalize_full_name(full_name)
    if normalized_full_name is None:
        return repos

    repo_paths = (normalized_full_name, f"{normalized_full_name}.git")
    for repo in payload_repos:
        hostname, username, port, is_ssh_url = repo_connection(repo)
        if (
            hostname is None
            or username is None
            or not (is_ssh_url or repo_is_scp_like(repo))
            or repo_path(repo) != normalized_full_name
        ):
            continue
        formatted_host = url_host(hostname)
        port_part = f":{port}" if port is not None else ""
        repos.extend(
            f"ssh://{username}@{formatted_host}{port_part}/{repo_path}"
            for repo_path in repo_paths
        )
        if port in {None, 22} and ":" not in hostname:
            repos.extend(
                f"{username}@{hostname}:{repo_path}" for repo_path in repo_paths
            )

    return list(dict.fromkeys(repos))


def normalize_branch_ref(ref: str | None) -> str:
    """Normalize a Git ref to a branch name."""
    if not isinstance(ref, str) or not ref:
        msg = "Missing ref in payload"
        raise HookPayloadError(msg)
    return re.sub(r"^refs/heads/", "", ref)


def require_mapping(value: JSONValue, field_name: str) -> JSONMapping:
    """Validate that the payload field is a mapping."""
    if not isinstance(value, Mapping):
        msg = f"Invalid {field_name} in payload"
        raise HookPayloadError(msg)
    return value


def require_string(value: JSONValue, field_name: str) -> str:
    """Validate that the payload field is a string."""
    if not isinstance(value, str):
        msg = f"Invalid {field_name} in payload"
        raise HookPayloadError(msg)
    return value


def optional_string(value: JSONValue, field_name: str) -> str | None:
    """Validate that the payload field is a string or null."""
    if value is None:
        return None
    return require_string(value, field_name)


def register_hook(handler: HandlerType) -> HandlerType:
    """Register hook handler."""
    name = handler.__name__.split("_")[0]
    HOOK_HANDLERS[name] = handler
    return handler


class HookMatchDict(TypedDict):
    repository_matches: int
    branch_matches: int
    enabled_hook_matches: int


class HookMatchSerializer(serializers.Serializer):
    repository_matches = serializers.IntegerField()
    branch_matches = serializers.IntegerField()
    enabled_hook_matches = serializers.IntegerField()


class HookResponseSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)
    status = serializers.ChoiceField(choices=["success", "failure"])
    match_status = HookMatchSerializer(required=False)
    updated_components = MultiFieldHyperlinkedIdentityField(
        view_name="api:component-detail",
        lookup_field=("project__slug", "slug"),
        many=True,
        read_only=True,
        required=False,
    )


class HookRequestSerializer(serializers.Serializer):
    """Native webhook payload from the notifying service."""

    default_error_messages: ClassVar[dict[str, StrOrPromise]] = {
        "invalid": "Invalid data in json payload!",
    }

    def to_internal_value(self, data: object) -> JSONDict:
        if not isinstance(data, Mapping) or not data:
            raise serializers.ValidationError(
                {api_settings.NON_FIELD_ERRORS_KEY: [self.error_messages["invalid"]]}
            )
        return cast("JSONDict", dict(data))


class HookPayloadSerializer(serializers.Serializer):
    payload = serializers.JSONField()


def extract_payload(request_data: FormData) -> JSONValue:
    serializer = HookPayloadSerializer(data=request_data)
    if not serializer.is_valid():
        detail = serializer.errors.get(
            "payload",
            serializer.errors.get(
                api_settings.NON_FIELD_ERRORS_KEY,
                ["Invalid payload parameter!"],
            ),
        )[0]
        raise ParseError(str(detail))
    return cast("JSONValue", serializer.validated_data["payload"])


def extract_request_data(
    content_type: str | None,
    request_data: JSONValue | FormData,
) -> JSONValue:
    media_type = (
        content_type.partition(";")[0].strip().lower() if content_type else None
    )
    if media_type == parsers.JSONParser.media_type:
        return cast("JSONValue", request_data)
    return extract_payload(cast("FormData", request_data))


def bitbucket_extract_changes(data: dict) -> list[dict]:
    if "changes" in data:
        return data["changes"]
    if "push" in data:
        return data["push"]["changes"]
    if "commits" in data:
        return data["commits"]
    return []


def bitbucket_extract_branch(data: dict) -> str | None:
    changes = bitbucket_extract_changes(data)
    if changes:
        last = changes[-1]
        if "branch" in last:
            return last["branch"]
        if last.get("new"):
            return changes[-1]["new"]["name"]
        if last.get("old"):
            return changes[-1]["old"]["name"]
        if "ref" in last:
            return last["ref"]["displayId"]
    # Pullrequest merged action
    if "pullrequest" in data:
        return data["pullrequest"]["destination"]["branch"]["name"]
    return None


def bitbucket_extract_full_name(repository: dict) -> str:
    if "full_name" in repository:
        return repository["full_name"]
    if "fullName" in repository:
        return repository["fullName"]
    if "owner" in repository and "slug" in repository:
        return f"{repository['owner']}/{repository['slug']}"
    if "project" in repository and "slug" in repository:
        return f"{repository['project']['key']}/{repository['slug']}"
    msg = "Could not determine repository full name"
    raise ValueError(msg)


def bitbucket_extract_repo_url(data: dict, repository: dict) -> str:
    if "links" in repository:
        if "html" in repository["links"]:
            return repository["links"]["html"]["href"]
        return repository["links"]["self"][0]["href"]
    if "canon_url" in data:
        return f"{data['canon_url']}{repository['absolute_url']}"
    msg = "Could not determine repository URL"
    raise ValueError(msg)


@register_hook
def bitbucket_hook_helper(data, request: Request | None) -> HandlerResponse | None:
    """Parse service hook from Bitbucket."""
    # Bitbucket ping event
    if request and request.headers.get("x-event-key") not in {
        "repo:push",
        "repo:refs_changed",
        "pullrequest:fulfilled",
        "pr:merged",
    }:
        return None

    if "pullRequest" in data:
        # The pr:merged event
        repository = data["pullRequest"]["fromRef"]["repository"]
    else:
        repository = data["repository"]
    full_name = bitbucket_extract_full_name(repository)
    repo_url = bitbucket_extract_repo_url(data, repository)

    # Extract repository links
    if "links" in repository and "clone" in repository["links"]:
        repos = [val["href"] for val in repository["links"]["clone"]]
    else:
        repo_servers = {"bitbucket.org", urlparse(repo_url).hostname}
        repos = []
        templates: tuple[str, ...]
        if "scm" not in data["repository"]:
            templates = BITBUCKET_GIT_REPOS + BITBUCKET_HG_REPOS
        elif data["repository"]["scm"] == "hg":
            templates = BITBUCKET_HG_REPOS
        else:
            templates = BITBUCKET_GIT_REPOS

        # Construct possible repository URLs if full name is valid
        # We will fail with ValueError later if not
        if validate_full_name(full_name):
            for repo in templates:
                repos.extend(
                    repo.format(full_name=full_name, server=server)
                    for server in repo_servers
                )

    if not repos:
        LOGGER.error("unsupported repository: %s", repr(data["repository"]))
        msg = "unsupported repository"
        raise ValueError(msg)

    return {
        "service_long_name": "Bitbucket",
        "repo_url": repo_url,
        "repos": repos,
        "branch": bitbucket_extract_branch(data),
        "full_name": full_name,
    }


def _lookup_github_installation(data: dict, hostname: str | None = None):
    """Return the GitHubInstallation referenced by the webhook payload, if any."""
    installation_id = (data.get("installation") or {}).get("id")
    if not installation_id:
        return None

    if hostname is not None:
        return GitHubInstallation.objects.get_for_installation(
            hostname, installation_id
        )

    matches = list(
        GitHubInstallation.objects.filter(installation_id=str(installation_id))[:2]
    )
    if len(matches) == 1:
        return matches[0]
    return None


def _refresh_github_installations(installations) -> None:
    """Refresh repositories once and copy the result to matching project rows."""
    if not installations:
        return
    try:
        repositories = installations[0].refresh_repositories()
    except Exception:
        report_error("Failed to refresh connected GitHub account repositories")
        return

    repositories_updated = installations[0].repositories_updated
    for installation in installations[1:]:
        installation.repositories = repositories
        installation.repositories_updated = repositories_updated
        installation.save(update_fields=["repositories", "repositories_updated"])


def _github_http_host(hostname: str) -> str:
    """Return the hostname used in GitHub repository URLs."""
    return "github.com" if hostname == "github.com" else hostname


def _github_repository_entry(repo: Mapping[str, object], hostname: str) -> dict:
    """Return cached repository metadata from a GitHub webhook repository object."""
    full_name = cast("str", repo["full_name"])
    http_host = _github_http_host(hostname)
    return {
        "name": repo.get("name") or full_name.rsplit("/", 1)[-1],
        "full_name": full_name,
        "clone_url": repo.get("clone_url") or f"https://{http_host}/{full_name}.git",
        "ssh_url": repo.get("ssh_url") or f"git@{http_host}:{full_name}.git",
        "html_url": repo.get("html_url") or f"https://{http_host}/{full_name}",
        "default_branch": repo.get("default_branch", "main"),
        "private": repo.get("private", False),
        "description": repo.get("description", ""),
    }


def _github_repository_entries(repositories, hostname: str) -> list[dict]:
    return [_github_repository_entry(repo, hostname) for repo in repositories or []]


def _store_pending_github_installation_event(
    data: dict, hostname: str, installation_id: str
) -> None:
    """Persist a signed installation event until setup validates a workspace."""
    PendingInstallation.objects.update_or_create(
        provider=InstallationProvider.GITHUB,
        hostname=hostname,
        installation_id=installation_id,
        defaults={"payload": data},
    )
    LOGGER.info(
        "Stored pending GitHub account %s/%s webhook until setup completes",
        hostname,
        installation_id,
    )


def apply_pending_github_installation_event(
    hostname: str, installation_id: str | int
) -> bool:
    """Apply a previously signed installation webhook to authorized workspace rows."""
    installation_id = str(installation_id)
    pending = PendingInstallation.objects.filter(
        provider=InstallationProvider.GITHUB,
        hostname=hostname,
        installation_id=installation_id,
    ).first()
    if pending is None:
        return False

    installation = GitHubInstallation.objects.get_for_installation(
        hostname, installation_id
    )
    _handle_github_installation_event(pending.payload, installation, hostname)
    pending.delete()
    return True


def _rename_github_repository(
    repo: dict,
    *,
    hostname: str,
    old_login: str,
    new_login: str,
) -> tuple[dict, str | None, str | None]:
    """Return repository metadata updated after a GitHub account rename."""
    full_name = repo.get("full_name")
    old_prefix = f"{old_login}/"
    if not isinstance(full_name, str) or not full_name.startswith(old_prefix):
        return repo, None, None

    new_full_name = f"{new_login}/{full_name.removeprefix(old_prefix)}"
    http_host = _github_http_host(hostname)
    renamed = {**repo, "full_name": new_full_name}
    old_clone_url = repo.get("clone_url")
    new_clone_url = None
    if isinstance(old_clone_url, str):
        new_clone_url = f"https://{http_host}/{new_full_name}.git"
        renamed["clone_url"] = new_clone_url
    if "ssh_url" in renamed:
        renamed["ssh_url"] = f"git@{http_host}:{new_full_name}.git"
    if "html_url" in renamed:
        renamed["html_url"] = f"https://{http_host}/{new_full_name}"
    return (
        renamed,
        old_clone_url if isinstance(old_clone_url, str) else None,
        new_clone_url,
    )


def _get_github_installation_old_login(data: dict, installation) -> str:
    """Return the previous GitHub login from the payload or stored row."""
    changes = data.get("changes")
    if isinstance(changes, Mapping):
        login = changes.get("login")
        if isinstance(login, Mapping):
            old_login = login.get("from")
            if isinstance(old_login, str):
                return old_login
    return installation.target_login if installation is not None else ""


def _handle_github_installation_target_event(
    data: dict, installation, hostname: str | None
) -> None:
    """Handle GitHub account or organization rename events."""
    if data.get("action") != "renamed":
        return

    payload = data.get("installation") or {}
    installation_id = str(payload.get("id", ""))
    new_login = data["account"]["login"]
    if not installation_id or not new_login:
        return

    hostname = installation.hostname if installation is not None else hostname
    if hostname is None:
        return

    old_login = _get_github_installation_old_login(data, installation)
    if not old_login:
        return

    installations = list(
        GitHubInstallation.objects.filter_for_installation(hostname, installation_id)
    )
    if not installations:
        return

    for item in installations:
        repo_updates = []
        repositories = []
        for repo in item.repositories:
            renamed, old_clone_url, new_clone_url = _rename_github_repository(
                repo,
                hostname=item.hostname,
                old_login=old_login,
                new_login=new_login,
            )
            repositories.append(renamed)
            if old_clone_url and new_clone_url:
                repo_updates.append((old_clone_url, new_clone_url))

        item.target_login = new_login
        item.repositories = repositories
        item.save(update_fields=["target_login", "repositories"])

        for old_clone_url, new_clone_url in repo_updates:
            Component.objects.filter(
                project__workspace_id=item.workspace_id,
                vcs="github-app",
                repo=old_clone_url,
            ).update(repo=new_clone_url, push="", push_branch="")

    LOGGER.info(
        "Connected GitHub account %s/%s renamed from %s to %s",
        hostname,
        installation_id,
        old_login,
        new_login,
    )


def _handle_github_installation_event(  # noqa: C901
    data: dict, installation, hostname: str | None
) -> None:
    """Handle ``installation`` and ``installation_repositories`` events."""
    action = data.get("action", "")
    payload = data.get("installation") or {}
    installation_id = str(payload.get("id", ""))
    if not installation_id:
        return

    config = get_github_app_settings(hostname) if hostname is not None else None
    hostname = (
        installation.hostname
        if installation is not None
        else config.hostname
        if config is not None
        else None
    )
    if hostname is None:
        return

    if action in {"deleted", "suspend"}:
        GitHubInstallation.objects.filter(
            hostname=hostname, installation_id=installation_id
        ).update(enabled=False)
        LOGGER.info(
            "Connected GitHub account %s/%s %s",
            hostname,
            installation_id,
            action,
        )
        return

    if action == "unsuspend":
        installations = list(
            GitHubInstallation.objects.filter_for_installation(
                hostname, installation_id
            )
        )
        if not installations:
            # Nothing to do until the setup flow binds the installation to a workspace.
            return
        for item in installations:
            item.enabled = True
            item.save(update_fields=["enabled"])
        if any(item.repositories for item in installations):
            _refresh_github_installations(installations)
        LOGGER.info(
            "Connected GitHub account %s/%s unsuspended",
            hostname,
            installation_id,
        )
        return

    if action in {"created", "new_permissions_accepted"}:
        installations = list(
            GitHubInstallation.objects.filter_for_installation(
                hostname, installation_id
            )
        )
        if not installations:
            _store_pending_github_installation_event(data, hostname, installation_id)
            return
        repositories = _github_repository_entries(data.get("repositories"), hostname)
        for item in installations:
            updated = GitHubInstallation.objects.upsert_from_data(
                hostname,
                installation_id,
                payload,
                workspace=item.workspace,
                enabled=True,
            )
            if repositories:
                updated.repositories = repositories
                updated.save(update_fields=["repositories"])
        if config is not None:
            _refresh_github_installations(
                list(
                    GitHubInstallation.objects.filter_for_installation(
                        hostname, installation_id
                    )
                )
            )
        PendingInstallation.objects.filter(
            provider=InstallationProvider.GITHUB,
            hostname=hostname,
            installation_id=installation_id,
        ).delete()
        LOGGER.info(
            "Connected GitHub account %s/%s synchronized",
            hostname,
            installation_id,
        )
        return

    if action in {"added", "removed"}:
        installations = list(
            GitHubInstallation.objects.filter_for_installation(
                hostname, installation_id
            )
        )
        if not installations:
            return
        removed_names = {
            repo["full_name"] for repo in data.get("repositories_removed") or []
        }
        for item in installations:
            repos = list(item.repositories)
            existing_names = {r.get("full_name") for r in repos}

            for repo in data.get("repositories_added") or []:
                entry = _github_repository_entry(repo, hostname)
                if entry["full_name"] in existing_names:
                    continue
                repos.append(entry)
                existing_names.add(entry["full_name"])

            if removed_names:
                repos = [r for r in repos if r.get("full_name") not in removed_names]

            item.repositories = repos
            item.save(update_fields=["repositories"])
        LOGGER.info(
            "Connected GitHub account %s/%s repositories updated: +%d -%d",
            hostname,
            installation_id,
            len(data.get("repositories_added") or []),
            len(data.get("repositories_removed") or []),
        )


def _github_push_hook_response(
    data: dict,
    *,
    repos: list[str] | None = None,
    exact_match: bool = False,
    project_ids: list[int] | None = None,
    component_vcs: str | None = None,
) -> HandlerResponse:
    # Parse owner, branch and repository name
    repository = require_mapping(data.get("repository"), "repository")
    o_data = require_mapping(repository.get("owner"), "repository.owner")
    owner = optional_string(o_data.get("login"), "repository.owner.login")
    if owner is None:
        owner = require_string(o_data.get("name"), "repository.owner.name")
    slug = require_string(repository.get("name"), "repository.name")
    repo_url = require_string(repository.get("url"), "repository.url")
    branch = normalize_branch_ref(data.get("ref"))

    params = {"owner": owner, "slug": slug}

    if repos is None and "clone_url" not in repository:
        # Construct possible repository URLs
        repos = [repo % params for repo in GITHUB_REPOS]
    elif repos is None:
        repos = []
        keys = ["clone_url", "git_url", "ssh_url", "svn_url", "html_url", "url"]
        for key in keys:
            url = optional_string(repository.get(key), f"repository.{key}")
            if not url:
                continue
            repos.append(url)
            if url.endswith(".git"):
                repos.append(url[:-4])

    response: HandlerResponse = {
        "service_long_name": "GitHub",
        "repo_url": repo_url,
        "repos": sorted(set(repos)),
        "branch": branch,
        "full_name": f"{owner}/{slug}",
    }
    if exact_match:
        response["exact_match"] = True
    if project_ids is not None:
        response["project_ids"] = project_ids
    if component_vcs is not None:
        response["component_vcs"] = component_vcs
    return response


@register_hook
def github_hook_helper(data: dict, request: Request | None) -> HandlerResponse | None:
    """Parse generic repository hooks from GitHub."""
    if request:
        event = request.headers.get("x-github-event", "")
        if data.get("installation"):
            msg = "GitHub App webhooks must use the per-integration hook URL"
            raise PermissionDenied(msg)
        if event != "push":
            return None

    response = _github_push_hook_response(data)
    response["exclude_component_vcs"] = ["github-app"]
    return response


def github_integration_hook_helper(
    data: dict, request: Request | None, *, integration_token: str
) -> HandlerResponse | None:
    """
    Parse a signed webhook delivered to a single GitHub App integration.

    The integration is identified by the ``integration_token`` embedded in the
    hook URL.
    """
    if request is None:
        msg = "GitHub App webhooks require a request"
        raise PermissionDenied(msg)

    try:
        config = GitHubAppCredentials.objects.get(webhook_token=integration_token)
    except GitHubAppCredentials.DoesNotExist:
        LOGGER.warning(
            "Rejected GitHub App webhook for unknown integration token %s",
            integration_token,
        )
        msg = "Unknown GitHub App integration"
        raise PermissionDenied(msg) from None

    signature = request.headers.get("x-hub-signature-256", "")
    if not verify_webhook_signature(request.body, signature, config.webhook_secret):
        LOGGER.warning(
            "Rejected GitHub App webhook with invalid signature for %s",
            config.hostname,
        )
        msg = "Invalid webhook signature"
        raise PermissionDenied(msg)

    hostname = config.hostname
    event = request.headers.get("x-github-event", "")
    if event in {"installation", "installation_repositories"}:
        installation = _lookup_github_installation(data, hostname)
        _handle_github_installation_event(data, installation, hostname)
        return None
    if event == "installation_target":
        installation = _lookup_github_installation(data, hostname)
        _handle_github_installation_target_event(data, installation, hostname)
        return None
    if event != "push":
        return None

    repository = data["repository"]
    repo_url = repository.get("clone_url")
    if not repo_url:
        msg = "Missing repository clone URL in GitHub App webhook"
        raise HookPayloadError(msg)

    installation_id = str((data.get("installation") or {}).get("id", ""))
    project_ids: list[int] = []
    if installation_id:
        workspace_ids = list(
            GitHubInstallation.objects.filter_for_installation(
                hostname, installation_id
            )
            .filter(enabled=True)
            .values_list("workspace_id", flat=True)
            .distinct()
        )
        if workspace_ids:
            from weblate.trans.models import Project  # noqa: PLC0415

            project_ids = list(
                Project.objects.filter(workspace_id__in=workspace_ids)
                .values_list("pk", flat=True)
                .distinct()
            )

    return _github_push_hook_response(
        data,
        repos=[repo_url],
        exact_match=True,
        project_ids=project_ids,
        component_vcs="github-app",
    )


def _gitea_like_hook_helper(
    data: dict, service_long_name: str
) -> HandlerResponse | None:
    repository = require_mapping(data.get("repository"), "repository")
    html_url = require_string(repository.get("html_url"), "repository.html_url")
    clone_url = require_string(repository.get("clone_url"), "repository.clone_url")
    ssh_url = require_string(repository.get("ssh_url"), "repository.ssh_url")
    full_name = optional_string(repository.get("full_name"), "repository.full_name")
    return {
        "service_long_name": service_long_name,
        "repo_url": html_url,
        "repos": gitea_like_repo_variants(clone_url, ssh_url, html_url, full_name),
        "branch": normalize_branch_ref(data.get("ref")),
        "full_name": full_name,
    }


@register_hook
def gitea_hook_helper(data: dict, request: Request | None) -> HandlerResponse | None:
    return _gitea_like_hook_helper(data, "Gitea")


@register_hook
def forgejo_hook_helper(data: dict, request: Request | None) -> HandlerResponse | None:
    return _gitea_like_hook_helper(data, "Forgejo")


@register_hook
def gitee_hook_helper(data: dict, request: Request | None) -> HandlerResponse | None:
    return {
        "service_long_name": "Gitee",
        "repo_url": data["repository"]["html_url"],
        "repos": [
            data["repository"]["git_http_url"],
            data["repository"]["git_ssh_url"],
            data["repository"]["git_url"],
            data["repository"]["ssh_url"],
            data["repository"]["html_url"],
        ],
        "branch": normalize_branch_ref(data.get("ref")),
        "full_name": data["repository"]["path_with_namespace"],
    }


@register_hook
def gitlab_hook_helper(data: dict, request: Request | None) -> HandlerResponse | None:
    """Parse hook from GitLab."""
    # Ignore non known events
    if "ref" not in data:
        return None
    ssh_url = data["repository"]["url"]
    http_url = f"{data['repository']['homepage']}.git"
    branch = normalize_branch_ref(data.get("ref"))

    # Construct possible repository URLs
    repos = [
        ssh_url,
        http_url,
        data["repository"]["git_http_url"],
        data["repository"]["git_ssh_url"],
        data["repository"]["homepage"],
    ]

    return {
        "service_long_name": "GitLab",
        "repo_url": data["repository"]["homepage"],
        "repos": repos,
        "branch": branch,
        "full_name": data["project"]["path_with_namespace"],
    }


@register_hook
def pagure_hook_helper(data: dict, request: Request | None) -> HandlerResponse | None:
    """Parse hook from Pagure."""
    # Ignore non known events
    if "msg" not in data or data.get("topic") != "git.receive":
        return None

    server = urlparse(data["msg"]["pagure_instance"]).hostname
    project = data["msg"]["project_fullname"]

    repos = [repo.format(server=server, project=project) for repo in PAGURE_REPOS]

    return {
        "service_long_name": "Pagure",
        "repo_url": repos[0],
        "repos": repos,
        "branch": data["msg"]["branch"],
        "full_name": project,
    }


def expand_quoted(name: str) -> Generator[str]:
    yield name
    quoted = quote(name)
    if quoted != name:
        yield quoted


@register_hook
def azure_hook_helper(data: dict, request: Request | None) -> HandlerResponse | None:
    if data.get("eventType") != "git.push":
        return None

    http_url = data["resource"]["repository"]["remoteUrl"]
    branch = re.sub(r"^refs/heads/", "", data["resource"]["refUpdates"][0]["name"])
    project = data["resource"]["repository"]["project"]["name"]
    projectid = data["resource"]["repository"]["project"]["id"]
    repository = data["resource"]["repository"]["name"]
    repositoryid = data["resource"]["repository"]["id"]

    match = re.match(
        r"^https?:\/\/dev\.azure\.com\/"
        r"(?P<organization>[a-zA-Z0-9]+[a-zA-Z0-9-]*[a-zA-Z0-9]*)",
        http_url,
    )

    # Fallback to support old url structure {organization}.visualstudio.com
    if match is None:
        match = re.match(
            r"^https?:\/\/"
            r"(?P<organization>[a-zA-Z0-9]+[a-zA-Z0-9-]*[a-zA-Z0-9]*)"
            r"\.visualstudio\.com",
            http_url,
        )
    organization = None

    if match is not None:
        organization = match.group("organization")

    if organization is not None:
        repos = [
            repo.format(
                organization=organization,
                project=e_project,
                projectId=projectid,
                repository=e_repository,
                repositoryId=repositoryid,
            )
            for repo in AZURE_REPOS
            for e_project in expand_quoted(project)
            for e_repository in expand_quoted(repository)
        ]
    else:
        repos = [http_url]

    return {
        "service_long_name": "Azure",
        "repo_url": http_url,
        "repos": repos,
        "branch": branch,
        # Using just a repository name will avoid using endswith matching here
        "full_name": repository,
    }


class BaseHookView(APIView):
    # ruff: ignore[mutable-class-default]
    authentication_classes = []
    # ruff: ignore[mutable-class-default]
    permission_classes = [AllowAny]
    # ruff: ignore[mutable-class-default]
    throttle_classes = []
    # ruff: ignore[mutable-class-default]
    http_method_names = ["post"]
    parser_classes = (
        parsers.JSONParser,
        parsers.MultiPartParser,
        parsers.FormParser,
    )
    default_exclude_component_vcs: tuple[str, ...] = ()

    def hook_response(
        self,
        response: str = "Update triggered",
        status: int = 200,
        match_status: HookMatchDict | None = None,
        updated_components: list[Component] | None = None,
    ) -> Response:
        """Create a hook response."""
        serializer = HookResponseSerializer(
            {
                "status": "success" if status in {200, 201} else "failure",
                "message": response,
                "match_status": match_status,
                "updated_components": updated_components,
            },
            context={"request": self.request},
        )
        return Response(serializer.data, status=status)

    def run_hook(
        self, request: Request, hook_helper: HandlerType, service: str
    ) -> Response:
        """Validate the payload, dispatch to ``hook_helper`` and trigger updates."""
        # We support only post methods
        if not settings.ENABLE_HOOKS:
            msg = "POST"
            raise MethodNotAllowed(msg)

        # Cache the raw request body before DRF's parser consumes the input
        # stream, so webhook signature verification can read the unparsed
        # bytes later (e.g. in :func:`github_integration_hook_helper`).
        _ = request.body

        request_data = extract_request_data(request.content_type, request.data)
        request_serializer = HookRequestSerializer(data=request_data)
        if not request_serializer.is_valid():
            detail = request_serializer.errors.get(
                api_settings.NON_FIELD_ERRORS_KEY,
                ["Invalid data in json payload!"],
            )[0]
            raise ValidationError(str(detail))
        data = cast("dict[str, object]", request_serializer.validated_data)

        # Send the request data to the service handler.
        try:
            service_data = hook_helper(data, request)
        except HookPayloadError as exc:
            msg = f"Invalid data in json payload: {exc}"
            raise ValidationError(msg) from exc
        except APIException:
            # Auth/permission errors raised by hook handlers (e.g. invalid
            # webhook signature) must surface as their original status code.
            raise
        except Exception as exc:
            report_error("Invalid service data")
            msg = "Invalid data in json payload!"
            raise ValidationError(msg) from exc

        # This happens on ping request upon installation
        if service_data is None:
            return self.hook_response("Hook working", status=201)

        if self.default_exclude_component_vcs and "component_vcs" not in service_data:
            service_data = {
                **service_data,
                "exclude_component_vcs": [
                    *service_data.get("exclude_component_vcs", []),
                    *(
                        vcs
                        for vcs in self.default_exclude_component_vcs
                        if vcs not in service_data.get("exclude_component_vcs", [])
                    ),
                ],
            }

        # Log data
        service_long_name = service_data["service_long_name"]
        repo_url = service_data["repo_url"]
        branch = service_data["branch"]
        full_name = service_data["full_name"]

        user = User.objects.get_or_create_bot(
            scope="webhook",
            name=service,
            verbose=f"{service_data['service_long_name']} webhook",
        )

        repo_components, match_method = get_hook_components(
            service_data["repos"],
            full_name,
            exact_match=service_data.get("exact_match", False),
            project_ids=service_data.get("project_ids"),
            component_vcs=service_data.get("component_vcs"),
            exclude_component_vcs=service_data.get("exclude_component_vcs"),
        )

        if branch is not None:
            all_components = repo_components.filter(branch=branch)
        else:
            all_components = repo_components

        all_components_count = all_components.count()
        repo_components_count = repo_components.count()
        enabled_components = all_components.filter(project__enable_hooks=True)

        LOGGER.info(
            "received %s notification on repository %s, URL %s, branch %s, "
            "%d matching components, %d to process, %d linked",
            service_long_name,
            full_name,
            repo_url,
            branch,
            all_components_count,
            len(enabled_components),
            Component.objects.filter(linked_component__in=enabled_components).count(),
        )

        # Trigger updates
        updated_components: list[Component] = []
        for obj in enabled_components:
            hook_details = service_data | {"match_method": match_method}
            updated_components.append(obj)
            LOGGER.info("%s notification will update %s", service_long_name, obj)
            obj.change_set.create(
                action=ActionEvents.HOOK, details=hook_details, user=user
            )
            if match_method == HOOK_MATCH_FALLBACK:
                obj.add_alert(
                    "InexactHookMatch", **inexact_hook_alert_details(hook_details)
                )
            else:
                obj.delete_alert("InexactHookMatch")
            perform_update.delay("Component", obj.pk, user_id=user.id)

        match_status = HookMatchDict(
            repository_matches=repo_components_count,
            branch_matches=all_components_count,
            enabled_hook_matches=len(enabled_components),
        )

        if not updated_components:
            return self.hook_response(
                "No matching repositories found!",
                status=202,
                match_status=match_status,
            )

        updated_component_slugs = [obj.full_slug for obj in updated_components]

        return self.hook_response(
            f"Update triggered: {', '.join(updated_component_slugs)}",
            match_status=match_status,
            updated_components=updated_components,
        )


# ServiceHookView is defined after all @register_hook calls so the OpenAPI
# service enum is derived automatically from HOOK_HANDLERS.
@extend_schema(
    responses=HookResponseSerializer,
    request=HookRequestSerializer,
    parameters=[
        OpenApiParameter(
            "service",
            enum=sorted(HOOK_HANDLERS.keys()),
            location=OpenApiParameter.PATH,
        ),
    ],
)
class ServiceHookView(BaseHookView):
    default_exclude_component_vcs = ("github-app",)

    def post(self, request: Request, service: str) -> Response:
        """Process incoming webhook from a code hosting site."""
        try:
            hook_helper = HOOK_HANDLERS[service]
        except KeyError as exc:
            msg = f"Hook {service} not supported"
            raise NotFound(msg) from exc
        return self.run_hook(request, hook_helper, service)


@extend_schema(exclude=True)
class IntegrationHookView(BaseHookView):
    """Authenticated webhook endpoint for a single registered integration."""

    def post(self, request: Request, integration_token: uuid.UUID) -> Response:
        """Process a signed webhook addressed to one integration token."""
        hook_helper = partial(
            github_integration_hook_helper,
            integration_token=str(integration_token),
        )
        return self.run_hook(request, hook_helper, "github-integration")
