# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import logging
import secrets
import uuid
from collections import defaultdict
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.signing import BadSignature, SignatureExpired
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.utils.translation import gettext
from django.views import View

from weblate.auth.decorators import management_access, management_permission_required
from weblate.trans.models import Category, Project
from weblate.trans.views.create import INTEGRATION_IMPORT_VCS_KEY, SESSION_CREATE_KEY
from weblate.trans.views.hooks import apply_pending_github_installation_event
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.ratelimit import check_rate_limit
from weblate.utils.site import get_site_url
from weblate.vcs.forms import (
    GitHubAppRegisterCallbackForm,
    GitHubAppRegisterForm,
    GitHubAppSetupCallbackForm,
    clean_github_app_hostname,
)
from weblate.vcs.github import (
    GITHUB_APP_MANIFEST_EVENTS,
    GITHUB_APP_MANIFEST_PERMISSIONS,
    GITHUB_APP_NAME_MAX_LENGTH,
    GitHubAppCredentials,
    GitHubInstallation,
    build_github_app_manifest,
    exchange_github_app_manifest_code,
    exchange_github_user_code,
    get_github_app_configurations,
    get_github_app_install_url,
    get_github_app_manifest_new_url,
    get_github_app_settings,
    get_github_repository_import_url,
    get_user_admin_installation,
    github_app_is_configured,
    normalize_github_app_hostname,
)
from weblate.vcs.permissions import (
    github_app_installation_workspaces,
    user_can_install_github_app_in_workspace,
)
from weblate.wladmin.views import MENU
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from weblate.auth.results import PermissionResult

logger = logging.getLogger(__name__)

_MENU_CONTEXT = {"menu_items": MENU, "menu_page": "github"}
_GITHUB_APP_STATE_SALT = "weblate.vcs.github.install"
_GITHUB_APP_STATE_MAX_AGE = 60 * 60
_GITHUB_APP_REGISTER_SALT = "weblate.vcs.github.register"
_GITHUB_APP_REGISTER_MAX_AGE = 60 * 60


def _managed_workspaces(user):
    """Return workspaces the user can manage."""
    return (
        Workspace.objects.filter(projects__in=user.managed_projects)
        | user.workspaces_with_perm("workspace.edit")
    ).distinct()


def _installation_workspaces(user):
    return github_app_installation_workspaces(user)


def _user_can_install_github_app(user) -> bool:
    return _installation_workspaces(user).exists()


def _require_github_app_access(request) -> None:
    if not _user_can_install_github_app(request.user):
        raise PermissionDenied


def _default_next_url(request, workspace: Workspace | None = None) -> str:
    if workspace is not None:
        return (
            f"{reverse('github-app-repositories')}?"
            f"{urlencode({'workspace': workspace.pk})}"
        )
    if _managed_workspaces(request.user).exists():
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


def _get_managed_workspace(user, workspace_id) -> Workspace:
    return _get_workspace(_managed_workspaces(user), workspace_id)


def _get_installation_workspace(user, workspace_id) -> Workspace:
    return _get_workspace(_installation_workspaces(user), workspace_id)


def _get_requested_workspace(request, workspaces) -> Workspace | None:
    workspace_id = request.GET.get("workspace", "").strip()
    if workspace_id:
        return _get_workspace(workspaces, workspace_id)
    workspaces = list(workspaces)
    if len(workspaces) == 1:
        return workspaces[0]
    return None


def _get_managed_request_workspace(request) -> Workspace | None:
    return _get_requested_workspace(request, _managed_workspaces(request.user))


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


def _build_install_state(
    request, next_url: str, hostname: str, workspace: Workspace
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
            "host": hostname,
            "workspace": str(workspace.pk),
        },
        salt=_GITHUB_APP_STATE_SALT,
    )


def _load_install_state(request, state: str) -> dict[str, str]:
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
        next_url = _default_next_url(request)

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


def _user_can_use_installation(user, installation: GitHubInstallation) -> bool:
    return (
        user.has_perm("management.use")
        or _managed_workspaces(user).filter(pk=installation.workspace_id).exists()
    )


def _user_can_manage_installation(user, installation: GitHubInstallation) -> bool:
    return _installation_workspaces(user).filter(pk=installation.workspace_id).exists()


def _require_installation_access(request, installation: GitHubInstallation) -> None:
    if not _user_can_manage_installation(request.user, installation):
        raise PermissionDenied


def _require_installation_use(request, installation: GitHubInstallation) -> None:
    if not _user_can_use_installation(request.user, installation):
        raise PermissionDenied


