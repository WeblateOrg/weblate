# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from ipaddress import ip_address
from typing import TYPE_CHECKING, ClassVar, TypedDict, cast
from urllib.parse import quote, urlparse

from django.conf import settings
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import parsers, serializers
from rest_framework.exceptions import (
    MethodNotAllowed,
    NotFound,
    ParseError,
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
from weblate.trans.models import Component
from weblate.trans.tasks import perform_update
from weblate.utils.errors import report_error

if TYPE_CHECKING:
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


HandlerType = Callable[[dict, Request | None], HandlerResponse | None]


HOOK_HANDLERS: dict[str, HandlerType] = {}


class HookPayloadError(Exception):
    """Raised for malformed but expected webhook payload problems."""


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


def strip_git_suffix(value: str) -> str:
    """Strip a trailing .git suffix from a repository path."""
    if value.endswith(".git"):
        return value[:-4]
    return value


def normalize_full_name(full_name: str | None) -> str | None:
    """Normalize repository full name for matching helpers."""
    if not full_name:
        return None
    full_name = strip_git_suffix(full_name.strip("/"))
    parts = full_name.split("/")
    if len(parts) < 2 or any(not part for part in parts):
        return None
    return full_name


def repo_connection(repo: str) -> tuple[str | None, str | None, int | None, bool]:
    """Extract hostname, username and SSH port from repository URL."""
    parsed = urlparse(repo)
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
    return urlparse(repo).hostname is None and ":" in repo


def repo_path(repo: str) -> str | None:
    """Extract repository path from URL or scp-like Git syntax."""
    parsed = urlparse(repo)
    if parsed.hostname is not None:
        return strip_git_suffix(parsed.path.lstrip("/")) or None
    if ":" not in repo:
        return None
    return strip_git_suffix(repo.split(":", 1)[1].lstrip("/")) or None


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


def allow_fallback_matching(repos: list[str]) -> bool:
    """
    Allow suffix fallback only for payloads with at least one non-loopback URL.

    Forgejo and Gitea test deliveries use sample localhost repository URLs. If
    exact matching fails, suffix fallback would scan all components for that
    sample repository path before responding to the hook.
    """
    return any(not repo_is_loopback(repo) for repo in repos)


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


def bitbucket_extract_repo_url(data, repository: dict) -> str:
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


@register_hook
def github_hook_helper(data: dict, request: Request | None) -> HandlerResponse | None:
    """Parse hooks from GitHub."""
    # Ignore non push events
    if request and request.headers.get("x-github-event") != "push":
        return None
    # Parse owner, branch and repository name
    o_data = data["repository"]["owner"]
    owner = o_data["login"] if "login" in o_data else o_data["name"]
    slug = data["repository"]["name"]
    branch = normalize_branch_ref(data.get("ref"))

    params = {"owner": owner, "slug": slug}

    if "clone_url" not in data["repository"]:
        # Construct possible repository URLs
        repos = [repo % params for repo in GITHUB_REPOS]
    else:
        repos = []
        keys = ["clone_url", "git_url", "ssh_url", "svn_url", "html_url", "url"]
        for key in keys:
            url = data["repository"].get(key)
            if not url:
                continue
            repos.append(url)
            if url.endswith(".git"):
                repos.append(url[:-4])

    return {
        "service_long_name": "GitHub",
        "repo_url": data["repository"]["url"],
        "repos": sorted(set(repos)),
        "branch": branch,
        "full_name": f"{owner}/{slug}",
    }


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


def expand_quoted(name: str):
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
class ServiceHookView(APIView):
    authentication_classes = []  # noqa: RUF012
    permission_classes = [AllowAny]  # noqa: RUF012
    throttle_classes = []  # noqa: RUF012
    http_method_names = ["post"]  # noqa: RUF012
    parser_classes = (
        parsers.JSONParser,
        parsers.MultiPartParser,
        parsers.FormParser,
    )

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

    def post(self, request: Request, service: str) -> Response:
        """Process incoming webhook from a code hosting site."""
        # We support only post methods
        if not settings.ENABLE_HOOKS:
            msg = "POST"
            raise MethodNotAllowed(msg)

        # Get service helper
        try:
            hook_helper = HOOK_HANDLERS[service]
        except KeyError as exc:
            msg = f"Hook {service} not supported"
            raise NotFound(msg) from exc

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
        except Exception as exc:
            report_error("Invalid service data")
            msg = "Invalid data in json payload!"
            raise ValidationError(msg) from exc

        # This happens on ping request upon installation
        if service_data is None:
            return self.hook_response("Hook working", status=201)

        # Log data
        service_long_name = service_data["service_long_name"]
        repos = service_data["repos"]
        repo_url = service_data["repo_url"]
        branch = service_data["branch"]
        full_name = service_data["full_name"]

        # Generate filter
        spfilter = Q(repo__in=repos)

        user = User.objects.get_or_create_bot(
            scope="webhook",
            name=service,
            verbose=f"{service_data['service_long_name']} webhook",
        )

        for repo in repos:
            # We need to match also URLs which include username and password
            if repo.startswith("http://"):
                spfilter |= Q(repo__startswith="http://") & Q(
                    repo__endswith=f"@{repo[7:]}"
                )
            elif repo.startswith("https://"):
                spfilter |= Q(repo__startswith="https://") & Q(
                    repo__endswith=f"@{repo[8:]}"
                )
            # Include URLs with trailing slash
            spfilter |= Q(repo=f"{repo}/")

        repo_components = Component.objects.filter(spfilter)

        fallback_full_name = normalize_full_name(full_name)
        if (
            not repo_components.exists()
            and fallback_full_name is not None
            and validate_full_name(fallback_full_name)
            and allow_fallback_matching(repos)
        ):
            # Fall back to endswith matching if repository full name is reasonable
            repo_components = Component.objects.filter(
                Q(repo__iendswith=fallback_full_name)
                | Q(repo__iendswith=f"{fallback_full_name}/")
                | Q(repo__iendswith=f"{fallback_full_name}.git")
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
            updated_components.append(obj)
            LOGGER.info("%s notification will update %s", service_long_name, obj)
            obj.change_set.create(
                action=ActionEvents.HOOK, details=service_data, user=user
            )
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
