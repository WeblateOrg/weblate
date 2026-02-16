# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Internal Django service for Boost documentation add-or-update.

Uses only in-memory component data: no temporary JSON files.
Builds supported formats from Weblate's FILE_FORMATS (same as list_file_format_params).
Creates/updates Project and Component via Django ORM only (no external API).

Alignment with REST API (POST /api/projects/, POST .../components/, POST .../translations/):
- Project: same as API (get_or_create + post_create when created). API does not use Celery for create.
- Component: same create + post_create; we then call do_update/create_translations_immediate so the
  component is ready before adding a language. The API relies on Component.save() which schedules
  component_after_save (Celery when not eager), so the API does not wait for repo/template in the request.
- Translation: same checks and add_new_language as API; we call create_translations_immediate before
  so template is on disk (API assumes component was already synced).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.messages import get_messages
from django.db import transaction

from weblate.formats.models import FILE_FORMATS
from weblate.lang.models import Language
from weblate.logger import LOGGER
from weblate.trans.models import Component, Project
from weblate.utils.errors import report_error

# Weblate API limit for component name
MAX_COMPONENT_NAME_LENGTH = 100
# When over limit: first 64 + " ... " + last 25 (94 chars) to keep names unique
TRUNCATE_NAME_HEAD = 64
TRUNCATE_NAME_TAIL = 25
TRUNCATE_NAME_SEP = " ... "
# Seconds to wait after sync so VCS lock can release / repo state can settle
SYNC_SETTLE_SECONDS = 60


def _submodule_slug(name: str) -> str:
    """Normalize submodule name to URL-safe slug: lower case, underscores to hyphens."""
    return name.lower().replace("_", "-")


def truncate_component_name(name: str, max_len: int = MAX_COMPONENT_NAME_LENGTH) -> str:
    """Truncate component name to max_len. If over limit: first 64 + ' ... ' + last 25."""
    if len(name) <= max_len:
        return name
    return name[:TRUNCATE_NAME_HEAD] + TRUNCATE_NAME_SEP + name[-TRUNCATE_NAME_TAIL:]


def _build_extension_to_format() -> dict[str, str]:
    """Build extension -> format_id from Weblate FILE_FORMATS (internal API)."""
    result = {}
    for format_cls in FILE_FORMATS.data.values():
        format_id = getattr(format_cls, "format_id", None) or getattr(
            format_cls, "name", ""
        )
        if not format_id or not getattr(format_cls, "autoload", ()):
            continue
        for pattern in format_cls.autoload:
            # e.g. "*.adoc" -> ".adoc", "*.po" -> ".po"
            if pattern.startswith("*.") and len(pattern) > 2:
                ext = "." + pattern[2:].lower()
                result[ext] = format_id
    return result