@method_decorator(management_access, name="dispatch")
class GitHubInstallationListView(View):
    def get(self, request):
        installations = list(
            GitHubInstallation.objects.select_related("workspace").order_by("-created")
        )
        installations_by_host: defaultdict[str, list[GitHubInstallation]] = defaultdict(
            list
        )
        for installation in installations:
            installations_by_host[installation.hostname].append(installation)

        configurations = get_github_app_configurations()
        apps = []
        for hostname in sorted(configurations):
            config = configurations[hostname]
            host_installations = installations_by_host.get(hostname, [])
            apps.append(
                {
                    "hostname": hostname,
                    "app_id": config.app_id,
                    "app_slug": config.app_slug,
                    "html_url": config.html_url,
                    "credentials_pk": config.pk,
                    "installations": host_installations,
                    "can_remove": (
                        request.user.has_perm("management.configure")
                        and not host_installations
                    ),
                    "install_url": _get_install_link(
                        request,
                        reverse("manage-github-accounts"),
                    ),
                }
            )

        return render(
            request,
            "vcs/github_installation_list.html",
            {
                "apps": apps,
                "github_app_configured": bool(apps),
                "github_app_install_url": _get_install_link(
                    request, reverse("manage-github-accounts")
                ),
                "github_app_register_url": (
                    reverse("github-app-register")
                    if request.user.has_perm("management.configure")
                    else None
                ),
                **_MENU_CONTEXT,
            },
        )


@method_decorator(login_required, name="dispatch")
class UserVCSIntegrationListView(View):
    def get(self, request):
        workspace_queryset = _managed_workspaces(request.user).order_by("name")
        selected_workspace = None
        workspace_id = request.GET.get("workspace", "").strip()
        if workspace_id:
            selected_workspace = _get_managed_workspace(request.user, workspace_id)
            workspaces = [selected_workspace]
        else:
            workspaces = list(workspace_queryset)

        installations = list(
            GitHubInstallation.objects.filter(workspace__in=workspaces)
            .select_related("workspace")
            .order_by("hostname", "workspace__name", "target_login")
        )
        manageable_installations = {
            installation.pk
            for installation in installations
            if _user_can_manage_installation(request.user, installation)
        }
        installations_by_host: defaultdict[str, list[GitHubInstallation]] = defaultdict(
            list
        )
        for installation in installations:
            installations_by_host[installation.hostname].append(installation)

        configurations = get_github_app_configurations() if workspaces else {}
        apps = []
        for hostname in sorted(set(configurations) | set(installations_by_host)):
            config = configurations.get(hostname)
            workspace_links = []
            if config is not None:
                workspace_links = [
                    {
                        "workspace": workspace,
                        "install_url": _get_workspace_install_url(
                            request.get_full_path(), hostname, workspace
                        ),
                    }
                    for workspace in workspaces
                    if _user_can_install_in_workspace(request.user, workspace)
                ]
            apps.append(
                {
                    "hostname": hostname,
                    "app_slug": config.app_slug if config is not None else "",
                    "html_url": config.html_url if config is not None else "",
                    "configured": config is not None,
                    "installations": installations_by_host.get(hostname, []),
                    "manageable_installations": manageable_installations,
                    "workspace_links": workspace_links,
                }
            )

        return render(
            request,
            "vcs/account_integrations.html",
            {
                "apps": apps,
                "managed_workspaces": workspaces,
                "next_url": request.get_full_path(),
                "selected_workspace": selected_workspace,
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
                "repositories": repositories,
                "github_app_install_url": _get_install_link(
                    request,
                    reverse("manage-github-account-detail", kwargs={"pk": pk}),
                    installation.workspace,
                ),
                "app_configured": app_configured,
                **_MENU_CONTEXT,
            },
        )


