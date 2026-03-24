# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from django.core.management.utils import find_command
from django.utils import timezone
from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon, UpdateBaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.forms import (
    DjangoExtractPotForm,
    GenerateMoForm,
    SphinxExtractPotForm,
    XgettextExtractPotForm,
)
from weblate.formats.base import UpdateError
from weblate.formats.exporters import MoExporter
from weblate.trans.util import get_clean_env
from weblate.utils.errors import report_error
from weblate.utils.files import cleanup_error_message
from weblate.utils.state import STATE_FUZZY, STATE_TRANSLATED

SPHINX_CONFIG_DIR = Path(__file__).resolve().parent / "extractors" / "sphinx"
DJANGO_EXTRACT_RUNNER = (
    Path(__file__).resolve().parent / "extractors" / "django" / "run.py"
)
if TYPE_CHECKING:
    from collections.abc import Generator

    from weblate.addons.base import CompatDict
    from weblate.trans.models import Category, Component, Project, Translation


class GettextBaseAddon(BaseAddon):
    compat: ClassVar[CompatDict] = {"file_format": {"po", "po-mono"}}


class GenerateMoAddon(GettextBaseAddon):
    events: ClassVar[set[AddonEvent]] = {
        AddonEvent.EVENT_PRE_COMMIT,
    }
    name = "weblate.gettext.mo"
    verbose = gettext_lazy("Generate MO files")
    description = gettext_lazy(
        "Automatically generates a MO file for every changed PO file."
    )
    settings_form = GenerateMoForm

    def pre_commit(
        self,
        translation: Translation,
        author: str,
        store_hash: bool,
        activity_log_id: int | None = None,
    ) -> None:
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

        Path(output).write_bytes(exporter.serialize())
        translation.addon_commit_files.append(output)


class UpdateLinguasAddon(GettextBaseAddon):
    events: ClassVar[set[AddonEvent]] = {
        AddonEvent.EVENT_POST_ADD,
        AddonEvent.EVENT_DAILY,
    }
    name = "weblate.gettext.linguas"
    verbose = gettext_lazy("Update LINGUAS file")
    description = gettext_lazy(
        "Updates the LINGUAS file when a new translation is added."
    )

    @staticmethod
    def get_linguas_path(component: Component) -> str:
        base = component.get_new_base_filename()
        if not base:
            base = os.path.join(
                component.full_path, component.filemask.replace("*", "x")
            )
        return os.path.join(os.path.dirname(base), "LINGUAS")

    @classmethod
    def can_install(
        cls,
        *,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
    ) -> bool:
        if not super().can_install(
            component=component, category=category, project=project
        ):
            return False
        if component is None:
            return True
        path = cls.get_linguas_path(component)
        return bool(path) and os.path.exists(path)

    @staticmethod
    def update_linguas(lines: list[str], codes: set[str]) -> tuple[bool, list[str]]:
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
                    lines[i] = f"{expected}\n"
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

    def sync_linguas(self, component: Component, path: str) -> bool:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()

        codes = set(
            component.translation_set.exclude(
                language=component.source_language
            ).values_list("language_code", flat=True)
        )

        changed, lines = self.update_linguas(lines, codes)

        if changed:
            with open(path, "w", encoding="utf-8") as handle:
                handle.writelines(lines)

        return changed

    def post_add(
        self, translation: Translation, activity_log_id: int | None = None
    ) -> None:
        with translation.component.repository.lock:
            path = self.get_linguas_path(translation.component)
            if self.sync_linguas(translation.component, path):
                translation.addon_commit_files.append(path)

    def daily_component(
        self,
        component: Component,
        activity_log_id: int | None = None,
    ) -> None:
        with component.repository.lock:
            path = self.get_linguas_path(component)
            if self.sync_linguas(component, path):
                self.commit_and_push(component, [path])


