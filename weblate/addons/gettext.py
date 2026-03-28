# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, ClassVar, cast

from django.core.exceptions import ValidationError
from django.core.management.utils import find_command
from django.db import models
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
from weblate.vcs.base import RepositoryError

SPHINX_CONFIG_DIR = Path(__file__).resolve().parent / "extractors" / "sphinx"
DJANGO_EXTRACT_RUNNER = (
    Path(__file__).resolve().parent / "extractors" / "django" / "run.py"
)
if TYPE_CHECKING:
    from collections.abc import Generator

    from weblate.addons.base import CompatDict
    from weblate.formats.ttkit import PoFormat
    from weblate.trans.models import Category, Component, Project, Translation


class GettextBaseAddon(BaseAddon):
    compat: ClassVar[CompatDict] = {"file_format": {"po", "po-mono"}}


def find_runtime_command(command: str) -> str | None:
    """Find executable either on PATH or next to the active Python interpreter."""
    if path := find_command(command):
        return path
    interpreter_dir = Path(sys.executable).parent
    candidates = [
        interpreter_dir / command,
        interpreter_dir / f"{command}.exe",
    ]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return os.fspath(candidate)
    return None


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
        try:
            path = cls.get_linguas_path(component)
            component.check_file_is_valid(path)
        except ValidationError:
            return False
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
        component.check_file_is_valid(path)

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
            try:
                path = self.get_linguas_path(translation.component)
                changed = self.sync_linguas(translation.component, path)
            except ValidationError:
                return
            if changed:
                translation.addon_commit_files.append(path)

    def daily_component(
        self,
        component: Component,
        activity_log_id: int | None = None,
    ) -> None:
        with component.repository.lock:
            try:
                path = self.get_linguas_path(component)
                changed = self.sync_linguas(component, path)
            except ValidationError:
                return
            if changed:
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
        for name in ("configure", "configure.in", "configure.ac"):
            try:
                path = component.get_validated_component_filename(name)
            except ValidationError:
                continue
            if path and os.path.exists(path):
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
        if find_runtime_command("msgmerge") is None:
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
                    "output": template or "<missing>",
                    "error": "Template for new translations not found",
                }
            )
            self.trigger_alerts(component)
            component.log_info("%s addon skipped, new base was not found", self.name)
            return
        file_format_cls = cast("PoFormat", component.file_format_cls)
        args = file_format_cls.get_msgmerge_args(component)
        for translation in component.translation_set.iterator():
            filename = translation.get_filename()
            if (
                (translation.is_source and not translation.is_template)
                or not filename
                or not os.path.exists(filename)
            ):
                continue
            try:
                file_format_cls.update_bilingual(filename, template, args=args)
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
    alert = "ExtractPotAddonError"
    compat: ClassVar[CompatDict] = {"file_format": {"po"}}
    INTERVALS: ClassVar[dict[str, int]] = {"daily": 1, "weekly": 7, "monthly": 30}
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
        self.successful_components: set[int] = set()
        self.pending_successful_revisions: dict[int, str] = {}

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
        file_format_cls = cast("PoFormat", component.file_format_cls)
        return [
            arg
            for arg in file_format_cls.get_msgmerge_args(component)
            if arg in {"--no-location", "--no-wrap"}
        ]

    def ensure_msgmerge_addon(self) -> None:
        from weblate.addons.models import Addon

        install_msgmerge = self.instance.configuration.get("_install_msgmerge", False)
        if not install_msgmerge:
            return
        if self.has_applicable_msgmerge_addon(Addon):
            return
        kwargs = self.get_msgmerge_addon_create_kwargs()
        if not MsgmergeAddon.can_install(**kwargs):
            self.warnings.append(
                {
                    "addon": self.name,
                    "command": "msgmerge",
                    "output": self.instance.component.new_base
                    if self.instance.component
                    else "",
                    "error": "Could not install the msgmerge add-on for PO updates",
                }
            )
            return
        MsgmergeAddon.create(run=False, **kwargs)

    def has_applicable_msgmerge_addon(self, addon_model) -> bool:
        if self.instance.component is not None:
            return self.instance.component.get_addon(MsgmergeAddon.name) is not None
        if self.instance.category is not None:
            category_ids = []
            category = self.instance.category
            while category is not None:
                category_ids.append(category.pk)
                category = category.category
            return (
                addon_model.objects.filter(
                    name=MsgmergeAddon.name,
                )
                .filter(
                    models.Q(category_id__in=category_ids)
                    | models.Q(project=self.instance.category.project)
                    | models.Q(
                        component__isnull=True,
                        category__isnull=True,
                        project__isnull=True,
                    )
                )
                .exists()
            )
        if self.instance.project is not None:
            return (
                addon_model.objects.filter(
                    name=MsgmergeAddon.name,
                )
                .filter(
                    models.Q(project=self.instance.project)
                    | models.Q(
                        component__isnull=True,
                        category__isnull=True,
                        project__isnull=True,
                    )
                )
                .exists()
            )
        return addon_model.objects.filter(
            component__isnull=True,
            category__isnull=True,
            project__isnull=True,
            name=MsgmergeAddon.name,
        ).exists()

    def get_msgmerge_addon_create_kwargs(
        self,
    ) -> dict[str, Component | Category | Project | None]:
        if self.instance.component is not None:
            return {"component": self.instance.component}
        if self.instance.category is not None:
            return {"category": self.instance.category}
        if self.instance.project is not None:
            return {"project": self.instance.project}
        return {}

    def post_configure_run(self) -> None:
        self.ensure_msgmerge_addon()
        super().post_configure_run()
        if self.instance.configuration.pop("_install_msgmerge", False):
            self.instance.save(update_fields=["configuration"])

    def post_configure_run_component(
        self, component: Component, skip_daily: bool = False
    ) -> None:
        self.update_component_state(
            component,
            lambda state: state.__setitem__("_force_run", True),
        )
        try:
            super().post_configure_run_component(component, skip_daily=skip_daily)
        finally:
            self.update_component_state(
                component,
                lambda state: state.pop("_force_run", None),
            )
            if self.alerts or self.warnings:
                self.trigger_alerts(component)

    def is_schedule_due(self, component: Component) -> bool:
        state = self.get_component_state(component)
        if state.get("_force_run"):
            return True
        if component.alert_set.filter(name=self.alert).exists():
            return True
        last_run = cast("str | None", state.get("last_run"))
        if not last_run:
            return True
        try:
            last_run_date = date.fromisoformat(last_run)
        except ValueError:
            return True
        return timezone.now().date() - last_run_date >= timedelta(
            days=self.get_interval()
        )

    def get_last_successful_revision(self, component: Component) -> str | None:
        revision = self.get_component_state(component).get("last_revision")
        return revision if isinstance(revision, str) and revision else None

    def get_configuration_signature(self) -> str:
        return json.dumps(self.instance.configuration, sort_keys=True, default=str)

    def get_last_successful_configuration_signature(
        self, component: Component
    ) -> str | None:
        signature = self.get_component_state(component).get("configuration_signature")
        return signature if isinstance(signature, str) and signature else None

    def mark_successful_run(self, component: Component, revision: str) -> None:
        configuration_signature = self.get_configuration_signature()
        today = timezone.now().date().isoformat()
        self.update_component_state(
            component,
            lambda state: state.update(
                {
                    "last_run": today,
                    "last_revision": revision,
                    "configuration_signature": configuration_signature,
                }
            ),
        )

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
        file_format_cls = cast("PoFormat", component.file_format_cls)
        store = file_format_cls(
            filename,
            file_format_params=component.file_format_params,
        )
        header = store.store.units[0]
        component_name = self.get_component_full_name(component)
        had_descriptive_title = "SOME DESCRIPTIVE TITLE.\n" in header.target.splitlines(
            keepends=True
        )
        header.othercomments = [
            comment
            for comment in header.othercomments
            if not comment.startswith("# FIRST AUTHOR")
            and not comment.startswith(
                "# Copyright (C) YEAR THE PACKAGE'S COPYRIGHT HOLDER"
            )
            and not comment.startswith(
                "# This file is distributed under the same license as the"
            )
            and not re.match(r"^# Copyright \(C\) [0-9– -]* Michal Čihař", comment)
        ]

        header_updates = {"project_id_version": component_name}
        if component.report_source_bugs:
            header_updates["report_msgid_bugs_to"] = component.report_source_bugs
        store.update_header(**header_updates)

        if had_descriptive_title:
            title_line = f"Translations for {component_name}.\n"
            header_lines = header.target.splitlines(keepends=True)
            insert_at = next(
                (
                    index
                    for index, line in enumerate(header_lines)
                    if line.startswith("Content-Type:")
                ),
                len(header_lines),
            )
            header_lines.insert(insert_at, title_line)
            header.target = "".join(header_lines)

        store.save()

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

    def validate_repository_tree(
        self, component: Component, root: Path | None = None
    ) -> bool:
        pending = [root or Path(component.full_path)]
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
        return self.is_schedule_due(component)

    def execute_update(self, component: Component, previous_head: str) -> bool:
        raise NotImplementedError

    def update_translations(self, component: Component, previous_head: str) -> None:
        self.extra_files = []
        self.successful_components.discard(component.pk)
        self.pending_successful_revisions.pop(component.pk, None)
        current_revision = component.repository.last_revision
        if not self.should_run_update(component, previous_head):
            return
        if self.execute_update(component, previous_head) and not self.alerts:
            if msgmerge_addon := self.get_msgmerge_addon(component):
                msgmerge_addon.update_translations(component, "")
            self.pending_successful_revisions[component.pk] = current_revision
            self.successful_components.add(component.pk)
        self.trigger_alerts(component)

    def commit_and_push(
        self,
        component: Component,
        files: list[str] | None = None,
        skip_push: bool = False,
    ) -> bool:
        committed = super().commit_and_push(component, files=files, skip_push=skip_push)
        revision = self.pending_successful_revisions.pop(component.pk, None)
        if revision is None:
            return committed
        if committed:
            self.mark_successful_run(component, component.repository.last_revision)
        else:
            self.mark_successful_run(component, revision)
        return committed