class BoostComponentService:
    """Service for managing Boost documentation components (internal Django usage)."""

    def __init__(
        self,
        organization: str,
        lang_code: str,
        version: str,
        extensions: list[str] | None = None,
    ):
        self.organization = organization
        self.lang_code = lang_code
        self.version = version
        self.extensions = extensions  # If None or empty, no filtering by extension list
        self.temp_dir: str | None = None
        self._ext_to_format: dict[str, str] | None = None

    def get_extension_to_format(self) -> dict[str, str]:
        """Extension -> Weblate format_id from FILE_FORMATS."""
        if self._ext_to_format is None:
            self._ext_to_format = _build_extension_to_format()
        return self._ext_to_format

    def get_supported_extensions(self) -> set[str]:
        """Set of supported file extensions (from Weblate formats).
        If self.extensions is non-empty, restrict to those that are both
        Weblate-supported and in the list.
        """
        supported = set(self.get_extension_to_format().keys())
        if not self.extensions:
            return supported
        # Normalize: ensure leading dot and lower case for comparison
        allowed = set()
        for e in self.extensions:
            e = e.strip().lower()
            if e and not e.startswith("."):
                e = "." + e
            if e:
                allowed.add(e)
        return supported & allowed

    def clone_repository(self, submodule: str, target_dir: str, branch: str = "local") -> bool:
        """Clone a git repository to target directory."""
        repo_url = f"https://github.com/{self.organization}/{submodule}.git"

        try:
            LOGGER.info("Cloning %s to %s", repo_url, target_dir)
            cmd = ["git", "clone", "-b", branch, "--depth", "1", repo_url, target_dir]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                LOGGER.error("Failed to clone: %s", result.stderr)
                return False

            LOGGER.info("Cloned %s", submodule)
            return True

        except subprocess.TimeoutExpired:
            LOGGER.error("Clone timeout for %s", submodule)
            return False
        except Exception as e:
            LOGGER.error("Clone exception: %s", e)
            report_error(cause="Boost component clone")
            return False

    def scan_documentation_files(self, repo_dir: str) -> list[dict[str, Any]]:
        """Scan repo for doc files; return list of in-memory component configs.
        Only files in subfolders are included; files in repo root are skipped.
        Uses get_supported_extensions() which respects self.extensions when set.
        """
        supported_exts = self.get_supported_extensions()
        configs = []

        for root, dirs, files in os.walk(repo_dir):
            # Skip hidden directories and common non-doc directories
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".") and d not in {"__pycache__", "node_modules"}
            ]

            for file in files:
                file_path = Path(root) / file
                ext = file_path.suffix.lower()

                if ext not in supported_exts:
                    continue

                relative_path = file_path.relative_to(repo_dir)
                # Skip files in repo root (only include files in subfolders)
                if len(relative_path.parts) <= 1:
                    continue

                config = self.generate_component_config(str(relative_path), ext)
                if config:
                    configs.append(config)

        return configs

    def generate_component_config(self, file_path: str, extension: str) -> dict[str, Any] | None:
        """Build in-memory component config for a doc file (no JSON file written)."""
        ext_to_fmt = self.get_extension_to_format()
        file_format = ext_to_fmt.get(extension)
        if not file_format:
            return None

        # Extract file name without extension
        path_obj = Path(file_path)
        filename_base = path_obj.stem
        dir_path = path_obj.parent

        # Generate component name from path
        component_name_parts = []
        if str(dir_path) != ".":
            component_name_parts.extend(dir_path.parts)
        component_name_parts.append(filename_base)
        component_name = " / ".join(
            part.replace("_", " ").replace("-", " ").title()
            for part in component_name_parts
        )

        # Generate slug
        slug_parts = [part.lower().replace("_", "-") for part in component_name_parts]
        component_slug = "-".join(slug_parts)

        # File mask for translations (e.g., "doc/intro_*.adoc" for "doc/intro.adoc")
        filemask = str(dir_path / f"{filename_base}_*{extension}")
        template = file_path
        new_base = file_path

        return {
            "component_name": component_name,
            "component_slug": component_slug,
            "filemask": filemask,
            "template": template,
            "new_base": new_base,
            "file_format": file_format,
            "file_path": file_path,
        }

    def get_or_create_project(self, submodule: str, user=None) -> Project:
        """Get or create a Weblate project for the submodule."""
        slug = _submodule_slug(submodule)
        project_name = f"Boost {submodule.replace('_', ' ').title()} Documentation"
        project_slug = f"boost-{slug}-documentation"
        project_web = f"https://www.boost.org/doc/libs/master/libs/{slug}/doc/html/"

        with transaction.atomic():
            project, created = Project.objects.get_or_create(
                slug=project_slug,
                defaults={
                    "name": project_name,
                    "web": project_web,
                    "instructions": (
                        f"Please translate the Boost.{submodule.replace('_', ' ').title()} "
                        "documentation. Maintain technical accuracy and follow exact "
                        "formatting conventions."
                    ),
                    "access_control": Project.ACCESS_PUBLIC,
                    "commit_policy": 0,
                }
            )

            if created:
                LOGGER.info("Created project: %s", project_name)
                # Match API: ProjectViewSet.create uses perform_create -> post_create(user, billing).
                if user:
                    project.post_create(user, billing=None)
            else:
                LOGGER.info("Project exists: %s", project_name)

            if user:
                project.acting_user = user

        return project

    def create_or_update_component(
        self,
        project: Project,
        submodule: str,
        config: dict[str, Any],
        user=None,
        request=None,
    ) -> tuple[Component | None, bool]:
        """Create or update a component. Returns (component, was_created).

        Settings and logic aligned with scripts/auto/create_component.py and
        scripts/auto/boost-submodule-component-configs/setup_boost-*-.json
        (same as API POST projects/{project_slug}/components/).
        """
        required_config_keys = {
            "component_slug",
            "component_name",
            "filemask",
            "template",
            "new_base",
            "file_format",
        }
        missing = required_config_keys - set(config.keys())
        if missing:
            LOGGER.error("Invalid component config: missing keys %s", missing)
            return None, False

        slug = _submodule_slug(submodule)
        component_slug = f"boost-{slug}-documentation-{config['component_slug']}"
        # Match reference: push_branch keeps lang_code as-is (e.g. zh_Hans)
        push_branch = f"boost-{slug}-{self.lang_code}-translation-{self.version}"

        # Component name: "Boost {Submodule} Documentation / Doc / Library Detail"
        submodule_title = submodule.replace("_", " ").title()
        component_name = truncate_component_name(
            f"Boost {submodule_title} Documentation / {config['component_name']}"
        )

        # Source language: "en" (hardcoded)
        try:
            source_language = Language.objects.get(code="en")
        except Language.DoesNotExist:
            LOGGER.error("Source language 'en' not found; cannot create component")
            report_error(cause="Component creation/update")
            return None, False

        # Single clone per repo: first component gets real repo, others use weblate://
        real_repo = f"git@github.com:{self.organization}/{submodule}.git"
        repo_owner = (
            Component.objects.filter(project=project, repo=real_repo)
            .order_by("slug")
            .first()
        )
        if repo_owner is not None:
            # Another component already has the clone; link to it
            repo_url = f"weblate://{project.slug}/{repo_owner.slug}"
            push_url = ""
        else:
            repo_url = real_repo
            push_url = real_repo

        # Component defaults aligned with create_component.py / reference JSON
        component_defaults = {
            "name": component_name,
            "vcs": "github",
            "repo": repo_url,
            "push": push_url,
            "branch": "local",
            "push_branch": push_branch,
            "filemask": config["filemask"],
            "template": config["template"],
            "new_base": config["new_base"],
            "file_format": config["file_format"],
            "edit_template": False,
            "source_language": source_language,
            "license": "",
            "allow_translation_propagation": False,
            "enable_suggestions": True,
            "suggestion_voting": False,
            "suggestion_autoaccept": 0,
            "check_flags": "",
            "language_regex": f"^{self.lang_code}$",
        }

        try:
            # Ensure project still exists (e.g. not deleted by another process)
            if not Project.objects.filter(pk=project.pk).exists():
                project = self.get_or_create_project(submodule, user=user)
            with transaction.atomic():
                component, created = Component.objects.get_or_create(
                    project=project,
                    slug=component_slug,
                    defaults=component_defaults,
                )

                if user:
                    component.acting_user = user

                if created:
                    LOGGER.info("Created component: %s", component.name)
                    # Match API: ProjectViewSet.components (POST) calls instance.post_create(user, origin="api")
                    if user:
                        component.post_create(user, origin="boost_endpoint")
                    # Synchronization: ensure repo/translations exist before add_language_to_component.
                    self._sync_component_for_translation(component, request, created=True)
                else:
                    LOGGER.info("Component exists: %s", component.name)
                    # Ensure branch is "local" (avoid "fatal: no such branch: 'master'"
                    # when remote has no master/main)
                    update_fields = []
                    if component.branch != "local":
                        component.branch = "local"
                        update_fields.append("branch")
                    if component.push_branch != push_branch:
                        component.push_branch = push_branch
                        update_fields.append("push_branch")
                    if update_fields:
                        component.save(update_fields=update_fields)

                    # Trigger git pull only for repo owner; linked components share the same lock.
                    self._sync_component_for_translation(component, request, created=False)
                # Add language: ensure template/translations are loaded (sync) so add_new_language can succeed.
                self.add_language_to_component(component, request)

            return component, created

        except Exception as e:
            LOGGER.error(
                "Failed to create/update component (%s): %s",
                type(e).__name__,
                e,
            )
            report_error(cause="Component creation/update")
            return None, False

    def _sync_component_for_translation(
        self, component: Component, request, *, created: bool
    ) -> None:
        """Ensure repo/translations are ready before add_language_to_component. Idempotent."""
        if not component.is_repo_link:
            try:
                component.do_update(request)
                LOGGER.info(
                    "%s for %s",
                    "Initial clone/update for new component"
                    if created
                    else "Updated component repository",
                    component.name,
                )
            except Exception as e:
                LOGGER.warning(
                    "Failed to %s %s: %s",
                    "clone/update new component" if created else "update component",
                    component.name,
                    e,
                )
                report_error(cause="Component creation" if created else "Component update")
        else:
            if not created:
                LOGGER.info("Skipping do_update for repo link: %s", component.name)
            try:
                component.create_translations_immediate(request=request, force=True)
                LOGGER.info(
                    "%s: %s",
                    "Loaded translations for new repo link"
                    if created
                    else "Refreshed translations for repo link",
                    component.name,
                )
            except Exception as e:
                LOGGER.warning(
                    "Failed to %s %s: %s",
                    "load translations for new link" if created else "refresh translations for",
                    component.name,
                    e,
                )

        time.sleep(SYNC_SETTLE_SECONDS)

    def add_language_to_component(
        self, component: Component, request=None
    ) -> bool:
        """Add language to component if not already added.

        Logic matches API view ComponentViewSet.translations (POST).
        """
        if request is None:
            LOGGER.error("add_language_to_component requires request for permissions")
            return False

        try:
            language = Language.objects.get(code=self.lang_code)
        except Language.DoesNotExist:
            LOGGER.error("Language %s not found", self.lang_code)
            return False

        if component.translation_set.filter(language=language).exists():
            LOGGER.info(
                "Language %s already exists in %s", self.lang_code, component.name
            )
            return True

        # Guarantee synchronization: ensure template/base is on disk before can_add_new_language.
        # When CELERY_TASK_ALWAYS_EAGER is False, do_update/create_translations only schedule a task.
        try:
            component.create_translations_immediate(request=request, force=True)
        except Exception as e:
            LOGGER.warning("create_translations_immediate before add language: %s", e)

        if not request.user.has_perm("translation.add", component):
            LOGGER.warning("Can not create translation: no translation.add on %s", component.name)
            return False

        if not component.can_add_new_language(request.user):
            reason = getattr(component, "new_lang_error_message", None) or "Can not add new language"
            LOGGER.warning("Could not add language %s to %s: %s", self.lang_code, component.name, reason)
            return False

        base_languages = component.get_all_available_languages()
        if not request.user.has_perm("translation.add_more", component):
            base_languages = base_languages.filter_for_add(component.project)

        try:
            language = base_languages.get(code=self.lang_code)
        except Language.DoesNotExist:
            LOGGER.error("Could not add %r to %s (language not available)", self.lang_code, component.name)
            return False

        try:
            translation = component.add_new_language(language, request)
        except Exception as e:
            LOGGER.error("Failed to add language %s: %s", self.lang_code, e)
            report_error(cause="Add language")
            return False

        if translation is None:
            storage = get_messages(request)
            message = "\n".join(m.message for m in storage) if storage else (
                getattr(component, "new_lang_error_message", None)
                or f"Could not add {self.lang_code!r}!"
            )
            LOGGER.warning("Could not add language %s to %s: %s", self.lang_code, component.name, message)
            return False

        LOGGER.info("Added language %s to %s", self.lang_code, component.name)
        return True

    def _delete_component_and_commit_removal(
        self, component: Component, result: dict[str, Any]
    ) -> None:
        """Delete component, remove its translation files from disk, commit and push.

        Updates result["components_deleted"] and result["errors"] as needed.
        """
        name = component.name
        base_path = component.full_path
        repo_owner = component.linked_component if component.is_repo_link else component
        push_branch = repo_owner.push_branch
        push_url = repo_owner.push
        translation_files = [
            os.path.join(base_path, t.filename)
            for t in component.translation_set.exclude(
                language=component.source_language
            )
        ]
        component.delete()

        removed_any = False
        for file_path in translation_files:
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    removed_any = True
                    LOGGER.info("Removed translation file: %s", file_path)
                except OSError as e:
                    LOGGER.warning(
                        "Failed to remove translation file %s: %s",
                        file_path,
                        e,
                    )
                    result["errors"].append(f"Failed to remove {file_path}: {e}")

        if removed_any and os.path.isdir(os.path.join(base_path, ".git")):
            try:
                subprocess.run(
                    ["git", "-C", base_path, "add", "-u"],
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                status = subprocess.run(
                    ["git", "-C", base_path, "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if status.stdout.strip():
                    author = (
                        f"{getattr(settings, 'DEFAULT_COMMITER_NAME', 'Weblate')} "
                        f"<{getattr(settings, 'DEFAULT_COMMITER_EMAIL', 'noreply@weblate.org')}>"
                    )
                    subprocess.run(
                        [
                            "git",
                            "-C",
                            base_path,
                            "commit",
                            "-m",
                            f"Remove translation files for deleted component: {name}",
                            "--author",
                            author,
                        ],
                        check=True,
                        capture_output=True,
                        timeout=30,
                    )
                    LOGGER.info("Committed deletion of translation files for: %s", name)
                    if push_url and push_branch:
                        subprocess.run(
                            [
                                "git",
                                "-C",
                                base_path,
                                "push",
                                "origin",
                                push_branch,
                            ],
                            check=True,
                            capture_output=True,
                            timeout=120,
                        )
                        LOGGER.info("Pushed to origin %s", push_branch)
            except subprocess.CalledProcessError as e:
                LOGGER.warning(
                    "Git commit/push failed for %s: %s", name, e.stderr or e
                )
                result["errors"].append(
                    f"Git commit/push failed: {e.stderr or e}"
                )
            except subprocess.TimeoutExpired:
                LOGGER.warning("Git commit/push timeout for %s", name)
                result["errors"].append("Git commit/push timeout")

        result["components_deleted"] += 1
        LOGGER.info("Deleted component (not in configs): %s", name)

    def process_submodule(
        self, submodule: str, user=None, request=None
    ) -> dict[str, Any]:
        """Process a single submodule: clone, scan, create/update components."""
        result = {
            "submodule": submodule,
            "success": False,
            "components_created": 0,
            "components_updated": 0,
            "components_deleted": 0,
            "errors": [],
        }

        # Create temp directory for this submodule
        temp_submodule_dir = os.path.join(self.temp_dir, submodule)
        os.makedirs(temp_submodule_dir, exist_ok=True)

        # Clone repository
        if not self.clone_repository(submodule, temp_submodule_dir, "master"):
            result["errors"].append(f"Failed to clone repository for {submodule}")
            return result

        # Scan for documentation files
        configs = self.scan_documentation_files(temp_submodule_dir)
        if not configs:
            result["errors"].append(f"No supported documentation files found in {submodule}")
            return result

        LOGGER.info("Found %s documentation files in %s", len(configs), submodule)

        # Get or create project
        try:
            project = self.get_or_create_project(submodule, user)
        except Exception as e:
            result["errors"].append(f"Failed to create project: {e}")
            report_error(cause="Project creation")
            return result

        # Match API: ProjectViewSet.components (POST) requires project.edit on the project
        if request is not None and user is not None and not user.has_perm("project.edit", project):
            result["errors"].append("Can not create components (missing project.edit)")
            return result

        # Create or update components
        for config in configs:
            component, was_created = self.create_or_update_component(
                project, submodule, config, user=user, request=request
            )
            if component is not None:
                if was_created:
                    result["components_created"] += 1
                else:
                    result["components_updated"] += 1

        # Delete components that are not in configs (no longer in repo scan).
        # Never delete glossary components (is_glossary); they are managed by Weblate.
        prefix = f"boost-{_submodule_slug(submodule)}-documentation-"
        wanted_slugs = {f"{prefix}{c['component_slug']}" for c in configs}
        for component in project.component_set.all():
            if component.slug not in wanted_slugs and not component.is_glossary:
                try:
                    self._delete_component_and_commit_removal(component, result)
                except Exception as e:
                    LOGGER.warning(
                        "Failed to delete component %s: %s", component.slug, e
                    )
                    result["errors"].append(f"Failed to delete {component.slug}: {e}")

        result["success"] = True
        return result

    def process_all(
        self, submodules: list[str], user=None, request=None
    ) -> dict[str, Any]:
        """Process all submodules."""
        # Create temp directory
        self.temp_dir = tempfile.mkdtemp(prefix="boost_endpoint_")
        LOGGER.info("Using temp directory: %s", self.temp_dir)

        results = {
            "total_submodules": len(submodules),
            "successful": 0,
            "failed": 0,
            "submodule_results": [],
        }

        try:
            for submodule in submodules:
                LOGGER.info("Processing submodule: %s", submodule)
                result = self.process_submodule(
                    submodule, user=user, request=request
                )
                results["submodule_results"].append(result)

                if result["success"]:
                    results["successful"] += 1
                else:
                    results["failed"] += 1

        finally:
            # Cleanup temp directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                LOGGER.info("Cleaned up temp directory: %s", self.temp_dir)

        return results
