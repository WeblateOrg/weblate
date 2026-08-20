# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext, gettext_lazy

from weblate.trans.alerts.base import (
    AlertCategory,
    BaseAlert,
    ErrorAlert,
)
from weblate.trans.alerts.registry import register
from weblate.utils.docs import get_doc_url
from weblate.vcs.base import (
    RepositoryDiagnosis,
    RepositoryDiagnosisCode,
    RepositoryErrorCode,
    RepositoryStructuredError,
    format_stored_repository_error,
    get_repository_error_diagnoses,
)

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.trans.models.component import Component


REPOSITORY_URL_INVALID_ERRORS: frozenset[RepositoryErrorCode] = frozenset(
    {
        "repository_url_invalid",
        "repository_url_parse_invalid",
        "repository_url_parse_failed",
    }
)
REPOSITORY_URL_PRIVATE_ERRORS: frozenset[RepositoryErrorCode] = frozenset(
    {
        "repository_url_backend_unsupported",
        "repository_url_host_not_allowed",
        "repository_url_private_target",
    }
)
REPOSITORY_URL_RESOLUTION_ERRORS: frozenset[RepositoryErrorCode] = frozenset(
    {
        "repository_ssh_destination_unresolved",
        "repository_ssh_destination_unresolved_with_error",
        "repository_url_unresolved",
        "repository_url_unresolved_with_error",
    }
)


def normalize_repository_error_fingerprint(error: str) -> str:
    """Normalize legacy repository URL redaction in alert identities."""
    return error.replace("repository URL", "...")


class RepositoryAlert(BaseAlert):
    category = AlertCategory.VCS
    repository_permissions: tuple[str, ...] = ()

    @classmethod
    def can_user_act_for(
        cls, user: User, component: Component, details: dict[str, Any]
    ) -> bool:
        return super().can_user_act_for(user, component, details) or any(
            user.has_perm(permission, component)
            for permission in cls.repository_permissions
        )