class UpdateConfigureAddon(GettextBaseAddon):
    events: ClassVar[set[AddonEvent]] = {
        AddonEvent.EVENT_POST_ADD,
        AddonEvent.EVENT_DAILY,
    }
    name = "weblate.gettext.configure"
    verbose = gettext_lazy('Update ALL_LINGUAS variable in the "configure" file')
    description = gettext_lazy(
        'Updates the ALL_LINGUAS variable in "configure", '
        '"configure.in" or "configure.ac" files, when a new translation is added.'
    )

    @staticmethod
    def get_configure_paths(component: Component) -> Generator[str]:
        base = component.full_path
        for name in ("configure", "configure.in", "configure.ac"):
            path = os.path.join(base, name)
            if os.path.exists(path):
                yield path

    @classmethod
    def can_install(
        cls,
        *,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
    ) -> bool:
        if not super().can_install(
            component=component, category=category, project=project
        ):
            return False
        if component is None:
            return True
        for name in cls.get_configure_paths(component):
            try:
                if 'ALL_LINGUAS="' in Path(name).read_text(encoding="utf-8"):
                    return True
            except UnicodeDecodeError:
                continue
        return False

    def sync_linguas(self, component: Component, paths: list[str]) -> bool:
        added = False
        codes = " ".join(
            component.translation_set.exclude(language_id=component.source_language_id)
            .values_list("language_code", flat=True)
            .order_by("language_code")
        )
        expected = f'ALL_LINGUAS="{codes}"\n'
        for path in paths:
            with open(path, encoding="utf-8") as handle:
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
                with open(path, "w", encoding="utf-8") as handle:
                    handle.writelines(lines)

        return added

    def post_add(
        self, translation: Translation, activity_log_id: int | None = None
    ) -> None:
        with translation.component.repository.lock:
            paths = list(self.get_configure_paths(translation.component))
            if self.sync_linguas(translation.component, paths):
                translation.addon_commit_files.extend(paths)

    def daily_component(
        self,
        component: Component,
        activity_log_id: int | None = None,
    ) -> None:
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
    compat: ClassVar[CompatDict] = {"file_format": {"po"}}
    versions_changed = (
        (
            "5.13",
            ":guilabel:`Settings` configuration has been moved to :ref:`file_format_params`.",
        ),
    )

    @classmethod
    def can_install(
        cls,
        *,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
    ) -> bool:
        if find_command("msgmerge") is None:
            return False
        return super().can_install(
            component=component, category=category, project=project
        )

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
        args = component.file_format_cls.get_msgmerge_args(component)
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


