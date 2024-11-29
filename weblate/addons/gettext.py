# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from typing import TYPE_CHECKING, cast

from django.core.management.utils import find_command
from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon, StoreBaseAddon, UpdateBaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.forms import GenerateMoForm, GettextCustomizeForm, MsgmergeForm
from weblate.formats.base import TranslationFormat, UpdateError
from weblate.formats.exporters import MoExporter
from weblate.utils.state import STATE_FUZZY, STATE_TRANSLATED

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.formats.ttkit import BasePoFormat
    from weblate.trans.models import Component, Translation


class GettextBaseAddon(BaseAddon):
    compat = {"file_format": {"po", "po-mono"}}


class GenerateMoAddon(GettextBaseAddon):
    events: set[AddonEvent] = {
        AddonEvent.EVENT_PRE_COMMIT,
    }
    name = "weblate.gettext.mo"
    verbose = gettext_lazy("Generate MO files")
    description = gettext_lazy(
        "Automatically generates a MO file for every changed PO file."
    )
    settings_form = GenerateMoForm

    def pre_commit(self, translation, author: str, store_hash: bool) -> None:
        exporter = MoExporter(translation=translation)

        if self.instance.configuration.get("fuzzy"):
            state = STATE_FUZZY
        else:
            state = STATE_TRANSLATED
        units = translation.unit_set.filter(state__gte=state)

        exporter.add_units(units.prefetch_full())

        template = self.instance.configuration.get("path")
        if not template:
            template = "{{ filename|stripext }}.mo"

        output = self.render_repo_filename(template, translation)
        if not output:
            return

        with open(output, "wb") as handle:
            handle.write(exporter.serialize())
        translation.addon_commit_files.append(output)


class UpdateLinguasAddon(GettextBaseAddon):
    events: set[AddonEvent] = {AddonEvent.EVENT_POST_ADD, AddonEvent.EVENT_DAILY}
    name = "weblate.gettext.linguas"
    verbose = gettext_lazy("Update LINGUAS file")
    description = gettext_lazy(
        "Updates the LINGUAS file when a new translation is added."
    )

    @staticmethod
    def get_linguas_path(component: Component):
        base = component.get_new_base_filename()
        if not base:
            base = os.path.join(
                component.full_path, component.filemask.replace("*", "x")
            )
        return os.path.join(os.path.dirname(base), "LINGUAS")

    @classmethod
    def can_install(cls, component: Component, user: User | None):
        if not super().can_install(component, user):
            return False
        path = cls.get_linguas_path(component)
        return path and os.path.exists(path)

    @staticmethod
    def update_linguas(lines: list[str], codes: set[str]):
        changed = False
        remove = []

        for i, line in enumerate(lines):
            # Split at comment and strip whitespace
            stripped = line.split("#", 1)[0].strip()
            # Comment/blank lines
            if not stripped:
                continue
            # Languages in one line
            if " " in stripped:
                expected = " ".join(sorted(codes))
                if stripped != expected:
                    lines[i] = expected + "\n"
                    changed = True
                codes = set()
                break
            # Language is already there
            if stripped in codes:
                codes.remove(stripped)
            else:
                remove.append(i)

        # Remove no longer present codes
        if remove:
            for i in reversed(remove):
                del lines[i]
            changed = True

        # Add missing codes
        if codes:
            lines.extend(f"{code}\n" for code in codes)
            changed = True

        return changed, lines

    def sync_linguas(self, component, path):
        with open(path) as handle:
            lines = handle.readlines()

        codes = set(
            component.translation_set.exclude(
                language=component.source_language
            ).values_list("language_code", flat=True)
        )

        changed, lines = self.update_linguas(lines, codes)

        if changed:
            with open(path, "w") as handle:
                handle.writelines(lines)

        return changed

    def post_add(self, translation) -> None:
        with translation.component.repository.lock:
            path = self.get_linguas_path(translation.component)
            if self.sync_linguas(translation.component, path):
                translation.addon_commit_files.append(path)

    def daily(self, component) -> None:
        with component.repository.lock:
            path = self.get_linguas_path(component)
            if self.sync_linguas(component, path):
                self.commit_and_push(component, [path])


class UpdateConfigureAddon(GettextBaseAddon):
    events: set[AddonEvent] = {AddonEvent.EVENT_POST_ADD, AddonEvent.EVENT_DAILY}
    name = "weblate.gettext.configure"
    verbose = gettext_lazy('Update ALL_LINGUAS variable in the "configure" file')
    description = gettext_lazy(
        'Updates the ALL_LINGUAS variable in "configure", '
        '"configure.in" or "configure.ac" files, when a new translation is added.'
    )

    @staticmethod
    def get_configure_paths(component):
        base = component.full_path
        for name in ("configure", "configure.in", "configure.ac"):
            path = os.path.join(base, name)
            if os.path.exists(path):
                yield path

    @classmethod
    def can_install(cls, component, user: User | None) -> bool:
        if not super().can_install(component, user):
            return False
        for name in cls.get_configure_paths(component):
            try:
                with open(name) as handle:
                    if 'ALL_LINGUAS="' in handle.read():
                        return True
            except UnicodeDecodeError:
                continue
        return False

    def sync_linguas(self, component, paths):
        added = False
        codes = " ".join(
            component.translation_set.exclude(language_id=component.source_language_id)
            .values_list("language_code", flat=True)
            .order_by("language_code")
        )
        expected = f'ALL_LINGUAS="{codes}"\n'
        for path in paths:
            with open(path) as handle:
                lines = handle.readlines()

            for i, line in enumerate(lines):
                stripped = line.strip()
                # Comment
                if stripped.startswith("#"):
                    continue
                if not stripped.startswith('ALL_LINGUAS="'):
                    continue
                if line != expected:
                    lines[i] = expected
                    added = True

            if added:
                with open(path, "w") as handle:
                    handle.writelines(lines)

        return added

    def post_add(self, translation) -> None:
        with translation.component.repository.lock:
            paths = list(self.get_configure_paths(translation.component))
            if self.sync_linguas(translation.component, paths):
                translation.addon_commit_files.extend(paths)

    def daily(self, component) -> None:
        with component.repository.lock:
            paths = list(self.get_configure_paths(component))
            if self.sync_linguas(component, paths):
                self.commit_and_push(component, paths)


