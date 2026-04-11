# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING, cast

from django.core.exceptions import PermissionDenied

from weblate.addons.models import Addon
from weblate.trans.autotranslate import BatchAutoTranslate

if TYPE_CHECKING:
    from weblate.trans.models import Component
    from weblate.vcs.git import GitRepository


BASE_INHERITED_COMPONENT_FIELDS = (
    "vcs",
    "license",
    "agreement",
    "source_language",
    "report_source_bugs",
    "hide_glossary_matches",
    "allow_translation_propagation",
    "contribute_project_tm",
    "enable_suggestions",
    "suggestion_voting",
    "suggestion_autoaccept",
    "check_flags",
    "enforced_checks",
    "new_lang",
    "language_code_style",
    "file_format_params",
    "commit_message",
    "add_message",
    "delete_message",
    "merge_message",
    "addon_message",
    "pull_message",
    "push_on_commit",
    "commit_pending_age",
    "edit_template",
    "manage_units",
    "variant_regex",
    "priority",
    "restricted",
    "key_filter",
    "secondary_language",
)


def get_inherited_component_fields(*extra_fields: str) -> tuple[str, ...]:
    """Return base inherited component fields extended by caller-specific fields."""
    return (*BASE_INHERITED_COMPONENT_FIELDS, *extra_fields)


def copy_component_addons(
    component: Component,
    source_component: Component,
    *,
    same_project_only: bool,
) -> None:
    """Copy compatible component-scoped add-ons from the source component."""
    if same_project_only and component.project_id != source_component.project_id:
        return

    addons = Addon.objects.filter(component=source_component, repo_scope=False)
    for addon in addons:
        if component.addon_set.filter(name=addon.name).exists():
            continue
        if not addon.addon.can_install(component=component):
            continue
        addon.addon.create(component=component, configuration=addon.configuration)


def replace_component_checkout(
    component: Component, source_component: Component
) -> bool:
    """Replace the destination checkout with a copy of the source checkout."""
    if not os.path.isdir(source_component.full_path):
        return False

    source_has_git_checkout = os.path.isdir(
        os.path.join(source_component.full_path, ".git")
    )
    preserve_target_git = component.is_repo_local and not source_has_git_checkout
    ignore_vcs_metadata = shutil.ignore_patterns(".git", ".hg", ".svn", ".bzr")

    with source_component.repository.lock, component.repository.lock:
        os.makedirs(component.full_path, exist_ok=True)
        for entry in os.listdir(component.full_path):
            if entry == ".git" and (not component.is_repo_local or preserve_target_git):
                continue
            target_name = os.path.join(component.full_path, entry)
            if os.path.isdir(target_name) and not os.path.islink(target_name):
                shutil.rmtree(target_name)
            else:
                os.unlink(target_name)
        shutil.copytree(
            source_component.full_path,
            component.full_path,
            dirs_exist_ok=True,
            ignore=ignore_vcs_metadata
            if not component.is_repo_local or preserve_target_git
            else None,
            symlinks=True,
        )

    return True


def normalize_local_copy_branch(component: Component) -> None:
    """Ensure copied local repositories use the component branch."""
    if not component.is_repo_local:
        return

    repository = cast("GitRepository", component.repository)

    with repository.lock:
        if repository.has_branch(component.branch):
            repository.execute(["checkout", component.branch])
        else:
            repository.execute(["checkout", "-B", component.branch])
        repository.branch = component.branch
        repository.clean_revision_cache()


def auto_translate_component_copy(
    component: Component, source_component: Component
) -> None:
    """Overlay current source translations on the copied checkout."""
    auto = BatchAutoTranslate(
        component,
        user=None,
        q="",
        mode="translate",
        component_wide=True,
        allow_non_shared_tm_source_components=True,
    )
    try:
        auto.perform(
            auto_source="others",
            source_component_ids=[source_component.pk],
            engines=[],
            threshold=0,
        )
    except PermissionDenied as error:
        component.log_warning("automatic translation skipped: %s", error)

    for warning in auto.get_warnings():
        component.log_warning("%s", warning)


def seed_component_from_source(
    component: Component,
    source_component: Component,
    *,
    author_name: str,
    skip_push: bool,
) -> bool:
    """Seed a newly created component from another component."""
    component.log_info(
        "copying repository checkout from %s as %s",
        source_component.full_slug,
        author_name,
    )
    if skip_push:
        component.log_debug("skipping push for repository copy seed")

    if not replace_component_checkout(component, source_component):
        return False
    normalize_local_copy_branch(component)

    component.create_translations(force=True)
    auto_translate_component_copy(component, source_component)
    component.run_batched_checks()
    return True


def clone_component_addons(component: Component, source_component: Component) -> None:
    """Clone component-scoped add-ons from the source component."""
    copy_component_addons(component, source_component, same_project_only=True)