class ExtractPotBaseAddon(GettextBaseAddon, UpdateBaseAddon):
    settings_form = None
    alert = "ExtractPotAddonError"
    compat: ClassVar[CompatDict] = {"file_format": {"po"}}
    INTERVALS: ClassVar[dict[str, int]] = {"daily": 1, "weekly": 7}
    PROCESS_TIMEOUT: ClassVar[int] = 300

    @classmethod
    def can_install(
        cls,
        *,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
    ) -> bool:
        if not super().can_install(
            component=component, category=category, project=project
        ):
            return False
        if component is None:
            return True
        return bool(component.new_base)

    def __init__(self, storage) -> None:
        super().__init__(storage)
        self.warnings: list[dict[str, str]] = []

    def get_interval(self) -> int:
        return self.INTERVALS.get(
            self.instance.configuration.get("interval", "weekly"), 7
        )

    def get_domain(self, component: Component) -> str:
        return Path(component.new_base).stem

    def get_component_full_name(self, component: Component) -> str:
        return f"{component.project.name} / {component.name}"

    def should_normalize_header(self) -> bool:
        return bool(self.instance.configuration.get("normalize_header"))

    def get_template_filename(self, component: Component) -> str | None:
        return component.get_new_base_filename()

    def get_gettext_format_args(self, component: Component) -> list[str]:
        """Return gettext CLI flags implied by component file-format settings."""
        return [
            arg
            for arg in component.file_format_cls.get_msgmerge_args(component)
            if arg in {"--no-location", "--no-wrap"}
        ]

    def ensure_msgmerge_addon(self, component: Component) -> None:
        install_msgmerge = self.instance.configuration.pop("_install_msgmerge", False)
        if install_msgmerge:
            self.instance.save(update_fields=["configuration"])
        if not install_msgmerge:
            return
        if component.get_addon(MsgmergeAddon.name) is not None:
            return
        if not MsgmergeAddon.can_install(component=component):
            self.warnings.append(
                {
                    "addon": self.name,
                    "command": "msgmerge",
                    "output": component.new_base,
                    "error": "Could not install the msgmerge add-on for PO updates",
                }
            )
            return
        MsgmergeAddon.create(component=component, run=False)

    def post_configure_run_component(
        self, component: Component, skip_daily: bool = False
    ) -> None:
        self.ensure_msgmerge_addon(component)
        super().post_configure_run_component(component, skip_daily=skip_daily)

    def is_schedule_due(self) -> bool:
        if (
            self.instance.component
            and self.instance.component.alert_set.filter(name=self.alert).exists()
        ):
            return True
        last_run = self.instance.state.get("last_run")
        if not last_run:
            return True
        try:
            last_run_date = date.fromisoformat(last_run)
        except ValueError:
            return True
        return timezone.now().date() - last_run_date >= timedelta(
            days=self.get_interval()
        )

    def get_last_successful_revision(self) -> str | None:
        revision = self.instance.state.get("last_revision")
        return revision if isinstance(revision, str) and revision else None

    def mark_successful_run(self, revision: str) -> None:
        self.instance.state["last_run"] = timezone.now().date().isoformat()
        self.instance.state["last_revision"] = revision
        self.save_state()

    def trigger_alerts(self, component: Component) -> None:
        occurrences = [*self.alerts, *self.warnings]
        if occurrences:
            component.add_alert(self.alert, occurrences=occurrences)
            self.alerts = []
            self.warnings = []
        else:
            component.delete_alert(self.alert)

    def get_msgmerge_addon(self, component: Component):
        addon = component.get_addon(MsgmergeAddon.name)
        return None if addon is None else addon.addon

    def run_process(
        self,
        component: Component,
        cmd: list[str],
        env: dict[str, str] | None = None,
        *,
        cwd: str | None = None,
        extra_path: str | None = None,
    ) -> str | None:
        component.log_debug("%s add-on exec: %s", self.name, " ".join(cmd))
        try:
            output = subprocess.check_output(
                cmd,
                env=get_clean_env(env, extra_path),
                cwd=component.full_path if cwd is None else cwd,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=self.PROCESS_TIMEOUT,
            )
        except subprocess.TimeoutExpired as err:
            output = getattr(err, "output", "") or ""
            component.log_error(
                "timed out exec %s after %s seconds", repr(cmd), self.PROCESS_TIMEOUT
            )
            for line in output.splitlines():
                component.log_error("program output: %s", line)
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": " ".join(cmd),
                    "output": cleanup_error_message(output),
                    "error": f"Command timed out after {self.PROCESS_TIMEOUT} seconds",
                }
            )
            report_error("Add-on script timeout", project=component.project)
            return None
        except (OSError, subprocess.CalledProcessError) as err:
            output = getattr(err, "output", "")
            component.log_error("failed to exec %s: %s", repr(cmd), err)
            for line in output.splitlines():
                component.log_error("program output: %s", line)
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": " ".join(cmd),
                    "output": cleanup_error_message(output),
                    "error": str(err),
                }
            )
            report_error("Add-on script error", project=component.project)
            return None
        component.log_debug("exec result: %s", output)
        return output

    def normalize_header(self, component: Component, filename: str) -> None:
        content = Path(filename).read_text(encoding="utf-8")
        component_name = self.get_component_full_name(component)
        lines = []
        for line in content.splitlines(keepends=True):
            if line.startswith("# FIRST AUTHOR"):
                continue
            if line.startswith("# Copyright (C) YEAR THE PACKAGE'S COPYRIGHT HOLDER"):
                continue
            if line.startswith(
                "# This file is distributed under the same license as the"
            ):
                continue
            if re.match(r"^# Copyright \(C\) [0-9– -]* Michal Čihař", line):
                continue
            if line.startswith('"Project-Id-Version:'):
                lines.append(f'"Project-Id-Version: {component_name}\\n"\n')
                continue
            if component.report_source_bugs and line.startswith(
                '"Report-Msgid-Bugs-To:'
            ):
                lines.append(
                    f'"Report-Msgid-Bugs-To: {component.report_source_bugs}\\n"\n'
                )
                continue
            if "SOME DESCRIPTIVE TITLE." in line:
                lines.append(
                    line.replace(
                        "SOME DESCRIPTIVE TITLE.",
                        f"Translations for {component_name}.",
                    )
                )
                continue
            lines.append(line)
        updated = "".join(lines)
        if updated != content:
            Path(filename).write_text(updated, encoding="utf-8")

    def finalize_template(self, component: Component) -> bool:
        template = self.get_template_filename(component)
        if template is None:
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": self.name,
                    "output": component.new_base,
                    "error": "Template for new translations not found",
                }
            )
            return False
        if self.should_normalize_header():
            self.normalize_header(component, template)
        self.extra_files.append(template)
        return True

    def validate_repository_tree(self, component: Component) -> bool:
        pending = [Path(component.full_path)]
        seen: set[str] = set()

        while pending:
            current = pending.pop()
            try:
                resolved_current = component.repository.resolve_symlinks(
                    os.fspath(current)
                )
            except ValueError:
                component.log_error("refused to read out of repository: %s", current)
                return False

            if resolved_current in seen:
                continue
            seen.add(resolved_current)

            if not current.is_dir():
                continue

            for entry in current.iterdir():
                try:
                    component.repository.resolve_symlinks(os.fspath(entry))
                except ValueError:
                    component.log_error("refused to read out of repository: %s", entry)
                    return False
                if entry.is_dir():
                    pending.append(entry)
        return True

    def should_run_update(self, component: Component, previous_head: str) -> bool:
        return self.is_schedule_due()

    def execute_update(self, component: Component, previous_head: str) -> bool:
        raise NotImplementedError

    def update_translations(self, component: Component, previous_head: str) -> None:
        self.extra_files = []
        current_revision = component.repository.last_revision
        if not self.should_run_update(component, previous_head):
            return
        if self.execute_update(component, previous_head) and not self.alerts:
            if msgmerge_addon := self.get_msgmerge_addon(component):
                msgmerge_addon.update_translations(component, previous_head)
            self.mark_successful_run(current_revision)
        self.trigger_alerts(component)