class MsgmergeAddon(GettextBaseAddon, UpdateBaseAddon):
    name = "weblate.gettext.msgmerge"
    verbose = gettext_lazy("Update PO files to match POT (msgmerge)")
    description = gettext_lazy(
        'Updates all PO files (as configured by "File mask") to match the '
        'POT file (as configured by "Template for new translations") using msgmerge.'
    )
    alert = "MsgmergeAddonError"
    settings_form = MsgmergeForm

    @classmethod
    def can_install(cls, component: Component, user: User | None):
        if find_command("msgmerge") is None:
            return False
        return super().can_install(component, user)

    def get_msgmerge_args(self, component: Component):
        args = []
        if not self.instance.configuration.get("fuzzy", True):
            args.append("--no-fuzzy-matching")
        if self.instance.configuration.get("previous", True):
            args.append("--previous")
        if self.instance.configuration.get("no_location", False):
            args.append("--no-location")

        # Apply gettext customize add-on configuration
        if customize_addon := component.get_addon(GettextCustomizeAddon.name):
            args.extend(customize_addon.addon.get_msgmerge_args(component))
        return args

    def update_translations(self, component: Component, previous_head: str) -> None:
        # Run always when there is an alerts, there is a chance that
        # the update clears it.
        repository = component.repository
        if previous_head and not component.alert_set.filter(name=self.alert).exists():
            changes = repository.list_changed_files(
                repository.ref_to_remote.format(previous_head)
            )
            if component.new_base not in changes:
                component.log_info(
                    "%s addon skipped, new base was not updated in %s..%s",
                    self.name,
                    previous_head,
                    repository.last_revision,
                )
                return
        template = component.get_new_base_filename()
        if not template or not os.path.exists(template):
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": "msgmerge",
                    "output": template,
                    "error": "Template for new translations not found",
                }
            )
            self.trigger_alerts(component)
            component.log_info("%s addon skipped, new base was not found", self.name)
            return
        args = self.get_msgmerge_args(component)
        for translation in component.translation_set.iterator():
            filename = translation.get_filename()
            if (
                (translation.is_source and not translation.is_template)
                or not filename
                or not os.path.exists(filename)
            ):
                continue
            try:
                component.file_format_cls.update_bilingual(
                    filename, template, args=args
                )
            except UpdateError as error:
                self.alerts.append(
                    {
                        "addon": self.name,
                        "command": error.cmd,
                        "output": str(error.output),
                        "error": str(error),
                    }
                )
                component.log_info("%s addon failed: %s", self.name, error)
        self.trigger_alerts(component)

    def commit_and_push(
        self,
        component: Component,
        files: list[str] | None = None,
        skip_push: bool = False,
    ) -> bool:
        if super().commit_and_push(component, files=files, skip_push=skip_push):
            component.create_translations()
            return True
        return False


class GettextCustomizeAddon(GettextBaseAddon, StoreBaseAddon):
    name = "weblate.gettext.customize"
    verbose = gettext_lazy("Customize gettext output")
    description = gettext_lazy(
        "Allows customization of gettext output behavior, for example line wrapping."
    )
    settings_form = GettextCustomizeForm

    def store_post_load(
        self, translation: Translation, store: TranslationFormat
    ) -> None:
        cast("BasePoFormat", store).store.wrapper.width = int(
            self.instance.configuration.get("width", 77)
        )

    def get_msgmerge_args(self, component: Component):
        if int(self.instance.configuration.get("width", 77)) != 77:
            return ["--no-wrap"]
        return []


class GettextAuthorComments(GettextBaseAddon):
    events: set[AddonEvent] = {
        AddonEvent.EVENT_PRE_COMMIT,
    }
    name = "weblate.gettext.authors"
    verbose = gettext_lazy("Contributors in comment")
    description = gettext_lazy(
        "Updates the comment part of the PO file header to include contributor names "
        "and years of contributions."
    )

    def pre_commit(
        self, translation: Translation, author: str, store_hash: bool
    ) -> None:
        if "noreply@weblate.org" in author:
            return
        if "<" in author:
            name, email = author.split("<")
            name = name.strip()
            email = email.rstrip(">")
        else:
            name = author
            email = None

        translation.store.store.updatecontributor(name, email)
        translation.store.save()
        if store_hash:
            translation.store_hash()
