# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.utils.translation import gettext_lazy

from weblate.addons.base import UpdateBaseAddon
from weblate.addons.events import AddonEvent
from weblate.trans.exceptions import FileParseError


class BaseCleanupAddon(UpdateBaseAddon):
    @classmethod
    def can_install(cls, component, user):
        if not component.has_template():
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
    events = (AddonEvent.EVENT_PRE_COMMIT, AddonEvent.EVENT_POST_UPDATE)

    def update_translations(self, component, previous_head) -> None:
        for translation in self.iterate_translations(component):
            filenames = translation.store.cleanup_unused()
            if filenames is None:
                continue
            self.extra_files.extend(filenames)
            # Do not update hash here as this is just before parsing updated files

    def pre_commit(self, translation, author) -> None:
        if translation.is_source and not translation.component.intermediate:
            return
        try:
            filenames = translation.store.cleanup_unused()
        except FileParseError:
            return
        if filenames is not None:
            self.extra_files.extend(filenames)
            translation.store_hash()


class RemoveBlankAddon(BaseCleanupAddon):
    name = "weblate.cleanup.blank"
    verbose = gettext_lazy("Remove blank strings")
    description = gettext_lazy(
        "Removes strings without a translation from translation files."
    )
    events = (AddonEvent.EVENT_POST_COMMIT, AddonEvent.EVENT_POST_UPDATE)
    icon = "eraser.svg"

    def update_translations(self, component, previous_head) -> None:
        for translation in self.iterate_translations(component):
            filenames = translation.store.cleanup_blank()
            if filenames is None:
                continue
            self.extra_files.extend(filenames)
            # Do not update hash in post_update, only in post_commit
            if previous_head == "weblate:post-commit":
                translation.store_hash()

    def post_commit(self, component) -> None:
        self.post_update(component, "weblate:post-commit", skip_push=True, child=False)
