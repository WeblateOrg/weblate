# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import logging
import secrets
import uuid
from collections import defaultdict
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.signing import BadSignature, SignatureExpired
from django.http import HttpResponse, HttpResponseNotAllowed
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
from weblate.utils.site import get_site_url
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
    get_user_accessible_installation,
    github_app_is_configured,
    normalize_github_app_hostname,
)
from weblate.wladmin.views import MENU
from weblate.workspaces.models import Workspace

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


def _user_can_install_github_app(user) -> bool:
    return _managed_workspaces(user).exists()


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


def _get_managed_workspace(user, workspace_id) -> Workspace:
    try:
        return _managed_workspaces(user).get(pk=workspace_id)
    except (Workspace.DoesNotExist, ValidationError, ValueError) as error:
        raise PermissionDenied from error


def _get_install_workspace(request) -> Workspace | None:
    workspace_id = request.GET.get("workspace", "").strip()
    if workspace_id:
        return _get_managed_workspace(request.user, workspace_id)
    workspaces = list(_managed_workspaces(request.user))
    if len(workspaces) == 1:
        return workspaces[0]
    return None


def _get_install_link(
    request, next_url: str | None = None, workspace: Workspace | None = None
) -> str | None:
    if not github_app_is_configured():
        return None
    if workspace is None:
        workspace = _get_install_workspace(request)
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


def _user_can_manage_installation(user, installation: GitHubInstallation) -> bool:
    return (
        user.has_perm("management.use")
        or _managed_workspaces(user).filter(pk=installation.workspace_id).exists()
    )


def _require_installation_access(request, installation: GitHubInstallation) -> None:
    if not _user_can_manage_installation(request.user, installation):
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
                ]
            apps.append(
                {
                    "hostname": hostname,
                    "app_slug": config.app_slug if config is not None else "",
                    "html_url": config.html_url if config is not None else "",
                    "configured": config is not None,
                    "installations": installations_by_host.get(hostname, []),
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
    that the installation appears in the user's own installation list.
    """
    if not code:
        return None
    try:
        user_token = exchange_github_user_code(config, code)
        return get_user_accessible_installation(config, user_token, installation_id)
    except Exception:
        report_error("Failed to verify GitHub installation ownership")
        return None


@login_required
def github_app_setup(request):
    """Finish connecting a GitHub account after GitHub redirects back."""
    _require_github_app_access(request)

    next_url = _default_next_url(request)
    hostname = ""
    workspace = None
    try:
        state = _load_install_state(request, request.GET.get("state", ""))
        next_url = str(state["next"])
        hostname = str(state["host"])
        workspace = _get_managed_workspace(request.user, state["workspace"])
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

    installation_id = request.GET.get("installation_id", "").strip()
    if not installation_id:
        messages.error(
            request,
            gettext("GitHub did not return an installation ID."),
        )
        return redirect(next_url)

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

    code = request.GET.get("code", "").strip()
    authorized_installation = _get_authorized_installation(
        request, config, code, installation_id
    )
    if authorized_installation is None:
        messages.error(
            request,
            gettext(
                "Weblate could not confirm that you have access to this GitHub "
                "installation. Start the installation again and approve the "
                "authorization request."
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
        messages.info(
            request,
            gettext(
                "GitHub is still syncing the connected account. "
                "The repositories will appear here once the webhook is processed."
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

    selected_workspace = _get_install_workspace(request)
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
    _require_installation_access(request, installation)

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
    return f"Weblate ({host})"[:GITHUB_APP_NAME_MAX_LENGTH]


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


def _read_register_fields(request) -> tuple[str, str, str, bool]:
    """Pull (hostname, org, name, public) from the request."""
    source = request.POST if request.method == "POST" else request.GET
    hostname_raw = source.get("host", "").strip() or "github.com"
    hostname = normalize_github_app_hostname(hostname_raw)
    org = source.get("org", "").strip()
    name = source.get("name", "").strip() or _default_register_name(request)
    # GitHub rejects App names longer than 34 characters; truncate so we never
    # build a manifest GitHub will refuse.
    name = name[:GITHUB_APP_NAME_MAX_LENGTH]
    # Unticked checkboxes are absent from POST data; default the form to
    # public on the initial GET so the visibility checkbox starts checked.
    public = source.get("public") == "1" if request.method == "POST" else True
    return hostname, org, name, public


@management_permission_required("management.configure")
def github_app_register(request):
    """Render the GitHub App registration form (editable host/org/name)."""
    hostname, org, name, public = _read_register_fields(request)

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
            "hostname": hostname,
            "org": org,
            "name": name,
            "public": public,
            "name_max_length": GITHUB_APP_NAME_MAX_LENGTH,
            "permissions": GITHUB_APP_MANIFEST_PERMISSIONS,
            "events": GITHUB_APP_MANIFEST_EVENTS,
            "webhook_url": webhook_url,
            "existing_hosts": existing_hosts,
            "host_already_registered": hostname in existing_hosts,
            **_MENU_CONTEXT,
        },
    )


@management_permission_required("management.configure")
def github_app_register_submit(request):
    """Render the intermediate page that posts the manifest to GitHub."""
    if request.method != "POST":
        return redirect("github-app-register")

    hostname, org, name, public = _read_register_fields(request)
    if GitHubAppCredentials.objects.filter(hostname=hostname).exists():
        messages.error(
            request,
            gettext(
                "A Weblate GitHub App is already registered for %(hostname)s. "
                "Remove it before registering another one."
            )
            % {"hostname": hostname},
        )
        return redirect("manage-github-accounts")

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
    # The intermediate form posts to ``github_app_register_redirect`` (same
    # origin, allowed by CSP form-action 'self'); that view answers with a 307
    # that re-sends the manifest body to GitHub.
    request.session["github_app_register_action_url"] = action_url

    return render(
        request,
        "vcs/github_app_register_submit.html",
        {
            "manifest_json": json.dumps(manifest),
            "hostname": hostname,
            "org": org,
            "name": name,
            **_MENU_CONTEXT,
        },
    )


@management_permission_required("management.configure")
def github_app_register_redirect(request):
    """
    307-redirect the POSTed manifest to GitHub, preserving the body.

    The browser's CSP only checks the form ``action`` URL against
    ``form-action``; redirects are not validated, so we can stay within
    ``'self'`` while still POSTing the manifest cross-origin to GitHub.
    """
    if request.method != "POST":
        return redirect("github-app-register")

    action_url = request.session.pop("github_app_register_action_url", None)
    if not action_url or not action_url.startswith("https://"):
        messages.error(
            request,
            gettext(
                "Start the Weblate GitHub App registration again to refresh "
                "the request."
            ),
        )
        return redirect("github-app-register")

    response = HttpResponse(status=307)
    response["Location"] = action_url
    return response


@management_permission_required("management.configure")
def github_app_register_callback(request):
    """Exchange a temporary manifest code for the App's credentials."""
    accounts_url = reverse("manage-github-accounts")
    code = request.GET.get("code", "").strip()
    if not code:
        messages.error(
            request,
            gettext("GitHub did not return a registration code."),
        )
        return redirect(accounts_url)

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