class RepositoryErrorAlert(ErrorAlert):
    category = AlertCategory.VCS
    repository_permissions: tuple[str, ...] = ()

    def __init__(
        self,
        instance,
        error: str | RepositoryStructuredError,
        diagnoses: list[RepositoryDiagnosis] | None = None,
    ) -> None:
        self.stored_error = error
        canonical_error = format_stored_repository_error(error)
        super().__init__(instance, canonical_error)
        self.diagnoses = (
            get_repository_error_diagnoses(canonical_error)
            if diagnoses is None
            else diagnoses
        )

    def get_context(self, user: User) -> dict[str, Any]:
        result = super().get_context(user)
        result["error"] = format_stored_repository_error(self.stored_error, gettext)
        return result

    def has_diagnosis(self, code: RepositoryDiagnosisCode) -> bool:
        """Return whether the alert contains a diagnosis code."""
        return any(diagnosis.get("code") == code for diagnosis in self.diagnoses)

    def get_diagnosis_params(
        self, code: RepositoryDiagnosisCode
    ) -> dict[str, str] | None:
        """Return parameters for the first matching diagnosis."""
        for diagnosis in self.diagnoses:
            if diagnosis.get("code") == code:
                return diagnosis.get("params", {})
        return None

    @property
    def error_code(self) -> RepositoryErrorCode | None:
        if isinstance(self.stored_error, dict):
            return self.stored_error["code"]
        return None

    @property
    def is_repository_url_error(self) -> bool:
        return self.error_code is not None and self.error_code.startswith(
            ("repository_redirect", "repository_ssh_destination_", "repository_url_")
        )

    def get_instance_documentation_url(self, user: User | None = None) -> str:
        if self.is_repository_url_error:
            return get_doc_url("vcs", "vcs-repository-url-troubleshooting", user=user)
        return super().get_instance_documentation_url(user)

    def get_analysis(self) -> dict[str, Any]:
        error_code = self.error_code
        return {
            "redirect": self.has_diagnosis("repository_redirect"),
            "git_lfs_missing_objects": self.has_diagnosis("git_lfs_missing_objects"),
            "repository_url_failure": self.is_repository_url_error,
            "repository_url_backend_unsupported": (
                error_code == "repository_url_backend_unsupported"
            ),
            "repository_url_invalid": error_code in REPOSITORY_URL_INVALID_ERRORS,
            "repository_url_private": error_code in REPOSITORY_URL_PRIVATE_ERRORS,
            "repository_url_redirect": (
                error_code is not None and error_code.startswith("repository_redirect")
            ),
            "repository_url_resolution": (
                error_code in REPOSITORY_URL_RESOLUTION_ERRORS
            ),
            "repository_url_scheme": (
                error_code == "repository_url_scheme_not_allowed"
            ),
        }

    @classmethod
    def get_dismissal_context(
        cls, _component: Component, details: dict[str, Any]
    ) -> dict[str, Any]:
        """Exclude diagnosis metadata from the repository failure identity."""
        identity_details = {
            key: value
            for key, value in details.items()
            if key not in {"diagnoses", "error"}
        }
        if error := details.get("error"):
            identity_details["error"] = normalize_repository_error_fingerprint(
                format_stored_repository_error(error)
            )
        return {"details": identity_details}

    @classmethod
    def can_user_act_for(
        cls, user: User, component: Component, details: dict[str, Any]
    ) -> bool:
        return super().can_user_act_for(user, component, details) or any(
            user.has_perm(permission, component)
            for permission in cls.repository_permissions
        )


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
class MergeFailure(RepositoryErrorAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not merge the repository.")
    category = AlertCategory.VCS
    link_wide = True
    doc_page = "faq"
    doc_anchor = "merge"
    repository_permissions = ("vcs.update", "vcs.reset")


@register
class RepositoryOperationFailure(RepositoryErrorAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not recover the repository.")
    category = AlertCategory.VCS
    link_wide = True
    doc_page = "admin/projects"
    doc_anchor = "component-repo"
    repository_permissions = ("vcs.reset",)


class BaseGitFailure(RepositoryErrorAlert):
    category = AlertCategory.VCS
    link_wide = True

    def get_analysis(self) -> dict[str, Any]:
        analysis = super().get_analysis()
        github_pull_request_params = self.get_diagnosis_params(
            "github_pull_request_creation_restricted"
        )
        terminal_disabled = self.has_diagnosis("missing_credentials")
        repo_suggestion = None
        force_push_suggestion = False
        component = self.instance.component
        host_key_mismatch = self.has_diagnosis("ssh_host_key_mismatch")
        host_key = self.has_diagnosis("ssh_host_key_unverified")
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

        behind = self.has_diagnosis("branch_behind")
        if behind:
            force_push_suggestion = (
                component.vcs == "git"
                and component.merge_style == "rebase"
                and bool(component.push_branch)
            )

        return {
            **analysis,
            "terminal": terminal_disabled,
            "behind": behind,
            "repo_suggestion": repo_suggestion,
            "force_push_suggestion": force_push_suggestion,
            "host_key_message": host_key_message,
            "not_found": self.has_diagnosis("repository_not_found"),
            "permission": self.has_diagnosis("repository_permission"),
            "gerrit": self.has_diagnosis("gerrit_permission"),
            "temporary": self.has_diagnosis("temporary_failure"),
            "github_pull_request_creation_restricted": (
                github_pull_request_params is not None
            ),
            "github_pull_request_creation_restricted_username": (
                github_pull_request_params.get("username")
                if github_pull_request_params
                else None
            ),
        }


@register
class PushFailure(BaseGitFailure):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not push the repository.")
    repository_permissions = ("vcs.push", "vcs.reset")

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
    repository_permissions = ("vcs.update", "vcs.reset")


@register
class RepositoryOutdated(RepositoryAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Repository outdated.")
    category = AlertCategory.VCS
    link_wide = True
    doc_page = "admin/continuous"
    doc_anchor = "update-vcs"
    repository_permissions = ("vcs.update", "vcs.reset")


@register
class RepositoryChanges(RepositoryAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Repository has changes.")
    category = AlertCategory.VCS
    link_wide = True
    dismissible = True
    doc_page = "admin/continuous"
    doc_anchor = "push-changes"
    repository_permissions = ("vcs.push", "vcs.reset")

    @classmethod
    def get_dismissal_context(cls, component: Component, details: dict) -> dict:
        return {
            "details": details,
            "branch": component.branch,
            "local_revision": component.local_revision,
            "repo": component.repo,
        }
