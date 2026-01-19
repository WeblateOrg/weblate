# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, TypedDict, cast
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
from rest_framework.views import APIView

from weblate.api.serializers import MultiFieldHyperlinkedIdentityField
from weblate.auth.models import User
from weblate.logger import LOGGER
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Component
from weblate.trans.tasks import perform_update
from weblate.utils.errors import report_error

if TYPE_CHECKING:
    from django.http import QueryDict

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


class HandlerResponse(TypedDict):
    service_long_name: str
    repo_url: str
    repos: list[str]
    branch: str | None
    full_name: str


HandlerType = Callable[[dict, Request | None], HandlerResponse | None]


HOOK_HANDLERS: dict[str, HandlerType] = {}


def validate_full_name(full_name: str) -> bool:
    """
    Validate that repository full name is suitable for endswith matching.

    This is to avoid using too short expression with possibly too broad matches.
    """
    return "/" in full_name and len(full_name) > 5


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


class PayloadMixin:
    @staticmethod
    def extract_payload(request_data: QueryDict | parsers.DataAndFiles | dict) -> dict:
        data: QueryDict | dict
        if isinstance(request_data, parsers.DataAndFiles):
            data = request_data.data
        else:
            data = request_data
        try:
            payload = cast("str | bytes", data["payload"])
        except KeyError as exc:
            msg = "Missing payload parameter!"
            raise ParseError(msg) from exc
        try:
            return json.loads(payload)
        except ValueError as exc:
            msg = f"JSON parse error - {exc!s}"
            raise ParseError(msg) from exc


class PayloadMultiPartParser(parsers.MultiPartParser, PayloadMixin):
    """Extract payload from application/x-www-form-urlencoded."""

    def parse(self, stream, media_type=None, parser_context=None):
        return self.extract_payload(
            super().parse(stream, media_type=media_type, parser_context=parser_context)
        )


class PayloadFormParserParser(parsers.FormParser, PayloadMixin):
    """Extract payload from multipart/form-data."""

    def parse(self, stream, media_type=None, parser_context=None):
        return self.extract_payload(
            super().parse(stream, media_type=media_type, parser_context=parser_context)
        )


@extend_schema(
    responses=HookResponseSerializer,
    request=HookRequestSerializer,
    parameters=[
        OpenApiParameter(
            "service",
            enum=["bitbucket", "github", "gitea", "gitee", "gitlab", "pagure", "azure"],
            location=OpenApiParameter.PATH,
        ),
    ],
)
class ServiceHookView(APIView):
    authentication_classes = []  # noqa: RUF012
    permission_classes = [AllowAny]  # noqa: RUF012
    http_method_names = ["post"]  # noqa: RUF012
    parser_classes = (
        parsers.JSONParser,
        PayloadMultiPartParser,
        PayloadFormParserParser,
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

        # Check if we got payload
        data = request.data
        if not data:
            msg = "Invalid data in json payload!"
            raise ValidationError(msg)

        # Send the request data to the service handler.
        try:
            service_data = hook_helper(data, request)
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

        if not repo_components.exists() and validate_full_name(full_name):
            # Fall back to endswith matching if repository full name is reasonable
            repo_components = Component.objects.filter(
                Q(repo__iendswith=full_name)
                | Q(repo__iendswith=f"{full_name}/")
                | Q(repo__iendswith=f"{full_name}.git")
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
        updates = 0
        for obj in enabled_components:
            updates += 1
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

        if updates == 0:
            return self.hook_response(
                "No matching repositories found!",
                status=202,
                match_status=match_status,
            )

        updated_components = [obj.full_slug for obj in enabled_components]

        return self.hook_response(
            f"Update triggered: {', '.join(updated_components)}",
            match_status=match_status,
            updated_components=updated_components,
        )


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
    branch = re.sub(r"^refs/heads/", "", data["ref"])

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


@register_hook
def gitea_hook_helper(data: dict, request: Request | None) -> HandlerResponse | None:
    return {
        "service_long_name": "Gitea",
        "repo_url": data["repository"]["html_url"],
        "repos": [
            data["repository"]["clone_url"],
            data["repository"]["ssh_url"],
            data["repository"]["html_url"],
        ],
        "branch": re.sub(r"^refs/heads/", "", data["ref"]),
        "full_name": data["repository"]["full_name"],
    }


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
        "branch": re.sub(r"^refs/heads/", "", data["ref"]),
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
    branch = re.sub(r"^refs/heads/", "", data["ref"])

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