class XgettextAddon(ExtractPotBaseAddon):
    name = "weblate.gettext.xgettext"
    version_added = "5.17"
    verbose = gettext_lazy("Update POT file (xgettext)")
    description = gettext_lazy(
        "Updates the gettext template using xgettext on selected source files."
    )
    settings_form = XgettextExtractPotForm

    def __init__(self, storage) -> None:
        super().__init__(storage)
        self._relevant_changes_cache: dict[tuple[object, ...], bool] = {}

    @classmethod
    def can_install(
        cls,
        *,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
    ) -> bool:
        return find_runtime_command("xgettext") is not None and super().can_install(
            component=component, category=category, project=project
        )

    def get_source_patterns(self) -> list[str]:
        return self.instance.configuration.get("source_patterns", [])

    def get_input_mode(self) -> str:
        return self.instance.configuration.get("input_mode", "patterns")

    def get_potfiles_path(self) -> str:
        return self.instance.configuration.get("potfiles_path", "")

    def get_potfiles_manifest_filename(self, component: Component) -> Path:
        return Path(component.full_path) / self.get_potfiles_path()

    def resolve_potfiles_manifest(self, component: Component) -> Path | None:
        manifest = self.get_potfiles_manifest_filename(component)
        try:
            component.repository.resolve_symlinks(os.fspath(manifest))
        except ValueError:
            component.log_error(
                "refused to read POTFILES manifest out of repository: %s", manifest
            )
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": "xgettext",
                    "output": os.fspath(manifest),
                    "error": "POTFILES manifest points outside repository",
                }
            )
            return None
        if not manifest.exists():
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": "xgettext",
                    "output": self.get_potfiles_path(),
                    "error": "POTFILES manifest not found",
                }
            )
            return None
        if not manifest.is_file():
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": "xgettext",
                    "output": self.get_potfiles_path(),
                    "error": "POTFILES path has to point to a file",
                }
            )
            return None
        return manifest

    def resolve_potfiles_entries(self, component: Component) -> list[str]:
        manifest = self.resolve_potfiles_manifest(component)
        if manifest is None:
            return []

        result: set[str] = set()
        base_dir = manifest.parent
        for raw_line in manifest.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            candidate = Path(line)
            if candidate.is_absolute():
                self.alerts.append(
                    {
                        "addon": self.name,
                        "command": "xgettext",
                        "output": line,
                        "error": "POTFILES entries must be relative paths",
                    }
                )
                return []
            resolved = (base_dir / candidate).resolve(strict=False)
            try:
                component.repository.resolve_symlinks(os.fspath(resolved))
            except ValueError:
                component.log_error(
                    "refused to read POTFILES input out of repository: %s", resolved
                )
                self.alerts.append(
                    {
                        "addon": self.name,
                        "command": "xgettext",
                        "output": line,
                        "error": "POTFILES entry points outside repository",
                    }
                )
                return []
            try:
                relative = resolved.relative_to(Path(component.full_path))
            except ValueError:
                self.alerts.append(
                    {
                        "addon": self.name,
                        "command": "xgettext",
                        "output": line,
                        "error": "POTFILES entry points outside repository",
                    }
                )
                return []
            if not resolved.is_file():
                self.alerts.append(
                    {
                        "addon": self.name,
                        "command": "xgettext",
                        "output": line,
                        "error": "POTFILES entry not found",
                    }
                )
                return []
            result.add(relative.as_posix())
        return sorted(result)

    def get_relevant_changes_cache_key(
        self, component: Component, previous_head: str
    ) -> tuple[object, ...]:
        return (
            component.pk,
            previous_head,
            self.get_last_successful_revision(component),
            self.get_last_successful_configuration_signature(component),
            self.get_configuration_signature(),
            bool(self.get_component_state(component).get("_force_run")),
            component.alert_set.filter(name=self.alert).exists(),
        )

    def has_relevant_changes(self, component: Component, previous_head: str) -> bool:
        cache_key = self.get_relevant_changes_cache_key(component, previous_head)
        if cache_key in self._relevant_changes_cache:
            return self._relevant_changes_cache[cache_key]
        if self.get_component_state(component).get("_force_run"):
            self._relevant_changes_cache[cache_key] = True
            return True
        if component.alert_set.filter(name=self.alert).exists():
            self._relevant_changes_cache[cache_key] = True
            return True
        if (
            self.get_last_successful_configuration_signature(component)
            != self.get_configuration_signature()
        ):
            self._relevant_changes_cache[cache_key] = True
            return True
        compare_revision = self.get_last_successful_revision(component) or previous_head
        if not compare_revision:
            self._relevant_changes_cache[cache_key] = True
            return True
        try:
            changed = component.repository.list_changed_files(
                component.repository.ref_to_remote.format(compare_revision)
            )
        except RepositoryError as error:
            component.log_info(
                "%s addon falling back to full rerun, could not compare against %s: %s",
                self.name,
                compare_revision,
                error,
            )
            self._relevant_changes_cache[cache_key] = True
            return True
        if self.get_input_mode() == "potfiles":
            watched_paths = set(self.resolve_potfiles_entries(component))
            if self.alerts:
                self._relevant_changes_cache[cache_key] = True
                return True
            watched_paths.add(self.get_potfiles_path())
            result = any(path in watched_paths for path in changed)
        else:
            result = any(
                PurePosixPath(path).match(pattern)
                for pattern in self.get_source_patterns()
                for path in changed
            )
        self._relevant_changes_cache[cache_key] = result
        return result

    def resolve_input_files(self, component: Component) -> list[str]:
        if self.get_input_mode() == "potfiles":
            return self.resolve_potfiles_entries(component)
        result: set[str] = set()
        root = Path(component.full_path)
        patterns = self.get_source_patterns()
        for current, dirnames, filenames in root.walk(follow_symlinks=False):
            # Never descend into symlinked directories, even if they point back
            # into the repository tree.
            dirnames[:] = [
                dirname for dirname in dirnames if not (current / dirname).is_symlink()
            ]
            for filename in filenames:
                match = current / filename
                relative = os.path.relpath(match, component.full_path).replace(
                    os.sep, "/"
                )
                if not any(
                    PurePosixPath(relative).match(pattern) for pattern in patterns
                ):
                    continue
                try:
                    component.repository.resolve_symlinks(os.fspath(match))
                except ValueError:
                    component.log_error("refused to read out of repository: %s", match)
                    continue
                result.add(relative)
        return sorted(result)

    def should_run_update(self, component: Component, previous_head: str) -> bool:
        return super().should_run_update(
            component, previous_head
        ) and self.has_relevant_changes(component, previous_head)

    def execute_update(self, component: Component, previous_head: str) -> bool:
        if not self.has_relevant_changes(component, previous_head):
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
            if not self.alerts:
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
                    *self.get_gettext_format_args(component),
                    "--",
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
        if not (
            find_runtime_command("xgettext") is not None
            and find_runtime_command("msguniq") is not None
            and super().can_install(
                component=component, category=category, project=project
            )
        ):
            return False
        if component is None:
            return True
        if Path(component.new_base).stem not in {"django", "djangojs"}:
            return False
        return cls.get_source_dir(component) is not None

    def execute_update(self, component: Component, previous_head: str) -> bool:
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
        if not self.validate_repository_tree(component, source_dir):
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": "django makemessages",
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
            "--source-prefix",
            self.get_source_prefix(component, source_dir),
            *self.get_gettext_format_args(component),
        ]
        with tempfile.TemporaryDirectory(prefix="weblate-django-") as tempdir:
            locale_dir = Path(tempdir) / "locale"
            env = {"WEBLATE_EXTRACT_LOCALE_PATH": os.fspath(locale_dir)}
            if (
                self.run_process(
                    component, command, env=env, cwd=os.fspath(component.full_path)
                )
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

    @staticmethod
    def get_source_dir(component: Component) -> Path | None:
        template = Path(component.new_base)
        parts = template.parts
        if "locale" not in parts:
            return Path(component.full_path)
        locale_index = parts.index("locale")
        if locale_index == 0:
            return Path(component.full_path)
        if locale_index == 1 and parts[0] == "conf":
            return Path(component.full_path)
        source_dir = Path(component.full_path).joinpath(*parts[:locale_index])
        if not source_dir.is_dir():
            return None
        return source_dir

    @staticmethod
    def get_source_prefix(component: Component, source_dir: Path) -> str:
        relative = os.path.relpath(source_dir, component.full_path)
        return "." if relative == "." else relative.replace(os.sep, "/")


class SphinxAddon(ExtractPotBaseAddon):
    name = "weblate.gettext.sphinx"
    version_added = "5.17"
    verbose = gettext_lazy("Update POT file (Sphinx)")
    description = gettext_lazy(
        "Updates the gettext template using Sphinx's gettext builder without loading project configuration."
    )
    settings_form = SphinxExtractPotForm
    WEBLATE_DOCS_EXCLUDE_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"""
        ^(
            [0-9]+
            |
            [A-Z]*_[A-Z_]*
            |
            ``[^`]*``
            |
            :[a-z]*:`[a-z0-9./_\*-]*`
            |
            [<>]json[ ].*
            |
            :(ref|doc|setting|envvar):`[^<`]+`
            |
            /[a-z_./-]+
            |
            Django
            |
            Translate\ Toolkit
            |
            `([a-z0-9_-]*)\ <[^>]*>`_
        )$
        """,
        re.VERBOSE,
    )
    WEBLATE_DOCS_NAMES_RE: ClassVar[re.Pattern[str]] = re.compile(r"^[a-z_]+$")

    @classmethod
    def can_install(
        cls,
        *,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
    ) -> bool:
        if not (
            find_runtime_command("sphinx-build") is not None
            and super().can_install(
                component=component, category=category, project=project
            )
        ):
            return False
        if component is None:
            return True
        addon = cls(cls.create_object(component=component))
        source_dir = addon.get_sphinx_source_dir(component)
        return source_dir is not None and (source_dir / "conf.py").is_file()

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

    def get_filter_mode(self) -> str:
        return str(self.instance.configuration.get("filter_mode", "none"))

    def execute_update(self, component: Component, previous_head: str) -> bool:
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
        if not self.validate_repository_tree(component, source_dir):
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": "sphinx-build",
                    "output": component.new_base,
                    "error": "Repository contains symlink outside repository",
                }
            )
            return False
        domain = self.get_domain(component)
        with tempfile.TemporaryDirectory(prefix="weblate-sphinx-") as tempdir:
            doctree_dir = Path(tempdir) / "doctrees"
            build_dir = Path(tempdir) / "build"
            # Sphinx derives DOCUTILSCONFIG from the trusted -c directory, so the
            # bundled docutils.conf next to conf.py hardens Docutils without
            # needing a separate environment override here.
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
                ".",
                os.fspath(build_dir),
            ]
            if self.run_process(component, command, cwd=os.fspath(source_dir)) is None:
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
            self.postprocess_sphinx_template(
                component, generated, source_dir, build_dir
            )
            template = self.get_template_filename(component)
            if template is None:
                return False
            Path(template).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(generated, template)
        return self.finalize_template(component)

    def postprocess_sphinx_template(
        self, component: Component, template: Path, source_dir: Path, build_dir: Path
    ) -> None:
        source_root = source_dir.resolve()
        build_root = build_dir.resolve()
        file_format_cls = cast("PoFormat", component.file_format_cls)
        store = file_format_cls(
            template,
            file_format_params=component.file_format_params,
        )
        changed = False
        for unit in store.content_units:
            locations = unit.mainunit.getlocations()
            normalized_locations = [
                SphinxAddon.normalize_sphinx_location(location, source_root, build_root)
                for location in locations
            ]
            if normalized_locations == locations:
                continue
            unit.mainunit.sourcecomments = [
                comment
                for comment in unit.mainunit.sourcecomments
                if not comment.startswith("#:")
            ]
            for location in normalized_locations:
                unit.mainunit.addlocation(location)
            changed = True

        if self.get_filter_mode() == "weblate_docs":
            filtered_units = [
                unit
                for unit in store.store.units
                if unit.isheader() or not self.should_skip_weblate_docs_unit(unit)
            ]
            if len(filtered_units) != len(store.store.units):
                store.store.units = filtered_units
                changed = True

        if changed:
            store.save()

    @classmethod
    def should_skip_weblate_docs_unit(cls, unit) -> bool:
        if cls.WEBLATE_DOCS_EXCLUDE_RE.match(unit.source):
            return True
        return bool(
            any("admin/management.rst" in location for location in unit.getlocations())
            and cls.WEBLATE_DOCS_NAMES_RE.match(unit.source)
        )

    @staticmethod
    def normalize_sphinx_location(
        location: str, source_root: Path, build_root: Path
    ) -> str:
        path_part, separator, line_part = location.rpartition(":")
        if not separator or not line_part.isdigit():
            return location
        candidate = Path(path_part)
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (build_root / candidate).resolve()
        )
        try:
            relative = resolved.relative_to(source_root)
        except ValueError:
            return location
        return f"{relative.as_posix()}:{line_part}"


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
