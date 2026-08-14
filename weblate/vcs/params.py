# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Per-component version control parameters.

These mirror :mod:`weblate.trans.file_format_params`: instead of encoding a
behavioural variant in a dedicated VCS backend, a component stores the tweaks
it needs in :attr:`weblate.trans.models.Component.vcs_params`, and each backend
reads them through :meth:`weblate.vcs.base.Repository.get_vcs_param`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal, TypedDict, cast

from django import forms
from django.utils.functional import classproperty
from django.utils.translation import gettext_lazy

from weblate.utils.params import (
    BaseParam,
    get_default_params_for_scope,
    get_param_by_name,
    get_params_for_scope,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django_stubs_ext import StrOrPromise


class VCSParams(TypedDict, total=False):
    git_force_push: bool
    create_merge_request: bool
    merge_request_automerge: bool
    merge_request_merge_method: Literal["merge", "squash", "rebase"]


VCSParamKey = Literal[
    "git_force_push",
    "create_merge_request",
    "merge_request_automerge",
    "merge_request_merge_method",
]


class BaseVCSParam(BaseParam):
    name: VCSParamKey  # type: ignore[assignment]
    vcs_backends: Sequence[str] = []
    widget_css_class: ClassVar[str] = "vcs-param"
    scope_attribute: ClassVar[str] = "vcses"

    @classmethod
    def get_scopes(cls) -> Sequence[str]:
        return cls.vcs_backends

    @classmethod
    def supports_vcs(cls, vcs: str) -> bool:
        return cls.supports_scope(vcs)


VCS_PARAMS: list[type[BaseVCSParam]] = []


def register_vcs_param(param_class: type[BaseVCSParam]) -> type[BaseVCSParam]:
    """Register a new version control parameter class."""
    VCS_PARAMS.append(param_class)
    return param_class


def get_params_for_vcs(vcs: str) -> list[type[BaseVCSParam]]:
    """Get all registered version control parameters for a given backend."""
    return get_params_for_scope(VCS_PARAMS, vcs)


def get_default_params_for_vcs(vcs: str) -> VCSParams:
    """Get default values for all registered version control parameters."""
    return cast("VCSParams", get_default_params_for_scope(VCS_PARAMS, vcs))


def strip_unused_vcs_params(vcs: str, vcs_params: VCSParams) -> VCSParams:
    """Remove parameters which do not apply to the given version control system."""
    for param in VCS_PARAMS:
        if not param.supports_vcs(vcs):
            vcs_params.pop(param.name, None)
    return vcs_params


def get_vcs_param_for_name(name: str) -> type[BaseVCSParam]:
    """Get parameter class for given name."""
    return get_param_by_name(VCS_PARAMS, name)


@register_vcs_param
class GitForcePush(BaseVCSParam):
    vcs_backends = ("git",)
    name = "git_force_push"
    label = gettext_lazy("Force push")
    field_class = forms.BooleanField
    default = False
    help_text = gettext_lazy(
        "Overwrite the remote branch instead of refusing to push non-fast-forward "
        "changes. Only use this with a repository dedicated to translations, as it "
        "discards upstream commits which are not present in Weblate."
    )


class BaseMergeRequestParam(BaseVCSParam):
    @classproperty
    def vcs_backends(self) -> Sequence[str]:  # type: ignore[override]
        # ruff: ignore[import-outside-top-level]
        from weblate.vcs.models import VCS_REGISTRY

        return sorted(VCS_REGISTRY.unfiltered_merge_request_based)


@register_vcs_param
class CreateMergeRequest(BaseMergeRequestParam):
    name = "create_merge_request"
    label = gettext_lazy("Create merge requests")
    field_class = forms.BooleanField
    default = True
    help_text = gettext_lazy(
        "Open a pull or merge request for the translation changes. When turned off, "
        "Weblate pushes to the translated branch directly, which requires write "
        "access to it."
    )


class BaseGitHubMergeRequestParam(BaseVCSParam):
    vcs_backends = ("github", "github-app")


@register_vcs_param
class MergeRequestAutomerge(BaseGitHubMergeRequestParam):
    name = "merge_request_automerge"
    label = gettext_lazy("Merge pull requests automatically")
    field_class = forms.BooleanField
    default = False
    help_text = gettext_lazy(
        "Turn on GitHub auto-merge for pull requests created by Weblate, so that "
        "they are merged once the required checks pass. Pull requests with nothing "
        "to wait for are merged right away."
    )


@register_vcs_param
class MergeRequestMergeMethod(BaseGitHubMergeRequestParam):
    name = "merge_request_merge_method"
    label = gettext_lazy("Merge method")
    field_class = forms.ChoiceField
    choices: ClassVar[list[tuple[str | int, StrOrPromise]] | None] = [
        ("merge", gettext_lazy("Create a merge commit")),
        ("squash", gettext_lazy("Squash and merge")),
        ("rebase", gettext_lazy("Rebase and merge")),
    ]
    default = "merge"
    help_text = gettext_lazy(
        "Method used when merging pull requests automatically. The repository has to "
        "allow it."
    )
