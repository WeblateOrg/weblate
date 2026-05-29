# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import logging
import secrets
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.signing import BadSignature, SignatureExpired
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy
from django.views import View

from weblate.auth.decorators import management_access
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
    get_github_app_configurations,
    get_github_app_install_url,
    get_github_app_manifest_new_url,
    get_github_app_settings,
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
    """Return workspaces the user can manage (via any managed project)."""
    return Workspace.objects.filter(projects__in=user.managed_projects).distinct()


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
    except (Workspace.DoesNotExist, ValueError) as error:
        raise PermissionDenied from error


def _get_install_workspace(request) -> Workspace | None:
    workspace_id = request.GET.get("workspace", "").strip()
    if workspace_id:
        return _get_managed_workspace(request.user, workspace_id)
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


def _get_installable_configs() -> dict[str, dict[str, str]]:
    return {
        hostname: config
        for hostname, config in get_github_app_configurations().items()
        if config["webhook_secret"]
    }


def _get_install_choices(next_url: str, workspace: Workspace) -> list[dict[str, str]]:
    install_url = reverse("github-app-install")
    result = []
    for hostname, config in sorted(_get_installable_configs().items()):
        query = urlencode(
            {"next": next_url, "host": hostname, "workspace": workspace.pk}
        )
        result.append(
            {
                "hostname": hostname,
                "app_slug": config["app_slug"],
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


@method_decorator(management_access, name="dispatch")
class GitHubInstallationListView(View):
    def get(self, request):
        installations = list(
            GitHubInstallation.objects.select_related("workspace").order_by("-created")
        )
        installations_by_host: dict[str, list[GitHubInstallation]] = {}
        for installation in installations:
            installations_by_host.setdefault(installation.hostname, []).append(
                installation
            )

        configurations = get_github_app_configurations()
        db_credentials = {
            row.hostname: row
            for row in GitHubAppCredentials.objects.order_by("hostname")
        }
        apps = []
        for hostname in sorted(configurations):
            config = configurations[hostname]
            credentials = db_credentials.get(hostname)
            host_installations = installations_by_host.get(hostname, [])
            apps.append(
                {
                    "hostname": hostname,
                    "app_id": config.get("app_id"),
                    "app_slug": config.get("app_slug"),
                    "html_url": credentials.html_url if credentials else "",
                    "is_db_managed": credentials is not None,
                    "credentials_pk": credentials.pk if credentials else None,
                    "installations": host_installations,
                    "install_url": _get_install_link(
                        request,
                        reverse("manage-github-accounts"),
                    )
                    if config.get("webhook_secret")
                    else None,
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
                "github_app_register_url": reverse("github-app-register"),
                **_MENU_CONTEXT,
            },
        )


@method_decorator(management_access, name="dispatch")
class GitHubInstallationDetailView(View):
    def get(self, request, pk):
        installation = get_object_or_404(
            GitHubInstallation.objects.select_related("workspace"), pk=pk
        )
        return render(
            request,
            "vcs/github_installation_detail.html",
            {
                "installation": installation,
                "repositories": installation.repositories,
                "github_app_install_url": _get_install_link(
                    request,
                    reverse("manage-github-account-detail", kwargs={"pk": pk}),
                    installation.workspace,
                ),
                "app_configured": get_github_app_settings(installation.hostname)
                is not None,
                **_MENU_CONTEXT,
            },
        )


@management_access
def remove_installation(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    installation = get_object_or_404(GitHubInstallation, pk=pk)
    target = str(installation)
    installation.delete()
    messages.success(
        request,
        gettext_lazy("Removed connected GitHub account %(target)s.")
        % {"target": target},
    )
    return redirect("manage-github-accounts")


@management_access
def remove_github_app(request, pk):
    """Delete the Weblate GitHub App credentials registered for one host."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    credentials = get_object_or_404(GitHubAppCredentials, pk=pk)
    hostname = credentials.hostname
    credentials.delete()
    messages.success(
        request,
        gettext_lazy("Removed Weblate GitHub App credentials for %(hostname)s.")
        % {"hostname": hostname},
    )
    return redirect("manage-github-accounts")


@management_access
def refresh_repositories(request, pk):
    installation = get_object_or_404(GitHubInstallation, pk=pk)
    try:
        repos = installation.refresh_repositories()
    except Exception:
        report_error("Failed to refresh connected GitHub account repositories")
        return JsonResponse(
            {"status": "error", "message": "Failed to refresh repositories"},
            status=500,
        )
    return JsonResponse({"status": "success", "count": len(repos)})


@login_required
def github_app_install(request):
    """Start the Weblate GitHub app installation flow."""
    _require_github_app_access(request)

    next_url = _get_next_url(request)
    configs = _get_installable_configs()
    if not configs:
        messages.error(
            request,
            gettext_lazy(
                "Weblate GitHub app is not configured on this Weblate instance."
            ),
        )
        return redirect(next_url)

    workspace = _get_install_workspace(request)
    if workspace is None:
        messages.error(
            request,
            gettext_lazy("Select a workspace before connecting a GitHub account."),
        )
        return redirect(next_url)

    host = request.GET.get("host", "").strip()
    if host:
        host = normalize_github_app_hostname(host)
        if host not in configs:
            messages.error(
                request,
                gettext_lazy(
                    "Weblate GitHub app is not configured for the selected host."
                ),
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
            gettext_lazy(
                "Weblate GitHub app is not configured on this Weblate instance."
            ),
        )
        return redirect(next_url)

    return redirect(install_url)


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
            gettext_lazy(
                "The Weblate GitHub app installation link is no longer valid. "
                "Start the installation again."
            ),
        )
        return redirect(next_url)
    except PermissionDenied:
        messages.error(
            request,
            gettext_lazy(
                "You do not have permission to connect GitHub to this workspace."
            ),
        )
        return redirect(next_url)

    installation_id = request.GET.get("installation_id", "").strip()
    if not installation_id:
        messages.error(
            request,
            gettext_lazy("GitHub did not return an installation ID."),
        )
        return redirect(next_url)

    config = get_github_app_settings(hostname or None)
    if config is None:
        messages.error(
            request,
            gettext_lazy(
                "Weblate GitHub app is not configured on this Weblate instance."
            ),
        )
        return redirect(next_url)

    if workspace is None:
        messages.error(
            request,
            gettext_lazy(
                "You do not have permission to connect GitHub to this workspace."
            ),
        )
        return redirect(next_url)
    try:
        installation, is_new_install = GitHubInstallation.objects.connect_workspace(
            config["hostname"], installation_id, workspace
        )
    except Exception:
        report_error("Failed to connect GitHub account to workspace")
        messages.info(
            request,
            gettext_lazy(
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
            gettext_lazy(
                "The connected GitHub account was saved, but refreshing the "
                "repository list failed. Try again in a moment."
            ),
        )
    else:
        if is_new_install:
            messages.success(
                request,
                gettext_lazy("Connected GitHub account added."),
            )
        else:
            messages.success(
                request,
                gettext_lazy("Connected GitHub account updated."),
            )
    return redirect(next_url)


@login_required
def github_app_repository_list(request):
    """List repositories from connected GitHub accounts for component creation."""
    workspaces = _managed_workspaces(request.user)
    if not workspaces.exists():
        raise PermissionDenied

    selected_workspace = _get_install_workspace(request)
    installations = GitHubInstallation.objects.filter(
        enabled=True, workspace__in=workspaces
    ).select_related("workspace")
    if selected_workspace is not None:
        installations = installations.filter(workspace=selected_workspace)
    installations = installations.order_by(
        "workspace__name", "target_login", "hostname"
    )
    all_repos = []
    for installation in installations:
        for repo in installation.repositories:
            entry = dict(repo)
            entry["installation_id"] = installation.pk
            entry["account_name"] = str(installation)
            entry["workspace_id"] = str(installation.workspace_id)
            entry["workspace_name"] = installation.workspace.name
            all_repos.append(entry)

    return render(
        request,
        "vcs/github_repository_list.html",
        {
            "repositories": all_repos,
            "installations": installations,
            "selected_workspace": selected_workspace,
            "github_app_configured": github_app_is_configured(),
            "github_app_install_url": _get_install_link(
                request, request.get_full_path(), selected_workspace
            ),
        },
    )


def _build_register_state(request, hostname: str) -> str:
    nonce = request.session.get("github_app_register_nonce")
    if not nonce:
        nonce = secrets.token_urlsafe(16)
        request.session["github_app_register_nonce"] = nonce
    return signing.dumps(
        {"user": request.user.pk, "nonce": nonce, "host": hostname},
        salt=_GITHUB_APP_REGISTER_SALT,
    )


def _load_register_state(request, state: str) -> str:
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
    return normalize_github_app_hostname(hostname)


def _default_register_name(request) -> str:
    host = request.get_host().split(":", 1)[0]
    return f"Weblate ({host})"[:GITHUB_APP_NAME_MAX_LENGTH]


def _build_manifest_for_request(
    request, *, hostname: str, name: str, public: bool
) -> tuple[dict[str, object], str]:
    """Build the manifest JSON and the webhook URL used by the form."""
    base_url = get_site_url()
    redirect_url = get_site_url(reverse("github-app-register-callback"))
    setup_url = get_site_url(reverse("github-app-setup"))
    webhook_url = get_site_url(reverse("webhook", kwargs={"service": "github-app"}))
    if hostname != "github.com":
        webhook_url = f"{webhook_url}?host={hostname}"

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


@management_access
def github_app_register(request):
    """Render the GitHub App registration form (editable host/org/name)."""
    hostname, org, name, public = _read_register_fields(request)

    manifest, webhook_url = _build_manifest_for_request(
        request, hostname=hostname, name=name, public=public
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


@management_access
def github_app_register_submit(request):
    """Render the intermediate page that posts the manifest to GitHub."""
    if request.method != "POST":
        return redirect("github-app-register")

    hostname, org, name, public = _read_register_fields(request)
    if GitHubAppCredentials.objects.filter(hostname=hostname).exists():
        messages.error(
            request,
            gettext_lazy(
                "A Weblate GitHub App is already registered for %(hostname)s. "
                "Remove it before registering another one."
            )
            % {"hostname": hostname},
        )
        return redirect("manage-github-accounts")

    manifest, _webhook_url = _build_manifest_for_request(
        request, hostname=hostname, name=name, public=public
    )
    state = _build_register_state(request, hostname)
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


@management_access
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
            gettext_lazy(
                "Start the Weblate GitHub App registration again to refresh "
                "the request."
            ),
        )
        return redirect("github-app-register")

    response = HttpResponse(status=307)
    response["Location"] = action_url
    return response


@management_access
def github_app_register_callback(request):
    """Exchange a temporary manifest code for the App's credentials."""
    accounts_url = reverse("manage-github-accounts")
    code = request.GET.get("code", "").strip()
    if not code:
        messages.error(
            request,
            gettext_lazy("GitHub did not return a registration code."),
        )
        return redirect(accounts_url)

    try:
        hostname = _load_register_state(request, request.GET.get("state", ""))
    except (BadSignature, SignatureExpired):
        messages.error(
            request,
            gettext_lazy(
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
            gettext_lazy(
                "GitHub rejected the registration code. Start the registration again."
            ),
        )
        return redirect(accounts_url)

    pem = data.get("pem", "").strip()
    # GitHub returns ``id`` as a JSON number; coerce to str so the model
    # CharField accepts it.
    app_id = str(data.get("id", "")).strip()
    app_slug = data.get("slug", "").strip()
    webhook_secret = data.get("webhook_secret", "").strip()
    if not pem or not app_id or not app_slug or not webhook_secret:
        messages.error(
            request,
            gettext_lazy("GitHub returned an incomplete App registration response."),
        )
        return redirect(accounts_url)

    credentials, created = GitHubAppCredentials.objects.update_or_create(
        hostname=hostname,
        defaults={
            "app_id": app_id,
            "app_slug": app_slug,
            "private_key": pem,
            "webhook_secret": webhook_secret,
            "html_url": data.get("html_url", "").strip(),
        },
    )
    request.session.pop("github_app_register_nonce", None)
    logger.info(
        "Registered Weblate GitHub App %s for %s (new=%s)",
        credentials.app_slug,
        credentials.hostname,
        created,
    )
    if created:
        messages.success(
            request,
            gettext_lazy(
                "Weblate GitHub App registered. You can now connect a GitHub account."
            ),
        )
    else:
        messages.success(
            request,
            gettext_lazy("Weblate GitHub App credentials updated."),
        )
    return redirect(accounts_url)