class XgettextAddon(ExtractPotBaseAddon):
    name = "weblate.gettext.xgettext"
    version_added = "5.17"
    verbose = gettext_lazy("Update POT file (xgettext)")
    description = gettext_lazy(
        "Updates the gettext template using xgettext on selected source files."
    )
    settings_form = XgettextExtractPotForm

    @classmethod
    def can_install(
        cls,
        *,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
    ) -> bool:
        return find_command("xgettext") is not None and super().can_install(
            component=component, category=category, project=project
        )

    def get_source_patterns(self) -> list[str]:
        return self.instance.configuration.get("files", [])

    def has_relevant_changes(self, component: Component, previous_head: str) -> bool:
        if component.alert_set.filter(name=self.alert).exists():
            return True
        compare_revision = self.get_last_successful_revision() or previous_head
        if not compare_revision:
            return True
        changed = component.repository.list_changed_files(
            component.repository.ref_to_remote.format(compare_revision)
        )
        return any(
            fnmatch.fnmatch(path, pattern)
            for pattern in self.get_source_patterns()
            for path in changed
        )

    def resolve_input_files(self, component: Component) -> list[str]:
        result: set[str] = set()
        root = Path(component.full_path)
        for pattern in self.get_source_patterns():
            for match in root.glob(pattern):
                if not match.is_file():
                    continue
                try:
                    component.repository.resolve_symlinks(os.fspath(match))
                except ValueError:
                    component.log_error("refused to read out of repository: %s", match)
                    continue
                result.add(os.path.relpath(match, component.full_path))
        return sorted(result)

    def should_run_update(self, component: Component, previous_head: str) -> bool:
        return super().should_run_update(
            component, previous_head
        ) and self.has_relevant_changes(component, previous_head)

    def execute_update(self, component: Component, previous_head: str) -> bool:
        if not self.has_relevant_changes(component, previous_head):
            return False
        if not self.validate_repository_tree(component):
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": "xgettext",
                    "output": component.new_base,
                    "error": "Repository contains symlink outside repository",
                }
            )
            return False

        template = self.get_template_filename(component)
        if template is None:
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": "xgettext",
                    "output": component.new_base,
                    "error": "Template for new translations not found",
                }
            )
            return False

        files = self.resolve_input_files(component)
        if not files:
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": "xgettext",
                    "output": "",
                    "error": "No source files matched configured patterns",
                }
            )
            return False

        Path(template).parent.mkdir(parents=True, exist_ok=True)
        language = self.instance.configuration["language"]
        if (
            self.run_process(
                component,
                [
                    "xgettext",
                    "--output",
                    component.new_base,
                    "--language",
                    language,
                    *files,
                ],
            )
            is None
        ):
            return False
        return self.finalize_template(component)


