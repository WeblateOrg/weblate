# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib import admin

from weblate.vcs.github import GitHubAppCredentials, GitHubInstallation
from weblate.wladmin.models import WeblateModelAdmin


@admin.register(GitHubInstallation)
class GitHubInstallationAdmin(WeblateModelAdmin):
    list_display = (
        "target_login",
        "workspace",
        "hostname",
        "installation_id",
        "enabled",
        "created",
    )
    list_filter = ("enabled", "hostname", "target_type", "workspace")
    search_fields = ("target_login", "installation_id", "workspace__name")
    readonly_fields = ("created", "repositories_updated")


@admin.register(GitHubAppCredentials)
class GitHubAppCredentialsAdmin(WeblateModelAdmin):
    list_display = ("app_slug", "hostname", "app_id", "created", "updated")
    search_fields = ("app_slug", "hostname", "app_id")
    readonly_fields = ("created", "updated")
