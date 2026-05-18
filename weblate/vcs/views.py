# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import secrets
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.signing import BadSignature, SignatureExpired
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy
from django.views import View

from weblate.auth.decorators import management_access
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.vcs.github import (
    GitHubInstallation,
    get_github_app_configurations,
    get_github_app_install_url,
    get_github_app_settings,
    github_app_is_configured,
    normalize_github_app_hostname,
)
from weblate.wladmin.views import MENU

logger = logging.getLogger(__name__)

_MENU_CONTEXT = {"menu_items": MENU, "menu_page": "github"}
_GITHUB_APP_STATE_SALT = "weblate.vcs.github.install"
_GITHUB_APP_STATE_MAX_AGE = 60 * 60


def _user_can_install_github_app(user) -> bool:
    return user.has_perm("project.add") or user.has_perm("management.use")


def _require_github_app_access(request) -> None:
    if not _user_can_install_github_app(request.user):
        raise PermissionDenied


def _default_next_url(request) -> str:
    if request.user.has_perm("project.add"):
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


def _get_install_link(request, next_url: str | None = None) -> str | None:
    if not github_app_is_configured():
        return None
    target = next_url or request.get_full_path()
    return f"{reverse('github-app-install')}?{urlencode({'next': target})}"


def _get_installable_configs() -> dict[str, dict[str, str]]:
    return {
        hostname: config
        for hostname, config in get_github_app_configurations().items()
        if config["webhook_secret"]
    }


def _get_install_choices(next_url: str) -> list[dict[str, str]]:
    install_url = reverse("github-app-install")
    return [
        {
            "hostname": hostname,
            "app_slug": config["app_slug"],
            "install_url": f"{install_url}?{urlencode({'next': next_url, 'host': hostname})}",
        }
        for hostname, config in sorted(_get_installable_configs().items())
    ]


def _build_install_state(request, next_url: str, hostname: str) -> str:
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

    return {
        "next": next_url,
        "host": normalize_github_app_hostname(hostname) if hostname else "",
    }


@method_decorator(management_access, name="dispatch")
class GitHubInstallationListView(View):
    def get(self, request):
        return render(
            request,
            "vcs/github_installation_list.html",
            {
                "installations": GitHubInstallation.objects.all().order_by("-created"),
                "github_app_configured": github_app_is_configured(),
                "github_app_install_url": _get_install_link(
                    request, reverse("manage-github-accounts")
                ),
                **_MENU_CONTEXT,
            },
        )


@method_decorator(management_access, name="dispatch")
class GitHubInstallationDetailView(View):
    def get(self, request, pk):
        installation = get_object_or_404(GitHubInstallation, pk=pk)
        return render(
            request,
            "vcs/github_installation_detail.html",
            {
                "installation": installation,
                "repositories": installation.repositories,
                "github_app_install_url": _get_install_link(
                    request, reverse("manage-github-account-detail", kwargs={"pk": pk})
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
                "install_choices": _get_install_choices(next_url),
                "next_url": next_url,
                **_MENU_CONTEXT,
            },
        )
    else:
        host = next(iter(configs))

    try:
        install_url = get_github_app_install_url(
            _build_install_state(request, next_url, host),
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
    try:
        state = _load_install_state(request, request.GET.get("state", ""))
        next_url = state["next"]
        hostname = state["host"]
    except (BadSignature, SignatureExpired):
        messages.error(
            request,
            gettext_lazy(
                "The Weblate GitHub app installation link is no longer valid. Start the installation again."
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

    installation = GitHubInstallation.objects.get_for_installation(
        config["hostname"], installation_id
    )
    if installation is None:
        messages.info(
            request,
            gettext_lazy(
                "GitHub is still syncing the connected account. "
                "The repositories will appear here once the webhook is processed."
            ),
        )
        return redirect(next_url)

    # A first-time connect has no created_by yet (the row was just made by
    # the GitHub installation webhook). A returning user reconfiguring repos hits
    # this view with the row already attributed to them.
    is_new_install = installation.created_by_id is None
    if is_new_install:
        installation.created_by = request.user
        installation.save(update_fields=["created_by"])

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
    if not request.user.has_perm("project.add"):
        raise PermissionDenied

    installations = GitHubInstallation.objects.filter(enabled=True).order_by(
        "target_login", "hostname"
    )
    all_repos = []
    for installation in installations:
        for repo in installation.repositories:
            entry = dict(repo)
            entry["installation_id"] = installation.pk
            entry["account_name"] = str(installation)
            all_repos.append(entry)

    return render(
        request,
        "vcs/github_repository_list.html",
        {
            "repositories": all_repos,
            "installations": installations,
            "github_app_configured": github_app_is_configured(),
            "github_app_install_url": _get_install_link(
                request, reverse("github-app-repositories")
            ),
        },
    )
