# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext_lazy

from weblate.trans.actions import ActionEvents
from weblate.trans.alerts.base import (
    AlertCategory,
    AlertSeverity,
    BaseAlert,
    ErrorAlert,
)
from weblate.trans.alerts.registry import register
from weblate.trans.hooks.matching import (
    HOOK_MATCH_EXACT,
    HOOK_MATCH_FALLBACK,
    repo_matches_exact_repos,
)
from weblate.vcs.base import (
    is_ssh_host_key_mismatch_error,
    is_ssh_host_key_verification_error,
)

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.trans.models.component import Component


@register
class InexactHookMatch(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Repository hook matched inexactly.")
    category = AlertCategory.VCS
    severity = AlertSeverity.WARNING
    dismissible = True
    doc_page = "admin/continuous"
    doc_anchor = "update-vcs"

    def __init__(
        self,
        instance,
        service_long_name: str = "",
        repo_url: str = "",
        branch: str = "",
        full_name: str = "",
    ) -> None:
        super().__init__(instance)
        self.service_long_name = service_long_name
        self.repo_url = repo_url
        self.branch = branch
        self.full_name = full_name

    @staticmethod
    def get_change_details(change) -> dict[str, str]:
        details = change.details
        return {
            "service_long_name": str(details.get("service_long_name") or ""),
            "repo_url": str(details.get("repo_url") or ""),
            "branch": str(details.get("branch") or ""),
            "full_name": str(details.get("full_name") or ""),
        }

    @classmethod
    def check_component(cls, component: Component) -> bool | dict | None:
        change = (
            component.change_set.filter(action=ActionEvents.HOOK)
            .order_by("-id")
            .first()
        )
        if change is None:
            return False

        if change.details.get("match_method") == HOOK_MATCH_EXACT:
            return False
        if change.details.get("match_method") == HOOK_MATCH_FALLBACK:
            return cls.get_change_details(change)

        repos = change.details.get("repos")
        if (
            isinstance(repos, list)
            and all(isinstance(repo, str) for repo in repos)
            and repo_matches_exact_repos(component.repo, repos)
        ):
            return False

        return cls.get_change_details(change)


@register
class ConflictingRepositorySetup(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Conflicting repository setup.")
    category = AlertCategory.VCS

    def __init__(self, instance, component_ids: list[int]) -> None:
        super().__init__(instance)
        self.component_ids = component_ids

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        conflicts = list(
            component.get_conflicting_setup_components().values_list("id", flat=True)
        )
        if conflicts:
            return {"component_ids": conflicts}
        return False

    def get_analysis(self) -> dict[str, Any]:
        return {"repo_link": self.instance.component.get_repo_link_url()}

    def get_context(self, user: User) -> dict[str, Any]:
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Component

        result = super().get_context(user)
        result["analysis"]["conflicts"] = list(
            Component.objects.filter(pk__in=self.component_ids)
            .filter_access(user)
            .select_related("project")
            .order_by("project__slug", "slug")
        )
        return result


@register
class MergeFailure(ErrorAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not merge the repository.")
    category = AlertCategory.VCS
    link_wide = True
    doc_page = "faq"
    doc_anchor = "merge"


class BaseGitFailure(ErrorAlert):
    category = AlertCategory.VCS
    link_wide = True
    behind_messages = (
        "The tip of your current branch is behind its remote counterpart",
        "fetch first",
    )
    terminal_message = "terminal prompts disabled"
    not_found_messages = (
        "Repository not found.",
        "HTTP Error 404: Not Found",
        "Repository was archived so is read-only",
        "does not appear to be a git repository",
    )
    temporary_messages = (
        "Empty reply from server",
        "no suitable response from remote hg",
        "cannot lock ref",
        "Too many retries",
        "Connection timed out",
    )
    permission_messages = (
        "denied to",
        "The repository exists, but forking is disabled.",
        "protected branch hook declined",
        "GH006:",
    )
    gerrit_messages = (
        "is not registered in your account, and you lack 'forge",
        "prohibited by Gerrit",
    )

    def get_analysis(self) -> dict[str, Any]:
        terminal_disabled = self.terminal_message in self.error
        repo_suggestion = None
        force_push_suggestion = False
        component = self.instance.component
        host_key_mismatch = is_ssh_host_key_mismatch_error(self.error)
        host_key = (
            is_ssh_host_key_verification_error(self.error) and not host_key_mismatch
        )
        host_key_message = None
        if host_key_mismatch:
            host_key_message = component.get_ssh_host_key_mismatch_error_message()
        elif host_key:
            host_key_message = component.get_ssh_host_key_error_message()

        if terminal_disabled:
            if component.push:
                if component.push.startswith("https://github.com/"):
                    repo_suggestion = f"git@github.com:{component.push[19:]}"
            elif component.repo.startswith("https://github.com/"):
                repo_suggestion = f"git@github.com:{component.repo[19:]}"

        behind = any(message in self.error for message in self.behind_messages)
        if behind:
            force_push_suggestion = (
                component.vcs == "git"
                and component.merge_style == "rebase"
                and bool(component.push_branch)
            )

        return {
            "terminal": terminal_disabled,
            "behind": behind,
            "repo_suggestion": repo_suggestion,
            "force_push_suggestion": force_push_suggestion,
            "host_key_message": host_key_message,
            "not_found": any(
                message in self.error for message in self.not_found_messages
            ),
            "permission": any(
                message in self.error for message in self.permission_messages
            ),
            "gerrit": any(message in self.error for message in self.gerrit_messages),
            "temporary": any(
                message in self.error for message in self.temporary_messages
            ),
        }


@register
class PushFailure(BaseGitFailure):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not push the repository.")

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        if not component.can_push():
            return False
        return None


@register
class UpdateFailure(BaseGitFailure):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not update the repository.")
    link_wide = True
    doc_page = "admin/projects"
    doc_anchor = "component-repo"


@register
class RepositoryOutdated(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Repository outdated.")
    category = AlertCategory.VCS
    link_wide = True


@register
class RepositoryChanges(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Repository has changes.")
    category = AlertCategory.VCS
    link_wide = True
    dismissible = True