class DjangoAddon(ExtractPotBaseAddon):
    name = "weblate.gettext.django"
    version_added = "5.17"
    verbose = gettext_lazy("Update POT file (Django)")
    description = gettext_lazy(
        "Updates the gettext template using Django's built-in makemessages command."
    )
    settings_form = DjangoExtractPotForm

    @classmethod
    def can_install(
        cls,
        *,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
    ) -> bool:
        return find_command("xgettext") is not None and super().can_install(
            component=component, category=category, project=project
        )

    def execute_update(self, component: Component, previous_head: str) -> bool:
        if not self.validate_repository_tree(component):
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": "django makemessages",
                    "output": component.new_base,
                    "error": "Repository contains symlink outside repository",
                }
            )
            return False
        source_dir = self.get_source_dir(component)
        if source_dir is None:
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": "django makemessages",
                    "output": component.new_base,
                    "error": "Could not determine Django source directory",
                }
            )
            return False
        template = self.get_template_filename(component)
        if template is None:
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": "django makemessages",
                    "output": component.new_base,
                    "error": "Template for new translations not found",
                }
            )
            return False
        domain = self.get_domain(component)
        if domain not in {"django", "djangojs"}:
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": "django makemessages",
                    "output": component.new_base,
                    "error": "The Django extractor only supports django.pot and djangojs.pot templates",
                }
            )
            return False
        command = [
            sys.executable,
            os.fspath(DJANGO_EXTRACT_RUNNER),
            "-d",
            domain,
            *self.get_gettext_format_args(component),
        ]
        with tempfile.TemporaryDirectory(prefix="weblate-django-") as tempdir:
            locale_dir = Path(tempdir) / "locale"
            env = {"WEBLATE_EXTRACT_LOCALE_PATH": os.fspath(locale_dir)}
            if (
                self.run_process(component, command, env=env, cwd=os.fspath(source_dir))
                is None
            ):
                return False
            generated = locale_dir / f"{domain}.pot"
            if not generated.exists():
                self.alerts.append(
                    {
                        "addon": self.name,
                        "command": "django makemessages",
                        "output": component.new_base,
                        "error": "Generated POT file was not found",
                    }
                )
                return False
            Path(template).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(generated, template)
        return self.finalize_template(component)

    def get_source_dir(self, component: Component) -> Path | None:
        template = Path(component.new_base)
        parts = template.parts
        if "locale" not in parts:
            return Path(component.full_path)
        locale_index = parts.index("locale")
        if locale_index == 0:
            return Path(component.full_path)
        source_dir = Path(component.full_path).joinpath(*parts[:locale_index])
        if not source_dir.is_dir():
            return None
        return source_dir


class SphinxAddon(ExtractPotBaseAddon):
    name = "weblate.gettext.sphinx"
    version_added = "5.17"
    verbose = gettext_lazy("Update POT file (Sphinx)")
    description = gettext_lazy(
        "Updates the gettext template using Sphinx's gettext builder without loading project configuration."
    )
    settings_form = SphinxExtractPotForm

    @classmethod
    def can_install(
        cls,
        *,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
    ) -> bool:
        return find_command("sphinx-build") is not None and super().can_install(
            component=component, category=category, project=project
        )

    def get_sphinx_source_dir(self, component: Component) -> Path | None:
        template = Path(component.new_base)
        parts = template.parts
        if "locales" not in parts:
            return None
        locales_index = parts.index("locales")
        if locales_index == 0:
            return Path(component.full_path)
        source_dir = Path(component.full_path).joinpath(*parts[:locales_index])
        if not source_dir.is_dir():
            return None
        return source_dir

    def execute_update(self, component: Component, previous_head: str) -> bool:
        if not self.validate_repository_tree(component):
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": "sphinx-build",
                    "output": component.new_base,
                    "error": "Repository contains symlink outside repository",
                }
            )
            return False
        source_dir = self.get_sphinx_source_dir(component)
        if source_dir is None:
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": "sphinx-build",
                    "output": component.new_base,
                    "error": "Could not determine Sphinx source directory",
                }
            )
            return False
        domain = self.get_domain(component)
        with tempfile.TemporaryDirectory(prefix="weblate-sphinx-") as tempdir:
            doctree_dir = Path(tempdir) / "doctrees"
            build_dir = Path(tempdir) / "build"
            command = [
                "sphinx-build",
                "-b",
                "gettext",
                "-E",
                "-d",
                os.fspath(doctree_dir),
                "-c",
                os.fspath(SPHINX_CONFIG_DIR),
                "-D",
                "project=Documentation",
                "-D",
                f"gettext_compact={domain}",
                os.fspath(source_dir),
                os.fspath(build_dir),
            ]
            if self.run_process(component, command) is None:
                return False
            generated = build_dir / domain / f"{domain}.pot"
            if not generated.exists():
                generated = build_dir / f"{domain}.pot"
            if not generated.exists():
                self.alerts.append(
                    {
                        "addon": self.name,
                        "command": "sphinx-build",
                        "output": component.new_base,
                        "error": "Generated POT file was not found",
                    }
                )
                return False
            template = self.get_template_filename(component)
            if template is None:
                return False
            Path(template).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(generated, template)
        return self.finalize_template(component)


class GettextAuthorComments(GettextBaseAddon):
    events: ClassVar[set[AddonEvent]] = {
        AddonEvent.EVENT_PRE_COMMIT,
    }
    name = "weblate.gettext.authors"
    verbose = gettext_lazy("Contributors in comment")
    description = gettext_lazy(
        "Updates the comment part of the PO file header to include contributor names "
        "and years of contributions."
    )

    def pre_commit(
        self,
        translation: Translation,
        author: str,
        store_hash: bool,
        activity_log_id: int | None = None,
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
