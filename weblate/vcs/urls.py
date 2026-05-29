# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.urls import path

from weblate.vcs.views import (
    GitHubInstallationDetailView,
    GitHubInstallationListView,
    github_app_install,
    github_app_register,
    github_app_register_callback,
    github_app_register_redirect,
    github_app_register_submit,
    github_app_repository_list,
    github_app_setup,
    refresh_repositories,
    remove_github_app,
    remove_installation,
)

urlpatterns = [
    path(
        "manage/integrations/",
        GitHubInstallationListView.as_view(),
        name="manage-github-accounts",
    ),
    path(
        "manage/integrations/register/",
        github_app_register,
        name="github-app-register",
    ),
    path(
        "manage/integrations/register/submit/",
        github_app_register_submit,
        name="github-app-register-submit",
    ),
    path(
        "manage/integrations/register/redirect/",
        github_app_register_redirect,
        name="github-app-register-redirect",
    ),
    path(
        "manage/integrations/register/callback/",
        github_app_register_callback,
        name="github-app-register-callback",
    ),
    path(
        "manage/integrations/<int:pk>/",
        GitHubInstallationDetailView.as_view(),
        name="manage-github-account-detail",
    ),
    path(
        "manage/integrations/<int:pk>/refresh/",
        refresh_repositories,
        name="manage-github-account-refresh",
    ),
    path(
        "manage/integrations/<int:pk>/remove/",
        remove_installation,
        name="manage-github-account-remove",
    ),
    path(
        "manage/integrations/apps/<int:pk>/remove/",
        remove_github_app,
        name="manage-github-app-remove",
    ),
    path(
        "create/component/github-app/",
        github_app_repository_list,
        name="github-app-repositories",
    ),
    path(
        "integrations/github/install/",
        github_app_install,
        name="github-app-install",
    ),
    path(
        "integrations/github/setup/",
        github_app_setup,
        name="github-app-setup",
    ),
]
