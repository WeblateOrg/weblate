#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#


import json
import re
from urllib.parse import urlparse

from django.conf import settings
from django.db.models import Q
from django.http import (
    Http404,
    HttpResponseBadRequest,
    HttpResponseNotAllowed,
    JsonResponse,
)
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from weblate.logger import LOGGER
from weblate.trans.models import Change, Component
from weblate.trans.tasks import perform_update
from weblate.utils.errors import report_error
from weblate.utils.views import get_component, get_project

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

HOOK_HANDLERS = {}


def hook_response(
    response: str = "Update triggered",
    message: str = "success",
    status: int = 200,
    **kwargs,
):
    """Generic okay hook response."""
    data = {"status": message, "message": response}
    data.update(kwargs)
    return JsonResponse(data=data, status=status)


def register_hook(handler):
    """Register hook handler."""
    name = handler.__name__.split("_")[0]
    HOOK_HANDLERS[name] = handler
    return handler


@csrf_exempt
def update_component(request, project, component):
    """API hook for updating git repos."""
    if not settings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    obj = get_component(request, project, component, True)
    if not obj.project.enable_hooks:
        return HttpResponseNotAllowed([])
    perform_update.delay("Component", obj.pk)
    return hook_response()


@csrf_exempt
def update_project(request, project):
    """API hook for updating git repos."""
    if not settings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    obj = get_project(request, project, True)
    if not obj.enable_hooks:
        return HttpResponseNotAllowed([])
    perform_update.delay("Project", obj.pk)
    return hook_response()


def parse_hook_payload(request):
    """Parse hook payload.

    We handle both application/x-www-form-urlencoded and application/json.
    """
    if "application/json" in request.META["CONTENT_TYPE"].lower():
        return json.loads(request.body.decode())
    return json.loads(request.POST["payload"])


@require_POST
@csrf_exempt
def vcs_service_hook(request, service):
    """Shared code between VCS service hooks.

    Currently used for bitbucket_hook, github_hook and gitlab_hook, but should be usable
    for other VCS services (Google Code, custom coded sites, etc.) too.
    """
    # We support only post methods
    if not settings.ENABLE_HOOKS:
        return HttpResponseNotAllowed(())

    # Get service helper
    try:
        hook_helper = HOOK_HANDLERS[service]
    except KeyError:
        raise Http404(f"Hook {service} not supported")

    # Check if we got payload
    try:
        data = parse_hook_payload(request)
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Could not parse JSON payload!")

    if not data:
        return HttpResponseBadRequest("Invalid data in json payload!")

    # Send the request data to the service handler.
    try:
        service_data = hook_helper(data, request)
    except Exception:
        LOGGER.error("failed to parse service %s data", service)
        report_error()
        return HttpResponseBadRequest("Invalid data in json payload!")

    # This happens on ping request upon installation
    if service_data is None:
        return hook_response("Hook working", status=201)

    # Log data
    service_long_name = service_data["service_long_name"]
    repos = service_data["repos"]
    repo_url = service_data["repo_url"]
    branch = service_data["branch"]
    full_name = service_data["full_name"]

    # Generate filter
    spfilter = (
        Q(repo__in=repos)
        | Q(repo__iendswith=full_name)
        | Q(repo__iendswith=f"{full_name}.git")
    )

    for repo in repos:
        # We need to match also URLs which include username and password
        if repo.startswith("http://"):
            spfilter |= Q(repo__startswith="http://") & Q(
                repo__endswith="@{}".format(repo[7:])
            )
        elif repo.startswith("https://"):
            spfilter |= Q(repo__startswith="https://") & Q(
                repo__endswith="@{}".format(repo[8:])
            )
        # Include URLs with trailing slash
        spfilter |= Q(repo=repo + "/")

    all_components = repo_components = Component.objects.filter(spfilter)

    if branch is not None:
        all_components = repo_components.filter(branch=branch)

    enabled_components = all_components.filter(project__enable_hooks=True)

    LOGGER.info(
        "received %s notification on repository %s, URL %s, branch %s, "
        "%d matching components, %d to process, %d linked",
        service_long_name,
        full_name,
        repo_url,
        branch,
        all_components.count(),
        enabled_components.count(),
        Component.objects.filter(linked_component__in=enabled_components).count(),
    )

    # Trigger updates
    updates = 0
    for obj in enabled_components:
        updates += 1
        LOGGER.info("%s notification will update %s", service_long_name, obj)
        Change.objects.create(
            component=obj, action=Change.ACTION_HOOK, details=service_data
        )
        perform_update.delay("Component", obj.pk)

    match_status = {
        "repository_matches": repo_components.count(),
        "branch_matches": all_components.count(),
        "enabled_hook_matches": len(enabled_components),
    }

    if updates == 0:
        return hook_response(
            "No matching repositories found!",
            "failure",
            status=202,
            match_status=match_status,
        )

    updated_components = [obj.full_slug for obj in enabled_components]

    return hook_response(
        "Update triggered: {}".format(", ".join(updated_components)),
        match_status=match_status,
        updated_components=updated_components,
    )


