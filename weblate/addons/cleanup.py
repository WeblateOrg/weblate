# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy

from weblate.addons.base import UpdateBaseAddon
from weblate.addons.events import AddonEvent
from weblate.formats.base import TranslationFormat
from weblate.trans.exceptions import FileParseError

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.trans.models import Component


class BaseCleanupAddon(UpdateBaseAddon):
    @staticmethod
    def can_install_format(component: Component) -> bool:
        return component.file_format_cls.can_delete_unit

    @classmethod
    def can_install(cls, component: Component, user: User | None) -> bool:
        if not component.has_template() or not cls.can_install_format(component):
            return False
        return super().can_install(component, user)


class CleanupAddon(BaseCleanupAddon):
    name = "weblate.cleanup.generic"
    verbose = gettext_lazy("Cleanup translation files")
    description = gettext_lazy(
        "Update all translation files to match the monolingual base file. "
        "For most file formats, this means removing stale translation keys "
        "no longer present in the base file."
    )
    icon = "eraser.svg"
    events: set[AddonEvent] = {
        AddonEvent.EVENT_PRE_COMMIT,
        AddonEvent.EVENT_POST_UPDATE,
    }

    @classmethod
    def can_install_format(cls, component: Component) -> bool:
        return (
            super().can_install_format(component)
            or component.file_format_cls.cleanup_unused
            != TranslationFormat.cleanup_unused
        )

    def update_translations(self, component, previous_head) -> None:
        for translation in self.iterate_translations(component):
            filenames = translation.store.cleanup_unused()
            if filenames is None:
                continue
            self.extra_files.extend(filenames)
            # Do not update hash here as this is just before parsing updated files

    def pre_commit(self, translation, author: str, store_hash: bool) -> None:
        if translation.is_source and not translation.component.intermediate:
            return
        try:
            filenames = translation.store.cleanup_unused()
        except FileParseError:
            return
        if filenames is not None:
            self.extra_files.extend(filenames)
            if store_hash:
                translation.store_hash()


class RemoveBlankAddon(BaseCleanupAddon):
    name = "weblate.cleanup.blank"
    verbose = gettext_lazy("Remove blank strings")
    description = gettext_lazy(
        "Removes strings without a translation from translation files."
    )
    events: set[AddonEvent] = {
        AddonEvent.EVENT_POST_COMMIT,
        AddonEvent.EVENT_POST_UPDATE,
    }
    icon = "eraser.svg"

    def update_translations(self, component: Component, previous_head: str) -> None:
        for translation in self.iterate_translations(component):
            filenames = translation.store.cleanup_blank()
            if filenames is None:
                continue
            self.extra_files.extend(filenames)
            # Do not update hash in post_update, only in post_commit
            if previous_head == "weblate:post-commit":
                translation.store_hash()

    def post_commit(self, component: Component, store_hash: bool) -> None:
        self.post_update(
            component,
            "weblate:post-commit" if store_hash else "weblate:post-commit-no-store",
            skip_push=True,
        )
