# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import logging
import secrets
import uuid
from collections import defaultdict
from itertools import islice
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict
from urllib.parse import urlencode

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.core.signing import BadSignature, SignatureExpired
from django.db import transaction
from django.db.models import (
    Case,
    Count,
    Exists,
    Min,
    OuterRef,
    Q,
    Value,
    When,
    prefetch_related_objects,
)
from django.db.models.functions import Lower
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import aget_object_or_404, get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.crypto import salted_hmac
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.utils.translation import gettext, ngettext
from django.views import View
from django.views.decorators.http import require_http_methods, require_safe

from weblate.auth.decorators import management_access, management_permission_required
from weblate.checks.locks import lock_check_projects
from weblate.trans.actions import ActionEvents
from weblate.trans.component_creation import get_creation_projects
from weblate.trans.models import Category, Change, Component, Project
from weblate.trans.models.component import component_settings_lookups
from weblate.trans.views.create import INTEGRATION_IMPORT_VCS_KEY, SESSION_CREATE_KEY
from weblate.trans.views.hooks import apply_pending_github_installation_event
from weblate.trans.workspace_move import get_project_workspace_move_error
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.ratelimit import check_rate_limit
from weblate.utils.site import get_site_url
from weblate.vcs.base import RepositoryError
from weblate.vcs.forms import (
    GitHubAppMigrationForm,
    GitHubAppRecoveryForm,
    GitHubAppRegisterCallbackForm,
    GitHubAppRegisterForm,
    GitHubAppSetupCallbackForm,
    GitHubAppWorkspaceMoveForm,
    clean_github_app_hostname,
)
from weblate.vcs.github import (
    GITHUB_APP_MANIFEST_EVENTS,
    GITHUB_APP_MANIFEST_PERMISSIONS,
    GITHUB_APP_MIGRATABLE_VCS,
    GITHUB_APP_NAME_MAX_LENGTH,
    GitHubAppCredentials,
    GitHubAppInvalidCodeError,
    GithubAppRepository,
    GitHubInstallation,
    InstallationRemoval,
    aget_github_app_configurations,
    aget_github_app_settings,
    build_github_app_manifest,
    exchange_github_app_manifest_code,
    exchange_github_user_code,
    get_github_app_configurations,
    get_github_app_install_url,
    get_github_app_manifest_new_url,
    get_github_app_settings,
    get_github_oauth_base,
    get_github_repository_clone_url,
    get_github_repository_identity,
    get_github_repository_import_url,
    get_user_admin_installation,
    github_app_is_configured,
    normalize_github_app_hostname,
    normalize_github_installation_id,
    remove_github_installation,
)
from weblate.vcs.params import strip_unused_vcs_params
from weblate.vcs.permissions import (
    github_app_installation_workspaces,
    managed_workspaces,
    user_can_install_github_app_in_workspace,
    user_can_use_github_app_in_workspace,
)
from weblate.wladmin.views import MENU
from weblate.workspaces.models import (
    WORKSPACE_NAME_LENGTH,
    WORKSPACE_OWNERS_GROUP,
    Workspace,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from uuid import UUID

    from django.forms.boundfield import BoundWidget

    from weblate.auth.models import AuthenticatedHttpRequest, User
    from weblate.auth.results import PermissionResult
    from weblate.trans.models.component import ComponentQuerySet
    from weblate.trans.models.project import ProjectQuerySet
    from weblate.workspaces.models import WorkspaceQuerySet

logger = logging.getLogger(__name__)

_MENU_CONTEXT = {"menu_items": MENU, "menu_page": "github"}
_GITHUB_APP_STATE_SALT = "weblate.vcs.github.install"
_GITHUB_APP_STATE_MAX_AGE = 60 * 60
_GITHUB_APP_REGISTER_SALT = "weblate.vcs.github.register"
_GITHUB_APP_REGISTER_MAX_AGE = 60 * 60
_GITHUB_APP_MIGRATION_SALT = "weblate.vcs.github.migration"
MIGRATION_BATCH_SIZE = 25
LIST_PAGE_SIZE = 25


type MigrationRepositories = dict[tuple[str, str], str]

type MigrationStatus = Literal["ready", "access-needed", "using-app"]


class GitHubAppMigrationEntry(TypedDict):
    component: Component
    full_name: str
    status: MigrationStatus
    checkbox: NotRequired[BoundWidget]


def _installation_workspaces(user):
    return github_app_installation_workspaces(user)


def _user_can_install_github_app(user) -> bool:
    return _installation_workspaces(user).exists()


async def _auser_can_install_github_app(user) -> bool:
    await user.aprepare_permissions()
    return await _installation_workspaces(user).aexists()


def _handle_missing_github_app_access(request, next_url: str) -> HttpResponse | None:
    if _user_can_install_github_app(request.user):
        return None
    if request.user.has_perm("management.use") and not Workspace.objects.exists():
        messages.error(
            request,
            gettext(
                "Create a workspace before connecting a GitHub account. "
                "GitHub App connections are linked to workspaces."
            ),
        )
        return redirect(next_url)
    raise PermissionDenied


async def _ahandle_missing_github_app_access(
    request, next_url: str
) -> HttpResponse | None:
    if await _auser_can_install_github_app(request.user):
        return None
    if (
        request.user.has_perm("management.use")
        and not await Workspace.objects.aexists()
    ):
        messages.error(
            request,
            gettext(
                "Create a workspace before connecting a GitHub account. "
                "GitHub App connections are linked to workspaces."
            ),
        )
        return redirect(next_url)
    raise PermissionDenied


def _default_next_url(request, workspace: Workspace | None = None) -> str:
    if workspace is not None:
        return (
            f"{reverse('github-app-repositories')}?"
            f"{urlencode({'workspace': workspace.pk})}"
        )
    if managed_workspaces(request.user).exists():
        return reverse("github-app-repositories")
    return reverse("manage-github-accounts")


async def _adefault_next_url(request, workspace: Workspace | None = None) -> str:
    if workspace is not None:
        return (
            f"{reverse('github-app-repositories')}?"
            f"{urlencode({'workspace': workspace.pk})}"
        )
    await request.user.aprepare_permissions()
    if await managed_workspaces(request.user).aexists():
        return reverse("github-app-repositories")
    return reverse("manage-github-accounts")


def _get_next_url(request) -> str:
    default_url = _default_next_url(request)
    next_url = request.GET.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return default_url


def _get_workspace(workspaces, workspace_id) -> Workspace:
    try:
        return workspaces.get(pk=workspace_id)
    except (Workspace.DoesNotExist, ValidationError, ValueError) as error:
        raise PermissionDenied from error


async def _aget_installation_workspace(user, workspace_id) -> Workspace:
    await user.aprepare_permissions()
    try:
        return await _installation_workspaces(user).aget(pk=workspace_id)
    except (Workspace.DoesNotExist, ValidationError, ValueError) as error:
        raise PermissionDenied from error


def _get_requested_workspace(request, workspaces) -> Workspace | None:
    workspace_id = request.GET.get("workspace", "").strip()
    if workspace_id:
        return _get_workspace(workspaces, workspace_id)
    workspaces = list(workspaces[:2])
    if len(workspaces) == 1:
        return workspaces[0]
    return None


def _get_install_workspace(request) -> Workspace | None:
    return _get_requested_workspace(request, _installation_workspaces(request.user))


def _user_can_install_in_workspace(
    user, workspace: Workspace
) -> PermissionResult | bool:
    return user_can_install_github_app_in_workspace(user, workspace)


def _get_install_link(
    request, next_url: str | None = None, workspace: Workspace | None = None
) -> str | None:
    if not github_app_is_configured():
        return None
    if workspace is None:
        workspace = _get_install_workspace(request)
    elif not _user_can_install_in_workspace(request.user, workspace):
        return None
    if workspace is None:
        return None
    target = next_url or request.get_full_path()
    return (
        f"{reverse('github-app-install')}?"
        f"{urlencode({'next': target, 'workspace': workspace.pk})}"
    )


def _get_install_choices(next_url: str, workspace: Workspace) -> list[dict[str, str]]:
    install_url = reverse("github-app-install")
    result = []
    for hostname, config in sorted(get_github_app_configurations().items()):
        query = urlencode(
            {"next": next_url, "host": hostname, "workspace": workspace.pk}
        )
        result.append(
            {
                "hostname": hostname,
                "app_slug": config.app_slug,
                "install_url": f"{install_url}?{query}",
            }
        )
    return result


def _get_github_app_migration_repositories(
    workspace: Workspace,
    hostname: str | None = None,
    installations: list[GitHubInstallation] | None = None,
) -> tuple[MigrationRepositories, list[GitHubInstallation], set[str]]:
    """Return canonical repository URLs available to a workspace."""
    configured_hosts = set(get_github_app_configurations())
    if hostname is not None:
        configured_hosts.intersection_update({hostname})
    if installations is None:
        installations = list(
            GitHubInstallation.objects.filter(
                workspace=workspace, enabled=True, hostname__in=configured_hosts
            ).order_by("hostname", "target_login", "pk")
        )
    else:
        installations = [
            row
            for row in installations
            if row.enabled and row.hostname in configured_hosts
        ]
    return _migration_repositories(installations), installations, configured_hosts


def _migration_repositories(
    installations: Iterable[GitHubInstallation],
) -> MigrationRepositories:
    repositories: MigrationRepositories = {}
    for installation in installations:
        for repository in installation.repositories:
            if repository.get("archived", False):
                continue
            clone_url = get_github_repository_clone_url(
                installation.hostname, repository
            )
            full_name = repository.get("full_name")
            if clone_url is None or not isinstance(full_name, str):
                continue
            repositories.setdefault(
                (installation.hostname, full_name.casefold()), clone_url
            )
    return repositories


def _get_bulk_migration_inventories(
    workspace_ids: set[UUID], hostname: str | None
) -> dict[UUID, MigrationRepositories]:
    hosts = (
        [hostname] if hostname is not None else list(get_github_app_configurations())
    )
    by_workspace: defaultdict[UUID, list[GitHubInstallation]] = defaultdict(list)
    for installation in GitHubInstallation.objects.filter(
        enabled=True, hostname__in=hosts, workspace_id__in=workspace_ids
    ).order_by("hostname", "target_login", "pk"):
        by_workspace[installation.workspace_id].append(installation)
    return {
        workspace_id: _migration_repositories(installations)
        for workspace_id, installations in by_workspace.items()
    }


def _get_github_app_migration_target(
    component: Component, repositories: MigrationRepositories
) -> str | None:
    """Return the canonical URL for an eligible component."""
    if component.vcs not in GITHUB_APP_MIGRATABLE_VCS:
        return None
    identity = get_github_repository_identity(component.repo)
    if identity is None:
        return None
    hostname, full_name = identity
    return repositories.get((hostname, full_name.casefold()))


def _get_github_app_migration_entries(
    user, workspace: Workspace, hostname: str | None = None
) -> tuple[
    list[GitHubAppMigrationEntry],
    dict[tuple[str, str], str],
    list[GitHubInstallation],
]:
    repositories, installations, configured_hosts = (
        _get_github_app_migration_repositories(workspace, hostname)
    )
    entries: list[GitHubAppMigrationEntry] = []
    components = (
        Component.objects.filter(
            project__workspace=workspace,
            vcs__in=GITHUB_APP_MIGRATABLE_VCS | {"github-app"},
        )
        .prefetch(alerts=False)
        .order_by("project__name", "name", "pk")
    )
    for component in components:
        if not user.has_perm("component.edit", component):
            continue
        identity = get_github_repository_identity(component.repo)
        if identity is None:
            continue
        host, full_name = identity
        if hostname is not None and host != hostname:
            continue
        status: MigrationStatus
        if component.vcs == "github-app":
            status = "using-app"
        elif host not in configured_hosts:
            continue
        elif (host, full_name.casefold()) in repositories:
            status = "ready"
        else:
            status = "access-needed"
        entries.append(
            {
                "component": component,
                "full_name": full_name,
                "status": status,
            }
        )
    return entries, repositories, installations


def _build_install_state(
    request,
    next_url: str,
    hostname: str,
    workspace: Workspace,
    installation_id: str = "",
) -> str:
    nonce = request.session.get("github_app_install_nonce")
    if not nonce:
        nonce = secrets.token_urlsafe(16)
        request.session["github_app_install_nonce"] = nonce
    return signing.dumps(
        {
            "user": request.user.pk,
            "next": next_url,
            "nonce": nonce,
            "installation_id": installation_id,
            "host": hostname,
            "workspace": str(workspace.pk),
        },
        salt=_GITHUB_APP_STATE_SALT,
    )


def _load_install_state(
    request, state: str, default_next_url: str | None = None
) -> dict[str, str]:
    payload = signing.loads(
        state,
        salt=_GITHUB_APP_STATE_SALT,
        max_age=_GITHUB_APP_STATE_MAX_AGE,
    )
    if payload.get("user") != request.user.pk:
        msg = "State user mismatch"
        raise BadSignature(msg)
    if payload.get("nonce") != request.session.get("github_app_install_nonce"):
        msg = "State session mismatch"
        raise BadSignature(msg)

    next_url = payload.get("next", "")
    if not isinstance(next_url, str) or not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = default_next_url or _default_next_url(request)

    hostname = payload.get("host", "")
    if not isinstance(hostname, str):
        hostname = ""

    workspace_id = payload.get("workspace", "")
    if not workspace_id:
        msg = "State workspace mismatch"
        raise BadSignature(msg)

    return {
        "next": next_url,
        "host": normalize_github_app_hostname(hostname) if hostname else "",
        "workspace": str(workspace_id),
        "installation_id": payload.get("installation_id", ""),
    }


def _get_redirect_url(request, default_url: str) -> str:
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return default_url


def _get_installation_repository_url(installation: GitHubInstallation) -> str:
    return (
        f"{reverse('github-app-repositories')}?"
        f"{urlencode({'workspace': installation.workspace_id})}"
    )


def _get_workspace_install_url(
    next_url: str, hostname: str, workspace: Workspace
) -> str:
    return (
        f"{reverse('github-app-install')}?"
        f"{urlencode({'next': next_url, 'host': hostname, 'workspace': workspace.pk})}"
    )


def _user_can_manage_installation(user, installation: GitHubInstallation) -> bool:
    return _installation_workspaces(user).filter(pk=installation.workspace_id).exists()


async def _auser_can_use_installation(user, installation: GitHubInstallation) -> bool:
    await user.aprepare_permissions()
    return await sync_to_async(user_can_use_github_app_in_workspace)(
        user, installation.workspace
    )


async def _auser_can_manage_installation(
    user, installation: GitHubInstallation
) -> bool:
    await user.aprepare_permissions()
    return (
        await _installation_workspaces(user)
        .filter(pk=installation.workspace_id)
        .aexists()
    )


def _require_installation_access(request, installation: GitHubInstallation) -> None:
    if not _user_can_manage_installation(request.user, installation):
        raise PermissionDenied


async def _arequire_installation_access(
    request, installation: GitHubInstallation
) -> None:
    if not await _auser_can_manage_installation(request.user, installation):
        raise PermissionDenied


async def _arequire_installation_use(request, installation: GitHubInstallation) -> None:
    if not await _auser_can_use_installation(request.user, installation):
        raise PermissionDenied


@method_decorator(management_access, name="dispatch")
class GitHubInstallationListView(View):
    def get(self, request):
        counts = dict(
            GitHubInstallation.objects.order_by()
            .values("hostname")
            .annotate(total=Count("pk"))
            .values_list("hostname", "total")
        )
        can_configure = request.user.has_perm("management.configure")
        apps = [
            {
                "hostname": host,
                "app_id": config.app_id,
                "app_slug": config.app_slug,
                "html_url": config.html_url,
                "credentials_pk": config.pk,
                "count": counts.get(host, 0),
                "can_remove": can_configure and config.pk and host not in counts,
                "connections_url": reverse(
                    "manage-github-connections", query={"host": host}
                ),
                "migration_url": reverse("manage-github-migration", args=[host]),
            }
            for host, config in sorted(get_github_app_configurations().items())
        ]
        return render(
            request,
            "vcs/github_installation_list.html",
            {
                "apps": apps,
                "github_app_register_url": reverse("github-app-register")
                if can_configure
                else None,
                **_MENU_CONTEXT,
            },
        )


@management_access
@require_safe
def github_connections(request):
    host = request.GET.get("host", "")
    configurations = get_github_app_configurations()
    installations = GitHubInstallation.objects.select_related("workspace").order_by(
        "-created", "-pk"
    )
    if host:
        installations = installations.filter(hostname=host)
    return render(
        request,
        "vcs/github_connections.html",
        {
            "host": host,
            "page_obj": Paginator(installations, LIST_PAGE_SIZE).get_page(
                request.GET.get("page")
            ),
            "migration_urls": [
                (name, reverse("manage-github-migration", args=[name]))
                for name in sorted(configurations)
                if not host or host == name
            ],
            "has_workspaces": Workspace.objects.exists(),
            **_MENU_CONTEXT,
        },
    )


def _integration_workspaces(user: User) -> WorkspaceQuerySet:
    return (
        Workspace.objects.all()
        if user.has_perm("management.use")
        else managed_workspaces(user)
    )


def _get_workspace_integrations_workspace(
    user: User, workspace_id: UUID | str
) -> Workspace:
    return _get_workspace(_integration_workspaces(user), workspace_id)


def _workspace_picker_context(request, workspaces: WorkspaceQuerySet):
    owned = (
        request.user.groups.filter(name=WORKSPACE_OWNERS_GROUP)
        .order_by()
        .values("defining_workspace_id")
    )
    candidates = workspaces.only("name").order_by(
        Case(When(pk__in=owned, then=Value(0)), default=Value(1)),
        "name",
        "pk",
    )
    query = request.GET.get("q", "").strip()
    if query:
        candidates = candidates.filter(name__icontains=query)
    return {
        "workspace_page": Paginator(candidates, LIST_PAGE_SIZE).get_page(
            request.GET.get("page")
        ),
        "query": query,
    }


@login_required
@require_safe
def legacy_account_integrations(request):
    workspace_id = request.GET.get("workspace", "").strip()
    if workspace_id:
        workspace = _get_workspace_integrations_workspace(request.user, workspace_id)
        return redirect("workspace-integrations", workspace_id=workspace.pk)

    workspaces = managed_workspaces(request.user)
    matches = list(workspaces.only("name").order_by("name", "pk")[:2])
    if not matches:
        return redirect("workspaces")
    if len(matches) == 1:
        return redirect("workspace-integrations", workspace_id=matches[0].pk)
    return render(
        request,
        "vcs/legacy_workspace_integrations.html",
        _workspace_picker_context(request, workspaces),
    )


@login_required
@require_safe
def workspace_integrations(request, workspace_id):
    workspace = _get_workspace_integrations_workspace(request.user, workspace_id)
    next_url = reverse("workspace-integrations", args=[workspace.pk])
    can_manage = _user_can_install_in_workspace(request.user, workspace)
    installations_by_host: defaultdict[str, list[GitHubInstallation]] = defaultdict(
        list
    )
    installations = list(
        GitHubInstallation.objects.filter(workspace=workspace).order_by(
            "hostname", "target_login", "pk"
        )
    )
    if can_manage:
        GitHubInstallation.objects.prefetch_components(installations)
    for installation in installations:
        installations_by_host[installation.hostname].append(installation)

    configurations = get_github_app_configurations()
    apps = [
        {
            "hostname": host,
            "config": configurations.get(host),
            "installations": installations_by_host[host],
            "install_url": (
                _get_workspace_install_url(next_url, host, workspace)
                if host in configurations and can_manage
                else None
            ),
        }
        for host in sorted(set(configurations) | set(installations_by_host))
    ]
    repositories, _, _ = _get_github_app_migration_repositories(
        workspace, installations=installations
    )
    return render(
        request,
        "vcs/workspace_integrations.html",
        {
            "apps": apps,
            "bread_image": "project.svg",
            "can_manage": can_manage,
            "has_ready_components": bool(repositories)
            and any(
                _ready_migration_candidates(
                    request.user,
                    _legacy_migration_components(request.user)
                    .filter(project__workspace=workspace)
                    .iterator(),
                    {workspace.pk: repositories},
                )
            ),
            "next_url": next_url,
            "selected_workspace": workspace,
        },
    )


@method_decorator(login_required, name="dispatch")
class GitHubInstallationDetailView(View):
    def get(self, request, pk):
        installation = get_object_or_404(
            GitHubInstallation.objects.select_related("workspace"), pk=pk
        )
        _require_installation_access(request, installation)
        app_configured = get_github_app_settings(installation.hostname) is not None
        can_import = installation.enabled and app_configured
        repositories = []
        for repo in installation.repositories:
            if repo.get("archived", False):
                continue
            entry = dict(repo)
            if can_import:
                entry["import_url"] = get_github_repository_import_url(
                    entry, installation_id=installation.pk
                )
            repositories.append(entry)
        return render(
            request,
            "vcs/github_installation_detail.html",
            {
                "installation": installation,
                "bread_image": "project.svg",
                "repositories": repositories,
                "github_app_install_url": _get_install_link(
                    request,
                    reverse("manage-github-account-detail", kwargs={"pk": pk}),
                    installation.workspace,
                ),
                "app_configured": app_configured,
            },
        )


@login_required
async def remove_installation(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    installation = await aget_object_or_404(GitHubInstallation, pk=pk)
    await _arequire_installation_access(request, installation)
    next_url = _get_redirect_url(
        request,
        (
            reverse("manage-github-connections", query={"host": installation.hostname})
            if request.user.has_perm("management.use")
            else _get_installation_repository_url(installation)
        ),
    )
    target = str(installation)
    result = await sync_to_async(remove_github_installation)(installation)
    if result == InstallationRemoval.FAILED:
        messages.error(
            request,
            gettext(
                "GitHub could not uninstall the connected account. "
                "The connection was not removed from Weblate, please try again."
            ),
        )
    elif result == InstallationRemoval.SHARED:
        messages.success(
            request,
            gettext(
                "Removed connected GitHub account %(target)s. The Weblate GitHub "
                "App remains installed because another workspace still uses it."
            )
            % {"target": target},
        )
    elif result == InstallationRemoval.UNINSTALLED:
        messages.success(
            request,
            gettext(
                "Removed connected GitHub account %(target)s and uninstalled "
                "the Weblate GitHub App from GitHub."
            )
            % {"target": target},
        )
    elif result == InstallationRemoval.UNREACHABLE:
        messages.warning(
            request,
            gettext(
                "Removed connected GitHub account %(target)s. GitHub no longer "
                "grants access to this installation, so it was not uninstalled. "
                "Check on GitHub whether the Weblate GitHub App is still installed."
            )
            % {"target": target},
        )
    else:
        messages.warning(
            request,
            gettext(
                "Removed connected GitHub account %(target)s. The Weblate GitHub "
                "App is no longer configured on this Weblate instance, so it "
                "could not be uninstalled, please remove it on GitHub manually."
            )
            % {"target": target},
        )
    return redirect(next_url)


@management_permission_required("management.configure")
async def remove_github_app(request, pk):
    """Delete the Weblate GitHub App credentials registered for one host."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    credentials = await aget_object_or_404(GitHubAppCredentials, pk=pk)
    hostname = credentials.hostname
    if await GitHubInstallation.objects.filter(hostname=hostname).aexists():
        messages.error(
            request,
            gettext(
                "Remove connected GitHub accounts on %(hostname)s before removing the app credentials."
            )
            % {"hostname": hostname},
        )
        return redirect("manage-github-accounts")
    await credentials.adelete()
    messages.success(
        request,
        gettext("Removed Weblate GitHub App credentials for %(hostname)s.")
        % {"hostname": hostname},
    )
    return redirect("manage-github-accounts")


@login_required
async def refresh_repositories(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    installation = await aget_object_or_404(GitHubInstallation, pk=pk)
    await _arequire_installation_access(request, installation)
    next_url = _get_redirect_url(
        request,
        _get_installation_repository_url(installation),
    )
    try:
        repos = await installation.refresh_repositories()
    except Exception as error:
        await sync_to_async(report_error)(
            "Failed to refresh connected GitHub account repositories", exception=error
        )
        messages.error(
            request,
            gettext("Failed to refresh repositories from GitHub."),
        )
    else:
        messages.success(
            request,
            gettext("Refreshed %(count)d repositories from GitHub.")
            % {"count": len(repos)},
        )
    return redirect(next_url)


@login_required
def github_app_install(request):
    """Start the Weblate GitHub app installation flow."""
    next_url = _get_next_url(request)
    if response := _handle_missing_github_app_access(request, next_url):
        return response

    configs = get_github_app_configurations()
    if not configs:
        messages.error(
            request,
            gettext("Weblate GitHub app is not configured on this Weblate instance."),
        )
        return redirect(next_url)

    workspace = _get_install_workspace(request)
    if workspace is None:
        messages.error(
            request,
            gettext("Select a workspace before connecting a GitHub account."),
        )
        return redirect(next_url)

    host = request.GET.get("host", "").strip()
    if host:
        host = normalize_github_app_hostname(host)
        if host not in configs:
            messages.error(
                request,
                gettext("Weblate GitHub app is not configured for the selected host."),
            )
            return redirect(next_url)
    elif len(configs) > 1:
        return render(
            request,
            "vcs/github_install_select.html",
            {
                "install_choices": _get_install_choices(next_url, workspace),
                "next_url": next_url,
                "workspace": workspace,
            },
        )
    else:
        host = next(iter(configs))

    try:
        install_url = get_github_app_install_url(
            _build_install_state(request, next_url, host, workspace),
            host,
        )
    except ValueError:
        messages.error(
            request,
            gettext("Weblate GitHub app is not configured on this Weblate instance."),
        )
        return redirect(next_url)

    connected = GitHubInstallation.objects.filter(hostname=host, workspace=workspace)
    accounts = GitHubInstallation.objects.filter(
        hostname=host,
        workspace__in=_installation_workspaces(request.user),
        enabled=True,
    ).exclude(installation_id__in=connected.values("installation_id"))

    account_priority: Value | Case = Value(0)
    if request.user.has_perm("management.use"):
        owned = request.user.groups.filter(name=WORKSPACE_OWNERS_GROUP).values(
            "defining_workspace_id"
        )
        account_priority = Case(
            When(workspace_id__in=owned, then=Value(0)), default=Value(1)
        )
    account_choices = (
        accounts.values("installation_id")
        .annotate(login=Min("target_login"), priority=Min(account_priority))
        .order_by("priority", Lower("login"), "installation_id")
        .values_list("login", "installation_id", "priority")
    )
    account_page = Paginator(account_choices, LIST_PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    choices = []
    other_choices = []
    for login, installation_id, priority in account_page:
        url = _get_authorize_url(
            request, configs[host], workspace, next_url, installation_id
        )
        if priority == 0:
            choices.append((login, url))
        else:
            other_choices.append((login, url))
    if choices or other_choices:
        return render(
            request,
            "vcs/github_install_account.html",
            {
                "choices": choices,
                "other_choices": other_choices,
                "page_obj": account_page,
                "install_url": install_url,
                "workspace": workspace,
            },
        )
    return redirect(install_url)


def _get_authorize_url(
    request: AuthenticatedHttpRequest,
    config: GitHubAppCredentials,
    workspace: Workspace,
    next_url: str,
    installation_id: str,
) -> str:
    query = urlencode(
        {
            "client_id": config.client_id,
            "state": _build_install_state(
                request, next_url, config.hostname, workspace, installation_id
            ),
            "redirect_uri": get_site_url(reverse("github-app-setup")),
        }
    )
    return f"{get_github_oauth_base(config.hostname)}/login/oauth/authorize?{query}"


def _recover_update(
    request: AuthenticatedHttpRequest,
    installation_id: str,
    next_url: str,
    configs: dict[str, GitHubAppCredentials],
) -> HttpResponse:
    try:
        installation_id = normalize_github_installation_id(installation_id)
    except ValueError:
        messages.error(
            request, gettext("GitHub did not return a valid installation ID.")
        )
        return redirect(next_url)

    workspaces = {
        str(workspace.pk): workspace
        for workspace in _installation_workspaces(request.user).order_by("name", "pk")
    }
    if not workspaces or not configs:
        messages.error(
            request,
            gettext(
                "The Weblate GitHub app installation link is no longer valid. "
                "Start the installation again."
            ),
        )
        return redirect(next_url)

    form = GitHubAppRecoveryForm(
        request.POST if request.method == "POST" else None,
        workspaces=workspaces.values(),
        hosts=sorted(configs),
    )
    if form.is_valid():
        workspace = workspaces[form.cleaned_data["workspace"]]
        return redirect(
            _get_authorize_url(
                request,
                configs[form.cleaned_data["host"]],
                workspace,
                _default_next_url(request, workspace),
                installation_id,
            )
        )
    return render(request, "vcs/github_install_recovery.html", {"form": form})


async def _aget_update_callback_installation(
    request: AuthenticatedHttpRequest,
    installation_id: str,
    configured_hosts: dict[str, GitHubAppCredentials],
) -> GitHubInstallation | None:
    """
    Return an existing accessible installation for GitHub's update callback.

    GitHub redirects users to the App setup URL after changing repository access
    when ``setup_on_update`` is enabled. That callback is not started by Weblate,
    so it does not carry a signed ``state``; when a signed ``state`` is present
    the request is a Weblate-initiated install flow and must be handled by the
    normal setup path instead.

    Only accept the callback for installations the current Weblate user can use:
    site-wide managers (``management.use``) may update any installation, other
    users only those in a workspace they manage.
    """
    if (
        request.GET.get("setup_action") != "update"
        or not installation_id
        or request.GET.get("state")
    ):
        return None

    await request.user.aprepare_permissions()
    if not configured_hosts:
        return None

    installations = GitHubInstallation.objects.filter(
        hostname__in=configured_hosts,
        installation_id=installation_id,
    )
    if not request.user.has_perm("management.use"):
        installations = installations.filter(
            workspace__in=managed_workspaces(request.user)
        )

    return await (
        installations.select_related("workspace")
        .order_by("workspace__name", "target_login", "hostname")
        .afirst()
    )


def _get_update_callback_next_url(request, installation: GitHubInstallation) -> str:
    if request.user.has_perm("management.use"):
        return reverse("manage-github-account-detail", kwargs={"pk": installation.pk})
    return _get_installation_repository_url(installation)


async def _verify_installation(
    request: AuthenticatedHttpRequest,
    config: GitHubAppCredentials,
    workspace: Workspace,
    next_url: str,
    installation_id: str,
    code: str,
) -> dict | HttpResponse:
    """Return the verified installation or the response needed to recover."""
    authorized_installation = None
    if code:
        try:
            token = await exchange_github_user_code(config, code)
            authorized_installation = await get_user_admin_installation(
                config, token, installation_id
            )
        except GitHubAppInvalidCodeError:
            authorize_url = await sync_to_async(_get_authorize_url)(
                request, config, workspace, next_url, installation_id
            )
            return await sync_to_async(render)(
                request,
                "vcs/github_install_recovery.html",
                {"authorize_url": authorize_url},
            )
        except Exception as error:
            await sync_to_async(report_error)(
                "Failed to verify GitHub installation ownership", exception=error
            )
            messages.error(
                request,
                gettext(
                    "Weblate could not verify the installation with GitHub. Try again later."
                ),
            )
            return redirect(next_url)
    if authorized_installation is None:
        messages.error(
            request,
            gettext(
                "Weblate could not confirm that you can administer this GitHub "
                "installation. Start the installation again with a GitHub user "
                "who owns the account or can administer the organization."
            ),
        )
        return redirect(next_url)
    return authorized_installation


@login_required
async def github_app_setup(request):
    """Finish connecting a GitHub account after GitHub redirects back."""
    next_url = await _adefault_next_url(request)
    installation_id = request.GET.get("installation_id", "").strip()

    # Handle GitHub's stateless ``setup_on_update`` callback before the stricter
    # install permission gate: it is not started by Weblate and carries no
    # signed ``state``. Signed callbacks fall through to the normal setup flow
    # below.
    if request.GET.get("setup_action") == "update" and not request.GET.get("state"):
        configs = await aget_github_app_configurations()
        installation = await _aget_update_callback_installation(
            request, installation_id, configs
        )
        if installation:
            messages.success(
                request,
                gettext("Connected GitHub account updated."),
            )
            return redirect(_get_update_callback_next_url(request, installation))
        return await sync_to_async(_recover_update)(
            request, installation_id, next_url, configs
        )

    if response := await _ahandle_missing_github_app_access(request, next_url):
        return response

    hostname = ""
    workspace = None
    try:
        state = _load_install_state(
            request,
            request.GET.get("state", ""),
            default_next_url=next_url,
        )
        next_url = str(state["next"])
        hostname = str(state["host"])
        workspace = await _aget_installation_workspace(
            request.user,
            state["workspace"],
        )
    except (BadSignature, SignatureExpired):
        messages.error(
            request,
            gettext(
                "The Weblate GitHub app installation link is no longer valid. "
                "Start the installation again."
            ),
        )
        return redirect(next_url)
    except PermissionDenied:
        messages.error(
            request,
            gettext("You do not have permission to connect GitHub to this workspace."),
        )
        return redirect(next_url)

    callback_data = request.GET.copy()
    if state["installation_id"]:
        callback_data["installation_id"] = state["installation_id"]
    callback_form = GitHubAppSetupCallbackForm(callback_data)
    if not callback_form.is_valid() and "installation_id" in callback_form.errors:
        messages.error(
            request,
            gettext("GitHub did not return a valid installation ID."),
        )
        return redirect(next_url)
    installation_id = callback_form.cleaned_data["installation_id"]

    config = await aget_github_app_settings(hostname or None)
    if config is None:
        messages.error(
            request,
            gettext("Weblate GitHub app is not configured on this Weblate instance."),
        )
        return redirect(next_url)

    if workspace is None:
        messages.error(
            request,
            gettext("You do not have permission to connect GitHub to this workspace."),
        )
        return redirect(next_url)

    if not await sync_to_async(check_rate_limit)("github_setup", request):
        messages.error(
            request,
            gettext(
                "Too many GitHub account connection attempts. "
                "The GitHub installation was not connected and might still be "
                "pending. Try connecting the account again later."
            ),
        )
        return redirect(next_url)

    authorized_installation = await _verify_installation(
        request,
        config,
        workspace,
        next_url,
        installation_id,
        callback_form.cleaned_data.get("code", ""),
    )
    if isinstance(authorized_installation, HttpResponse):
        return authorized_installation
    (
        installation,
        is_new_install,
    ) = await GitHubInstallation.objects.aupsert_pending_from_data(
        config.hostname,
        installation_id,
        authorized_installation,
        workspace=workspace,
        enabled=True,
    )
    await sync_to_async(apply_pending_github_installation_event)(
        config.hostname, installation_id
    )
    try:
        (
            installation,
            synced_is_new_install,
        ) = await GitHubInstallation.objects.connect_workspace(
            config.hostname, installation_id, workspace
        )
        is_new_install = is_new_install or synced_is_new_install
    except Exception as error:
        await sync_to_async(report_error)(
            "Failed to connect GitHub account to workspace", exception=error
        )
        messages.warning(
            request,
            gettext(
                "GitHub is still syncing the connected GitHub account. "
                "The connection is pending and repositories might not appear yet. "
                "Try connecting the account again later if they do not show up."
            ),
        )
        return redirect(next_url)

    try:
        await installation.refresh_repositories()
    except Exception as error:
        await sync_to_async(report_error)(
            "Failed to refresh connected GitHub account repositories", exception=error
        )
        messages.warning(
            request,
            gettext(
                "The connected GitHub account was saved, but refreshing the "
                "repository list failed. Try again in a moment."
            ),
        )
    else:
        if is_new_install:
            messages.success(
                request,
                gettext("Connected GitHub account added."),
            )
        else:
            messages.success(
                request,
                gettext("Connected GitHub account updated."),
            )
    return redirect(next_url)


def _pagination_links(request, page, parameter, *, reset_page=False):
    def link(number):
        params = request.GET.copy()
        if reset_page:
            params.pop("page", None)
        params[parameter] = number
        return f"?{params.urlencode()}"

    return {
        "page": page,
        "previous": link(page.previous_page_number()) if page.has_previous() else None,
        "next": link(page.next_page_number()) if page.has_next() else None,
    }


def _can_create_migration_workspaces(user: User) -> bool:
    return "weblate.billing" not in settings.INSTALLED_APPS and bool(
        user.has_perm("workspace.add")
    )


def _move_projects_to_new_workspace(
    request: AuthenticatedHttpRequest,
    projects: Iterable[Project],
    name: str,
    *,
    delegate_ownership: bool,
) -> Workspace:
    user = request.user
    project_ids = {project.pk for project in projects}
    try:
        with transaction.atomic():
            lock_check_projects(project_ids, exclusive=True)
            locked = list(
                # Translation saves take a project key-share lock before the
                # check-boundary lock. Moving a project does not change its key.
                Project.objects.select_for_update(no_key=True)
                .filter(pk__in=project_ids)
                .order_by("pk")
            )
            if len(locked) != len(project_ids) or any(
                project.workspace_id is not None
                or not user.has_perm("project.edit", project)
                for project in locked
            ):
                raise ValidationError(
                    gettext("The project selection changed. Select the projects again.")
                )
            workspace = Workspace.objects.create(name=name)
            workspace.add_owner(user, request)
            user.clear_permissions_cache()
            for project in locked:
                if error := get_project_workspace_move_error(user, project, workspace):
                    raise ValidationError(error)
                if delegate_ownership:
                    for admin in project.all_admins.filter(is_active=True).exclude(
                        pk=user.pk
                    ):
                        if admin.has_perm("project.edit", project):
                            workspace.add_owner(admin, request)
                project.workspace = workspace
                project.save(update_fields=["workspace"])
            Change.objects.create(
                action=ActionEvents.CREATE_WORKSPACE,
                workspace=workspace,
                user=user,
                author=user,
            )
    finally:
        user.clear_permissions_cache()
    return workspace


@management_access
@require_http_methods(["GET", "POST"])
def github_site_migration(request, host):
    config = _configured_app_or_404(host)
    next_url = reverse(
        "manage-github-migration",
        args=[config.hostname],
        query={
            name: request.GET[name]
            for name in ("q", "projects_page", "unconnected_page", "connected_page")
            if name in request.GET
        },
    )
    query = request.GET.get("q", "").strip()
    can_create = _can_create_migration_workspaces(request.user)
    projects = request.user.accessible_managed_projects.filter(
        workspace__isnull=True
    ).order_by("name", "pk")
    workspaces = (
        Workspace.objects.only("name")
        .order_by("name", "pk")
        .annotate(
            has_connection=Exists(
                GitHubInstallation.objects.filter(
                    workspace_id=OuterRef("pk"),
                    hostname=host,
                    enabled=True,
                )
            )
        )
    )
    has_connected_workspaces = workspaces.filter(has_connection=True).exists()
    if query:
        projects = projects.filter(Q(name__icontains=query) | Q(slug__icontains=query))
        workspaces = workspaces.filter(name__icontains=query)
    project_page = Paginator(projects, LIST_PAGE_SIZE).get_page(
        request.GET.get("projects_page")
    )
    move_form = GitHubAppWorkspaceMoveForm(
        request.POST if request.method == "POST" else None,
        projects=project_page,
    )
    if request.method == "POST":
        if not can_create:
            raise PermissionDenied
        if move_form.is_valid():
            ids = set(move_form.cleaned_data["projects"])
            selected = [project for project in project_page if str(project.pk) in ids]
            separate = move_form.cleaned_data["destination"] == "separate"
            groups = (
                [
                    ([project], project.name[:WORKSPACE_NAME_LENGTH])
                    for project in selected
                ]
                if separate
                else [(selected, move_form.cleaned_data["name"])]
            )
            created_workspaces = []
            for group, name in groups:
                try:
                    destination = _move_projects_to_new_workspace(
                        request,
                        group,
                        name,
                        delegate_ownership=separate,
                    )
                except (
                    ValidationError,
                    WeblateLockTimeoutError,
                    RepositoryError,
                ) as error:
                    messages.error(
                        request,
                        gettext("Could not move projects to %(workspace)s: %(error)s")
                        % {
                            "workspace": name,
                            "error": " ".join(error.messages)
                            if isinstance(error, ValidationError)
                            else str(error),
                        },
                    )
                else:
                    created_workspaces.append(destination)
            request.session["github_migration_workspaces"] = [
                str(item.pk) for item in created_workspaces
            ]
            return redirect(next_url)

    destination_ids = request.session.pop("github_migration_workspaces", [])
    destinations = Workspace.objects.filter(pk__in=destination_ids).order_by(
        "name", "pk"
    )
    unconnected_page = Paginator(
        workspaces.filter(has_connection=False), LIST_PAGE_SIZE
    ).get_page(request.GET.get("unconnected_page"))
    connected_page = Paginator(
        workspaces.filter(has_connection=True), LIST_PAGE_SIZE
    ).get_page(request.GET.get("connected_page"))
    return render(
        request,
        "vcs/github_site_migration.html",
        {
            "config": config,
            "query": query,
            "project_pagination": _pagination_links(
                request, project_page, "projects_page"
            ),
            "unconnected_pagination": _pagination_links(
                request, unconnected_page, "unconnected_page"
            ),
            "connected_pagination": _pagination_links(
                request, connected_page, "connected_page"
            ),
            "unconnected": [
                (item, _get_workspace_install_url(next_url, host, item))
                for item in unconnected_page
            ],
            "connected": [
                (item, _get_workspace_install_url(next_url, host, item))
                for item in connected_page
            ],
            "has_connected_workspaces": has_connected_workspaces,
            "move_form": move_form,
            "can_create": can_create,
            "billing_enabled": "weblate.billing" in settings.INSTALLED_APPS,
            "destinations": [
                (item, _get_workspace_install_url(next_url, host, item))
                for item in destinations
            ],
            **_MENU_CONTEXT,
        },
    )


def _legacy_migration_components(user: User) -> ComponentQuerySet:
    return (
        Component.objects.filter(vcs__in=GITHUB_APP_MIGRATABLE_VCS)
        .filter_permission_scope(user, "component.edit")
        .with_repo()
        .select_related("project")
        .order_by("pk")
    )


def _ready_migration_candidates(
    user: User,
    components: Iterable[Component],
    inventories: dict[UUID, MigrationRepositories],
) -> Iterator[Component]:
    for component in components:
        workspace_id = component.project.workspace_id
        if (
            workspace_id is not None
            and user.has_perm("component.edit", component)
            and _get_github_app_migration_target(
                component, inventories.get(workspace_id, {})
            )
        ):
            yield component


def _migration_fingerprint(component: Component) -> str:
    return salted_hmac(
        _GITHUB_APP_MIGRATION_SALT,
        json.dumps(
            (
                component.project_id,
                str(component.project.workspace_id),
                component.vcs,
                component.repo,
                component.push,
                component.push_branch,
                component.vcs_params,
            ),
            sort_keys=True,
        ),
    ).hexdigest()


def _migrate_component(component: Component, canonical_url: str) -> None:
    vcs_params = component.vcs_params.copy()
    if component.vcs == "git":
        vcs_params["create_merge_request"] = False
    component.vcs = "github-app"
    component.repo = canonical_url
    component.push = ""
    component.push_branch = ""
    component.vcs_params = strip_unused_vcs_params(component.vcs, vcs_params)
    GithubAppRepository.validate_component(component)
    for alert in ("GitHubAppMigration", "PushFailure", "UpdateFailure"):
        component.delete_alert(alert)
    component.save(update_fields=("vcs", "repo", "push", "push_branch", "vcs_params"))


def _apply_component_migration(
    request: AuthenticatedHttpRequest,
    components: Iterable[Component],
    inventories: dict[UUID, MigrationRepositories],
    fingerprints: dict[str, str] | None = None,
) -> None:
    migrated = skipped = 0
    for source in components:
        workspace_id = source.project.workspace_id
        if workspace_id is None or not request.user.has_perm("component.edit", source):
            skipped += 1
            continue
        authorized_component = None
        try:
            with source.locked_for_update(lock_project_boundary=True) as component:
                request.user.clear_permissions_cache()
                if (
                    component.project_id == source.project_id
                    and component.project.workspace_id == workspace_id
                    and request.user.has_perm("component.edit", component)
                    and (
                        fingerprints is None
                        or fingerprints[str(component.pk)]
                        == _migration_fingerprint(component)
                    )
                    and (
                        target := _get_github_app_migration_target(
                            component, inventories.get(workspace_id, {})
                        )
                    )
                ):
                    authorized_component = component
                    _migrate_component(component, target)
        except Component.DoesNotExist:
            skipped += 1
        except (ValidationError, WeblateLockTimeoutError, RepositoryError) as error:
            # Locking can fail before we can authorize the refreshed component.
            if authorized_component is None:
                messages.error(
                    request, gettext("Could not lock a component for migration.")
                )
                continue
            messages.error(
                request,
                gettext("Could not migrate %(component)s: %(error)s")
                % {
                    "component": authorized_component.full_slug,
                    "error": " ".join(error.messages)
                    if isinstance(error, ValidationError)
                    else str(error),
                },
            )
        else:
            if authorized_component is None:
                skipped += 1
            else:
                migrated += 1

    if migrated:
        messages.success(
            request,
            ngettext(
                "Migrated one component to the Weblate GitHub App.",
                "Migrated %(count)d components to the Weblate GitHub App.",
                migrated,
            )
            % {"count": migrated},
        )
    if skipped:
        messages.warning(
            request,
            ngettext(
                "One component was no longer eligible for migration.",
                "%(count)d components were no longer eligible for migration.",
                skipped,
            )
            % {"count": skipped},
        )


def _configured_app_or_404(host: str) -> GitHubAppCredentials:
    configurations = get_github_app_configurations()
    if host not in configurations:
        raise Http404
    return configurations[host]


def _bulk_migration(request, *, workspace=None, host=None, app_id=None):
    if workspace is None:
        return_url = reverse("manage-github-migration", args=[host])
    else:
        return_url = reverse("workspace-integrations", args=[workspace.pk])
    components = _legacy_migration_components(request.user)
    if workspace is not None:
        components = components.filter(project__workspace=workspace)
    else:
        components = components.filter(
            Exists(
                GitHubInstallation.objects.filter(
                    workspace_id=OuterRef("project__workspace_id"),
                    enabled=True,
                    hostname=host,
                )
            ),
            # Narrow the candidates before parsing their repository URLs.
            repo__icontains=host,
        )

    scope = [request.user.pk, str(workspace.pk) if workspace else None, host, app_id]
    if request.method == "POST":
        try:
            payload = signing.loads(
                request.POST.get("preview", ""),
                salt=_GITHUB_APP_MIGRATION_SALT,
                max_age=_GITHUB_APP_STATE_MAX_AGE,
            )
        except BadSignature:
            payload = None
        if payload is None or payload["scope"] != scope:
            messages.error(
                request,
                gettext(
                    "The migration preview has expired. Open it again to continue."
                ),
            )
            return redirect(return_url)
        fingerprints = payload["components"]
        selected = list(components.filter(pk__in=fingerprints))
        # Only use inventories in the confirmed workspace or for the confirmed App.
        workspace_ids = {
            workspace_id
            for component in selected
            if (workspace_id := component.project.workspace_id) is not None
            and (workspace is None or workspace_id == workspace.pk)
        }
        inventories = _get_bulk_migration_inventories(workspace_ids, host)
        selected_ids = {str(component.pk) for component in selected}
        if selected_ids != fingerprints.keys():
            messages.warning(
                request,
                gettext(
                    "Some components in this preview are no longer eligible for migration."
                ),
            )
        _apply_component_migration(request, selected, inventories, fingerprints)
        if workspace is not None and payload["next_after"] is not None:
            return redirect(
                reverse(
                    "workspace-github-bulk-migration",
                    args=[workspace.pk],
                    query={"after": payload["next_after"]},
                )
            )
        return redirect(return_url)

    over_limit = False
    has_more = False
    if workspace is not None:
        after = request.GET.get("after", "")
        if after.isascii() and after.isdecimal() and len(after) < 19:
            components = components.filter(pk__gt=int(after))
        repositories, _, _ = _get_github_app_migration_repositories(workspace)
        ready = (
            list(
                islice(
                    _ready_migration_candidates(
                        request.user,
                        components.iterator(),
                        {workspace.pk: repositories},
                    ),
                    MIGRATION_BATCH_SIZE + 1,
                )
            )
            if repositories
            else []
        )
        has_more = len(ready) > MIGRATION_BATCH_SIZE
        ready = ready[:MIGRATION_BATCH_SIZE]
    else:
        candidate_ids = list(
            islice(
                (
                    component_id
                    for component_id, repo in components.values_list(
                        "pk", "repo"
                    ).iterator()
                    if (identity := get_github_repository_identity(repo))
                    and identity[0] == host
                ),
                MIGRATION_BATCH_SIZE + 1,
            )
        )
        over_limit = len(candidate_ids) > MIGRATION_BATCH_SIZE
        ready = []
        if not over_limit:
            candidates = list(components.filter(pk__in=candidate_ids))
            workspace_ids = {
                workspace_id
                for component in candidates
                if (workspace_id := component.project.workspace_id) is not None
            }
            inventories = _get_bulk_migration_inventories(workspace_ids, host)
            ready = list(
                _ready_migration_candidates(request.user, candidates, inventories)
            )

    prefetch_related_objects(ready, *component_settings_lookups(defer=True))
    preview = (
        signing.dumps(
            {
                "scope": scope,
                "components": {
                    str(component.pk): _migration_fingerprint(component)
                    for component in ready
                },
                "next_after": ready[-1].pk if has_more else None,
            },
            salt=_GITHUB_APP_MIGRATION_SALT,
        )
        if ready
        else ""
    )
    return render(
        request,
        "vcs/github_bulk_migration.html",
        {
            "workspace": workspace,
            "host": host,
            "return_url": return_url,
            "components": ready,
            "preview": preview,
            "over_limit": over_limit,
            "has_more": has_more,
            "batch_size": MIGRATION_BATCH_SIZE,
            **({} if workspace else _MENU_CONTEXT),
        },
    )


@management_access
@require_http_methods(["GET", "POST"])
def github_site_bulk_migration(request, host):
    config = _configured_app_or_404(host)
    return _bulk_migration(request, host=host, app_id=config.app_id)


@login_required
@require_http_methods(["GET", "POST"])
def github_workspace_bulk_migration(request, workspace_id):
    workspace = _get_workspace_integrations_workspace(request.user, workspace_id)
    return _bulk_migration(request, workspace=workspace)


@login_required
@require_http_methods(["GET", "POST"])
def legacy_github_app_migration(request, workspace_id):
    _get_workspace_integrations_workspace(request.user, workspace_id)
    return redirect(
        reverse("github-app-migration", args=[workspace_id], query=request.GET),
        preserve_request=request.method == "POST",
    )


@login_required
@require_http_methods(["GET", "POST"])
def github_app_migration(request, workspace_id):
    """Migrate existing GitHub components to a workspace GitHub App."""
    workspace = _get_workspace_integrations_workspace(request.user, workspace_id)
    host = request.GET.get("host") or None
    if host:
        _configured_app_or_404(host)
    entries, repositories, installations = _get_github_app_migration_entries(
        request.user, workspace, host
    )
    available_entries = [entry for entry in entries if entry["status"] == "ready"]
    unavailable_entries = [
        entry for entry in entries if entry["status"] == "access-needed"
    ]
    entries_by_id = {str(entry["component"].pk): entry for entry in available_entries}
    form = GitHubAppMigrationForm(
        request.POST if request.method == "POST" else None,
        component_choices=[
            (component_id, entry["component"].full_slug)
            for component_id, entry in entries_by_id.items()
        ],
    )
    if request.method == "POST" and form.is_valid():
        _apply_component_migration(
            request,
            [
                entries_by_id[component_id]["component"]
                for component_id in form.cleaned_data["components"]
            ],
            {workspace.pk: repositories},
        )
        return redirect(
            reverse("github-app-migration", args=[workspace.pk], query=request.GET)
        )

    for checkbox in form["components"]:
        entries_by_id[checkbox.data["value"]]["checkbox"] = checkbox
    required_accounts = sorted(
        {entry["full_name"].split("/", 1)[0] for entry in unavailable_entries},
        key=str.casefold,
    )
    return render(
        request,
        "vcs/github_app_migration.html",
        {
            "workspace": workspace,
            "entries": entries,
            "bread_image": "project.svg",
            "available_entries": available_entries,
            "unavailable_entries": unavailable_entries,
            "installations": installations,
            "can_manage_installations": _user_can_install_in_workspace(
                request.user, workspace
            ),
            "required_accounts": required_accounts,
            "form": form,
            "next_url": request.get_full_path(),
            "github_app_install_url": (
                _get_workspace_install_url(request.get_full_path(), host, workspace)
                if host
                else _get_install_link(request, request.get_full_path(), workspace)
            )
            if _user_can_install_in_workspace(request.user, workspace)
            else None,
            "host": host,
        },
    )


def _get_repository_import_project(
    request: AuthenticatedHttpRequest, projects: ProjectQuerySet
) -> tuple[Project | None, str]:
    user = request.user
    project = None
    project_id = request.GET.get("project", "").strip()
    category_id = request.GET.get("category", "").strip()
    if project_id:
        try:
            project = projects.select_related("workspace").get(pk=project_id)
        except (Project.DoesNotExist, ValueError) as error:
            raise PermissionDenied from error
    if category_id:
        try:
            category = Category.objects.select_related("project__workspace").get(
                pk=category_id,
                project__in=projects,
            )
        except (Category.DoesNotExist, ValueError) as error:
            raise PermissionDenied from error
        if project is not None and category.project_id != project.pk:
            raise PermissionDenied
        project = category.project
    if project is not None and not user.has_perm("project.edit", project):
        raise PermissionDenied

    return project, category_id


@login_required
@require_safe
def github_app_repository_list(request, *, for_creation=False):
    """List repositories from connected GitHub accounts for component creation."""
    user = request.user
    creation_projects = get_creation_projects(user)
    workspaces = _integration_workspaces(user)
    projects = creation_projects if for_creation else user.accessible_managed_projects
    if for_creation:
        workspaces = workspaces.filter(
            pk__in=projects.order_by().values_list("workspace_id", flat=True)
        )
    project, category_id = _get_repository_import_project(request, projects)
    picker_context = {"workspace_page": None}
    workspace_id = request.GET.get("workspace", "").strip()
    if project is not None:
        selected_workspace = project.workspace
        if workspace_id and (
            selected_workspace is None or str(selected_workspace.pk) != workspace_id
        ):
            raise PermissionDenied
    elif workspace_id:
        selected_workspace = _get_workspace(workspaces, workspace_id)
    else:
        matches = list(workspaces.defer_huge().order_by("name", "pk")[:2])
        if not matches and not creation_projects.exists():
            raise PermissionDenied
        selected_workspace = matches[0] if len(matches) == 1 else None
        if len(matches) > 1:
            picker_context = _workspace_picker_context(request, workspaces)

    configured_hosts = set(get_github_app_configurations())
    context = {
        **picker_context,
        "selected_workspace": selected_workspace,
        "github_app_configured": bool(configured_hosts),
        "next_url": request.get_full_path(),
    }
    if selected_workspace is None:
        return render(request, "vcs/github_repository_list.html", context)

    installations = GitHubInstallation.objects.filter(
        enabled=True,
        hostname__in=configured_hosts,
        workspace=selected_workspace,
    ).order_by(Lower("target_login"), "hostname", "pk")
    account_page = Paginator(installations, LIST_PAGE_SIZE).get_page(
        request.GET.get("accounts_page")
    )
    can_manage = _user_can_install_in_workspace(user, selected_workspace)
    if can_manage:
        GitHubInstallation.objects.prefetch_components(account_page)
    # Only index repositories for the accounts shown on this page.
    indexed: list[tuple[int, str, dict]] = []
    for installation in account_page:
        indexed.extend(
            (installation.pk, installation.target_login, repo)
            for repo in sorted(
                installation.repositories,
                key=lambda item: str(item.get("full_name", "")).casefold(),
            )
            if not repo.get("archived", False)
        )
    repo_page = Paginator(indexed, LIST_PAGE_SIZE).get_page(request.GET.get("page"))
    repositories = []
    for installation_id, account_name, repo in repo_page:
        entry = dict(repo, account_name=account_name)
        entry["import_url"] = get_github_repository_import_url(
            entry,
            installation_id=installation_id,
            project_id=project.pk if project else None,
            category_id=category_id,
            for_creation=for_creation,
        )
        repositories.append(entry)
    return render(
        request,
        "vcs/github_repository_list.html",
        {
            **context,
            "repositories": repositories,
            "page_obj": repo_page,
            "accounts_pagination": _pagination_links(
                request, account_page, "accounts_page", reset_page=True
            ),
            "installations": account_page.object_list,
            "can_manage": can_manage,
            "github_app_install_url": _get_install_link(
                request, request.get_full_path(), selected_workspace
            ),
        },
    )


@login_required
async def github_app_import_repository(
    request, pk, repo_full_name, *, for_creation=False
):
    """Import a repository selected from a connected GitHub account."""
    configured_hosts = set(await aget_github_app_configurations())
    installation = await aget_object_or_404(
        GitHubInstallation.objects.select_related("workspace"),
        pk=pk,
        enabled=True,
        hostname__in=configured_hosts,
    )
    await _arequire_installation_use(request, installation)

    repository = None
    for entry in installation.repositories:
        if entry.get("full_name") == repo_full_name and not entry.get(
            "archived", False
        ):
            repository = entry
            break
    if repository is None:
        raise PermissionDenied

    params = {
        "repo": repository["clone_url"],
        "branch": repository.get("default_branch", "main"),
        "vcs": "github-app",
        "name": repository["name"],
        "slug": slugify(repository["name"]),
    }

    project_id = request.GET.get("project", "").strip()
    if project_id:
        try:
            selected_project = await request.user.accessible_managed_projects.aget(
                pk=project_id
            )
        except (Project.DoesNotExist, ValueError) as error:
            raise PermissionDenied from error
        if not await sync_to_async(request.user.has_perm)(
            "project.edit", selected_project
        ):
            raise PermissionDenied
        if selected_project.workspace_id != installation.workspace_id:
            raise PermissionDenied
        params["project"] = selected_project.pk

    category_id = request.GET.get("category", "").strip()
    if category_id:
        try:
            selected_category = await Category.objects.select_related(
                "project__workspace"
            ).aget(
                pk=category_id,
                project__in=request.user.accessible_managed_projects,
            )
        except (Category.DoesNotExist, ValueError) as error:
            raise PermissionDenied from error
        if not await sync_to_async(request.user.has_perm)(
            "project.edit", selected_category.project
        ):
            raise PermissionDenied
        if selected_category.project.workspace_id != installation.workspace_id:
            raise PermissionDenied
        if project_id and params["project"] != selected_category.project_id:
            raise PermissionDenied
        params["category"] = selected_category.pk
        params.setdefault("project", selected_category.project.pk)

    if for_creation:
        creation_projects = await sync_to_async(get_creation_projects)(request.user)
        eligible_projects = creation_projects.filter(
            workspace_id=installation.workspace_id
        )
        if "project" in params:
            eligible_projects = eligible_projects.filter(pk=params["project"])
        if not await eligible_projects.aexists():
            raise PermissionDenied

    params[INTEGRATION_IMPORT_VCS_KEY] = "github-app"
    request.session[SESSION_CREATE_KEY] = params
    return redirect(
        f"{reverse('create-component-vcs')}?{urlencode({SESSION_CREATE_KEY: 1})}"
    )


def _get_register_webhook_token(request) -> str:
    """
    Return a stable webhook token for the in-progress registration.

    The token is baked into the App's webhook URL at manifest-build time and
    persisted on the credentials row once GitHub returns them, so it must stay
    constant between the preview, the submitted manifest and the callback.
    """
    token = request.session.get("github_app_register_webhook_token")
    if not token:
        token = str(uuid.uuid4())
        request.session["github_app_register_webhook_token"] = token
    return token


def _build_register_state(request, hostname: str, webhook_token: str) -> str:
    nonce = request.session.get("github_app_register_nonce")
    if not nonce:
        nonce = secrets.token_urlsafe(16)
        request.session["github_app_register_nonce"] = nonce
    return signing.dumps(
        {
            "user": request.user.pk,
            "nonce": nonce,
            "host": hostname,
            "webhook_token": webhook_token,
        },
        salt=_GITHUB_APP_REGISTER_SALT,
    )


def _load_register_state(request, state: str) -> tuple[str, str]:
    payload = signing.loads(
        state,
        salt=_GITHUB_APP_REGISTER_SALT,
        max_age=_GITHUB_APP_REGISTER_MAX_AGE,
    )
    if payload.get("user") != request.user.pk:
        msg = "State user mismatch"
        raise BadSignature(msg)
    if payload.get("nonce") != request.session.get("github_app_register_nonce"):
        msg = "State session mismatch"
        raise BadSignature(msg)
    hostname = payload.get("host", "")
    if not isinstance(hostname, str) or not hostname:
        msg = "State host missing"
        raise BadSignature(msg)
    webhook_token = payload.get("webhook_token", "")
    if not isinstance(webhook_token, str) or not webhook_token:
        msg = "State webhook token missing"
        raise BadSignature(msg)
    return normalize_github_app_hostname(hostname), webhook_token


def _default_register_name(request) -> str:
    host = request.get_host().split(":", 1)[0]
    return f"{settings.SITE_TITLE} ({host})"[:GITHUB_APP_NAME_MAX_LENGTH]


def _build_manifest_for_request(
    request, *, hostname: str, name: str, public: bool, webhook_token: str
) -> tuple[dict[str, object], str]:
    """Build the manifest JSON and the webhook URL used by the form."""
    base_url = get_site_url()
    redirect_url = get_site_url(reverse("github-app-register-callback"))
    setup_url = get_site_url(reverse("github-app-setup"))
    # The per-App hook URL embeds an opaque token so deliveries are
    # authenticated against exactly one App secret without guessing the host.
    webhook_url = get_site_url(
        reverse("integration-webhook", kwargs={"integration_token": webhook_token})
    )

    manifest = build_github_app_manifest(
        name=name,
        base_url=base_url,
        redirect_url=redirect_url,
        setup_url=setup_url,
        webhook_url=webhook_url,
        public=public,
    )
    return manifest, webhook_url


def _get_register_initial(request) -> dict[str, str | bool]:
    hostname = request.GET.get("host", "").strip()
    name = request.GET.get("name", "").strip() or _default_register_name(request)
    return {
        "host": clean_github_app_hostname(hostname) if hostname else "github.com",
        "org": request.GET.get("org", "").strip(),
        "name": name[:GITHUB_APP_NAME_MAX_LENGTH],
        "public": True,
    }


def _render_github_app_register(
    request,
    register_form: GitHubAppRegisterForm,
    *,
    hostname: str,
    name: str,
    public: bool,
    status: int = 200,
):
    webhook_token = _get_register_webhook_token(request)
    manifest, webhook_url = _build_manifest_for_request(
        request,
        hostname=hostname,
        name=name,
        public=public,
        webhook_token=webhook_token,
    )

    existing_hosts = list(
        GitHubAppCredentials.objects.order_by("hostname").values_list(
            "hostname", flat=True
        )
    )
    return render(
        request,
        "vcs/github_app_register.html",
        {
            "manifest_json": json.dumps(manifest, indent=2, sort_keys=True),
            "register_form": register_form,
            "hostname": hostname,
            "name": name,
            "permissions": GITHUB_APP_MANIFEST_PERMISSIONS,
            "events": GITHUB_APP_MANIFEST_EVENTS,
            "webhook_url": webhook_url,
            "existing_hosts": existing_hosts,
            "host_already_registered": hostname in existing_hosts,
            **_MENU_CONTEXT,
        },
        status=status,
    )


@management_permission_required("management.configure")
def github_app_register(request):
    """Render the GitHub App registration form (editable host/org/name)."""
    try:
        initial = _get_register_initial(request)
    except ValidationError:
        messages.error(request, gettext("Enter a valid GitHub host."))
        initial = {
            "host": "github.com",
            "org": "",
            "name": _default_register_name(request),
            "public": True,
        }
    register_form = GitHubAppRegisterForm(initial=initial)
    hostname = str(initial["host"])
    name = str(initial["name"])
    public = bool(initial["public"])

    return _render_github_app_register(
        request,
        register_form,
        hostname=hostname,
        name=name,
        public=public,
    )


@management_permission_required("management.configure")
def github_app_register_submit(request):
    """Render the intermediate page that posts the manifest to GitHub."""
    if request.method != "POST":
        return redirect("github-app-register")

    form = GitHubAppRegisterForm(data=request.POST)
    if not form.is_valid():
        messages.error(
            request,
            gettext("Enter a valid GitHub App name and host."),
        )
        return redirect("github-app-register")
    hostname = form.cleaned_data["host"]
    org = form.cleaned_data["org"]
    name = form.cleaned_data["name"]
    public = form.cleaned_data["public"]
    if GitHubAppCredentials.objects.filter(hostname=hostname).exists():
        form.add_error(
            "host",
            gettext(
                "A Weblate GitHub App is already registered for %(hostname)s. "
                "Remove it before registering another one."
            )
            % {"hostname": hostname},
        )
        return _render_github_app_register(
            request,
            form,
            hostname=hostname,
            name=name,
            public=public,
        )

    webhook_token = _get_register_webhook_token(request)
    manifest, _webhook_url = _build_manifest_for_request(
        request,
        hostname=hostname,
        name=name,
        public=public,
        webhook_token=webhook_token,
    )
    state = _build_register_state(request, hostname, webhook_token)
    action_url = (
        f"{get_github_app_manifest_new_url(hostname, org or None)}"
        f"?{urlencode({'state': state})}"
    )
    request.csp_form_action_sources = (f"https://{hostname}",)

    return render(
        request,
        "vcs/github_app_register_submit.html",
        {
            "action_url": action_url,
            "manifest_json": json.dumps(manifest),
            "hostname": hostname,
            "org": org,
            "name": name,
            **_MENU_CONTEXT,
        },
    )


@management_permission_required("management.configure")
async def github_app_register_callback(request):
    """Exchange a temporary manifest code for the App's credentials."""
    accounts_url = reverse("manage-github-accounts")
    callback_form = GitHubAppRegisterCallbackForm(request.GET)
    if not callback_form.is_valid():
        messages.error(
            request,
            gettext("GitHub did not return a valid registration code."),
        )
        return redirect(accounts_url)
    code = callback_form.cleaned_data["code"]

    try:
        hostname, webhook_token = _load_register_state(
            request, request.GET.get("state", "")
        )
    except (BadSignature, SignatureExpired):
        messages.error(
            request,
            gettext(
                "The GitHub App registration link is no longer valid. "
                "Start the registration again."
            ),
        )
        return redirect(accounts_url)

    try:
        data = await exchange_github_app_manifest_code(code, hostname)
    except Exception as error:
        await sync_to_async(report_error)(
            "Failed to exchange GitHub App manifest code", exception=error
        )
        messages.error(
            request,
            gettext(
                "GitHub rejected the registration code. Start the registration again."
            ),
        )
        return redirect(accounts_url)

    pem = str(data.get("pem", "")).strip()
    # GitHub returns ``id`` as a JSON number; coerce to str so the model
    # CharField accepts it.
    app_id = str(data.get("id", "")).strip()
    app_slug = str(data.get("slug", "")).strip()
    webhook_secret = str(data.get("webhook_secret", "")).strip()
    client_id = str(data.get("client_id", "")).strip()
    client_secret = str(data.get("client_secret", "")).strip()
    if (
        not pem
        or not app_id
        or not app_slug
        or not webhook_secret
        or not client_id
        or not client_secret
    ):
        messages.error(
            request,
            gettext("GitHub returned an incomplete App registration response."),
        )
        return redirect(accounts_url)

    credentials, created = await GitHubAppCredentials.objects.aupdate_or_create(
        hostname=hostname,
        defaults={
            "app_id": app_id,
            "app_slug": app_slug,
            "private_key": pem,
            "webhook_secret": webhook_secret,
            "webhook_token": webhook_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "html_url": str(data.get("html_url", "")).strip(),
        },
    )
    request.session.pop("github_app_register_nonce", None)
    request.session.pop("github_app_register_webhook_token", None)
    logger.info(
        "Registered Weblate GitHub App %s for %s (new=%s)",
        credentials.app_slug,
        credentials.hostname,
        created,
    )
    if created:
        messages.success(
            request,
            gettext(
                "Weblate GitHub App registered. You can now connect a GitHub account."
            ),
        )
    else:
        messages.success(
            request,
            gettext("Weblate GitHub App credentials updated."),
        )
    return redirect(accounts_url)