def bitbucket_extract_changes(data):
    if "changes" in data:
        return data["changes"]
    if "push" in data:
        return data["push"]["changes"]
    if "commits" in data:
        return data["commits"]
    return []


def bitbucket_extract_branch(data):
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


def bitbucket_extract_full_name(repository):
    if "full_name" in repository:
        return repository["full_name"]
    if "fullName" in repository:
        return repository["fullName"]
    if "owner" in repository and "slug" in repository:
        return "{}/{}".format(repository["owner"], repository["slug"])
    if "project" in repository and "slug" in repository:
        return "{}/{}".format(repository["project"]["key"], repository["slug"])
    raise ValueError("Could not determine repository full name")


def bitbucket_extract_repo_url(data, repository):
    if "links" in repository:
        if "html" in repository["links"]:
            return repository["links"]["html"]["href"]
        return repository["links"]["self"][0]["href"]
    if "canon_url" in data:
        return "{}{}".format(data["canon_url"], repository["absolute_url"])
    raise ValueError("Could not determine repository URL")


@register_hook
def bitbucket_hook_helper(data, request):
    """API to handle service hooks from Bitbucket."""
    # Bitbucket ping event
    if request and request.META.get("HTTP_X_EVENT_KEY") not in (
        "repo:push",
        "repo:refs_changed",
        "pullrequest:fulfilled",
        "pr:merged",
    ):
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
        if "scm" not in data["repository"]:
            templates = BITBUCKET_GIT_REPOS + BITBUCKET_HG_REPOS
        elif data["repository"]["scm"] == "hg":
            templates = BITBUCKET_HG_REPOS
        else:
            templates = BITBUCKET_GIT_REPOS
        # Construct possible repository URLs
        for repo in templates:
            repos.extend(
                repo.format(full_name=full_name, server=server)
                for server in repo_servers
            )

    if not repos:
        LOGGER.error("unsupported repository: %s", repr(data["repository"]))
        raise ValueError("unsupported repository")

    return {
        "service_long_name": "Bitbucket",
        "repo_url": repo_url,
        "repos": repos,
        "branch": bitbucket_extract_branch(data),
        "full_name": f"{full_name}.git",
    }


@register_hook
def github_hook_helper(data, request):
    """API to handle commit hooks from GitHub."""
    # Ignore non push events
    if request and request.META.get("HTTP_X_GITHUB_EVENT") != "push":
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
            if key in data["repository"]:
                repos.append(data["repository"][key])

    return {
        "service_long_name": "GitHub",
        "repo_url": data["repository"]["url"],
        "repos": repos,
        "branch": branch,
        "full_name": f"{owner}/{slug}.git",
    }


@register_hook
def gitea_hook_helper(data, request):
    return {
        "service_long_name": "Gitea",
        "repo_url": data["repository"]["html_url"],
        "repos": [
            data["repository"]["clone_url"],
            data["repository"]["ssh_url"],
            data["repository"]["html_url"],
        ],
        "branch": re.sub(r"^refs/heads/", "", data["ref"]),
        "full_name": "{}.git".format(data["repository"]["full_name"]),
    }


@register_hook
def gitee_hook_helper(data, request):
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
        "full_name": "{}.git".format(data["repository"]["path_with_namespace"]),
    }


@register_hook
def gitlab_hook_helper(data, request):
    """API to handle commit hooks from GitLab."""
    # Ignore non known events
    if "ref" not in data:
        return None
    ssh_url = data["repository"]["url"]
    http_url = ".".join((data["repository"]["homepage"], "git"))
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
        "full_name": ssh_url.split(":", 1)[1],
    }


@register_hook
def pagure_hook_helper(data, request):
    """API to handle commit hooks from Pagure."""
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


@register_hook
def azure_hook_helper(data, request):
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
                project=project,
                projectId=projectid,
                repository=repository,
                repositoryId=repositoryid,
            )
            for repo in AZURE_REPOS
        ]
    else:
        repos = [http_url]

    return {
        "service_long_name": "Azure",
        "repo_url": http_url,
        "repos": repos,
        "branch": branch,
        "full_name": repository,
    }