@login_required
def remove_installation(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    installation = get_object_or_404(GitHubInstallation, pk=pk)
    _require_installation_access(request, installation)
    next_url = _get_redirect_url(
        request,
        (
            reverse("manage-github-accounts")
            if request.user.has_perm("management.use")
            else _get_installation_repository_url(installation)
        ),
    )
    target = str(installation)
    installation.delete()
    messages.success(
        request,
        gettext("Removed connected GitHub account %(target)s.") % {"target": target},
    )
    return redirect(next_url)


@management_permission_required("management.configure")
def remove_github_app(request, pk):
    """Delete the Weblate GitHub App credentials registered for one host."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    credentials = get_object_or_404(GitHubAppCredentials, pk=pk)
    hostname = credentials.hostname
    if GitHubInstallation.objects.filter(hostname=hostname).exists():
        messages.error(
            request,
            gettext(
                "Remove connected GitHub accounts on %(hostname)s before removing the app credentials."
            )
            % {"hostname": hostname},
        )
        return redirect("manage-github-accounts")
    credentials.delete()
    messages.success(
        request,
        gettext("Removed Weblate GitHub App credentials for %(hostname)s.")
        % {"hostname": hostname},
    )
    return redirect("manage-github-accounts")


@login_required
def refresh_repositories(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    installation = get_object_or_404(GitHubInstallation, pk=pk)
    _require_installation_access(request, installation)
    next_url = _get_redirect_url(
        request,
        _get_installation_repository_url(installation),
    )
    try:
        repos = installation.refresh_repositories()
    except Exception:
        report_error("Failed to refresh connected GitHub account repositories")
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
    _require_github_app_access(request)

    next_url = _get_next_url(request)
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
                **_MENU_CONTEXT,
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

    return redirect(install_url)


def _get_authorized_installation(request, config, code, installation_id) -> dict | None:
    """
    Return the installation when the current user controls it via OAuth.

    Exchanges the install-time ``code`` for a user-to-server token and checks
    that the user owns or administers the selected installation.
    """
    if not code:
        return None
    try:
        user_token = exchange_github_user_code(config, code)
        return get_user_admin_installation(config, user_token, installation_id)
    except Exception:
        report_error("Failed to verify GitHub installation ownership")
        return None


def _get_update_callback_installation(
    request, installation_id: str
) -> GitHubInstallation | None:
    """
    Return an existing accessible installation for GitHub's update callback.

    GitHub redirects users to the App setup URL after changing repository access
    when ``setup_on_update`` is enabled. That callback is not started by Weblate,
    so it might not carry a current signed ``state``. Only accept it for rows
    already connected to a workspace the current Weblate user can manage.
    """
    if request.GET.get("setup_action") != "update" or not installation_id:
        return None

    configured_hosts = set(get_github_app_configurations())
    if not configured_hosts:
        return None

    return (
        GitHubInstallation.objects.filter(
            hostname__in=configured_hosts,
            installation_id=installation_id,
            workspace__in=_managed_workspaces(request.user),
        )
        .select_related("workspace")
        .order_by("workspace__name", "target_login", "hostname")
        .first()
    )


def _get_update_callback_next_url(request, installation: GitHubInstallation) -> str:
    if request.user.has_perm("management.use"):
        return reverse("manage-github-account-detail", kwargs={"pk": installation.pk})
    return _get_installation_repository_url(installation)


@login_required
def github_app_setup(request):
    """Finish connecting a GitHub account after GitHub redirects back."""
    next_url = _default_next_url(request)
    installation_id = request.GET.get("installation_id", "").strip()
    installation = _get_update_callback_installation(request, installation_id)
    if installation:
        messages.success(
            request,
            gettext("Connected GitHub account updated."),
        )
        return redirect(_get_update_callback_next_url(request, installation))
    if request.GET.get("setup_action") == "update":
        messages.error(
            request,
            gettext(
                "The Weblate GitHub app installation link is no longer valid. "
                "Start the installation again."
            ),
        )
        return redirect(next_url)

    _require_github_app_access(request)

    hostname = ""
    workspace = None
    try:
        state = _load_install_state(request, request.GET.get("state", ""))
        next_url = str(state["next"])
        hostname = str(state["host"])
        workspace = _get_installation_workspace(request.user, state["workspace"])
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

    callback_form = GitHubAppSetupCallbackForm(request.GET)
    if not callback_form.is_valid() and "installation_id" in callback_form.errors:
        messages.error(
            request,
            gettext("GitHub did not return a valid installation ID."),
        )
        return redirect(next_url)
    installation_id = callback_form.cleaned_data["installation_id"]

    config = get_github_app_settings(hostname or None)
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

    if not check_rate_limit("github_setup", request):
        messages.error(
            request,
            gettext(
                "Too many GitHub account connection attempts. "
                "The GitHub installation was not connected and might still be "
                "pending. Try connecting the account again later."
            ),
        )
        return redirect(next_url)

    code = callback_form.cleaned_data.get("code", "")
    authorized_installation = _get_authorized_installation(
        request, config, code, installation_id
    )
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
    installation, is_new_install = GitHubInstallation.objects.upsert_pending_from_data(
        config.hostname,
        installation_id,
        authorized_installation,
        workspace=workspace,
        enabled=True,
    )
    apply_pending_github_installation_event(config.hostname, installation_id)
    try:
        installation, synced_is_new_install = (
            GitHubInstallation.objects.connect_workspace(
                config.hostname, installation_id, workspace
            )
        )
        is_new_install = is_new_install or synced_is_new_install
    except Exception:
        report_error("Failed to connect GitHub account to workspace")
        messages.warning(
            request,
            gettext(
                "GitHub is still syncing the connected account. "
                "The connection is pending and repositories might not appear yet. "
                "Try connecting the account again later if they do not show up."
            ),
        )
        return redirect(next_url)

    try:
        installation.refresh_repositories()
    except Exception:
        report_error("Failed to refresh connected GitHub account repositories")
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


@login_required
def github_app_repository_list(request):
    """List repositories from connected GitHub accounts for component creation."""
    workspaces = _managed_workspaces(request.user)
    if not workspaces.exists():
        raise PermissionDenied

    selected_workspace = _get_managed_request_workspace(request)
    selected_project = None
    selected_project_without_workspace = False
    project_id = request.GET.get("project", "").strip()
    if project_id:
        try:
            selected_project = request.user.managed_projects.get(pk=project_id)
        except (Project.DoesNotExist, ValueError) as error:
            raise PermissionDenied from error
        if selected_project.workspace_id is None:
            selected_project_without_workspace = True
        else:
            selected_workspace = selected_project.workspace

    category_id = request.GET.get("category", "").strip()
    configured_hosts = set(get_github_app_configurations())
    installations = GitHubInstallation.objects.filter(
        enabled=True, hostname__in=configured_hosts, workspace__in=workspaces
    ).select_related("workspace")
    if selected_project_without_workspace:
        installations = installations.none()
    elif selected_workspace is not None:
        installations = installations.filter(workspace=selected_workspace)
    installations = installations.order_by(
        "workspace__name", "target_login", "hostname"
    )
    manageable_installations = {
        installation.pk
        for installation in installations
        if _user_can_manage_installation(request.user, installation)
    }
    all_repos = []
    for installation in installations:
        for repo in installation.repositories:
            if repo.get("archived", False):
                continue
            entry = dict(repo)
            entry["installation_id"] = installation.pk
            entry["account_name"] = installation.target_login
            entry["workspace_id"] = str(installation.workspace_id)
            entry["workspace_name"] = installation.workspace.name
            entry["import_url"] = get_github_repository_import_url(
                entry,
                installation_id=installation.pk,
                project_id=selected_project.pk if selected_project else None,
                category_id=category_id,
            )
            all_repos.append(entry)

    return render(
        request,
        "vcs/github_repository_list.html",
        {
            "repositories": all_repos,
            "installations": installations,
            "manageable_installations": manageable_installations,
            "selected_workspace": selected_workspace,
            "selected_project": selected_project,
            "next_url": request.get_full_path(),
            "github_app_configured": github_app_is_configured(),
            "github_app_install_url": _get_install_link(
                request, request.get_full_path(), selected_workspace
            ),
        },
    )


@login_required
def github_app_import_repository(request, pk, repo_full_name):
    """Import a repository selected from a connected GitHub account."""
    configured_hosts = set(get_github_app_configurations())
    installation = get_object_or_404(
        GitHubInstallation.objects.select_related("workspace"),
        pk=pk,
        enabled=True,
        hostname__in=configured_hosts,
    )
    _require_installation_use(request, installation)

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
            selected_project = request.user.managed_projects.get(pk=project_id)
        except (Project.DoesNotExist, ValueError) as error:
            raise PermissionDenied from error
        if selected_project.workspace_id != installation.workspace_id:
            raise PermissionDenied
        params["project"] = selected_project.pk

    category_id = request.GET.get("category", "").strip()
    if category_id:
        try:
            selected_category = Category.objects.get(
                pk=category_id, project__in=request.user.managed_projects
            )
        except (Category.DoesNotExist, ValueError) as error:
            raise PermissionDenied from error
        if selected_category.project.workspace_id != installation.workspace_id:
            raise PermissionDenied
        params["category"] = selected_category.pk
        params.setdefault("project", selected_category.project.pk)

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
    # The per-integration hook URL embeds an opaque token so deliveries are
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
def github_app_register_callback(request):
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
        data = exchange_github_app_manifest_code(code, hostname)
    except Exception:
        report_error("Failed to exchange GitHub App manifest code")
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

    credentials, created = GitHubAppCredentials.objects.update_or_create(
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
