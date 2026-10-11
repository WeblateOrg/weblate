# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Explicit recovery of missing repository checkouts during reset."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
from uuid import uuid4

from django.core.cache import cache
from django.db import transaction
from django.utils.translation import gettext

from weblate.utils.data import data_path
from weblate.utils.files import get_repo_temp_dir, remove_tree
from weblate.vcs.base import RepositoryError, get_config_check_cache_key
from weblate.vcs.git import GitRepository, SubversionRepository

if TYPE_CHECKING:
    from collections.abc import Generator

    from weblate.auth.models import AuthenticatedHttpRequest, User
    from weblate.trans.models import Component


@contextmanager
# Keep preparation, filesystem replacement, and the caller inside one rollback boundary.
def recover_checkout(component: Component) -> Generator[bool]:
    """Stage recovery and restore the old checkout if reset subsequently fails."""
    repository = component.repository
    if (
        not isinstance(repository, GitRepository)
        or isinstance(repository, SubversionRepository)
        or not repository.checkout_is_missing()
    ):
        yield False
        return
    original = Path(repository.path)
    recovery_root = get_repo_temp_dir(
        original.parent,
        temp_dir=data_path("repository-recovery") / str(component.pk),
    )
    preserved = recovery_root / uuid4().hex
    moved = False
    installed = False
    committed = False

    def mark_committed() -> None:
        nonlocal committed
        committed = True

    component.log_info(
        "repository recovery started: component_id=%s path=%s", component.pk, original
    )
    try:  # ruff: ignore[too-many-statements-in-try-clause]
        with (
            transaction.atomic(durable=True),
            TemporaryDirectory(prefix="staging-", dir=recovery_root) as temporary,
        ):
            staged_path = Path(temporary) / "checkout"
            repository.stage_recovery_checkout(staged_path, original)
            if original.exists() or original.is_symlink():
                original.rename(preserved)
                moved = True
                component.log_info(
                    "repository preserved: component_id=%s path=%s",
                    component.pk,
                    preserved,
                )
            original.parent.mkdir(parents=True, exist_ok=True)
            staged_path.rename(original)
            installed = True
            repository.clean_revision_cache()
            repository._config_updated = False  # ruff: ignore[private-member-access]
            cache.delete(get_config_check_cache_key(component.pk))
            component.drop_template_store_cache()
            # Mark the commit before reset registers any follow-up callbacks.
            transaction.on_commit(mark_committed)
            yield True
        component.log_info(
            "repository recovery completed: component_id=%s path=%s",
            component.pk,
            original,
        )
    except BaseException:
        if committed:
            component.log_error(
                "repository recovery follow-up failed after commit: component_id=%s path=%s",
                component.pk,
                original,
            )
            raise
        if installed:
            remove_tree(original)
        if moved:
            preserved.rename(original)
        repository.clean_revision_cache()
        component.drop_template_store_cache()
        component.log_error(
            "repository recovery failed: component_id=%s path=%s",
            component.pk,
            original,
        )
        raise


def reset_with_recovery(
    component: Component,
    request: AuthenticatedHttpRequest | None,
    user: User | None,
    *,
    keep_changes: bool,
) -> str | None:
    """Recover before reset while preventing normal lock-session recovery."""
    with (
        component.repository.lock.without_recovery(),
        component.repository.lock,
        (
            recover_checkout(component) if keep_changes else nullcontext(False)
        ) as reconstructed,
    ):
        previous_head = component.reset_repository_to_remote(
            request, user, keep_changes=keep_changes
        )
        if reconstructed and previous_head is None:
            raise RepositoryError(
                1,
                gettext(
                    "Could not reapply translations to the reconstructed repository."
                ),
            )
        return previous_head
