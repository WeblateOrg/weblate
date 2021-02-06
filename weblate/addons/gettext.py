#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#


import os

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.utils import find_command
from django.utils.translation import gettext_lazy as _

from weblate.addons.base import BaseAddon, StoreBaseAddon, UpdateBaseAddon
from weblate.addons.events import EVENT_DAILY, EVENT_POST_ADD, EVENT_PRE_COMMIT
from weblate.addons.forms import GenerateMoForm, GettextCustomizeForm, MsgmergeForm
from weblate.formats.base import UpdateError
from weblate.formats.exporters import MoExporter


class GettextBaseAddon(BaseAddon):
    compat = {"file_format": {"po", "po-mono"}}


class GenerateMoAddon(GettextBaseAddon):
    events = (EVENT_PRE_COMMIT,)
    name = "weblate.gettext.mo"
    verbose = _("Generate MO files")
    description = _("Automatically generates a MO file for every changed PO file.")
    settings_form = GenerateMoForm

    def pre_commit(self, translation, author):
        exporter = MoExporter(translation=translation)
        exporter.add_units(translation.unit_set.prefetch_full())

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
    events = (EVENT_POST_ADD, EVENT_DAILY)
    name = "weblate.gettext.linguas"
    verbose = _("Update LINGUAS file")
    description = _("Updates the LINGUAS file when a new translation is added.")

    @staticmethod
    def get_linguas_path(component):
        base = component.get_new_base_filename()
        if not base:
            base = os.path.join(
                component.full_path, component.filemask.replace("*", "x")
            )
        return os.path.join(os.path.dirname(base), "LINGUAS")

    @classmethod
    def can_install(cls, component, user):
        if not super().can_install(component, user):
            return False
        path = cls.get_linguas_path(component)
        return path and os.path.exists(path)

    @staticmethod
    def update_linguas(lines, codes):
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
            for code in codes:
                lines.append(f"{code}\n")
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

    def post_add(self, translation):
        with translation.component.repository.lock:
            path = self.get_linguas_path(translation.component)
            if self.sync_linguas(translation.component, path):
                translation.addon_commit_files.append(path)

    def daily(self, component):
        with component.repository.lock:
            path = self.get_linguas_path(component)
            if self.sync_linguas(component, path):
                self.commit_and_push(component, [path])


class UpdateConfigureAddon(GettextBaseAddon):
    events = (EVENT_POST_ADD, EVENT_DAILY)
    name = "weblate.gettext.configure"
    verbose = _('Update ALL_LINGUAS variable in the "configure" file')
    description = _(
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
    def can_install(cls, component, user):
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
                if lines[i] != expected:
                    lines[i] = expected
                    added = True

            if added:
                with open(path, "w") as handle:
                    handle.writelines(lines)

        return added

    def post_add(self, translation):
        with translation.component.repository.lock:
            paths = list(self.get_configure_paths(translation.component))
            if self.sync_linguas(translation.component, paths):
                translation.addon_commit_files.extend(paths)

    def daily(self, component):
        with component.repository.lock:
            paths = list(self.get_configure_paths(component))
            if self.sync_linguas(component, paths):
                self.commit_and_push(component, paths)


class MsgmergeAddon(GettextBaseAddon, UpdateBaseAddon):
    name = "weblate.gettext.msgmerge"
    verbose = _("Update PO files to match POT (msgmerge)")
    description = _(
        'Updates all PO files (as configured by "Filemask") to match the '
        'POT file (as configured by "Template for new translations") using msgmerge.'
    )
    alert = "MsgmergeAddonError"
    settings_form = MsgmergeForm

    @classmethod
    def can_install(cls, component, user):
        if find_command("msgmerge") is None:
            return False
        return super().can_install(component, user)

    def update_translations(self, component, previous_head):
        # Run always when there is an alerts, there is a chance that
        # the update clears it.
        if previous_head and not component.alert_set.filter(name=self.alert).exists():
            changes = component.repository.list_changed_files(
                component.repository.ref_to_remote.format(previous_head)
            )
            if component.new_base not in changes:
                component.log_info(
                    "%s addon skipped, new base was not updated", self.name
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
            return
        args = []
        if not self.instance.configuration.get("fuzzy", True):
            args.append("--no-fuzzy-matching")
        if self.instance.configuration.get("previous", True):
            args.append("--previous")
        if self.instance.configuration.get("no_location", False):
            args.append("--no-location")
        try:
            width = component.addon_set.get(
                name="weblate.gettext.customize"
            ).configuration["width"]
            if width != 77:
                args.append("--no-wrap")
        except ObjectDoesNotExist:
            pass
        for translation in component.translation_set.iterator():
            filename = translation.get_filename()
            if translation.is_source or not filename or not os.path.exists(filename):
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
                        "output": error.output,
                        "error": str(error),
                    }
                )
        self.trigger_alerts(component)


class GettextCustomizeAddon(GettextBaseAddon, StoreBaseAddon):
    name = "weblate.gettext.customize"
    verbose = _("Customize gettext output")
    description = _(
        "Allows customization of gettext output behavior, for example line wrapping."
    )
    settings_form = GettextCustomizeForm

    def store_post_load(self, translation, store):
        store.store.wrapper.width = int(self.instance.configuration.get("width", 77))


class GettextAuthorComments(GettextBaseAddon):
    events = (EVENT_PRE_COMMIT,)
    name = "weblate.gettext.authors"
    verbose = _("Contributors in comment")
    description = _(
        "Updates the comment part of the PO file header to include contributor names "
        "and years of contributions."
    )

    def pre_commit(self, translation, author):
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
