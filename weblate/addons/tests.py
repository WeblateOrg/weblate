# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import base64
import contextlib
import json
import os
import re
import shutil
import subprocess  # noqa: S404
import sys
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, ClassVar, TypedDict, cast
from unittest.mock import patch

import jsonschema.exceptions
import requests
import responses
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.management.commands.makemessages import (
    Command as DjangoMakemessagesCommand,
)
from django.core.management.utils import find_command
from django.test import SimpleTestCase, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone
from standardwebhooks.webhooks import Webhook, WebhookVerificationError

from weblate.addons.forms import (
    MesonExtractPotForm,
    SphinxExtractPotForm,
    XgettextExtractPotForm,
)
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.file_format_params import get_default_params_for_file_format
from weblate.trans.models import (
    Announcement,
    Category,
    Change,
    Comment,
    Component,
    PendingUnitChange,
    Suggestion,
    Translation,
    Unit,
    Vote,
)
from weblate.trans.tests.test_views import ComponentTestCase, ViewTestCase
from weblate.utils.site import get_site_url
from weblate.utils.state import (
    FUZZY_STATES,
    STATE_EMPTY,
    STATE_NEEDS_REWRITING,
    STATE_READONLY,
    STATE_TRANSLATED,
)
from weblate.utils.unittest import tempdir_setting
from weblate.vcs.base import Repository, RepositoryError

from .autotranslate import DEFAULT_AUTO_TRANSLATE_THRESHOLD, AutoTranslateAddon
from .base import BaseAddon, UpdateBaseAddon
from .cdn import CDNJSAddon
from .cleanup import CleanupAddon, RemoveBlankAddon, ResetAddon
from .consistency import LanguageConsistencyAddon
from .discovery import DiscoveryAddon
from .events import AddonEvent
from .example import ExampleAddon
from .example_pre import ExamplePreAddon
from .fedora_messaging import FedoraMessagingAddon
from .flags import (
    BulkEditAddon,
    SameEditAddon,
    SourceEditAddon,
    TargetEditAddon,
    TargetRepoUpdateAddon,
)
from .forms import (
    BaseAddonForm,
    DiscoveryForm,
    GenerateForm,
    GitSquashForm,
    PropertiesSortAddonForm,
)
from .generate import (
    FillReadOnlyAddon,
    GenerateFileAddon,
    PrefillAddon,
    PseudolocaleAddon,
)
from .gettext import (
    DJANGO_EXTRACT_RUNNER,
    DjangoAddon,
    GenerateMoAddon,
    GettextAuthorComments,
    MesonAddon,
    MsgmergeAddon,
    SphinxAddon,
    UpdateConfigureAddon,
    UpdateLinguasAddon,
    XgettextAddon,
    is_xgettext_placeholder_comment,
)
from .git import GitSquashAddon
from .models import ADDONS, Addon, AddonActivityLog, handle_addon_event
from .properties import PropertiesSortAddon
from .removal import RemoveComments, RemoveSuggestions
from .resx import ResxUpdateAddon
from .tasks import (
    addon_change,
    cleanup_addon_activity_log,
    daily_addons,
    language_consistency,
    run_addon_manually,
)
from .webhooks import SlackWebhookAddon, WebhookAddon

if TYPE_CHECKING:
    from weblate.trans.models import (
        Project,
    )


class GettextUtilityTest(SimpleTestCase):
    def test_xgettext_placeholder_comment(self) -> None:
        self.assertTrue(is_xgettext_placeholder_comment("# SOME DESCRIPTIVE TITLE.\n"))
        self.assertTrue(is_xgettext_placeholder_comment("# Copyright (C)\n"))
        self.assertTrue(is_xgettext_placeholder_comment("# Copyright (C) \n"))
        self.assertTrue(is_xgettext_placeholder_comment("# Copyright (C) 2026\n"))
        self.assertFalse(
            is_xgettext_placeholder_comment("# Copyright (C) 2026 Example Corp.\n")
        )


class NoOpAddon(BaseAddon):
    """Testing add-on doing nothing."""

    settings_form = BaseAddonForm
    name = "weblate.base.test"
    verbose = "Test add-on"
    description = "Test add-on"


class CrashAddonError(Exception):
    pass


class CrashAddon(UpdateBaseAddon):
    """Testing add-on doing nothing."""

    name = "weblate.base.crash"
    verbose = "Crash test add-on"
    description = "Crash test add-on"

    def update_translations(self, component: Component, previous_head: str) -> None:
        if previous_head:
            msg = "Test error"
            raise CrashAddonError(msg)

    @classmethod
    def can_install(
        cls,
        *,
        component: Component | None = None,  # noqa: ARG003
        category: Category | None = None,  # noqa: ARG003
        project: Project | None = None,  # noqa: ARG003
    ) -> bool:
        return False


class TypedConfigAddonStoredConfiguration(TypedDict, total=False):
    count: int | str


class TypedConfigAddonConfiguration(TypedDict):
    count: int


class TypedConfigAddon(
    BaseAddon[TypedConfigAddonStoredConfiguration, TypedConfigAddonConfiguration]
):
    """Testing add-on with typed configuration normalization."""

    name = "weblate.base.typed"
    verbose = "Typed test add-on"
    description = "Typed test add-on"

    def normalize_configuration(
        self, configuration: TypedConfigAddonStoredConfiguration
    ) -> TypedConfigAddonConfiguration:
        raw_count = configuration.get("count", 0)
        if isinstance(raw_count, str):
            raw_count = int(raw_count)
        return {"count": raw_count}


class ManualResultAddon(BaseAddon):
    events: ClassVar[set[AddonEvent]] = {AddonEvent.EVENT_MANUAL}
    name = "weblate.base.manual-result"
    verbose = "Manual result add-on"
    description = "Manual result add-on"

    def manual_component(
        self,
        component: Component,
        activity_log_id: int | None = None,
    ) -> dict | None:
        return {"component": component.slug}


class TestAddonMixin:
    def setUp(self) -> None:
        super().setUp()
        ADDONS.data[NoOpAddon.name] = NoOpAddon
        ADDONS.data[ExampleAddon.name] = ExampleAddon
        ADDONS.data[CrashAddon.name] = CrashAddon
        ADDONS.data[ExamplePreAddon.name] = ExamplePreAddon
        ADDONS.data[ManualResultAddon.name] = ManualResultAddon

    def tearDown(self) -> None:
        super().tearDown()
        del ADDONS.data[NoOpAddon.name]
        del ADDONS.data[ExampleAddon.name]
        del ADDONS.data[CrashAddon.name]
        del ADDONS.data[ExamplePreAddon.name]
        del ADDONS.data[ManualResultAddon.name]


class AddonBaseTest(TestAddonMixin, ComponentTestCase):
    def test_can_install(self) -> None:
        self.assertTrue(NoOpAddon.can_install(component=self.component))

    def test_needs_component_blocks_non_component_install(self) -> None:
        """Addons with needs_component=True cannot be installed at category/project/site level."""
        self.assertFalse(DiscoveryAddon.can_install(project=self.project))
        category = self.create_category(self.project)
        self.assertFalse(DiscoveryAddon.can_install(category=category))
        self.assertFalse(DiscoveryAddon.can_install())

    def test_example(self) -> None:
        self.assertTrue(ExampleAddon.can_install(component=self.component))
        addon = ExampleAddon.create(component=self.component)
        addon.pre_commit(None, "", True)

    def test_create(self) -> None:
        addon = NoOpAddon.create(component=self.component)
        self.assertEqual(addon.name, "weblate.base.test")
        self.assertEqual(self.component.addon_set.count(), 1)

    def test_create_category_addon(self) -> None:
        category = self.create_category(self.project)
        self.component.category = category
        self.component.save()
        addon = NoOpAddon.create(category=category, acting_user=self.user)
        self.assertEqual(addon.name, "weblate.base.test")
        self.assertEqual(category.addon_set.count(), 1)
        self.assertIn("Test category", str(addon.instance))
        self.component.drop_addons_cache()
        self.assertIn("weblate.base.test", self.component.addons_cache.names)

        sitewide = Addon.objects.filter_sitewide()
        self.assertEqual(sitewide.count(), 0)

    def test_create_project_addon(self) -> None:
        self.component.project.acting_user = self.component.acting_user
        addon = NoOpAddon.create(project=self.component.project)
        self.assertEqual(addon.name, "weblate.base.test")
        self.assertEqual(self.component.project.addon_set.count(), 1)
        self.assertEqual("Test add-on: Test", str(addon.instance))

    def test_create_site_wide_addon(self) -> None:
        addon = NoOpAddon.create(acting_user=self.user)
        self.assertEqual(addon.name, "weblate.base.test")
        addon_object = Addon.objects.filter(name="weblate.base.test")
        self.assertEqual(addon_object.count(), 1)
        self.assertEqual("Test add-on: site-wide", str(addon.instance))

    def test_manual_returns_component_result(self) -> None:
        addon = ManualResultAddon.create(component=self.component, run=False)

        self.assertEqual(addon.manual(component=self.component), {"component": "test"})

    def test_manual_aggregates_multiple_component_results(self) -> None:
        component2 = self.create_po_new_base(
            name="Test 2",
            slug="test-2",
            project=self.project,
        )
        addon = ManualResultAddon.create(project=self.project, run=False)

        self.assertEqual(
            addon.manual(project=self.project),
            {
                "components": {
                    self.component.full_slug: {"component": "test"},
                    component2.full_slug: {"component": component2.slug},
                }
            },
        )

    def test_can_run_manually_for_manual_addon(self) -> None:
        addon = ManualResultAddon.create(component=self.component, run=False)

        self.assertTrue(addon.instance.can_run_manually)

    @patch("weblate.addons.tasks.run_addon_manually.delay_on_commit")
    def test_schedule_manual_run(self, mocked_delay) -> None:
        addon = ManualResultAddon.create(component=self.component, run=False)

        addon.instance.schedule_manual_run()

        mocked_delay.assert_called_once_with(addon.instance.pk)

    def test_run_addon_manually(self) -> None:
        addon = ManualResultAddon.create(component=self.component, run=False)

        run_addon_manually(addon.instance.pk)

        activity = AddonActivityLog.objects.get(addon=addon.instance)
        self.assertEqual(activity.event, AddonEvent.EVENT_MANUAL)
        self.assertEqual(activity.details["result"], {"component": "test"})
        self.assertFalse(activity.pending)

    def test_add_form(self) -> None:
        form = NoOpAddon.get_add_form(None, component=self.component, data={})
        self.assertTrue(form.is_valid())
        form.save()
        self.assertEqual(self.component.addon_set.count(), 1)

        addon = self.component.addon_set.all()[0]
        self.assertEqual(addon.name, "weblate.base.test")

    def test_add_form_category_addon(self) -> None:
        category = self.create_category(self.project)
        form = NoOpAddon.get_add_form(None, category=category, data={})
        self.assertTrue(form.is_valid())
        form.save()
        self.assertEqual(category.addon_set.count(), 1)

        addon = category.addon_set.all()[0]
        self.assertEqual(addon.name, "weblate.base.test")

    def test_add_form_project_addon(self) -> None:
        form = NoOpAddon.get_add_form(None, project=self.component.project, data={})
        self.assertTrue(form.is_valid())
        form.save()
        self.assertEqual(self.component.project.addon_set.count(), 1)

        addon = self.component.project.addon_set.all()[0]
        self.assertEqual(addon.name, "weblate.base.test")

    def test_add_form_site_wide_addon(self) -> None:
        form = NoOpAddon.get_add_form(None, data={})
        self.assertTrue(form.is_valid())
        form.save()
        addon_object = Addon.objects.filter(name="weblate.base.test")
        self.assertEqual(addon_object.count(), 1)

        addon = addon_object[0]
        self.assertEqual("Test add-on: site-wide", str(addon))

    def test_nested_category_addon_in_component_cache(self) -> None:
        """Addon on a parent category should appear in child component's cache."""
        parent = self.create_category(self.project)
        child = Category.objects.create(
            name="Child", slug="child", project=self.project, category=parent
        )
        self.component.category = child
        self.component.save()
        NoOpAddon.create(category=parent, acting_user=self.user)
        self.component.drop_addons_cache()
        self.assertIn("weblate.base.test", self.component.addons_cache.names)


class XgettextExtractPotFormTest(SimpleTestCase):
    def test_rejects_potfiles_symlink_outside_repository(self) -> None:
        repository_dir = tempfile.mkdtemp()
        outside_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, repository_dir, True)
        self.addCleanup(shutil.rmtree, outside_dir, True)
        os.symlink(outside_dir, Path(repository_dir) / "po")

        repository = SimpleNamespace(path=repository_dir)
        repository.resolve_symlinks = lambda path: Repository.resolve_symlinks(
            repository, path
        )
        component = SimpleNamespace(
            full_path=repository_dir,
            check_file_is_valid=lambda filename: Component.check_file_is_valid(
                SimpleNamespace(repository=repository), filename
            ),
        )
        addon = SimpleNamespace(
            instance=SimpleNamespace(component=component, pk=None),
            documentation_build=False,
        )
        form = XgettextExtractPotForm(
            None,
            addon,
            data={
                "interval": "weekly",
                "update_po_files": True,
                "input_mode": "potfiles",
                "language": "Python",
                "source_patterns": "",
                "potfiles_path": "po/POTFILES.in",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors["potfiles_path"],
            ["Invalid symbolic link in a repository."],
        )


class GettextRepositoryPathValidationTest(SimpleTestCase):
    @staticmethod
    def build_fake_component(repository_dir: str, *, new_base: str) -> SimpleNamespace:
        repository = SimpleNamespace(path=repository_dir)
        repository.resolve_symlinks = lambda path: Repository.resolve_symlinks(
            repository, path
        )
        component = SimpleNamespace(
            file_format="po",
            full_path=repository_dir,
            new_base=new_base,
            repository=repository,
            log_error=lambda *_args, **_kwargs: None,
        )
        component.check_file_is_valid = lambda filename: Component.check_file_is_valid(
            component, filename
        )
        component.get_new_base_filename = lambda: component.check_file_is_valid(
            os.path.join(repository_dir, new_base)
        )
        return component

    @staticmethod
    def build_fake_addon(addon_class, component: SimpleNamespace):
        addon = addon_class.__new__(addon_class)
        addon.instance = SimpleNamespace(component=component, pk=None, configuration={})
        addon.documentation_build = False
        addon.alerts = []
        addon.extra_files = []
        return addon

    def test_meson_form_rejects_gettext_symlink_outside_repository(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are not supported")

        repository_dir = tempfile.mkdtemp()
        outside_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, repository_dir, True)
        self.addCleanup(shutil.rmtree, outside_dir, True)
        (Path(repository_dir) / "meson.build").write_text(
            "project('test', 'c')\n", encoding="utf-8"
        )
        (Path(outside_dir) / "meson.build").write_text("", encoding="utf-8")
        (Path(outside_dir) / "POTFILES").write_text("src/main.c\n", encoding="utf-8")
        os.symlink(outside_dir, Path(repository_dir) / "po")

        component = self.build_fake_component(
            repository_dir, new_base="po/messages.pot"
        )
        addon = self.build_fake_addon(MesonAddon, component)
        form = MesonExtractPotForm(
            None,
            addon,
            data={
                "interval": "weekly",
                "normalize_header": False,
                "update_po_files": True,
                "preset": "glib",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.non_field_errors(),
            [
                "The Meson add-on expects a Meson gettext directory with meson.build and POTFILES or POTFILES.in."
            ],
        )

    def test_django_execute_update_rejects_source_symlink_outside_repository(
        self,
    ) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are not supported")

        repository_dir = tempfile.mkdtemp()
        outside_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, repository_dir, True)
        self.addCleanup(shutil.rmtree, outside_dir, True)
        os.symlink(outside_dir, Path(repository_dir) / "src")

        component = self.build_fake_component(
            repository_dir, new_base="src/locale/django.pot"
        )
        addon = self.build_fake_addon(DjangoAddon, component)

        result = addon.execute_update(component, "")

        self.assertFalse(result)
        self.assertEqual(
            addon.alerts[-1]["error"],
            "Repository contains symlink outside repository",
        )

    def test_django_execute_update_skips_repository_locale_tree_validation(
        self,
    ) -> None:
        repository_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, repository_dir, True)
        repository_locale_dir = Path(repository_dir) / "locale" / "cs" / "LC_MESSAGES"
        repository_locale_dir.mkdir(parents=True, exist_ok=True)
        (repository_locale_dir / "django.po").write_text("", encoding="utf-8")

        component = self.build_fake_component(
            repository_dir, new_base="locale/django.pot"
        )
        addon = self.build_fake_addon(DjangoAddon, component)
        original_resolve_symlinks = component.repository.resolve_symlinks

        def resolve_symlinks(path: str) -> str:
            if os.fspath(path).startswith(
                os.fspath(Path(repository_dir) / "locale" / "cs")
            ):
                self.fail("Django validation should skip repository locale trees")
            return original_resolve_symlinks(path)

        component.repository.resolve_symlinks = resolve_symlinks

        def run_process(component, command, env=None, cwd=None):
            locale_dir = Path(env["WEBLATE_EXTRACT_LOCALE_PATH"])
            locale_dir.mkdir(parents=True, exist_ok=True)
            (locale_dir / "django.pot").write_text(
                'msgid ""\nmsgstr ""\n', encoding="utf-8"
            )
            return ""

        with (
            patch.object(DjangoAddon, "get_gettext_format_args", return_value=[]),
            patch.object(DjangoAddon, "run_process", side_effect=run_process) as mocked,
        ):
            result = addon.execute_update(component, "")

        self.assertTrue(result, addon.alerts)
        self.assertEqual(mocked.call_args.kwargs["cwd"], repository_dir)
        self.assertEqual(
            (Path(repository_dir) / "locale" / "django.pot").read_text(
                encoding="utf-8"
            ),
            'msgid ""\nmsgstr ""\n',
        )

    def test_django_execute_update_rejects_symlinked_locale_output_directory(
        self,
    ) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are not supported")

        repository_dir = tempfile.mkdtemp()
        outside_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, repository_dir, True)
        self.addCleanup(shutil.rmtree, outside_dir, True)
        os.symlink(outside_dir, Path(repository_dir) / "locale")

        component = self.build_fake_component(
            repository_dir, new_base="locale/django.pot"
        )
        addon = self.build_fake_addon(DjangoAddon, component)

        with patch.object(DjangoAddon, "run_process", return_value="") as mocked:
            result = addon.execute_update(component, "")

        self.assertFalse(result)
        mocked.assert_not_called()
        self.assertEqual(
            addon.alerts[-1]["error"],
            "Repository contains symlink outside repository",
        )

    def test_django_execute_update_skips_nested_ignored_directories(self) -> None:
        repository_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, repository_dir, True)
        source_dir = Path(repository_dir) / "src"
        (source_dir / "locale").mkdir(parents=True, exist_ok=True)
        (source_dir / "node_modules").mkdir(parents=True, exist_ok=True)

        component = self.build_fake_component(
            repository_dir, new_base="src/locale/django.pot"
        )
        addon = self.build_fake_addon(DjangoAddon, component)
        original_resolve_symlinks = component.repository.resolve_symlinks

        def resolve_symlinks(path: str) -> str:
            if os.fspath(path).startswith(os.fspath(source_dir / "node_modules")):
                self.fail("Django validation should skip ignored source directories")
            return original_resolve_symlinks(path)

        component.repository.resolve_symlinks = resolve_symlinks

        def run_process(component, command, env=None, cwd=None):
            locale_dir = Path(env["WEBLATE_EXTRACT_LOCALE_PATH"])
            locale_dir.mkdir(parents=True, exist_ok=True)
            (locale_dir / "django.pot").write_text(
                'msgid ""\nmsgstr ""\n', encoding="utf-8"
            )
            return ""

        with (
            patch.object(DjangoAddon, "get_gettext_format_args", return_value=[]),
            patch.object(DjangoAddon, "run_process", side_effect=run_process) as mocked,
        ):
            result = addon.execute_update(component, "")

        self.assertTrue(result, addon.alerts)
        self.assertEqual(mocked.call_args.kwargs["cwd"], repository_dir)
        self.assertEqual(
            (source_dir / "locale" / "django.pot").read_text(encoding="utf-8"),
            'msgid ""\nmsgstr ""\n',
        )

    def test_sphinx_form_rejects_source_symlink_outside_repository(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are not supported")

        repository_dir = tempfile.mkdtemp()
        outside_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, repository_dir, True)
        self.addCleanup(shutil.rmtree, outside_dir, True)
        os.symlink(outside_dir, Path(repository_dir) / "docs")

        component = self.build_fake_component(
            repository_dir, new_base="docs/locales/docs.pot"
        )
        addon = self.build_fake_addon(SphinxAddon, component)
        form = SphinxExtractPotForm(
            None,
            addon,
            data={
                "interval": "weekly",
                "normalize_header": False,
                "update_po_files": True,
                "filter_mode": "none",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.non_field_errors(),
            ["Could not determine Sphinx source directory."],
        )


class IntegrationTest(TestAddonMixin, ViewTestCase):
    def create_component(self):
        return self.create_po_new_base(new_lang="add")

    def test_registry(self) -> None:
        GenerateMoAddon.create(component=self.component)
        addon = self.component.addon_set.all()[0]
        self.assertIsInstance(addon.addon, GenerateMoAddon)

    def test_commit(self) -> None:
        GenerateMoAddon.create(component=self.component)
        NoOpAddon.create(component=self.component)
        rev = self.component.repository.last_revision
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.get_translation().commit_pending("test", None)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("po/cs.mo", commit)

    def test_add(self) -> None:
        UpdateLinguasAddon.create(component=self.component)
        UpdateConfigureAddon.create(component=self.component)
        NoOpAddon.create(component=self.component)
        rev = self.component.repository.last_revision
        self.component.add_new_language(Language.objects.get(code="sk"), None)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("po/LINGUAS", commit)
        self.assertIn("configure", commit)

    def test_remove(self) -> None:
        UpdateLinguasAddon.create(component=self.component)
        UpdateConfigureAddon.create(component=self.component)
        NoOpAddon.create(component=self.component)
        translation = self.component.translation_set.get(language_code="cs")
        rev = self.component.repository.last_revision
        translation.remove(self.user)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("po/LINGUAS", commit)
        self.assertIn("configure", commit)

    def test_update(self) -> None:
        rev = self.component.repository.last_revision
        MsgmergeAddon.create(component=self.component)
        NoOpAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        self.component.trigger_post_update(
            previous_head=self.component.repository.last_revision,
            skip_push=False,
            user=None,
        )
        self.assertEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("po/cs.po", commit)

    def test_crash(self) -> None:
        self.assertEqual([], self.component.addons_cache.names)

        addon = CrashAddon.create(component=self.component)
        self.assertEqual(["weblate.base.crash"], self.component.addons_cache.names)
        self.assertTrue(Addon.objects.filter(name=CrashAddon.name).exists())

        with self.assertRaises(CrashAddonError):
            addon.post_update(self.component, "head", False)

        # The crash should be handled here and addon uninstalled
        self.component.trigger_post_update(
            previous_head=self.component.repository.last_revision,
            skip_push=False,
            user=None,
        )

        self.assertEqual([], self.component.addons_cache.names)
        self.assertFalse(Addon.objects.filter(name=CrashAddon.name).exists())

    def test_process_error(self) -> None:
        addon = NoOpAddon.create(component=self.component)
        addon.execute_process(self.component, ["false"])
        self.assertEqual(len(addon.alerts), 1)


class GettextAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_po_new_base(new_lang="add")

    def test_gettext_mo(self) -> None:
        translation = self.get_translation()
        self.assertTrue(GenerateMoAddon.can_install(component=translation.component))
        addon = GenerateMoAddon.create(component=translation.component)
        addon.pre_commit(translation, "", True)
        self.assertTrue(os.path.exists(translation.addon_commit_files[0]))

    def test_update_linguas(self) -> None:
        translation = self.get_translation()
        self.assertTrue(UpdateLinguasAddon.can_install(component=translation.component))
        addon = UpdateLinguasAddon.create(component=translation.component)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("LINGUAS", commit)
        self.assertIn("\n+cs\n", commit)
        addon.post_add(translation)
        self.assertEqual(translation.addon_commit_files, [])

        other = self._create_component(
            "po", "po-duplicates/*.dpo", name="Other", project=self.project
        )
        self.assertTrue(UpdateLinguasAddon.can_install(component=other))
        UpdateLinguasAddon.create(component=other)
        commit = other.repository.show(other.repository.last_revision)
        self.assertIn("LINGUAS", commit)
        self.assertIn("\n+cs de it", commit)

    def test_update_linguas_rejects_symlink(self) -> None:
        translation = self.get_translation()
        addon = UpdateLinguasAddon.create(component=translation.component)

        with tempfile.NamedTemporaryFile(
            delete=False, mode="w", encoding="utf-8"
        ) as handle:
            handle.write("outside repository\n")
        self.addCleanup(os.unlink, handle.name)

        linguas_path = os.path.join(self.component.full_path, "po", "LINGUAS")
        os.unlink(linguas_path)
        os.symlink(handle.name, linguas_path)

        self.assertFalse(
            UpdateLinguasAddon.can_install(component=translation.component)
        )

        addon.post_add(translation)
        self.assertEqual(translation.addon_commit_files, [])
        self.assertEqual(
            Path(handle.name).read_text(encoding="utf-8"), "outside repository\n"
        )

    def test_update_linguas_invalid_new_base_returns_false(self) -> None:
        translation = self.get_translation()
        addon = UpdateLinguasAddon.create(component=self.component)

        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(b"outside repository")
        self.addCleanup(os.unlink, handle.name)

        new_base_path = os.path.join(self.component.full_path, self.component.new_base)
        os.unlink(new_base_path)
        os.symlink(handle.name, new_base_path)

        self.assertFalse(UpdateLinguasAddon.can_install(component=self.component))
        addon.post_add(translation)
        self.assertEqual(translation.addon_commit_files, [])

    def test_update_linguas_post_add_propagates_validation_error(self) -> None:
        translation = self.get_translation()
        addon = UpdateLinguasAddon.create(component=translation.component)

        with (
            patch.object(
                UpdateLinguasAddon,
                "update_linguas",
                side_effect=ValidationError("unexpected validation"),
            ),
            self.assertRaisesMessage(ValidationError, "unexpected validation"),
        ):
            addon.post_add(translation)

    def assert_linguas(self, source, expected_add, expected_remove) -> None:
        # Test no-op
        self.assertEqual(
            UpdateLinguasAddon.update_linguas(source, {"de", "it"}), (False, source)
        )
        # Test adding cs
        self.assertEqual(
            UpdateLinguasAddon.update_linguas(source, {"cs", "de", "it"}),
            (True, expected_add),
        )
        # Test adding cs and removing de
        self.assertEqual(
            UpdateLinguasAddon.update_linguas(source, {"cs", "it"}),
            (True, expected_remove),
        )

    def test_linguas_files_oneline(self) -> None:
        self.assert_linguas(["de it\n"], ["cs de it\n"], ["cs it\n"])

    def test_linguas_files_line(self) -> None:
        self.assert_linguas(
            ["de\n", "it\n"], ["de\n", "it\n", "cs\n"], ["it\n", "cs\n"]
        )

    def test_linguas_files_line_comment(self) -> None:
        self.assert_linguas(
            ["# Linguas list\n", "de\n", "it\n"],
            ["# Linguas list\n", "de\n", "it\n", "cs\n"],
            ["# Linguas list\n", "it\n", "cs\n"],
        )

    def test_linguas_files_inline_comment(self) -> None:
        self.assert_linguas(
            ["de # German\n", "it # Italian\n"],
            ["de # German\n", "it # Italian\n", "cs\n"],
            ["it # Italian\n", "cs\n"],
        )

    def test_update_configure(self) -> None:
        translation = self.get_translation()
        self.assertTrue(
            UpdateConfigureAddon.can_install(component=translation.component)
        )
        addon = UpdateConfigureAddon.create(component=translation.component)
        addon.post_add(translation)
        self.assertEqual(translation.addon_commit_files, [])

    def test_update_configure_rejects_symlink(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(b'ALL_LINGUAS="cs"\n')
        self.addCleanup(os.unlink, handle.name)

        configure_path = os.path.join(self.component.full_path, "configure")
        os.unlink(configure_path)
        os.symlink(handle.name, configure_path)

        self.assertFalse(UpdateConfigureAddon.can_install(component=self.component))

    def test_xgettext_form(self) -> None:
        form = XgettextAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "normalize_header": True,
                "update_po_files": True,
                "input_mode": "patterns",
                "language": "Python",
                "source_patterns": "src/*.py\ntemplates/*.html\n",
                "potfiles_path": "",
            },
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.cleaned_data["source_patterns"],
            ["src/*.py", "templates/*.html"],
        )
        self.assertEqual(form.cleaned_data["comment_mode"], "off")
        self.assertEqual(form.cleaned_data["comment_tag"], "")
        self.assertEqual(form.cleaned_data["checks"], [])
        self.assertEqual(form.cleaned_data["keyword"], "")

    def test_xgettext_form_tagged_comments_require_tag(self) -> None:
        form = XgettextAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "normalize_header": True,
                "update_po_files": True,
                "input_mode": "patterns",
                "language": "Python",
                "source_patterns": "src/*.py\n",
                "potfiles_path": "",
                "comment_mode": "tagged",
                "comment_tag": "",
            },
        )
        self.assertFalse(form.is_valid())

    def test_xgettext_form_roundtrips_parameters(self) -> None:
        form = XgettextAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "normalize_header": True,
                "update_po_files": True,
                "input_mode": "patterns",
                "language": "Python",
                "source_patterns": "src/*.py\n",
                "potfiles_path": "",
                "comment_mode": "tagged",
                "comment_tag": "TRANSLATORS",
                "checks": ["ellipsis-unicode", "bullet-unicode"],
                "keyword": "tr",
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["comment_mode"], "tagged")
        self.assertEqual(form.cleaned_data["comment_tag"], "TRANSLATORS")
        self.assertEqual(
            form.cleaned_data["checks"], ["ellipsis-unicode", "bullet-unicode"]
        )
        self.assertEqual(form.cleaned_data["keyword"], "tr")

    def test_xgettext_form_potfiles(self) -> None:
        form = XgettextAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "normalize_header": True,
                "update_po_files": True,
                "input_mode": "potfiles",
                "language": "Python",
                "source_patterns": "",
                "potfiles_path": "po/POTFILES.in",
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["source_patterns"], [])
        self.assertEqual(form.cleaned_data["potfiles_path"], "po/POTFILES.in")

    def test_xgettext_form_missing_files(self) -> None:
        form = XgettextAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "update_po_files": True,
                "input_mode": "patterns",
                "language": "Python",
                "source_patterns": "",
                "potfiles_path": "",
            },
        )
        self.assertFalse(form.is_valid())

    def test_xgettext_form_missing_potfiles_path(self) -> None:
        form = XgettextAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "update_po_files": True,
                "input_mode": "potfiles",
                "language": "Python",
                "source_patterns": "",
                "potfiles_path": "",
            },
        )
        self.assertFalse(form.is_valid())

    def test_xgettext_form_rejects_potfiles_directory(self) -> None:
        (Path(self.component.full_path) / "po").mkdir(parents=True, exist_ok=True)
        form = XgettextAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "update_po_files": True,
                "input_mode": "potfiles",
                "language": "Python",
                "source_patterns": "",
                "potfiles_path": "po",
            },
        )
        self.assertFalse(form.is_valid())

    def test_extract_pot_settings_form_hides_install_msgmerge(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "normalize_header": False,
                "input_mode": "patterns",
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )

        form = addon.get_settings_form(None)

        self.assertIsNotNone(form)
        self.assertIn("update_po_files", form.fields)
        self.assertTrue(form.fields["update_po_files"].widget.is_hidden)

    def test_extract_pot_settings_form_ignores_posted_install_msgmerge(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "normalize_header": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )

        form = addon.get_settings_form(
            None,
            data={
                "interval": "weekly",
                "normalize_header": False,
                "update_po_files": True,
                "input_mode": "patterns",
                "language": "Python",
                "source_patterns": "src/*.py",
                "potfiles_path": "",
            },
        )

        self.assertIsNotNone(form)
        self.assertTrue(form.is_valid())
        self.assertNotIn("_install_msgmerge", form.serialize_form())

    def test_xgettext_settings_form_roundtrips_source_patterns(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "normalize_header": False,
                "input_mode": "patterns",
                "language": "Python",
                "source_patterns": ["src/*.py", "templates/*.html"],
            },
        )

        form = addon.get_settings_form(None)

        self.assertIsNotNone(form)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.serialize_form()["source_patterns"],
            ["src/*.py", "templates/*.html"],
        )

    def test_xgettext_settings_form_roundtrips_potfiles_path(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "normalize_header": False,
                "input_mode": "potfiles",
                "language": "Python",
                "source_patterns": [],
                "potfiles_path": "po/POTFILES.in",
            },
        )

        form = addon.get_settings_form(None)

        self.assertIsNotNone(form)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.serialize_form()["input_mode"], "potfiles")
        self.assertEqual(form.serialize_form()["potfiles_path"], "po/POTFILES.in")

    def test_xgettext_settings_form_roundtrips_parameters(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "normalize_header": False,
                "input_mode": "patterns",
                "language": "Python",
                "source_patterns": ["src/*.py"],
                "comment_mode": "tagged",
                "comment_tag": "TRANSLATORS",
                "checks": ["ellipsis-unicode", "quote-unicode"],
                "keyword": "tr",
            },
        )

        form = addon.get_settings_form(None)

        self.assertIsNotNone(form)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.serialize_form()["comment_mode"], "tagged")
        self.assertEqual(form.serialize_form()["comment_tag"], "TRANSLATORS")
        self.assertEqual(
            form.serialize_form()["checks"], ["ellipsis-unicode", "quote-unicode"]
        )
        self.assertEqual(form.serialize_form()["keyword"], "tr")

    def test_django_form(self) -> None:
        self.component.new_base = "locale/django.pot"
        form = DjangoAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "normalize_header": True,
                "update_po_files": True,
            },
        )
        self.assertTrue(form.is_valid())

    def test_django_form_invalid_domain(self) -> None:
        self.component.new_base = "locale/website.pot"
        form = DjangoAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "normalize_header": True,
                "update_po_files": True,
            },
        )
        self.assertFalse(form.is_valid())

    def test_django_form_project_scope(self) -> None:
        form = DjangoAddon.get_add_form(
            None,
            project=self.project,
            data={
                "interval": "weekly",
                "normalize_header": True,
                "update_po_files": True,
            },
        )
        self.assertTrue(form.is_valid())

    def test_django_can_install_is_component_specific(self) -> None:
        self.component.new_base = "locale/django.pot"
        self.assertTrue(DjangoAddon.can_install(component=self.component))

        self.component.new_base = "po/hello.pot"
        self.assertFalse(DjangoAddon.can_install(component=self.component))

    def test_sphinx_form_invalid_component(self) -> None:
        form = SphinxAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "normalize_header": False,
                "update_po_files": True,
            },
        )
        self.assertFalse(form.is_valid())

    def test_sphinx_form_valid_component(self) -> None:
        self.component.new_base = "docs/locales/docs.pot"
        (Path(self.component.full_path) / "docs").mkdir(parents=True, exist_ok=True)
        form = SphinxAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "normalize_header": False,
                "update_po_files": True,
            },
        )
        self.assertTrue(form.is_valid())

    def test_sphinx_form_valid_root_component(self) -> None:
        self.component.new_base = "locales/docs.pot"
        form = SphinxAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "normalize_header": False,
                "update_po_files": True,
            },
        )
        self.assertTrue(form.is_valid())

    def test_sphinx_form_project_scope(self) -> None:
        form = SphinxAddon.get_add_form(
            None,
            project=self.project,
            data={
                "interval": "weekly",
                "normalize_header": False,
                "update_po_files": True,
            },
        )
        self.assertTrue(form.is_valid())

    def test_sphinx_can_install_is_component_specific(self) -> None:
        self.component.new_base = "docs/locales/docs.pot"
        docs_dir = Path(self.component.full_path) / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "conf.py").write_text("", encoding="utf-8")
        self.assertTrue(SphinxAddon.can_install(component=self.component))

        self.component.new_base = "weblate/locale/django.pot"
        self.assertFalse(SphinxAddon.can_install(component=self.component))

    def test_meson_form_valid_component(self) -> None:
        self.component.new_base = "po/messages.pot"
        gettext_dir = Path(self.component.full_path) / "po"
        gettext_dir.mkdir(parents=True, exist_ok=True)
        (Path(self.component.full_path) / "meson.build").write_text(
            "project('test', 'c')\n", encoding="utf-8"
        )
        (gettext_dir / "meson.build").write_text("", encoding="utf-8")
        (gettext_dir / "POTFILES.in").write_text("src/main.c\n", encoding="utf-8")
        form = MesonAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "normalize_header": False,
                "update_po_files": True,
                "preset": "glib",
            },
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_meson_form_tagged_comments_require_tag(self) -> None:
        self.component.new_base = "po/messages.pot"
        gettext_dir = Path(self.component.full_path) / "po"
        gettext_dir.mkdir(parents=True, exist_ok=True)
        (Path(self.component.full_path) / "meson.build").write_text(
            "project('test', 'c')\n", encoding="utf-8"
        )
        (gettext_dir / "meson.build").write_text("", encoding="utf-8")
        (gettext_dir / "POTFILES.in").write_text("src/main.c\n", encoding="utf-8")
        form = MesonAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "normalize_header": False,
                "update_po_files": True,
                "preset": "glib",
                "comment_mode": "tagged",
                "comment_tag": "",
            },
        )
        self.assertFalse(form.is_valid())

    def test_meson_can_install_is_component_specific(self) -> None:
        self.component.new_base = "po/messages.pot"
        gettext_dir = Path(self.component.full_path) / "po"
        gettext_dir.mkdir(parents=True, exist_ok=True)
        (Path(self.component.full_path) / "meson.build").write_text(
            "project('test', 'c')\n", encoding="utf-8"
        )
        (gettext_dir / "meson.build").write_text("", encoding="utf-8")
        (gettext_dir / "POTFILES").write_text("src/main.c\n", encoding="utf-8")
        self.assertTrue(MesonAddon.can_install(component=self.component))

        (gettext_dir / "POTFILES").unlink()
        self.assertFalse(MesonAddon.can_install(component=self.component))

    def test_meson_can_install_requires_parent_meson_project(self) -> None:
        self.component.new_base = "po/messages.pot"
        gettext_dir = Path(self.component.full_path) / "po"
        gettext_dir.mkdir(parents=True, exist_ok=True)
        (gettext_dir / "meson.build").write_text("", encoding="utf-8")
        (gettext_dir / "POTFILES").write_text("src/main.c\n", encoding="utf-8")

        self.assertFalse(MesonAddon.can_install(component=self.component))

    def test_meson_can_install_allows_root_gettext_layout(self) -> None:
        self.component.new_base = "messages.pot"
        root = Path(self.component.full_path)
        (root / "meson.build").write_text("project('test', 'c')\n", encoding="utf-8")
        (root / "POTFILES").write_text("src/main.c\n", encoding="utf-8")

        self.assertTrue(MesonAddon.can_install(component=self.component))

    def test_sphinx_can_install_uses_runtime_venv_bin(self) -> None:
        self.component.new_base = "docs/locales/docs.pot"
        docs_dir = Path(self.component.full_path) / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "conf.py").write_text("", encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="weblate-sphinx-venv-") as tempdir:
            venv_bin = Path(tempdir) / "bin"
            venv_bin.mkdir(parents=True, exist_ok=True)
            fake_python = venv_bin / "python"
            fake_python.write_text("", encoding="utf-8")
            fake_python.chmod(0o755)
            sphinx_build = venv_bin / "sphinx-build"
            sphinx_build.write_text("", encoding="utf-8")
            sphinx_build.chmod(0o755)

            with (
                patch(
                    "weblate.utils.commands.find_command",
                    side_effect=lambda command, path=None: shutil.which(
                        command,
                        path=None if path is None else os.pathsep.join(path),
                    ),
                ),
                patch("weblate.utils.commands.sys.executable", os.fspath(fake_python)),
            ):
                self.assertTrue(SphinxAddon.can_install(component=self.component))

    def test_sphinx_can_install_uses_symlinked_runtime_venv_bin(self) -> None:
        self.component.new_base = "docs/locales/docs.pot"
        docs_dir = Path(self.component.full_path) / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "conf.py").write_text("", encoding="utf-8")
        with tempfile.TemporaryDirectory(
            prefix="weblate-sphinx-symlinked-venv-"
        ) as tempdir:
            venv_bin = Path(tempdir) / "bin"
            venv_bin.mkdir(parents=True, exist_ok=True)
            fake_python_target = Path(tempdir) / "python3"
            fake_python_target.write_text("", encoding="utf-8")
            fake_python_target.chmod(0o755)
            fake_python = venv_bin / "python"
            fake_python.symlink_to(fake_python_target)
            sphinx_build = venv_bin / "sphinx-build"
            sphinx_build.write_text("", encoding="utf-8")
            sphinx_build.chmod(0o755)

            with (
                patch(
                    "weblate.utils.commands.find_command",
                    side_effect=lambda command, path=None: shutil.which(
                        command,
                        path=None if path is None else os.pathsep.join(path),
                    ),
                ),
                patch("weblate.utils.commands.sys.executable", os.fspath(fake_python)),
            ):
                self.assertTrue(SphinxAddon.can_install(component=self.component))

    def test_sphinx_can_install_ignores_relative_runtime_executable(self) -> None:
        self.component.new_base = "docs/locales/docs.pot"
        docs_dir = Path(self.component.full_path) / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "conf.py").write_text("", encoding="utf-8")

        with (
            patch("weblate.utils.commands.find_command", return_value=None),
            patch("weblate.utils.commands.sys.executable", "python"),
        ):
            self.assertFalse(SphinxAddon.can_install(component=self.component))

    def test_sphinx_form_missing_source_dir(self) -> None:
        self.component.new_base = "docs/locales/docs.pot"
        form = SphinxAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "normalize_header": False,
                "update_po_files": True,
            },
        )
        self.assertFalse(form.is_valid())

    def test_extract_pot_requires_component_new_base(self) -> None:
        self.component.new_base = ""
        self.component.save(update_fields=["new_base"])

        self.assertFalse(XgettextAddon.can_install(component=self.component))
        self.assertFalse(MesonAddon.can_install(component=self.component))
        self.assertFalse(DjangoAddon.can_install(component=self.component))
        self.assertFalse(SphinxAddon.can_install(component=self.component))

    def test_xgettext(self) -> None:
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )

        with (
            patch.object(XgettextAddon, "run_process", return_value="") as mocked,
            patch.object(XgettextAddon, "validate_repository_tree", return_value=True),
        ):
            addon.update_translations(self.component, "")

        mocked.assert_called_once()
        command = mocked.call_args.args[1]
        self.assertEqual(
            command[:5],
            ["xgettext", "--output", "po/hello.pot", "--language", "Python"],
        )
        self.assertIn("--from-code=UTF-8", command)
        self.assertIn("src/messages.py", command)
        self.assertIn("--", command)
        self.assertIn(
            os.path.join(self.component.full_path, "po/hello.pot"),
            addon.extra_files,
        )

    def test_xgettext_uses_potfiles_manifest(self) -> None:
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        manifest = Path(self.component.full_path) / "po" / "POTFILES.in"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("src/messages.py\n", encoding="utf-8")
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "input_mode": "potfiles",
                "potfiles_path": "po/POTFILES.in",
                "language": "Python",
                "source_patterns": [],
            },
        )

        with patch.object(XgettextAddon, "run_process", return_value="") as mocked:
            addon.update_translations(self.component, "")

        command = mocked.call_args.args[1]
        self.assertIn("src/messages.py", command)
        self.assertIn("--", command)

    def test_xgettext_potfiles_skip_excludes_entries(self) -> None:
        source = Path(self.component.full_path) / "src"
        source.mkdir(parents=True, exist_ok=True)
        (source / "messages.py").write_text("", encoding="utf-8")
        (source / "skip.py").write_text("", encoding="utf-8")
        manifest = Path(self.component.full_path) / "po" / "POTFILES.in"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("src/messages.py\nsrc/skip.py\n", encoding="utf-8")
        (manifest.parent / "POTFILES.skip").write_text(
            "src/skip.py\n", encoding="utf-8"
        )
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "input_mode": "potfiles",
                "potfiles_path": "po/POTFILES.in",
                "language": "Python",
                "source_patterns": [],
            },
        )

        self.assertEqual(
            addon.resolve_potfiles_entries(self.component), ["src/messages.py"]
        )

    def test_xgettext_rejects_potfiles_directory_at_runtime(self) -> None:
        manifest = Path(self.component.full_path) / "po"
        manifest.mkdir(parents=True, exist_ok=True)
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "input_mode": "potfiles",
                "potfiles_path": "po",
                "language": "Python",
                "source_patterns": [],
            },
        )

        with patch.object(XgettextAddon, "run_process", return_value="") as mocked:
            result = addon.execute_update(self.component, "")

        self.assertFalse(result)
        mocked.assert_not_called()
        self.assertEqual(
            addon.alerts[-1]["error"],
            "POTFILES path has to point to a file",
        )

    def test_xgettext_invalid_potfiles_surfaces_alert_without_relevant_diff(
        self,
    ) -> None:
        manifest = Path(self.component.full_path) / "po"
        manifest.mkdir(parents=True, exist_ok=True)
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "input_mode": "potfiles",
                "potfiles_path": "po",
                "language": "Python",
                "source_patterns": [],
            },
        )
        addon.get_component_state(self.component)["last_revision"] = "stored-revision"
        addon.get_component_state(self.component)["configuration_signature"] = (
            addon.get_configuration_signature()
        )

        with patch.object(
            self.component.repository,
            "list_changed_files",
            return_value=["README.md"],
        ):
            addon.update_translations(self.component, "old-revision")

        self.assertTrue(self.component.alert_set.filter(name=addon.alert).exists())

    def test_xgettext_uses_delimiter_before_filenames(self) -> None:
        source = Path(self.component.full_path) / "src" / "--help.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )

        with patch.object(XgettextAddon, "run_process", return_value="") as mocked:
            addon.update_translations(self.component, "")

        command = mocked.call_args.args[1]
        self.assertIn("--", command)
        self.assertLess(command.index("--"), command.index("src/--help.py"))

    def test_xgettext_runs_on_install(self) -> None:
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )

        with (
            patch.object(XgettextAddon, "run_process", return_value="") as mocked,
        ):
            XgettextAddon.create(
                component=self.component,
                configuration={
                    "interval": "weekly",
                    "update_po_files": False,
                    "language": "Python",
                    "source_patterns": ["src/*.py"],
                },
            )

        mocked.assert_called_once()

    def test_xgettext_form_save_runs_on_install(self) -> None:
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        form = XgettextAddon.get_add_form(
            None,
            component=self.component,
            data={
                "interval": "weekly",
                "normalize_header": "",
                "update_po_files": "",
                "language": "Python",
                "source_patterns": "src/*.py",
            },
        )

        self.assertIsNotNone(form)
        self.assertTrue(form.is_valid(), form.errors)

        with patch.object(XgettextAddon, "run_process", return_value="") as mocked:
            form.save()

        mocked.assert_called_once()

    def test_xgettext_uses_file_format_gettext_flags(self) -> None:
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        params = get_default_params_for_file_format(self.component.file_format)
        params.update({"po_no_location": True, "po_line_wrap": -1})
        self.component.file_format_params = params
        self.component.save(update_fields=["file_format_params"])
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )

        with (
            patch.object(XgettextAddon, "run_process", return_value="") as mocked,
            patch.object(XgettextAddon, "validate_repository_tree", return_value=True),
        ):
            addon.update_translations(self.component, "")

        command = mocked.call_args.args[1]
        self.assertIn("--no-location", command)
        self.assertIn("--no-wrap", command)

    def test_xgettext_uses_parametrized_arguments(self) -> None:
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
                "comment_mode": "tagged",
                "comment_tag": "TRANSLATORS",
                "checks": ["ellipsis-unicode", "bullet-unicode"],
                "keyword": "tr",
            },
        )

        with (
            patch.object(XgettextAddon, "run_process", return_value="") as mocked,
            patch.object(XgettextAddon, "validate_repository_tree", return_value=True),
        ):
            addon.update_translations(self.component, "")

        command = mocked.call_args.args[1]
        self.assertIn("--from-code=UTF-8", command)
        self.assertIn("--add-comments=TRANSLATORS", command)
        self.assertIn("--check=ellipsis-unicode", command)
        self.assertIn("--check=bullet-unicode", command)
        self.assertIn("--keyword=tr", command)

    def test_meson_uses_glib_preset_and_potfiles(self) -> None:
        source = Path(self.component.full_path) / "src" / "main.c"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('_("Hello");\n', encoding="utf-8")
        gettext_dir = Path(self.component.full_path) / "po"
        gettext_dir.mkdir(parents=True, exist_ok=True)
        self.component.new_base = "po/messages.pot"
        self.component.save(update_fields=["new_base"])
        (Path(self.component.full_path) / "meson.build").write_text(
            "project('test', 'c')\n", encoding="utf-8"
        )
        (gettext_dir / "meson.build").write_text("", encoding="utf-8")
        (gettext_dir / "POTFILES.in").write_text("src/main.c\n", encoding="utf-8")
        addon = MesonAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "preset": "glib",
            },
        )

        with patch.object(MesonAddon, "run_process", return_value="") as mocked:
            addon.update_translations(self.component, "")

        command = mocked.call_args.args[1]
        self.assertEqual(command[:3], ["xgettext", "--output", "po/messages.pot"])
        self.assertNotIn("--language", command)
        self.assertIn("--keyword=g_dcgettext:2", command)
        self.assertIn("--keyword=g_dpgettext2:2c,3", command)
        self.assertIn("--flag=g_snprintf:3:c-format", command)
        self.assertIn("src/main.c", command)
        self.assertEqual(addon.get_effective_input_mode(self.component), "potfiles")
        self.assertEqual(
            addon.get_effective_potfiles_path(self.component), "po/POTFILES.in"
        )

    def test_meson_uses_shared_xgettext_parameters(self) -> None:
        source = Path(self.component.full_path) / "src" / "main.c"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('_("Hello");\n', encoding="utf-8")
        gettext_dir = Path(self.component.full_path) / "po"
        gettext_dir.mkdir(parents=True, exist_ok=True)
        self.component.new_base = "po/messages.pot"
        self.component.save(update_fields=["new_base"])
        (Path(self.component.full_path) / "meson.build").write_text(
            "project('test', 'c')\n", encoding="utf-8"
        )
        (gettext_dir / "meson.build").write_text("", encoding="utf-8")
        (gettext_dir / "POTFILES.in").write_text("src/main.c\n", encoding="utf-8")
        addon = MesonAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "preset": "glib",
                "comment_mode": "tagged",
                "comment_tag": "TRANSLATORS",
                "checks": ["ellipsis-unicode"],
                "keyword": "custom_tr",
            },
        )

        with patch.object(MesonAddon, "run_process", return_value="") as mocked:
            addon.update_translations(self.component, "")

        command = mocked.call_args.args[1]
        self.assertIn("--from-code=UTF-8", command)
        self.assertIn("--add-comments", command)
        self.assertIn("--add-comments=TRANSLATORS", command)
        self.assertIn("--check=ellipsis-unicode", command)
        self.assertIn("--keyword=custom_tr", command)

    def test_meson_prefers_potfiles_over_potfiles_in(self) -> None:
        gettext_dir = Path(self.component.full_path) / "po"
        gettext_dir.mkdir(parents=True, exist_ok=True)
        self.component.new_base = "po/messages.pot"
        self.component.save(update_fields=["new_base"])
        (Path(self.component.full_path) / "meson.build").write_text(
            "project('test', 'c')\n", encoding="utf-8"
        )
        (gettext_dir / "meson.build").write_text("", encoding="utf-8")
        (gettext_dir / "POTFILES").write_text("src/main.c\n", encoding="utf-8")
        (gettext_dir / "POTFILES.in").write_text("src/other.c\n", encoding="utf-8")
        addon = MesonAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "preset": "glib",
            },
        )

        self.assertEqual(
            addon.get_effective_potfiles_path(self.component), "po/POTFILES"
        )

    def test_meson_change_detection_tracks_manifest_transition(self) -> None:
        gettext_dir = Path(self.component.full_path) / "po"
        gettext_dir.mkdir(parents=True, exist_ok=True)
        source = Path(self.component.full_path) / "src" / "main.c"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("", encoding="utf-8")
        self.component.new_base = "po/messages.pot"
        self.component.save(update_fields=["new_base"])
        (Path(self.component.full_path) / "meson.build").write_text(
            "project('test', 'c')\n", encoding="utf-8"
        )
        (gettext_dir / "meson.build").write_text("", encoding="utf-8")
        (gettext_dir / "POTFILES.in").write_text("src/main.c\n", encoding="utf-8")
        addon = MesonAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "preset": "glib",
            },
        )
        addon.get_component_state(self.component)["last_revision"] = "stored-revision"
        addon.get_component_state(self.component)["configuration_signature"] = (
            addon.get_configuration_signature()
        )

        with patch.object(
            self.component.repository,
            "list_changed_files",
            return_value=["po/POTFILES"],
        ):
            self.assertTrue(addon.has_relevant_changes(self.component, "previous-head"))

    def test_meson_potfiles_skip_excludes_entries(self) -> None:
        gettext_dir = Path(self.component.full_path) / "po"
        gettext_dir.mkdir(parents=True, exist_ok=True)
        source = Path(self.component.full_path) / "src"
        source.mkdir(parents=True, exist_ok=True)
        (source / "main.c").write_text("", encoding="utf-8")
        (source / "skip.c").write_text("", encoding="utf-8")
        self.component.new_base = "po/messages.pot"
        self.component.save(update_fields=["new_base"])
        (Path(self.component.full_path) / "meson.build").write_text(
            "project('test', 'c')\n", encoding="utf-8"
        )
        (gettext_dir / "meson.build").write_text("", encoding="utf-8")
        (gettext_dir / "POTFILES.in").write_text(
            "src/main.c\nsrc/skip.c\n", encoding="utf-8"
        )
        (gettext_dir / "POTFILES.skip").write_text("src/skip.c\n", encoding="utf-8")
        addon = MesonAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "preset": "glib",
            },
        )

        self.assertEqual(addon.resolve_potfiles_entries(self.component), ["src/main.c"])

    def test_xgettext_skip_without_relevant_change(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )

        with (
            patch.object(
                self.component.repository,
                "list_changed_files",
                return_value=["README.md"],
            ),
            patch.object(XgettextAddon, "run_process", return_value="") as mocked,
        ):
            addon.update_translations(self.component, "old-revision")

        mocked.assert_not_called()

    def test_xgettext_potfiles_change_detection_tracks_manifest(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "input_mode": "potfiles",
                "potfiles_path": "po/POTFILES.in",
                "language": "Python",
                "source_patterns": [],
            },
        )
        manifest = Path(self.component.full_path) / "po" / "POTFILES.in"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("src/messages.py\n", encoding="utf-8")
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("", encoding="utf-8")
        addon.get_component_state(self.component)["last_revision"] = "stored-revision"
        addon.get_component_state(self.component)["configuration_signature"] = (
            addon.get_configuration_signature()
        )

        with patch.object(
            self.component.repository,
            "list_changed_files",
            return_value=["po/POTFILES.in"],
        ):
            self.assertTrue(addon.has_relevant_changes(self.component, "previous-head"))

    def test_xgettext_potfiles_change_detection_tracks_manifest_entries(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "input_mode": "potfiles",
                "potfiles_path": "po/POTFILES.in",
                "language": "Python",
                "source_patterns": [],
            },
        )
        manifest = Path(self.component.full_path) / "po" / "POTFILES.in"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("src/messages.py\n", encoding="utf-8")
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("", encoding="utf-8")
        addon.get_component_state(self.component)["last_revision"] = "stored-revision"
        addon.get_component_state(self.component)["configuration_signature"] = (
            addon.get_configuration_signature()
        )

        with patch.object(
            self.component.repository,
            "list_changed_files",
            return_value=["src/messages.py"],
        ):
            self.assertTrue(addon.has_relevant_changes(self.component, "previous-head"))

    def test_xgettext_potfiles_change_detection_tracks_skip_manifest(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "input_mode": "potfiles",
                "potfiles_path": "po/POTFILES.in",
                "language": "Python",
                "source_patterns": [],
            },
        )
        manifest = Path(self.component.full_path) / "po" / "POTFILES.in"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("src/messages.py\n", encoding="utf-8")
        (manifest.parent / "POTFILES.skip").write_text("", encoding="utf-8")
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("", encoding="utf-8")
        addon.get_component_state(self.component)["last_revision"] = "stored-revision"
        addon.get_component_state(self.component)["configuration_signature"] = (
            addon.get_configuration_signature()
        )

        with patch.object(
            self.component.repository,
            "list_changed_files",
            return_value=["po/POTFILES.skip"],
        ):
            self.assertTrue(addon.has_relevant_changes(self.component, "previous-head"))

    def test_xgettext_ignores_symlinked_source_directory(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are not supported")

        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/**/*.py"],
            },
        )

        with tempfile.TemporaryDirectory(prefix="weblate-xgettext-outside-") as tempdir:
            outside_dir = Path(tempdir)
            (outside_dir / "messages.py").write_text(
                'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
            )
            (Path(self.component.full_path) / "src").symlink_to(
                outside_dir, target_is_directory=True
            )

            with patch.object(XgettextAddon, "run_process", return_value="") as mocked:
                result = addon.execute_update(self.component, "")

        self.assertFalse(result)
        mocked.assert_not_called()
        self.assertEqual(
            addon.alerts[-1]["error"],
            "No source files matched configured patterns",
        )

    def test_extract_pot_weekly_schedule(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        addon.get_component_state(self.component)["last_run"] = (
            timezone.now().date().isoformat()
        )

        self.assertFalse(addon.is_schedule_due(self.component))

    def test_extract_pot_monthly_schedule(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "monthly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        addon.get_component_state(self.component)["last_run"] = (
            timezone.now().date() - timedelta(days=29)
        ).isoformat()

        self.assertFalse(addon.is_schedule_due(self.component))

        addon.get_component_state(self.component)["last_run"] = (
            timezone.now().date() - timedelta(days=30)
        ).isoformat()

        self.assertTrue(addon.is_schedule_due(self.component))

    def test_extract_pot_post_configure_bypasses_schedule(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        addon.get_component_state(self.component)["last_run"] = (
            timezone.now().date().isoformat()
        )
        addon.get_component_state(self.component)["configuration_signature"] = (
            addon.get_configuration_signature()
        )
        addon.save_state()

        with patch.object(
            XgettextAddon, "execute_update", return_value=False
        ) as mocked:
            addon.post_configure_run_component(self.component)

        mocked.assert_called_once_with(self.component, "")

    def test_extract_pot_manual_bypasses_schedule(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        addon.get_component_state(self.component)["last_run"] = (
            timezone.now().date().isoformat()
        )
        addon.get_component_state(self.component)["configuration_signature"] = (
            addon.get_configuration_signature()
        )
        addon.save_state()

        with patch.object(
            XgettextAddon, "execute_update", return_value=False
        ) as mocked:
            addon.manual_component(self.component)

        mocked.assert_called_once_with(self.component, "")
        self.assertNotIn("_force_run", addon.get_component_state(self.component))

    def test_extract_pot_manual_commits_pending_changes(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": True,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )

        with (
            patch.object(
                self.component, "commit_pending", return_value=False
            ) as mocked_commit,
            patch.object(XgettextAddon, "execute_update", return_value=False),
        ):
            addon.manual_component(self.component)

        mocked_commit.assert_called_once_with("add-on", None)

    def test_xgettext_uses_last_successful_revision_for_change_detection(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        addon.get_component_state(self.component)["last_revision"] = "stored-revision"
        addon.get_component_state(self.component)["configuration_signature"] = (
            addon.get_configuration_signature()
        )

        with patch.object(
            self.component.repository,
            "list_changed_files",
            return_value=["src/messages.py"],
        ) as mocked:
            self.assertTrue(addon.has_relevant_changes(self.component, "previous-head"))

        mocked.assert_called_once_with(
            self.component.repository.ref_to_remote.format("stored-revision")
        )

    def test_xgettext_falls_back_to_full_run_on_missing_last_revision(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "input_mode": "patterns",
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        addon.get_component_state(self.component)["last_revision"] = "stored-revision"
        addon.get_component_state(self.component)["configuration_signature"] = (
            addon.get_configuration_signature()
        )

        with patch.object(
            self.component.repository,
            "list_changed_files",
            side_effect=RepositoryError(1, "bad revision"),
        ) as mocked:
            self.assertTrue(addon.has_relevant_changes(self.component, "previous-head"))

        mocked.assert_called_once_with(
            self.component.repository.ref_to_remote.format("stored-revision")
        )

    def test_xgettext_change_detection_uses_same_glob_semantics(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/**/*.py"],
            },
        )
        addon.get_component_state(self.component)["last_revision"] = "stored-revision"
        addon.get_component_state(self.component)["configuration_signature"] = (
            addon.get_configuration_signature()
        )

        with patch.object(
            self.component.repository,
            "list_changed_files",
            return_value=["src/nested/messages.py"],
        ):
            self.assertTrue(addon.has_relevant_changes(self.component, "previous-head"))

    def test_xgettext_change_detection_is_evaluated_once_per_refresh(self) -> None:
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        addon.get_component_state(self.component)["last_revision"] = "stored-revision"
        addon.get_component_state(self.component)["configuration_signature"] = (
            addon.get_configuration_signature()
        )

        with (
            patch.object(
                self.component.repository,
                "list_changed_files",
                return_value=["src/messages.py"],
            ) as mocked,
            patch.object(XgettextAddon, "run_process", return_value=""),
        ):
            addon.update_translations(self.component, "previous-head")

        mocked.assert_called_once_with(
            self.component.repository.ref_to_remote.format("stored-revision")
        )

    def test_xgettext_updates_last_revision_after_commit(self) -> None:
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )

        revision_before = self.component.repository.last_revision

        def run_process(component, command, env=None, cwd=None, extra_path=None):
            template = Path(component.full_path) / "po" / "hello.pot"
            template.parent.mkdir(parents=True, exist_ok=True)
            template.write_text('msgid ""\nmsgstr ""\n', encoding="utf-8")
            return ""

        with patch.object(XgettextAddon, "run_process", side_effect=run_process):
            addon.post_update(self.component, revision_before, True)

        revision_after = self.component.repository.last_revision
        self.assertNotEqual(revision_before, revision_after)
        self.assertEqual(
            addon.get_component_state(self.component)["last_revision"], revision_after
        )

    def test_xgettext_does_not_mark_success_before_failed_commit(self) -> None:
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        revision_before = self.component.repository.last_revision

        def run_process(component, command, env=None, cwd=None, extra_path=None):
            template = Path(component.full_path) / "po" / "hello.pot"
            template.parent.mkdir(parents=True, exist_ok=True)
            template.write_text('msgid ""\nmsgstr ""\n', encoding="utf-8")
            return ""

        with (
            patch.object(XgettextAddon, "run_process", side_effect=run_process),
            patch.object(
                self.component, "commit_files", side_effect=RuntimeError("push failed")
            ),
            self.assertRaisesRegex(RuntimeError, "push failed"),
        ):
            addon.post_update(self.component, revision_before, True)

        self.assertNotIn(
            "last_revision",
            addon.get_component_state(self.component),
        )

    def test_xgettext_configuration_change_is_relevant(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        addon.get_component_state(self.component)["last_revision"] = "stored-revision"
        addon.get_component_state(self.component)["configuration_signature"] = (
            addon.get_configuration_signature()
        )
        addon.instance.configuration["language"] = "C"

        with patch.object(
            self.component.repository,
            "list_changed_files",
            return_value=["README.md"],
        ) as mocked:
            self.assertTrue(addon.has_relevant_changes(self.component, "previous-head"))

        mocked.assert_not_called()

    def test_extract_pot_state_is_per_component_for_project_addon(self) -> None:
        project_component = self.create_po_new_base(
            project=self.component.project,
            name="Project scoped",
            slug="project-scoped",
        )
        addon = XgettextAddon.create(
            project=self.component.project,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        addon.get_component_state(self.component)["last_run"] = (
            timezone.now().date().isoformat()
        )

        self.assertFalse(addon.is_schedule_due(self.component))
        self.assertTrue(addon.is_schedule_due(project_component))

    def test_extract_pot_component_state_updates_merge_for_project_addon(self) -> None:
        project_component = self.create_po_new_base(
            project=self.component.project,
            name="Project scoped",
            slug="project-scoped-merge",
        )
        addon = XgettextAddon.create(
            project=self.component.project,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        addon_other = XgettextAddon(Addon.objects.get(pk=addon.instance.pk))

        addon.mark_successful_run(self.component, "revision-one")
        addon_other.mark_successful_run(project_component, "revision-two")

        addon.instance.refresh_from_db()
        self.assertEqual(
            addon.get_component_state(self.component)["last_revision"],
            "revision-one",
        )
        self.assertEqual(
            addon.get_component_state(project_component)["last_revision"],
            "revision-two",
        )

    def test_extract_pot_commit_not_blocked_by_alerts(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        addon.alerts.append(
            {
                "addon": addon.name,
                "command": "xgettext",
                "output": "po/hello.pot",
                "error": "partial failure",
            }
        )

        with (
            patch.object(self.component.repository, "needs_commit", return_value=True),
            patch.object(self.component, "commit_files") as mocked_commit,
        ):
            committed = addon.commit_and_push(
                self.component, files=["po/hello.pot"], skip_push=True
            )

        self.assertTrue(committed)
        mocked_commit.assert_called_once()

    def test_extract_pot_normalize_header(self) -> None:
        addon = DjangoAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": True},
        )
        self.component.project.name = 'Test "Project"'
        self.component.name = r"Test\Component"
        self.component.report_source_bugs = "bugs@example.com"
        template = Path(self.component.full_path) / "po" / "hello.pot"
        template.write_text(
            """# FIRST AUTHOR <EMAIL@ADDRESS>, YEAR.\n# Copyright (C) YEAR THE PACKAGE'S COPYRIGHT HOLDER\n# This file is distributed under the same license as the PACKAGE package.\nmsgid ""\nmsgstr ""\n"Project-Id-Version: PACKAGE VERSION\\n"\n"Report-Msgid-Bugs-To: EMAIL@ADDRESS\\n"\n"SOME DESCRIPTIVE TITLE.\\n"\n""",
            encoding="utf-8",
        )

        addon.normalize_header(self.component, os.fspath(template))
        content = template.read_text(encoding="utf-8")
        self.assertIn(
            '"Project-Id-Version: Test \\"Project\\" / Test\\\\Component\\n"', content
        )
        self.assertIn('"Report-Msgid-Bugs-To: bugs@example.com\\n"', content)
        self.assertIn(
            '"Translations for Test \\"Project\\" / Test\\\\Component.\\n"',
            content,
        )
        self.assertIn(
            '# Generated translation template for Test "Project" / Test\\Component.',
            content,
        )
        self.assertIn("# Generated by Weblate.", content)
        self.assertNotIn("FIRST AUTHOR", content)
        self.assertNotIn("YEAR THE PACKAGE'S COPYRIGHT HOLDER", content)

    def test_extract_pot_normalize_header_uses_component_url_for_bugs(self) -> None:
        addon = DjangoAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": True},
        )
        self.component.report_source_bugs = ""
        template = Path(self.component.full_path) / "po" / "hello.pot"
        template.write_text(
            """# FIRST AUTHOR <EMAIL@ADDRESS>, YEAR.\n# Copyright (C) YEAR THE PACKAGE'S COPYRIGHT HOLDER\n# This file is distributed under the same license as the PACKAGE package.\nmsgid ""\nmsgstr ""\n"Project-Id-Version: PACKAGE VERSION\\n"\n"Report-Msgid-Bugs-To: EMAIL@ADDRESS\\n"\n""",
            encoding="utf-8",
        )

        addon.normalize_header(self.component, os.fspath(template))
        content = template.read_text(encoding="utf-8")

        self.assertIn(
            f'"Report-Msgid-Bugs-To: {get_site_url(self.component.get_absolute_url())}\\n"',
            content,
        )
        self.assertIn(
            f"# Generated translation template for {self.component.project.name} / {self.component.name}.",
            content,
        )
        self.assertIn("# Generated by Weblate.", content)
        self.assertNotIn("FIRST AUTHOR", content)
        self.assertNotIn("YEAR THE PACKAGE'S COPYRIGHT HOLDER", content)
        self.assertNotIn("This file is distributed under the same license", content)

    def test_extract_pot_normalize_header_is_idempotent(self) -> None:
        addon = DjangoAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": True},
        )
        template = Path(self.component.full_path) / "po" / "hello.pot"
        template.write_text(
            """# FIRST AUTHOR <EMAIL@ADDRESS>, YEAR.\n# Copyright (C) YEAR THE PACKAGE'S COPYRIGHT HOLDER\n# This file is distributed under the same license as the PACKAGE package.\nmsgid ""\nmsgstr ""\n"Project-Id-Version: PACKAGE VERSION\\n"\n"Report-Msgid-Bugs-To: EMAIL@ADDRESS\\n"\n"SOME DESCRIPTIVE TITLE.\\n"\n""",
            encoding="utf-8",
        )

        addon.normalize_header(self.component, os.fspath(template))
        addon.normalize_header(self.component, os.fspath(template))
        content = template.read_text(encoding="utf-8")
        generated_comment = f"# Generated translation template for {self.component.project.name} / {self.component.name}."

        self.assertEqual(content.count(generated_comment), 1)
        self.assertEqual(content.count("# Generated by Weblate."), 1)
        self.assertNotIn("FIRST AUTHOR", content)
        self.assertNotIn("YEAR THE PACKAGE'S COPYRIGHT HOLDER", content)
        self.assertNotIn("This file is distributed under the same license", content)

    def test_extract_pot_normalize_header_removes_blank_copyright(self) -> None:
        addon = DjangoAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": True},
        )
        template = Path(self.component.full_path) / "po" / "hello.pot"
        template.write_text(
            """# SOME DESCRIPTIVE TITLE.
# Copyright (C)
#
msgid ""
msgstr ""
"Project-Id-Version: PACKAGE VERSION\\n"
"Report-Msgid-Bugs-To: EMAIL@ADDRESS\\n"
""",
            encoding="utf-8",
        )

        addon.normalize_header(self.component, os.fspath(template))
        content = template.read_text(encoding="utf-8")
        generated_comment = f"# Generated translation template for {self.component.project.name} / {self.component.name}."

        self.assertEqual(content.count(generated_comment), 1)
        self.assertEqual(content.count("# Generated by Weblate."), 1)
        self.assertNotIn("# SOME DESCRIPTIVE TITLE.\n", content)
        self.assertNotIn("# Copyright (C)\n", content)
        self.assertNotIn("# Copyright (C) \n", content)

    def test_django_command(self) -> None:
        self.component.new_base = "locale/django.pot"
        addon = DjangoAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": False},
        )

        def run_process(component, command, env=None, cwd=None):
            locale_dir = Path(env["WEBLATE_EXTRACT_LOCALE_PATH"])
            locale_dir.mkdir(parents=True, exist_ok=True)
            (locale_dir / "django.pot").write_text(
                'msgid ""\nmsgstr ""\n', encoding="utf-8"
            )
            return ""

        with (
            patch.object(
                DjangoAddon, "validate_django_repository_tree", return_value=True
            ),
            patch.object(DjangoAddon, "run_process", side_effect=run_process) as mocked,
        ):
            addon.execute_update(self.component, "")

        command = mocked.call_args.args[1]
        self.assertEqual(
            command[:2], [sys.executable, os.fspath(DJANGO_EXTRACT_RUNNER)]
        )
        self.assertIn("django", command)
        self.assertIn("--source-prefix", command)
        self.assertIn(".", command)
        self.assertNotIn("--keep-pot", command)
        self.assertNotIn("-a", command)
        self.assertIn("WEBLATE_EXTRACT_LOCALE_PATH", mocked.call_args.kwargs["env"])
        self.assertEqual(mocked.call_args.kwargs["cwd"], self.component.full_path)

    def test_django_scopes_to_pot_parent_tree(self) -> None:
        self.component.new_base = "weblate/locale/django.pot"
        source_dir = Path(self.component.full_path) / "weblate"
        source_dir.mkdir(parents=True, exist_ok=True)
        addon = DjangoAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": False},
        )

        def run_process(component, command, env=None, cwd=None):
            locale_dir = Path(env["WEBLATE_EXTRACT_LOCALE_PATH"])
            locale_dir.mkdir(parents=True, exist_ok=True)
            (locale_dir / "django.pot").write_text(
                'msgid ""\nmsgstr ""\n', encoding="utf-8"
            )
            return ""

        with (
            patch.object(
                DjangoAddon, "validate_django_repository_tree", return_value=True
            ),
            patch.object(DjangoAddon, "run_process", side_effect=run_process) as mocked,
        ):
            addon.execute_update(self.component, "")

        command = mocked.call_args.args[1]
        self.assertEqual(mocked.call_args.kwargs["cwd"], self.component.full_path)
        self.assertIn("--source-prefix", command)
        self.assertIn("weblate", command)

    def test_django_conf_locale_scopes_to_repo_root(self) -> None:
        self.component.new_base = "conf/locale/django.pot"
        conf_dir = Path(self.component.full_path) / "conf"
        conf_dir.mkdir(parents=True, exist_ok=True)
        addon = DjangoAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": False},
        )

        def run_process(component, command, env=None, cwd=None):
            locale_dir = Path(env["WEBLATE_EXTRACT_LOCALE_PATH"])
            locale_dir.mkdir(parents=True, exist_ok=True)
            (locale_dir / "django.pot").write_text(
                'msgid ""\nmsgstr ""\n', encoding="utf-8"
            )
            return ""

        with (
            patch.object(
                DjangoAddon, "validate_django_repository_tree", return_value=True
            ),
            patch.object(DjangoAddon, "run_process", side_effect=run_process) as mocked,
        ):
            addon.execute_update(self.component, "")

        command = mocked.call_args.args[1]
        self.assertEqual(mocked.call_args.kwargs["cwd"], self.component.full_path)
        self.assertIn("--source-prefix", command)
        self.assertIn(".", command)

    def test_django_uses_file_format_gettext_flags(self) -> None:
        self.component.new_base = "locale/django.pot"
        params = get_default_params_for_file_format(self.component.file_format)
        params.update({"po_no_location": True, "po_line_wrap": -1})
        self.component.file_format_params = params
        self.component.save(update_fields=["file_format_params"])
        addon = DjangoAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": False},
        )

        def run_process(component, command, env=None, cwd=None):
            locale_dir = Path(env["WEBLATE_EXTRACT_LOCALE_PATH"])
            locale_dir.mkdir(parents=True, exist_ok=True)
            (locale_dir / "django.pot").write_text(
                'msgid ""\nmsgstr ""\n', encoding="utf-8"
            )
            return ""

        with (
            patch.object(
                DjangoAddon, "validate_django_repository_tree", return_value=True
            ),
            patch.object(DjangoAddon, "run_process", side_effect=run_process) as mocked,
        ):
            addon.execute_update(self.component, "")

        command = mocked.call_args.args[1]
        self.assertIn("--no-location", command)
        self.assertIn("--no-wrap", command)

    def test_sphinx_scopes_to_repo_root_locales(self) -> None:
        self.component.new_base = "locales/docs.pot"
        addon = SphinxAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": False},
        )

        with (
            patch.object(SphinxAddon, "run_process", return_value="") as mocked,
            tempfile.TemporaryDirectory(prefix="weblate-sphinx-test-") as tempdir,
            patch("weblate.addons.gettext.tempfile.TemporaryDirectory") as mocked_tmp,
            patch.object(SphinxAddon, "validate_repository_tree", return_value=True),
        ):
            build_dir = Path(tempdir) / "build"
            (build_dir / "docs").mkdir(parents=True, exist_ok=True)
            (build_dir / "docs" / "docs.pot").write_text(
                'msgid ""\nmsgstr ""\n', encoding="utf-8"
            )
            mocked_tmp.return_value.__enter__.return_value = tempdir
            mocked_tmp.return_value.__exit__.return_value = False
            addon.execute_update(self.component, "")

        self.assertEqual(mocked.call_args.args[1][-2], ".")
        self.assertEqual(mocked.call_args.kwargs["cwd"], self.component.full_path)

    def prepare_django_extraction_fixture(self) -> tuple[Path, Path, Path, Path, Path]:
        self.component.new_base = "extract-app/locale/django.pot"
        source_dir = Path(self.component.full_path) / "extract-app"
        module_one = source_dir / "module_one"
        module_two = source_dir / "module_two"
        top_level_locale = source_dir / "locale"
        module_one.mkdir(parents=True, exist_ok=True)
        (module_two / "templates" / "module_two").mkdir(parents=True, exist_ok=True)
        top_level_locale.mkdir(parents=True, exist_ok=True)

        (module_one / "views.py").write_text(
            "from django.utils.translation import gettext as _\n"
            '_("Module one string")\n',
            encoding="utf-8",
        )
        (module_two / "templates" / "module_two" / "page.html").write_text(
            '{% load i18n %}{% translate "Module two template" %}\n',
            encoding="utf-8",
        )

        module_one_po = module_one / "locale" / "cs" / "LC_MESSAGES" / "django.po"
        module_one_po.parent.mkdir(parents=True, exist_ok=True)
        module_one_po.write_text("module one sentinel\n", encoding="utf-8")

        module_two_po = module_two / "locale" / "de" / "LC_MESSAGES" / "django.po"
        module_two_po.parent.mkdir(parents=True, exist_ok=True)
        module_two_po.write_text("module two sentinel\n", encoding="utf-8")

        top_level_po = top_level_locale / "fr" / "LC_MESSAGES" / "django.po"
        top_level_po.parent.mkdir(parents=True, exist_ok=True)
        top_level_po.write_text("top level sentinel\n", encoding="utf-8")
        top_level_en_po = top_level_locale / "en" / "LC_MESSAGES" / "django.po"
        top_level_en_po.parent.mkdir(parents=True, exist_ok=True)
        top_level_en_po.write_text(
            'msgid ""\nmsgstr ""\n"Language: en\\n"\n\nmsgid "Old string"\nmsgstr ""\n',
            encoding="utf-8",
        )
        preexisting_top_level_pot = top_level_locale / "django.pot"
        preexisting_top_level_pot.write_text("stale pot\n", encoding="utf-8")
        return (
            source_dir,
            module_one_po,
            module_two_po,
            top_level_po,
            top_level_en_po,
        )

    def test_stock_django_uses_repository_locale_dir(self) -> None:
        source_dir, module_one_po, module_two_po, _top_level_po, top_level_en_po = (
            self.prepare_django_extraction_fixture()
        )

        with tempfile.TemporaryDirectory(prefix="weblate-django-stock-") as tempdir:
            original_cwd = os.getcwd()
            with (
                override_settings(
                    LOCALE_PATHS=[os.path.join(tempdir, "locale")],
                    LOCALE_FILTER_FILES=False,
                ),
                contextlib.ExitStack() as stack,
            ):
                stack.callback(os.chdir, original_cwd)
                os.chdir(source_dir)
                DjangoMakemessagesCommand().handle(
                    locale=["en"],
                    exclude=[],
                    domain="django",
                    verbosity=0,
                    all=False,
                    extensions=None,
                    symlinks=False,
                    ignore_patterns=[],
                    use_default_ignore_patterns=True,
                    no_wrap=False,
                    no_location=False,
                    add_location=None,
                    no_obsolete=False,
                    keep_pot=True,
                )

        module_one_en_po = module_one_po.parents[2] / "en" / "LC_MESSAGES" / "django.po"
        module_two_en_po = module_two_po.parents[2] / "en" / "LC_MESSAGES" / "django.po"
        self.assertEqual(
            top_level_en_po.read_text(encoding="utf-8"),
            'msgid ""\nmsgstr ""\n"Language: en\\n"\n\nmsgid "Old string"\nmsgstr ""\n',
        )
        self.assertTrue(module_one_en_po.exists())
        self.assertTrue(module_two_en_po.exists())
        self.assertIn(
            'msgid "Module one string"', module_one_en_po.read_text(encoding="utf-8")
        )
        self.assertIn(
            'msgid "Module two template"',
            module_two_en_po.read_text(encoding="utf-8"),
        )

    def test_django_ignores_repository_locale_dirs_during_extraction(self) -> None:
        (
            _source_dir,
            module_one_po,
            module_two_po,
            top_level_po,
            top_level_en_po,
        ) = self.prepare_django_extraction_fixture()

        addon = DjangoAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": False},
        )

        with patch.object(
            DjangoAddon, "validate_django_repository_tree", return_value=True
        ):
            result = addon.execute_update(self.component, "")

        self.assertTrue(result)
        generated = (
            Path(self.component.full_path) / "extract-app" / "locale" / "django.pot"
        )
        content = generated.read_text(encoding="utf-8")
        self.assertIn('msgid "Module one string"', content)
        self.assertIn('msgid "Module two template"', content)
        self.assertNotEqual(content, "stale pot\n")
        self.assertEqual(
            top_level_po.read_text(encoding="utf-8"), "top level sentinel\n"
        )
        self.assertEqual(
            top_level_en_po.read_text(encoding="utf-8"),
            'msgid ""\nmsgstr ""\n"Language: en\\n"\n\nmsgid "Old string"\nmsgstr ""\n',
        )
        self.assertEqual(
            module_one_po.read_text(encoding="utf-8"), "module one sentinel\n"
        )
        self.assertEqual(
            module_two_po.read_text(encoding="utf-8"), "module two sentinel\n"
        )
        self.assertFalse((module_one_po.parent / "django.pot").exists())
        self.assertFalse((module_two_po.parent / "django.pot").exists())

    def test_sphinx_command(self) -> None:
        self.component.new_base = "docs/locales/docs.pot"
        source_dir = Path(self.component.full_path) / "docs"
        source_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "index.rst").write_text("Heading\n=======\n", encoding="utf-8")
        addon = SphinxAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": False},
        )

        def run_process(component, command, env=None, cwd=None):
            build_dir = Path(command[-1])
            build_dir.mkdir(parents=True, exist_ok=True)
            (build_dir / "docs.pot").write_text(
                'msgid ""\nmsgstr ""\n', encoding="utf-8"
            )
            return ""

        with (
            patch.object(SphinxAddon, "validate_repository_tree", return_value=True),
            patch.object(SphinxAddon, "run_process", side_effect=run_process) as mocked,
        ):
            result = addon.execute_update(self.component, "")

        self.assertTrue(result)
        command = mocked.call_args.args[1]
        self.assertEqual(command[0], "sphinx-build")
        self.assertIn("-E", command)
        self.assertIn("-d", command)
        self.assertIn("-c", command)
        self.assertIn(".", command)
        self.assertEqual(mocked.call_args.kwargs["cwd"], os.fspath(source_dir))
        self.assertEqual(
            command[command.index("-c") + 1],
            os.fspath(
                Path(__file__).resolve().parent.parent
                / "addons"
                / "extractors"
                / "sphinx"
            ),
        )
        doctree_dir = Path(command[command.index("-d") + 1])
        self.assertEqual(doctree_dir.name, "doctrees")
        self.assertNotIn("env", mocked.call_args.kwargs)
        self.assertIn(
            os.path.join(self.component.full_path, "docs/locales/docs.pot"),
            addon.extra_files,
        )

    def test_sphinx_refuses_out_of_tree_symlink(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are not supported")

        self.component.new_base = "docs/locales/docs.pot"
        source_dir = Path(self.component.full_path) / "docs"
        source_dir.parent.mkdir(parents=True, exist_ok=True)
        addon = SphinxAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": False},
        )

        with tempfile.TemporaryDirectory(prefix="weblate-sphinx-outside-") as tempdir:
            outside_dir = Path(tempdir)
            (outside_dir / "index.rst").write_text(
                "Heading\n=======\n", encoding="utf-8"
            )
            source_dir.symlink_to(outside_dir, target_is_directory=True)

            with patch.object(SphinxAddon, "run_process", return_value="") as mocked:
                result = addon.execute_update(self.component, "")

        self.assertFalse(result)
        mocked.assert_not_called()
        self.assertEqual(
            addon.alerts[-1]["error"],
            "Repository contains symlink outside repository",
        )

    def test_sphinx_disables_docutils_file_insertion(self) -> None:
        if find_command("sphinx-build") is None:
            self.skipTest("sphinx-build is not installed")

        self.component.new_base = "docs/locales/docs.pot"
        source_dir = Path(self.component.full_path) / "docs"
        source_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            prefix="weblate-sphinx-include-",
            suffix=".txt",
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as included:
            included.write("TOP SECRET INCLUDED CONTENT\n")
            include_path = included.name

        self.addCleanup(
            lambda: os.path.exists(include_path) and os.unlink(include_path)
        )

        (source_dir / "index.rst").write_text(
            f"Heading\n=======\n\n.. include:: {include_path}\n",
            encoding="utf-8",
        )

        addon = SphinxAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": False},
        )

        with patch.object(SphinxAddon, "validate_repository_tree", return_value=True):
            result = addon.execute_update(self.component, "")

        generated = Path(self.component.full_path) / "docs" / "locales" / "docs.pot"
        if result:
            self.assertTrue(generated.exists())
            self.assertNotIn(
                "TOP SECRET INCLUDED CONTENT",
                generated.read_text(encoding="utf-8"),
            )
        else:
            self.assertTrue(addon.alerts)
            self.assertNotIn(
                "TOP SECRET INCLUDED CONTENT",
                addon.alerts[-1].get("output", ""),
            )

    def test_sphinx_emits_relative_source_references(self) -> None:
        if find_command("sphinx-build") is None:
            self.skipTest("sphinx-build is not installed")

        self.component.new_base = "docs/locales/docs.pot"
        source_dir = Path(self.component.full_path) / "docs"
        admin_dir = source_dir / "admin"
        admin_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "conf.py").write_text(
            'project = "Documentation"\n', encoding="utf-8"
        )
        (source_dir / "index.rst").write_text(
            ".. toctree::\n   :maxdepth: 1\n\n   admin/access\n",
            encoding="utf-8",
        )
        (admin_dir / "access.rst").write_text(
            "Access\n======\n\nWelcome to the admin docs.\n",
            encoding="utf-8",
        )

        addon = SphinxAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": False},
        )

        with patch.object(SphinxAddon, "validate_repository_tree", return_value=True):
            result = addon.execute_update(self.component, "")

        self.assertTrue(result, addon.alerts)
        generated = Path(self.component.full_path) / "docs" / "locales" / "docs.pot"
        content = generated.read_text(encoding="utf-8")
        self.assertIn("#: admin/access.rst:", content)
        self.assertNotIn(self.component.full_path, content)

    def test_sphinx_postprocess_uses_build_temp_dir_on_cross_device_repo_temp(
        self,
    ) -> None:
        addon = SphinxAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": False},
        )
        source_dir = Path(self.component.full_path) / "docs"
        source_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "index.rst").write_text(
            "Index\n=====\n\nHello\n", encoding="utf-8"
        )

        with tempfile.TemporaryDirectory(
            prefix="weblate-sphinx-postprocess-"
        ) as tempdir:
            build_dir = Path(tempdir) / "build"
            build_dir.mkdir()
            template = build_dir / "docs.pot"
            template.write_text(
                "\n".join(
                    (
                        'msgid ""',
                        'msgstr ""',
                        '"Content-Type: text/plain; charset=UTF-8\\n"',
                        "",
                        f"#: {source_dir / 'index.rst'}:1",
                        'msgid "Hello"',
                        'msgstr ""',
                        "",
                    )
                ),
                encoding="utf-8",
            )

            repo_temp_dir = self.component.repository.get_repo_temp_dir()
            self.assertIsNotNone(repo_temp_dir)
            if repo_temp_dir is None:
                self.fail("Repository temp dir should be configured for this test")
            build_root = build_dir.resolve()
            repo_temp_root = repo_temp_dir.resolve()
            temp_dirs: list[Path] = []
            original_named_temporary_file = tempfile.NamedTemporaryFile

            def fake_get_path_device_id(path: Path) -> int | None:
                resolved = path.resolve(strict=False)
                if resolved == build_root:
                    return 1
                if resolved == repo_temp_root:
                    return 2
                return 1

            def capture_named_temporary_file(*args, **kwargs):
                temp_dir = kwargs.get("dir")
                if temp_dir is None and len(args) > 6:
                    temp_dir = args[6]
                self.assertIsNotNone(temp_dir)
                if temp_dir is None:
                    self.fail("NamedTemporaryFile should be called with a temp dir")
                temp_dirs.append(Path(temp_dir).resolve(strict=False))
                return original_named_temporary_file(*args, **kwargs)

            with (
                patch(
                    "weblate.utils.files._get_path_device_id",
                    side_effect=fake_get_path_device_id,
                ),
                patch(
                    "weblate.formats.base.tempfile.NamedTemporaryFile",
                    side_effect=capture_named_temporary_file,
                ),
            ):
                addon.postprocess_sphinx_template(
                    self.component, template, source_dir, build_dir
                )
                content = template.read_text(encoding="utf-8")

        self.assertEqual(temp_dirs, [build_dir.resolve(strict=False)])
        self.assertIn("#: index.rst:1", content)

    def test_sphinx_weblate_docs_filter(self) -> None:
        if find_command("sphinx-build") is None:
            self.skipTest("sphinx-build is not installed")

        self.component.new_base = "docs/locales/docs.pot"
        source_dir = Path(self.component.full_path) / "docs"
        admin_dir = source_dir / "admin"
        admin_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "conf.py").write_text(
            'project = "Documentation"\n', encoding="utf-8"
        )
        (source_dir / "index.rst").write_text(
            ".. toctree::\n   :maxdepth: 1\n\n   admin/access\n   admin/management\n",
            encoding="utf-8",
        )
        (admin_dir / "access.rst").write_text(
            "Access\n======\n\nDjango\n\nWelcome to the admin docs.\n",
            encoding="utf-8",
        )
        (admin_dir / "management.rst").write_text(
            "Management\n==========\n\nfoo_bar\n",
            encoding="utf-8",
        )

        addon = SphinxAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "normalize_header": False,
                "filter_mode": "weblate_docs",
            },
        )

        with patch.object(SphinxAddon, "validate_repository_tree", return_value=True):
            result = addon.execute_update(self.component, "")

        self.assertTrue(result, addon.alerts)
        generated = Path(self.component.full_path) / "docs" / "locales" / "docs.pot"
        content = generated.read_text(encoding="utf-8")
        self.assertIn("Welcome to the admin docs.", content)
        self.assertNotIn('\nmsgid "Django"\n', content)
        self.assertNotIn('\nmsgid "foo_bar"\n', content)

    def test_django_refuses_out_of_tree_symlinked_source_file(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are not supported")

        self.component.new_base = "locale/django.pot"
        addon = DjangoAddon.create(
            component=self.component,
            run=False,
            configuration={"interval": "weekly", "normalize_header": False},
        )

        with tempfile.TemporaryDirectory(prefix="weblate-django-outside-") as tempdir:
            outside_dir = Path(tempdir)
            (outside_dir / "messages.py").write_text(
                'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
            )
            (Path(self.component.full_path) / "src.py").symlink_to(
                outside_dir / "messages.py"
            )

            with patch.object(DjangoAddon, "run_process", return_value="") as mocked:
                result = addon.execute_update(self.component, "")

        self.assertFalse(result)
        mocked.assert_not_called()
        self.assertEqual(
            addon.alerts[-1]["error"],
            "Repository contains symlink outside repository",
        )

    def test_extract_pot_installs_msgmerge(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "_install_msgmerge": True,
                "interval": "weekly",
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )

        with (
            patch.object(MsgmergeAddon, "can_install", return_value=True),
            patch.object(MsgmergeAddon, "create", autospec=True) as mocked_create,
            patch.object(XgettextAddon, "run_process", return_value=""),
        ):
            addon.post_configure_run()

        mocked_create.assert_called_once()

    def test_extract_pot_post_configure_triggers_newly_installed_msgmerge(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "_install_msgmerge": True,
                "interval": "weekly",
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        self.component.drop_addons_cache()
        _ = self.component.addons_cache

        with (
            patch.object(XgettextAddon, "run_process", return_value=""),
            patch.object(MsgmergeAddon, "update_translations", autospec=True) as mocked,
        ):
            addon.post_configure_run()

        mocked.assert_called_once()

    def test_extract_pot_installs_msgmerge_for_project_scope(self) -> None:
        self.create_po_new_base(
            project=self.component.project,
            name="Project scoped",
            slug="project-scoped-msgmerge",
        )
        addon = XgettextAddon.create(
            project=self.component.project,
            run=False,
            configuration={
                "_install_msgmerge": True,
                "interval": "weekly",
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )

        with (
            patch.object(MsgmergeAddon, "can_install", return_value=True),
            patch.object(MsgmergeAddon, "create", autospec=True) as mocked_create,
            patch.object(XgettextAddon, "run_process", return_value=""),
        ):
            addon.post_configure_run()

        mocked_create.assert_called_once()
        self.assertEqual(
            mocked_create.call_args.kwargs["project"], self.component.project
        )
        self.assertNotIn("component", mocked_create.call_args.kwargs)
        self.assertNotIn("_install_msgmerge", addon.instance.configuration)

    def test_extract_pot_reuses_inherited_msgmerge_on_install(self) -> None:
        MsgmergeAddon.create(project=self.component.project, run=False)
        self.component.drop_addons_cache()
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "_install_msgmerge": True,
                "interval": "weekly",
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )

        with (
            patch.object(MsgmergeAddon, "can_install", return_value=True),
            patch.object(MsgmergeAddon, "create", autospec=True) as mocked_create,
            patch.object(XgettextAddon, "run_process", return_value=""),
        ):
            addon.post_configure_run()

        mocked_create.assert_not_called()

    def test_extract_pot_warns_without_msgmerge(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "_install_msgmerge": True,
                "interval": "weekly",
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )

        with (
            patch.object(MsgmergeAddon, "can_install", return_value=False),
            patch.object(XgettextAddon, "run_process", return_value=""),
        ):
            addon.post_configure_run()

        self.assertFalse(addon.warnings)
        self.assertTrue(self.component.alert_set.filter(name=addon.alert).exists())

    def test_extract_pot_runtime_uses_existing_msgmerge_even_if_disabled(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        msgmerge = MsgmergeAddon.create(component=self.component, run=False)
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )

        with (
            patch.object(XgettextAddon, "run_process", return_value=""),
            patch.object(MsgmergeAddon, "update_translations", autospec=True) as mocked,
            patch.object(XgettextAddon, "validate_repository_tree", return_value=True),
        ):
            addon.update_translations(self.component, "")

        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.args[0].instance.pk, msgmerge.instance.pk)
        self.assertIs(mocked.call_args.args[1], self.component)
        self.assertEqual(mocked.call_args.args[2], "")

    def test_extract_pot_forces_msgmerge_after_local_template_update(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        msgmerge = MsgmergeAddon.create(component=self.component, run=False)
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )

        with (
            patch.object(XgettextAddon, "run_process", return_value=""),
            patch.object(MsgmergeAddon, "update_translations", autospec=True) as mocked,
            patch.object(XgettextAddon, "validate_repository_tree", return_value=True),
            patch.object(
                self.component.repository,
                "list_changed_files",
                return_value=["src/messages.py"],
            ),
        ):
            addon.update_translations(self.component, "old-revision")

        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.args[0].instance.pk, msgmerge.instance.pk)
        self.assertIs(mocked.call_args.args[1], self.component)
        self.assertEqual(mocked.call_args.args[2], "")

    def test_extract_pot_uses_project_level_msgmerge(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        msgmerge = MsgmergeAddon.create(project=self.component.project, run=False)
        self.component.drop_addons_cache()
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )

        with (
            patch.object(XgettextAddon, "run_process", return_value=""),
            patch.object(MsgmergeAddon, "update_translations", autospec=True) as mocked,
            patch.object(XgettextAddon, "validate_repository_tree", return_value=True),
        ):
            addon.update_translations(self.component, "")

        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.args[0].instance.pk, msgmerge.instance.pk)
        self.assertIs(mocked.call_args.args[1], self.component)
        self.assertEqual(mocked.call_args.args[2], "")

    def test_extract_pot_timeout(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )

        with patch(
            "weblate.addons.gettext.subprocess.check_output",
            side_effect=subprocess.TimeoutExpired(
                ["xgettext"], timeout=addon.PROCESS_TIMEOUT
            ),
        ):
            output = addon.run_process(self.component, ["xgettext"])

        self.assertIsNone(output)
        self.assertEqual(len(addon.alerts), 1)
        self.assertIn("timed out", addon.alerts[0]["error"].lower())

    def test_extract_pot_uses_runtime_interpreter_path_for_commands(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )

        with tempfile.TemporaryDirectory(prefix="weblate-runtime-command-") as tempdir:
            runtime_bin = Path(tempdir) / "runtime-bin"
            runtime_bin.mkdir(parents=True, exist_ok=True)
            fake_python = runtime_bin / "python"
            fake_python.write_text("", encoding="utf-8")
            fake_python.chmod(0o755)
            xgettext = runtime_bin / "xgettext"
            xgettext.write_text("#!/bin/sh\necho runtime-xgettext\n", encoding="utf-8")
            xgettext.chmod(0o755)

            with (
                patch("weblate.utils.commands.sys.executable", os.fspath(fake_python)),
                patch(
                    "weblate.utils.commands.sys.exec_prefix",
                    os.fspath(Path(tempdir) / "other-prefix"),
                ),
                patch.dict(os.environ, {"PATH": "/usr/bin"}),
            ):
                output = addon.run_process(self.component, ["xgettext"])

        self.assertEqual(output, "runtime-xgettext\n")

    def test_django_can_install_requires_msguniq(self) -> None:
        self.component.new_base = "locale/django.pot"
        self.component.save(update_fields=["new_base"])

        def fake_find_command(name, path=None):
            if name == "xgettext":
                return "/usr/bin/xgettext"
            if name == "msguniq":
                return None
            return "/usr/bin/other"

        with patch(
            "weblate.utils.commands.find_command", side_effect=fake_find_command
        ):
            self.assertFalse(DjangoAddon.can_install(component=self.component))

    def test_generate(self) -> None:
        self.assertTrue(GenerateFileAddon.can_install(component=self.component))
        GenerateFileAddon.create(
            component=self.component,
            configuration={
                "filename": "stats/{{ language_code }}.json",
                "template": """{
    "translated": {{ stats.translated_percent }}
}""",
            },
        )
        commit = self.component.repository.show(self.component.repository.last_revision)
        # Verify file is created upon install
        self.assertIn("stats/cs.json", commit)
        # Verify that source language file is not there
        self.assertNotIn("stats/en.json", commit)
        self.assertIn('"translated": 0', commit)

        # Verify file is updated upon edit
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.get_translation().commit_pending("test", None)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("stats/cs.json", commit)
        self.assertIn('"translated": 25', commit)

    def test_gettext_comment(self) -> None:
        translation = self.get_translation()
        self.assertTrue(
            GettextAuthorComments.can_install(component=translation.component)
        )
        addon = GettextAuthorComments.create(component=translation.component)
        addon.pre_commit(translation, "Stojan Jakotyc <stojan@example.com>", True)
        content = Path(translation.get_filename()).read_text(encoding="utf-8")
        self.assertIn("Stojan Jakotyc", content)

    def test_pseudolocale(self) -> None:
        self.assertTrue(PseudolocaleAddon.can_install(component=self.component))
        PseudolocaleAddon.create(
            component=self.component,
            configuration={
                "source": self.component.translation_set.get(language_code="en").pk,
                "target": self.component.translation_set.get(language_code="de").pk,
                "prefix": "@@@",
                "suffix": "!!!",
            },
        )
        translation = self.component.translation_set.get(language_code="de")
        self.assertEqual(translation.stats.translated, translation.stats.all)
        for unit in translation.unit_set.all():
            for text in unit.get_target_plurals():
                self.assertTrue(text.startswith("@@@"))
                # We need to deal with automated fixups
                self.assertTrue(text.endswith(("!!!", "!!!\n")))

    def test_pseudolocale_variable(self) -> None:
        self.assertTrue(PseudolocaleAddon.can_install(component=self.component))
        PseudolocaleAddon.create(
            component=self.component,
            configuration={
                "source": self.component.translation_set.get(language_code="en").pk,
                "target": self.component.translation_set.get(language_code="de").pk,
                "prefix": "@@@",
                "suffix": "!!!",
                "var_prefix": "_",
                "var_suffix": "_",
                "var_multiplier": 1,
            },
        )
        translation = self.component.translation_set.get(language_code="de")
        self.assertEqual(translation.check_flags, "ignore-all-checks")
        self.assertEqual(translation.stats.translated, translation.stats.all)
        for unit in translation.unit_set.all():
            for text in unit.get_target_plurals():
                self.assertTrue(text.startswith("@@@_"))
                # We need to deal with automated fixups
                self.assertTrue(text.endswith(("_!!!", "_!!!\n")))
        for addon in self.component.addon_set.all():
            addon.delete()
        translation = self.component.translation_set.get(language_code="de")
        self.assertEqual(translation.check_flags, "")

    def test_prefill(self) -> None:
        self.assertTrue(PrefillAddon.can_install(component=self.component))
        PrefillAddon.create(component=self.component)
        for translation in self.component.translation_set.prefetch():
            self.assertEqual(translation.stats.nottranslated, 0)
            for unit in translation.unit_set.all():
                sources = unit.get_source_plurals()
                for text in unit.get_target_plurals():
                    self.assertIn(text, sources)
        self.assertFalse(PendingUnitChange.objects.exists())

    def test_read_only(self) -> None:
        self.assertTrue(FillReadOnlyAddon.can_install(component=self.component))
        addon = FillReadOnlyAddon.create(component=self.component)
        for translation in self.component.translation_set.prefetch():
            if translation.is_source:
                continue
            self.assertEqual(translation.stats.readonly, 0)
        unit = self.get_unit().source_unit
        unit.extra_flags = "read-only"
        unit.save(same_content=True, update_fields=["extra_flags"])
        for translation in self.component.translation_set.prefetch():
            if translation.is_source:
                continue
            translation.invalidate_cache()
            self.assertEqual(translation.stats.readonly, 1)
            unit = translation.unit_set.get(state=STATE_READONLY)
            self.assertEqual(unit.target, "")
        addon.daily(self.component)
        for translation in self.component.translation_set.prefetch():
            if translation.is_source:
                continue
            self.assertEqual(translation.stats.readonly, 1)
            unit = translation.unit_set.get(state=STATE_READONLY)
            self.assertEqual(unit.target, unit.source)

    def test_read_only_daily_reuses_prefetched_units(self) -> None:
        self.assertTrue(FillReadOnlyAddon.can_install(component=self.component))
        addon = FillReadOnlyAddon.create(component=self.component)
        unit = self.get_unit().source_unit
        unit.extra_flags = "read-only"
        unit.save(same_content=True, update_fields=["extra_flags"])
        source_translation = self.component.source_translation

        with patch.object(
            addon, "fetch_strings", wraps=addon.fetch_strings
        ) as fetch_strings:
            addon.daily(self.component)

        self.assertEqual(fetch_strings.call_count, 1)
        self.assertEqual(fetch_strings.call_args.args[0].pk, source_translation.pk)


class AppStoreAddonTest(ComponentTestCase):
    def create_component(self):
        return self.create_appstore()

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(component=self.component))
        rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False)
        self.assertEqual(rev, self.component.repository.last_revision)
        addon.post_update(self.component, "", False)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("cs/changelogs/100000.txt", commit)


class AndroidAddonTest(ComponentTestCase):
    def create_component(self):
        return self.create_android(suffix="-not-synced", new_lang="add")

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(component=self.component))
        rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False)
        self.assertEqual(rev, self.component.repository.last_revision)
        addon.post_update(self.component, "", False)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("android-not-synced/values-cs/strings.xml", commit)
        self.assertIn('\n-    <string name="hello">Ahoj svete</string>', commit)


class WindowsRCAddonTest(ComponentTestCase):
    def create_component(self):
        return self.create_winrc()

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(component=self.component))
        rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False)
        self.assertEqual(rev, self.component.repository.last_revision)
        addon.post_update(self.component, "", False)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("winrc/cs-CZ.rc", commit)
        self.assertIn("\n-IDS_MSG5", commit)


class IntermediateAddonTest(ComponentTestCase):
    def create_component(self):
        return self.create_json_intermediate(new_lang="add")

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(component=self.component))
        rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False)
        self.assertEqual(rev, self.component.repository.last_revision)
        addon.post_update(self.component, "", False)
        commit = self.component.repository.show(self.component.repository.last_revision)
        # It should remove string not present in the English file
        self.assertIn("intermediate/cs.json", commit)
        self.assertIn('-    "orangutan"', commit)


class ResxAddonTest(ComponentTestCase):
    def create_component(self):
        return self.create_resx()

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(component=self.component))
        rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        # Unshallow the local repo
        with self.component.repository.lock:
            self.component.repository.execute(
                ["fetch", "--unshallow", "origin"],
                remote_op="pull",
            )
        addon.post_update(
            self.component, "da07dc0dc7052dc44eadfa8f3a2f2609ec634303", False
        )
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("resx/cs.resx", commit)

    def test_update(self) -> None:
        self.assertTrue(ResxUpdateAddon.can_install(component=self.component))
        addon = ResxUpdateAddon.create(component=self.component)
        rev = self.component.repository.last_revision
        # Unshallow the local repo
        with self.component.repository.lock:
            self.component.repository.execute(
                ["fetch", "--unshallow", "origin"],
                remote_op="pull",
            )
        addon.post_update(
            self.component, "da07dc0dc7052dc44eadfa8f3a2f2609ec634303", False
        )
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("resx/cs.resx", commit)


class CSVAddonTest(ComponentTestCase):
    def create_component(self):
        return self.create_csv_mono()

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(component=self.component))
        rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        addon.post_update(
            self.component, "da07dc0dc7052dc44eadfa8f3a2f2609ec634303", False
        )
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("csv-mono/cs.csv", commit)

    def test_remove_blank(self) -> None:
        self.assertTrue(RemoveBlankAddon.can_install(component=self.component))
        rev = self.component.repository.last_revision
        addon = RemoveBlankAddon.create(component=self.component)
        addon.post_update(
            self.component, "da07dc0dc7052dc44eadfa8f3a2f2609ec634303", False
        )
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("csv-mono/cs.csv", commit)


class JsonAddonTest(ComponentTestCase):
    def create_component(self):
        return self.create_json_mono(suffix="mono-sync")

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(component=self.component))
        rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False)
        self.assertEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("json-mono-sync/cs.json", commit)

    def test_remove_blank(self) -> None:
        self.assertTrue(RemoveBlankAddon.can_install(component=self.component))
        rev = self.component.repository.last_revision
        addon = RemoveBlankAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False)
        self.assertEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("json-mono-sync/cs.json", commit)

    def test_unit_flags(self) -> None:
        self.assertTrue(SourceEditAddon.can_install(component=self.component))
        self.assertTrue(TargetEditAddon.can_install(component=self.component))
        self.assertTrue(SameEditAddon.can_install(component=self.component))
        SourceEditAddon.create(component=self.component)
        TargetEditAddon.create(component=self.component)
        SameEditAddon.create(component=self.component)

        Unit.objects.filter(translation__language__code="cs").delete()
        self.component.create_translations_immediate(force=True)
        self.assertFalse(
            Unit.objects.filter(translation__language__code="cs")
            .exclude(state__in=(*FUZZY_STATES, STATE_EMPTY))
            .exists()
        )

        Unit.objects.all().delete()
        self.component.create_translations_immediate(force=True)
        self.assertFalse(
            Unit.objects.exclude(
                state__in=(*FUZZY_STATES, STATE_EMPTY, STATE_READONLY)
            ).exists()
        )


class ViewTests(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.make_manager()

    def setup_language_consistency_preview(self) -> None:
        self.component.new_lang = "add"
        self.component.new_base = "po/hello.pot"
        self.component.save()
        self.create_ts(
            name="TS",
            new_lang="add",
            new_base="ts/cs.ts",
            project=self.component.project,
        )

    def assert_language_consistency_confirmation(
        self, url: str, data: dict[str, object], scope_text: str
    ) -> None:
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Configure add-on")
        self.assertContains(response, "Review before installing")
        self.assertContains(response, scope_text)
        self.assertContains(response, "German")
        self.assertContains(response, "Italian")
        self.assertContains(response, "ts/de.ts")
        self.assertContains(response, "ts/it.ts")
        self.assertFalse(Addon.objects.filter(name=data["name"]).exists())

        response = self.client.post(
            url,
            {
                **data,
                "form": "1",
            },
            follow=True,
        )
        self.assertContains(
            response, "Please review and confirm the missing language changes."
        )
        self.assertFalse(Addon.objects.filter(name=data["name"]).exists())

        response = self.client.post(
            url,
            {
                **data,
                "form": "1",
                "confirm": True,
            },
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")

    def test_list(self) -> None:
        response = self.client.get(reverse("addons", kwargs=self.kw_component))
        self.assertContains(response, "Generate MO files")

    def test_nonexisting(self) -> None:
        identifier = "weblate.addon.nonexisting"
        # Use bulk_create to avoid hitting save() which relies on class existence
        Addon.objects.bulk_create([Addon(component=self.component, name=identifier)])

        # Listing of unknown add-on should not crash
        response = self.client.get(reverse("addons", kwargs=self.kw_component))
        self.assertContains(response, "Generate MO files")
        self.assertContains(response, identifier)

        # Deleting unknown add-on should work
        addon = Addon.objects.get(name=identifier)
        response = self.client.post(
            addon.get_absolute_url(), {"delete": "1"}, follow=True
        )
        self.assertContains(response, "No add-ons currently installed")
        self.assertContains(response, "Generate MO files")
        # History entry
        self.assertContains(response, identifier)

        self.assertFalse(Addon.objects.filter(name=identifier).exists())

    def test_addon_logs(self) -> None:
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.gettext.authors"},
            follow=True,
        )
        addon = self.component.addon_set.all()[0]
        response = self.client.get(reverse("addon-logs", kwargs={"pk": addon.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "addons/addon_logs.html")
        self.assertEqual(response.context["instance"], addon)

    def test_manual_run_button(self) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        ).instance

        response = self.client.get(reverse("addons", kwargs=self.kw_component))

        self.assertContains(response, "Run now")
        self.assertContains(response, addon.get_absolute_url())

    def test_non_daily_addon_has_no_manual_run_button(self) -> None:
        GettextAuthorComments.create(component=self.component, run=False)

        response = self.client.get(reverse("addons", kwargs=self.kw_component))

        self.assertNotContains(response, "Run now")

    @patch("weblate.addons.tasks.run_addon_manually.delay_on_commit")
    def test_manual_run(self, mocked_delay) -> None:
        addon = XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        ).instance

        response = self.client.post(addon.get_absolute_url(), {"run": "1"}, follow=True)

        mocked_delay.assert_called_once_with(addon.pk)
        self.assertContains(response, "Add-on run has been scheduled.")

    def test_nonexisting_detail(self) -> None:
        identifier = "weblate.addon.nonexisting"
        Addon.objects.bulk_create([Addon(component=self.component, name=identifier)])

        addon = Addon.objects.get(name=identifier)
        response = self.client.get(reverse("addon-detail", kwargs={"pk": addon.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "addons/addon_detail.html")
        self.assertContains(response, identifier)
        self.assertNotContains(response, 'name="form"')

    def test_nonexisting_logs(self) -> None:
        identifier = "weblate.addon.nonexisting"
        Addon.objects.bulk_create([Addon(component=self.component, name=identifier)])

        addon = Addon.objects.get(name=identifier)
        response = self.client.get(reverse("addon-logs", kwargs={"pk": addon.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "addons/addon_logs.html")
        self.assertContains(response, identifier)
        self.assertContains(response, "No add-on activity logs available.")

    def test_nonexisting_detail_post(self) -> None:
        identifier = "weblate.addon.nonexisting"
        Addon.objects.bulk_create([Addon(component=self.component, name=identifier)])

        addon = Addon.objects.get(name=identifier)
        response = self.client.post(
            reverse("addon-detail", kwargs={"pk": addon.pk}),
            {"form": "1"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid add-on name:")
        self.assertContains(response, identifier)
        self.assertTrue(Addon.objects.filter(pk=addon.pk).exists())

    def test_addon_logs_without_authentication(self) -> None:
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.gettext.authors"},
            follow=True,
        )
        addon = self.component.addon_set.all()[0]

        self.client.logout()
        response = self.client.get(reverse("addon-logs", kwargs={"pk": addon.pk}))
        self.assertEqual(response.status_code, 403)

    def test_add_simple(self) -> None:
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.gettext.authors"},
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")
        change = self.component.change_set.get(action=ActionEvents.ADDON_CREATE)
        self.assertEqual(change.user, self.user)

    def test_add_simple_with_nonexisting_installed(self) -> None:
        Addon.objects.bulk_create(
            [Addon(component=self.component, name="weblate.addon.nonexisting")]
        )

        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.gettext.authors"},
            follow=True,
        )

        self.assertContains(response, "Installed 2 add-ons")
        self.assertContains(response, "weblate.addon.nonexisting")
        self.assertContains(response, "Contributors in comment")
        self.assertTrue(
            Addon.objects.filter(
                component=self.component, name="weblate.gettext.authors"
            ).exists()
        )

    def test_add_simple_project_addon(self) -> None:
        self.setup_language_consistency_preview()
        self.assert_language_consistency_confirmation(
            reverse("addons", kwargs=self.kw_project_path),
            {"name": "weblate.consistency.languages"},
            "whole project",
        )

    def test_add_simple_category_addon(self) -> None:
        self.setup_language_consistency_preview()
        category = self.create_category(self.project)
        self.component.category = category
        self.component.save()
        addon_component = self.project.component_set.exclude(pk=self.component.pk).get()
        addon_component.category = category
        addon_component.save()
        self.assert_language_consistency_confirmation(
            reverse("addons", kwargs={"path": category.get_url_path()}),
            {"name": "weblate.consistency.languages"},
            "whole category",
        )

    def test_add_simple_site_wide_addon(self) -> None:
        self.setup_language_consistency_preview()
        response = self.client.post(
            reverse("manage-addons"),
            {"name": "weblate.consistency.languages"},
            follow=True,
        )
        self.assertEqual(response.status_code, 403)
        self.user.is_superuser = True
        self.user.save()
        self.assert_language_consistency_confirmation(
            reverse("manage-addons"),
            {"name": "weblate.consistency.languages"},
            "all projects",
        )

    def test_add_invalid(self) -> None:
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "invalid"},
            follow=True,
        )
        self.assertContains(response, "Invalid add-on name:")

    def test_add_blank(self) -> None:
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": ""},
            follow=True,
        )
        self.assertContains(response, "Invalid add-on name:")

    def test_add_incompatible(self) -> None:
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.resx.update"},
            follow=True,
        )
        self.assertContains(response, "Add-on cannot be installed:")

    def test_add_config(self) -> None:
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.generate.generate"},
            follow=True,
        )
        self.assertContains(response, "Configure add-on")
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.generate.generate",
                "form": "1",
                "filename": "stats/{{ language_code }}.json",
                "template": '{"code":"{{ language_code }}"}',
            },
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")
        change = self.component.change_set.get(action=ActionEvents.ADDON_CREATE)
        self.assertEqual(change.user, self.user)

    def test_add_config_site_wide_addon(self) -> None:
        response = self.client.post(
            reverse("manage-addons"),
            {"name": "weblate.generate.generate"},
            follow=True,
        )
        self.assertEqual(response.status_code, 403)
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("manage-addons"),
            {"name": "weblate.generate.generate"},
            follow=True,
        )
        self.assertContains(response, "Configure add-on")
        response = self.client.post(
            reverse("manage-addons"),
            {
                "name": "weblate.generate.generate",
                "form": "1",
                "filename": "stats/{{ language_code }}.json",
                "template": '{"code":"{{ language_code }}"}',
            },
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")

    def test_add_pseudolocale(self) -> None:
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.generate.pseudolocale"},
            follow=True,
        )
        self.assertContains(response, "Configure add-on")
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.generate.pseudolocale",
                "form": "1",
                "source": self.component.source_translation.pk,
                "target": self.component.translation_set.get(language__code="cs").pk,
            },
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")

    def test_edit_config(self) -> None:
        self.test_add_config()
        addon = self.component.addon_set.all()[0]
        response = self.client.get(addon.get_absolute_url())
        self.assertContains(response, "Configure add-on")
        response = self.client.post(addon.get_absolute_url())
        self.assertContains(response, "Configure add-on")
        self.assertContains(response, "This field is required")

    def test_delete(self) -> None:
        addon = SourceEditAddon.create(component=self.component)
        response = self.client.post(
            addon.instance.get_absolute_url(), {"delete": "1"}, follow=True
        )
        self.assertContains(response, "No add-ons currently installed")


class PropertiesAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_java()

    def test_sort(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.assertTrue(PropertiesSortAddon.can_install(component=self.component))
        PropertiesSortAddon.create(component=self.component)
        self.get_translation().commit_pending("test", None)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("java/swing_messages_cs.properties", commit)

    def test_sort_case_sensitive(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.assertTrue(PropertiesSortAddon.can_install(component=self.component))
        PropertiesSortAddon.create(
            component=self.component, configuration={"case_sensitive": True}
        )
        self.get_translation().commit_pending("test", None)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("java/swing_messages_cs.properties", commit)

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(component=self.component))
        init_rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        self.assertNotEqual(init_rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False)
        self.assertEqual(rev, self.component.repository.last_revision)
        addon.post_update(self.component, "", False)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("java/swing_messages_cs.properties", commit)
        self.component.do_reset()
        self.assertNotEqual(init_rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("java/swing_messages_cs.properties", commit)
        self.assertIn("-state=Stale", commit)


class ResetAddonTest(ComponentTestCase):
    def create_component(self):
        project = self.create_project(name="Sandbox", slug="sandbox")
        return self.create_po_new_base(project=project)

    def test_can_install(self) -> None:
        self.assertTrue(ResetAddon.can_install(component=self.component))
        other = self.create_po_new_base(
            project=self.create_project(name="Regular", slug="regular")
        )
        self.assertFalse(ResetAddon.can_install(component=other))

    def test_daily(self) -> None:
        ResetAddon.create(component=self.component, run=False)

        with patch.object(Component, "do_reset", autospec=True) as mocked_reset:
            daily_addons(modulo=False)

        mocked_reset.assert_called_once_with(self.component)


class CommandTest(ComponentTestCase):
    """Test for management commands."""

    def test_list_addons(self) -> None:
        output = StringIO()
        call_command("list_addons", stdout=output)
        generated = output.getvalue()
        self.assertIn("msgmerge", generated)
        self.assertNotIn("Guided preset", generated)
        self.assertIn(
            "Enter slug of a component to use as source, keep blank to use all "
            "components in the current project.",
            generated,
        )
        # Hidden fields such as DiscoveryForm.confirm (HiddenInput) should not be documented
        self.assertNotIn("confirm", generated)
        self.assertNotIn("Update PO files using msgmerge", generated)

    def test_install_not_supported(self) -> None:
        output = StringIO()
        call_command(
            "install_addon",
            "--all",
            "--addon",
            "weblate.flags.same_edit",
            stdout=output,
            stderr=output,
        )
        self.assertIn("Can not install on Test/Test", output.getvalue())

    def test_install_no_form(self) -> None:
        output = StringIO()
        call_command(
            "install_addon",
            "--all",
            "--addon",
            "weblate.gettext.authors",
            stdout=output,
            stderr=output,
        )
        self.assertIn("Successfully installed on Test/Test", output.getvalue())

    def test_install_missing_form(self) -> None:
        output = StringIO()
        call_command(
            "install_addon",
            "--all",
            "--addon",
            "weblate.gettext.mo",
            stdout=output,
            stderr=output,
        )
        self.assertIn("Successfully installed on Test/Test", output.getvalue())

    def test_install_form(self) -> None:
        output = StringIO()
        call_command(
            "install_addon",
            "--all",
            "--addon",
            "weblate.gettext.mo",
            "--configuration",
            '{"fuzzy":true}',
            stdout=output,
            stderr=output,
        )
        self.assertIn("Successfully installed on Test/Test", output.getvalue())
        # Test when component is None
        addon_count = Addon.objects.filter_sitewide()
        self.assertEqual(addon_count.count(), 0)
        addon = Addon.objects.get(component=self.component)
        self.assertEqual(addon.configuration, {"fuzzy": True})
        output = StringIO()
        call_command(
            "install_addon",
            "--all",
            "--addon",
            "weblate.gettext.mo",
            "--configuration",
            '{"fuzzy":false}',
            stdout=output,
            stderr=output,
        )
        self.assertIn("Already installed on Test/Test", output.getvalue())
        addon = Addon.objects.get(component=self.component)
        self.assertEqual(addon.configuration, {"fuzzy": True})
        output = StringIO()
        call_command(
            "install_addon",
            "--all",
            "--update",
            "--addon",
            "weblate.gettext.mo",
            "--configuration",
            '{"fuzzy":false}',
            stdout=output,
            stderr=output,
        )
        self.assertIn("Successfully updated on Test/Test", output.getvalue())
        addon = Addon.objects.get(component=self.component)
        self.assertEqual(addon.configuration, {"fuzzy": False})

    def test_install_addon_wrong(self) -> None:
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "install_addon",
                "--all",
                "--addon",
                "weblate.gettext.nonexisting",
                "--configuration",
                '{"width":77}',
            )
        with self.assertRaises(CommandError):
            call_command(
                "install_addon",
                "--all",
                "--addon",
                "weblate.gettext.mo",
                "--configuration",
                "{",
            )
        with self.assertRaises(CommandError):
            call_command(
                "install_addon",
                "--all",
                "--addon",
                "weblate.cdn.cdnjs",
                "--configuration",
                "{}",
                stdout=output,
            )
        with self.assertRaises(CommandError):
            call_command(
                "install_addon",
                "--all",
                "--addon",
                "weblate.cdn.cdnjs",
                "--configuration",
                '{"width":-65535}',
                stderr=output,
            )

    def test_install_pseudolocale(self) -> None:
        output = StringIO()
        call_command(
            "install_addon",
            "--all",
            "--addon",
            "weblate.generate.pseudolocale",
            "--configuration",
            json.dumps(
                {
                    "target": self.translation.id,
                    "source": self.component.source_translation.id,
                }
            ),
            stdout=output,
            stderr=output,
        )
        self.assertIn("Successfully installed on Test/Test", output.getvalue())


class DiscoveryTest(ViewTestCase):
    def test_creation(self) -> None:
        link = self.component.get_repo_link_url()
        self.assertEqual(Component.objects.filter(repo=link).count(), 0)
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            addon = DiscoveryAddon.create(
                component=self.component,
                configuration={
                    "file_format": "po",
                    "match": r"(?P<component>[^/]*)/(?P<language>[^/]*)\.po",
                    "name_template": "{{ component|title }}",
                    "language_regex": "^(?!xx).+$",
                    "base_file_template": "",
                    "remove": True,
                },
            )
        self.assertEqual(Component.objects.filter(repo=link).count(), 4)
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            addon.post_update(self.component, "", False)
        self.assertEqual(Component.objects.filter(repo=link).count(), 4)

    def test_form(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        # Missing params
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.discovery.discovery", "form": "1"},
            follow=True,
        )
        self.assertNotContains(response, "Please review and confirm")
        # Wrong params
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.discovery.discovery",
                "name_template": "xxx",
                "form": "1",
            },
            follow=True,
        )
        self.assertContains(response, "This template must include component markup.")
        # Missing variable
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.discovery.discovery",
                "form": "1",
                "file_format": "po",
                "match": r"(?P<component>[^/]*)/(?P<language>[^/]*)\.po",
                "name_template": "{{ component|title }}.{{ ext }}",
                "language_regex": "^(?!xx).+$",
                "base_file_template": "",
                "remove": True,
            },
            follow=True,
        )
        self.assertContains(response, "Undefined variable: &quot;ext&quot;")
        # Correct params for confirmation
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.discovery.discovery",
                "form": "1",
                "file_format": "po",
                "match": r"(?P<component>[^/]*)/(?P<language>[^/]*)\.(?P<ext>po)",
                "name_template": "{{ component|title }}.{{ ext }}",
                "language_regex": "^(?!xx).+$",
                "base_file_template": "",
                "remove": True,
            },
            follow=True,
        )
        self.assertContains(response, "Please review and confirm")
        content = response.content.decode()
        self.assertLess(
            content.index("po-mono/cs.po"),
            content.index("po-mono/de.po"),
        )
        self.assertLess(
            content.index("po-mono/de.po"),
            content.index("po-mono/en.po"),
        )
        self.assertLess(
            content.index("po-mono/en.po"),
            content.index("po-mono/it.po"),
        )
        # Discovery preview error
        with patch(
            "weblate.trans.discovery.regex_match",
            side_effect=TimeoutError,
        ):
            response = self.client.post(
                reverse("addons", kwargs=self.kw_component),
                {
                    "name": "weblate.discovery.discovery",
                    "form": "1",
                    "file_format": "po",
                    "match": r"(?P<component>[^/]*)/(?P<language>[^/]*)\.po",
                    "name_template": "{{ component|title }}",
                    "language_regex": "^(?!xx).+$",
                    "base_file_template": "",
                    "remove": True,
                },
                follow=True,
            )
        self.assertContains(
            response,
            "The regular expression used to match discovered files is too complex and took too long to evaluate.",
        )
        # Confirmation
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(
                reverse("addons", kwargs=self.kw_component),
                {
                    "name": "weblate.discovery.discovery",
                    "form": "1",
                    "match": r"(?P<component>[^/]*)/(?P<language>[^/]*)\.(?P<ext>po)",
                    "file_format": "po",
                    "name_template": "{{ component|title }}.{{ ext }}",
                    "language_regex": "^(?!xx).+$",
                    "base_file_template": "",
                    "remove": True,
                    "confirm": True,
                },
                follow=True,
            )
        self.assertContains(response, "Installed 1 add-on")

    def test_form_requires_component_template_markup(self) -> None:
        form = DiscoveryAddon.get_add_form(
            self.user,
            component=self.component,
            data={
                "file_format": "po",
                "match": r"(?P<component>[^/]*)/(?P<language>[^/]*)\.po",
                "name_template": "{{ language }}",
                "language_regex": "^(?!xx).+$",
                "base_file_template": "",
                "new_base_template": "",
                "intermediate_template": "",
                "remove": True,
                "confirm": True,
            },
        )
        self.assertIsNotNone(form)
        if form is None:
            self.fail("Expected discovery form to be created")
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors["name_template"],
            ["This template must include {{ component }}."],
        )

    def test_form_requires_component_markup_for_monolingual_paths(self) -> None:
        form = DiscoveryAddon.get_add_form(
            self.user,
            component=self.component,
            data={
                "file_format": "po-mono",
                "match": r"(?P<component>[^/]*)/(?P<language>[^/]*)\.po",
                "name_template": "{{ component }}",
                "language_regex": "^(?!xx).+$",
                "base_file_template": "{{ language }}.pot",
                "new_base_template": "{{ language }}.pot",
                "intermediate_template": "{{ language }}.po",
                "remove": True,
                "confirm": True,
            },
        )
        self.assertIsNotNone(form)
        if form is None:
            self.fail("Expected discovery form to be created")
        self.assertFalse(form.is_valid())
        self.assertIn(
            "This template must include {{ component }}.",
            form.errors["base_file_template"],
        )
        self.assertEqual(
            form.errors["new_base_template"],
            ["This template must include {{ component }}."],
        )
        self.assertEqual(
            form.errors["intermediate_template"],
            ["This template must include {{ component }}."],
        )

    def test_form_accepts_component_templates_with_colliding_probe_values(self) -> None:
        form = DiscoveryAddon.get_add_form(
            self.user,
            component=self.component,
            data={
                "file_format": "po",
                "match": r"(?P<component>[^/]*)/(?P<language>[^/]*)\.po",
                "name_template": "{{ component|last }}",
                "language_regex": "^(?!xx).+$",
                "base_file_template": "",
                "new_base_template": "",
                "intermediate_template": "",
                "remove": True,
                "confirm": True,
            },
        )
        self.assertIsNotNone(form)
        if form is None:
            self.fail("Expected discovery form to be created")
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_rejects_empty_render_without_component_markup(self) -> None:
        form = DiscoveryAddon.get_add_form(
            self.user,
            component=self.component,
            data={
                "file_format": "po",
                "match": r"(?P<component>[^/]*)/(?P<language>[^/]*)\.po",
                "name_template": '{{ language|slice:":0" }}',
                "language_regex": "^(?!xx).+$",
                "base_file_template": "",
                "new_base_template": "",
                "intermediate_template": "",
                "remove": True,
                "confirm": True,
            },
        )
        self.assertIsNotNone(form)
        if form is None:
            self.fail("Expected discovery form to be created")
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors["name_template"],
            ["This template must include {{ component }}."],
        )

    def test_ui_presets_are_not_part_of_form_configuration(self) -> None:
        form = DiscoveryAddon.get_add_form(
            self.user,
            component=self.component,
            data={
                "file_format": "po",
                "match": r"(?:(?P<path>.*/))?(?P<component>.+?)_(?P<language>[A-Za-z]{2,3}(?:[_-][A-Za-z0-9]+)*)\.(?P<extension>[^/.]+)",
                "name_template": "{{ component }}",
                "language_regex": "^[^.]+$",
                "base_file_template": "",
                "new_base_template": "",
                "intermediate_template": "",
                "remove": True,
                "confirm": True,
            },
        )
        self.assertIsNotNone(form)
        if form is None:
            self.fail("Expected discovery form to be created")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn("preset", form.fields)

        instance = form.save()
        self.assertEqual(
            instance.configuration["match"],
            r"(?:(?P<path>.*/))?(?P<component>.+?)_(?P<language>[A-Za-z]{2,3}(?:[_-][A-Za-z0-9]+)*)\.(?P<extension>[^/.]+)",
        )
        self.assertNotIn("preset", instance.configuration)

    def test_discovery_page_renders_ui_presets(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        with patch(
            "weblate.addons.forms.get_component_detected_discovery_presets",
            return_value=[],
        ) as mocked:
            response = self.client.post(
                reverse("addons", kwargs=self.kw_component),
                {"name": "weblate.discovery.discovery"},
                follow=True,
            )
        self.assertNotContains(response, 'id="addon-ui-preset"')
        self.assertContains(response, "Guided presets")
        self.assertContains(response, "Generic presets")
        self.assertContains(response, 'id="addon-discovery-presets"')
        self.assertContains(response, "row row-cols-1 row-cols-lg-2 g-3")
        self.assertContains(response, 'class="card h-100"')
        self.assertContains(
            response,
            'data-bs-target="#addon-discovery-section-generic"',
        )
        self.assertContains(response, 'data-addon-discovery-preset="filename-language"')
        self.assertContains(response, "Filename-based language variants")
        self.assertContains(response, "format not preset")
        self.assertContains(response, "Java Properties")
        self.assertContains(response, "no monolingual base")
        self.assertContains(response, "addon-ui-presets")
        self.assertNotContains(response, 'id="addon-discovery-feedback"')
        content = response.content.decode()
        self.assertRegex(
            content,
            re.compile(
                r'id="addon-discovery-section-generic"\s+'
                r'class="accordion-collapse collapse show"',
            ),
        )
        self.assertNotContains(response, 'id="addon-discovery-section-detected"')
        mocked.assert_called_once_with(self.component)

    def test_discovery_page_renders_detected_ui_presets(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        detected = [
            {
                "examples": (
                    "weblate/locale/*/LC_MESSAGES/django.po",
                    "weblate/locale/*/LC_MESSAGES/djangojs.po",
                ),
                "values": {
                    "match": r"weblate/locale/(?P<language>[^/.]*)/LC_MESSAGES/(?P<component>[^/]*)\.po",
                    "file_format": "po",
                    "name_template": "{{ component }}",
                    "language_regex": "^[^.]+$",
                    "base_file_template": "",
                    "new_base_template": "",
                    "intermediate_template": "",
                },
            }
        ]
        with patch(
            "weblate.addons.forms.get_component_detected_discovery_presets",
            return_value=detected,
        ) as mocked:
            response = self.client.post(
                reverse("addons", kwargs=self.kw_component),
                {"name": "weblate.discovery.discovery"},
                follow=True,
            )

        self.assertContains(response, "Detected from repository")
        self.assertContains(
            response,
            'data-addon-discovery-preset="detected-1"',
        )
        self.assertContains(response, 'id="addon-discovery-presets"')
        self.assertContains(
            response,
            'data-bs-target="#addon-discovery-section-detected"',
        )
        self.assertContains(
            response,
            'data-bs-target="#addon-discovery-section-generic"',
        )
        self.assertContains(
            response,
            "weblate/locale/*/LC_MESSAGES/*.po",
        )
        self.assertContains(response, "gettext PO file")
        self.assertContains(response, "no monolingual base")
        self.assertContains(
            response,
            "One folder per language",
        )
        content = response.content.decode()
        self.assertLess(
            content.index("Detected from repository"),
            content.index("Generic presets"),
        )
        self.assertRegex(
            content,
            re.compile(
                r'id="addon-discovery-section-detected"\s+'
                r'class="accordion-collapse collapse show"',
            ),
        )
        self.assertRegex(
            content,
            re.compile(
                r'id="addon-discovery-section-generic"\s+'
                r'class="accordion-collapse collapse"',
            ),
        )
        self.assertNotContains(response, "Prefills component discovery")
        mocked.assert_called_once_with(self.component)

    def test_render_detected_ui_preset_uses_component_wildcard_in_filename(
        self,
    ) -> None:
        form = DiscoveryAddon.get_add_form(self.user, component=self.component)
        self.assertIsNotNone(form)
        if form is None:
            self.fail("Expected discovery form to be created")
        form = cast("DiscoveryForm", form)

        rendered = form.render_detected_ui_preset(
            {
                "examples": (
                    "docs/news_*.md",
                    "docs/guide_*.md",
                ),
                "values": {
                    "match": r"docs/(?P<component>[^/]*)_(?P<language>[^/.]*)\.md",
                    "file_format": "markdown",
                    "name_template": "{{ component }}",
                    "language_regex": "^[^.]+$",
                    "base_file_template": "docs/{{ component }}.md",
                    "new_base_template": "",
                    "intermediate_template": "",
                },
            },
            1,
        )

        self.assertEqual(
            rendered["label"],
            "Detected: docs/*_*.md [Markdown file; monolingual base: docs/*.md]",
        )
        self.assertEqual(rendered["file_format_label"], "Markdown file")
        self.assertEqual(rendered["base_file_label"], "monolingual base: docs/*.md")
        self.assertEqual(rendered["description"], "")
        self.assertEqual(rendered["examples"], ())

    def test_get_ui_presets_lists_detected_before_generic_presets(self) -> None:
        with patch(
            "weblate.addons.forms.get_component_detected_discovery_presets",
            return_value=[
                {
                    "examples": ("docs/news_*.md", "docs/guide_*.md"),
                    "values": {
                        "match": r"docs/(?P<component>[^/]*)_(?P<language>[^/.]*)\.md",
                        "file_format": "markdown",
                        "name_template": "{{ component }}",
                        "language_regex": "^[^.]+$",
                        "base_file_template": "",
                        "new_base_template": "",
                        "intermediate_template": "",
                    },
                }
            ],
        ):
            form = DiscoveryAddon.get_add_form(self.user, component=self.component)
            self.assertIsNotNone(form)
            if form is None:
                self.fail("Expected discovery form to be created")
            form = cast("DiscoveryForm", form)
            presets = form.get_ui_presets()

        self.assertEqual(
            presets[0]["label"],
            "Detected: docs/*_*.md [Markdown file; no monolingual base]",
        )
        self.assertEqual(
            presets[1]["label"],
            "Generic preset: One folder per language [gettext PO file; no monolingual base]",
        )

    def test_detected_ui_presets_are_not_shown_when_editing_existing_addon(
        self,
    ) -> None:
        addon = DiscoveryAddon.create(
            component=self.component,
            configuration={
                "file_format": "po",
                "match": r"(?P<component>[^/]*)/(?P<language>[^/]*)\.po",
                "name_template": "{{ component|title }}",
                "language_regex": "^(?!xx).+$",
                "base_file_template": "",
                "new_base_template": "",
                "intermediate_template": "",
                "remove": True,
            },
            run=False,
        )
        with patch(
            "weblate.addons.forms.get_component_detected_discovery_presets"
        ) as mocked:
            form = addon.get_settings_form(self.user)

        self.assertIsNotNone(form)
        if form is None:
            self.fail("Expected discovery form to be created")
        form = cast("DiscoveryForm", form)
        self.assertEqual(form.detected_ui_presets, [])
        mocked.assert_not_called()

    def test_detected_ui_presets_skip_builtin_equivalent_matches(self) -> None:
        detected = [
            {
                "examples": ("*/application.po", "*/other.po"),
                "values": {
                    "match": r"(?P<language>[^/.]*)/(?P<component>[^/]*)\.po",
                    "file_format": "po",
                    "name_template": "{{ component }}",
                    "language_regex": "^[^.]+$",
                    "base_file_template": "",
                    "new_base_template": "",
                    "intermediate_template": "",
                },
            }
        ]
        with patch(
            "weblate.addons.forms.get_component_detected_discovery_presets",
            return_value=detected,
        ):
            form = DiscoveryAddon.get_add_form(self.user, component=self.component)
            self.assertIsNotNone(form)
            if form is None:
                self.fail("Expected discovery form to be created")
            form = cast("DiscoveryForm", form)
            presets = form.detected_ui_presets

        self.assertEqual(presets, [])

    def test_discovery_ui_presets_include_multiple_paths_template(self) -> None:
        presets = DiscoveryForm.get_builtin_ui_presets()
        multiple_paths = next(
            preset for preset in presets if preset["id"] == "multiple-paths"
        )
        self.assertEqual(
            multiple_paths["values"]["name_template"],
            "{{ originalHierarchy }}: {{ component }}",
        )

    def test_discovery_ui_presets_include_filename_language_file_format_clear(
        self,
    ) -> None:
        presets = DiscoveryForm.get_builtin_ui_presets()
        folder = next(
            preset for preset in presets if preset["id"] == "folder-per-language"
        )
        split_android = next(
            preset for preset in presets if preset["id"] == "split-android-strings"
        )
        filename_language = next(
            preset for preset in presets if preset["id"] == "filename-language"
        )

        self.assertEqual(folder["values"]["file_format"], "po")
        self.assertEqual(split_android["values"]["file_format"], "aresource")
        self.assertIn("file_format", filename_language["values"])
        self.assertEqual(filename_language["values"]["file_format"], "")


class ScriptsTest(TestAddonMixin, ComponentTestCase):
    def test_example_pre(self) -> None:
        self.assertTrue(ExamplePreAddon.can_install(component=self.component))
        translation = self.get_translation()
        addon = ExamplePreAddon.create(component=self.component)
        addon.pre_commit(translation, "", True)
        self.assertIn(
            os.path.join(
                self.component.full_path, f"po/{translation.language_code}.po"
            ),
            translation.addon_commit_files,
        )


class LanguageConsistencyTest(ComponentTestCase):
    CREATE_GLOSSARIES: bool = True

    def get_preview_addon(self, **kwargs) -> LanguageConsistencyAddon:
        return LanguageConsistencyAddon(
            LanguageConsistencyAddon.create_object(**kwargs)
        )

    def test_consistency_cannot_install_on_component(self) -> None:
        self.assertFalse(LanguageConsistencyAddon.can_install(component=self.component))

    def test_consistency_can_install_on_project(self) -> None:
        self.assertTrue(LanguageConsistencyAddon.can_install(project=self.project))

    def test_consistency_can_install_sitewide(self) -> None:
        self.assertTrue(LanguageConsistencyAddon.can_install())

    def test_consistency_preview_empty(self) -> None:
        preview = self.get_preview_addon(
            project=self.project
        ).get_installation_preview()

        self.assertEqual(preview.component_count, 0)
        self.assertEqual(preview.action_count, 0)
        self.assertEqual(preview.failure_count, 0)

    def test_consistency_preview_lists_actions(self) -> None:
        self.component.new_lang = "add"
        self.component.new_base = "po/hello.pot"
        self.component.save()
        self.create_ts(
            name="TS",
            new_lang="add",
            new_base="ts/cs.ts",
            project=self.project,
        )

        preview = self.get_preview_addon(
            project=self.project
        ).get_installation_preview()

        self.assertEqual(preview.component_count, 1)
        self.assertEqual(preview.action_count, 2)
        self.assertEqual(preview.failure_count, 0)
        self.assertEqual(preview.components[0].component.name, "TS")
        self.assertEqual(
            [
                (item.language.code, item.filename)
                for item in preview.components[0].actions
            ],
            [("de", "ts/de.ts"), ("it", "ts/it.ts")],
        )

    def test_consistency_preview_lists_failures(self) -> None:
        self.component.new_lang = "add"
        self.component.new_base = "po/hello.pot"
        self.component.save()
        component = self.create_ts(
            name="TS",
            new_lang="add",
            new_base="ts/cs.ts",
            project=self.project,
        )
        component.language_regex = "^it$"
        component.save(update_fields=["language_regex"])

        preview = self.get_preview_addon(
            project=self.project
        ).get_installation_preview()

        self.assertEqual(preview.component_count, 1)
        self.assertEqual(preview.action_count, 1)
        self.assertEqual(preview.failure_count, 1)
        self.assertEqual(
            [
                (item.language.code, item.filename)
                for item in preview.components[0].actions
            ],
            [("it", "ts/it.ts")],
        )
        self.assertEqual(preview.components[0].failures[0].language.code, "de")
        self.assertEqual(
            preview.components[0].failures[0].reason,
            "The given language is filtered by the language filter.",
        )

    def test_consistency_preview_is_truncated(self) -> None:
        self.component.new_lang = "add"
        self.component.new_base = "po/hello.pot"
        self.component.save()
        self.create_ts(
            name="TS",
            slug="ts",
            new_lang="add",
            new_base="ts/cs.ts",
            project=self.project,
        )
        self.create_ts(
            name="TS 2",
            slug="ts-2",
            new_lang="add",
            new_base="ts/cs.ts",
            project=self.project,
        )

        with (
            patch.object(LanguageConsistencyAddon, "preview_component_limit", 20),
            patch.object(LanguageConsistencyAddon, "preview_entry_limit", 2),
        ):
            preview = self.get_preview_addon(
                project=self.project
            ).get_installation_preview()

        self.assertEqual(preview.component_count, 1)
        self.assertEqual(preview.entry_count, 2)
        self.assertTrue(preview.is_truncated)

    def test_consistency_sitewide_preview_stops_after_project_limit(self) -> None:
        for index in range(3):
            self.create_ts(
                name=f"TS {index}",
                slug=f"ts-{index}",
                project=self.create_project(
                    slug=f"project-{index}", name=f"Project {index}"
                ),
            )

        with patch.object(LanguageConsistencyAddon, "preview_project_limit", 2):
            preview = self.get_preview_addon().get_installation_preview()

        self.assertEqual(preview.component_count, 0)
        self.assertEqual(preview.entry_count, 0)
        self.assertTrue(preview.is_truncated)

    def test_consistency_sitewide_preview_builds_language_cache_once(self) -> None:
        for index in range(2):
            self.create_ts(
                name=f"TS {index}",
                slug=f"ts-cache-{index}",
                project=self.create_project(
                    slug=f"project-cache-{index}", name=f"Project cache {index}"
                ),
            )

        with patch(
            "weblate.addons.consistency.Language.objects.build_fuzzy_get_cache",
            wraps=Language.objects.build_fuzzy_get_cache,
        ) as build_cache:
            self.get_preview_addon().get_installation_preview()

        self.assertEqual(build_cache.call_count, 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_consistency_post_add_not_skipped(self) -> None:
        """Project-level consistency addon must not be skipped on post_add."""
        LanguageConsistencyAddon.create(project=self.project)
        translation = self.component.translation_set.get(language__code="cs")

        self.component.drop_addons_cache()

        before = AddonActivityLog.objects.count()
        handle_addon_event(
            AddonEvent.EVENT_POST_ADD,
            "post_add",
            (translation,),
            translation=translation,
        )
        after = AddonActivityLog.objects.count()

        self.assertEqual(after - before, 1)

    def test_consistency_daily_project_level(self) -> None:
        """Test consistency addon at project level runs once via daily_addons."""
        self.create_po(new_base="po/project.pot", project=self.project, name="Second")
        LanguageConsistencyAddon.create(project=self.project)

        before = AddonActivityLog.objects.count()
        daily_addons(modulo=False)
        after = AddonActivityLog.objects.count()

        # Project-scope addon should produce exactly one activity log entry,
        # not one per component
        self.assertEqual(after - before, 1)

    def test_consistency_daily_category_level(self) -> None:
        """Test consistency addon at category level runs once via daily_addons."""
        category = self.create_category(self.project)
        self.component.category = category
        self.component.save()
        self.create_po(new_base="po/project.pot", project=self.project, name="Second")
        LanguageConsistencyAddon.create(category=category)

        before = AddonActivityLog.objects.count()
        daily_addons(modulo=False)
        after = AddonActivityLog.objects.count()

        self.assertEqual(after - before, 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_consistency_post_configure_category(self) -> None:
        """Test post_configure_run fires daily event for category addons."""
        category = self.create_category(self.project)
        self.component.category = category
        self.component.save()

        before = AddonActivityLog.objects.count()
        LanguageConsistencyAddon.create(category=category)
        after = AddonActivityLog.objects.count()

        self.assertEqual(after - before, 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_consistency_category_only_affects_category_components(self) -> None:
        """
        Category-level consistency addon should only affect components in that category.

        Hierarchy:
          top_category/
            comp_top (self.component) — PO, has cs + de + it + en (source)
            nested_category/
              comp_nested — TS, has cs + en (source) only
          outside_component — TS, has cs + en (source) only, no category
        """
        top_category = self.create_category(self.project)
        nested_category = Category.objects.create(
            name="Nested",
            slug="nested",
            project=self.project,
            category=top_category,
        )

        # comp_top: PO component in top_category
        self.component.new_lang = "add"
        self.component.new_base = "po/hello.pot"
        self.component.category = top_category
        self.component.save()

        # comp_nested: TS component in nested_category (fewer languages than comp_top)
        comp_nested = self.create_ts(
            name="Nested TS",
            new_lang="add",
            new_base="ts/cs.ts",
            project=self.project,
        )
        comp_nested.category = nested_category
        comp_nested.save()

        # outside_component: TS component with no category
        outside_component = self.create_ts(
            name="Outside TS",
            new_lang="add",
            new_base="ts/cs.ts",
            project=self.project,
        )

        # Snapshot languages before installing addon
        nested_langs_before = set(
            Translation.objects.filter(component=comp_nested).values_list(
                "language__code", flat=True
            )
        )
        outside_langs_before = set(
            Translation.objects.filter(component=outside_component).values_list(
                "language__code", flat=True
            )
        )

        # Install consistency addon at top_category level
        LanguageConsistencyAddon.create(category=top_category)

        # comp_nested should gain languages from comp_top (they share the category tree)
        nested_langs_after = set(
            Translation.objects.filter(component=comp_nested).values_list(
                "language__code", flat=True
            )
        )
        top_langs = set(
            Translation.objects.filter(component=self.component).values_list(
                "language__code", flat=True
            )
        )
        self.assertEqual(nested_langs_after, top_langs)
        self.assertTrue(nested_langs_after - nested_langs_before)

        # outside_component should be completely untouched
        outside_langs_after = set(
            Translation.objects.filter(component=outside_component).values_list(
                "language__code", flat=True
            )
        )
        self.assertEqual(outside_langs_after, outside_langs_before)

        # Part 2: Simulate post_add by calling the task directly with a
        # single language that is missing from comp_nested, and verify it
        # propagates within the category but NOT to outside_component.
        addon_instance = Addon.objects.get(name="weblate.consistency.languages")
        new_lang = Language.objects.get(code="it")

        # Remove "it" from comp_nested so we can verify it gets re-added
        Translation.objects.filter(component=comp_nested, language=new_lang).delete()

        outside_langs_before_post_add = set(
            Translation.objects.filter(component=outside_component).values_list(
                "language__code", flat=True
            )
        )

        # Call the task directly (as post_add would, bypassing delay_on_commit)
        language_consistency(
            addon_instance.id,
            [new_lang.id],
            category_id=top_category.pk,
        )

        # comp_nested should have gained "it" back
        nested_langs_after_post_add = set(
            Translation.objects.filter(component=comp_nested).values_list(
                "language__code", flat=True
            )
        )
        self.assertIn("it", nested_langs_after_post_add)

        # outside_component still untouched
        outside_langs_final = set(
            Translation.objects.filter(component=outside_component).values_list(
                "language__code", flat=True
            )
        )
        self.assertEqual(outside_langs_final, outside_langs_before_post_add)

    def test_consistency_daily_sitewide(self) -> None:
        """Test sitewide consistency addon runs once per project."""
        project_b = self.create_project(name="Project B", slug="project-b")
        self.create_po(new_base="po/project.pot", project=project_b, name="Comp B")
        LanguageConsistencyAddon.create()

        before = AddonActivityLog.objects.count()
        daily_addons(modulo=False)
        after = AddonActivityLog.objects.count()

        self.assertEqual(after - before, 2)

    def test_language_consistency(self) -> None:
        self.component.new_lang = "add"
        self.component.new_base = "po/hello.pot"
        self.component.save()
        ts_component = self.create_ts(
            name="TS",
            new_lang="add",
            new_base="ts/cs.ts",
            project=self.component.project,
        )
        self.assertEqual(Translation.objects.count(), 10)

        # Installation should make languages consistent
        addon = LanguageConsistencyAddon.create(project=self.project)
        self.component.drop_addons_cache()
        self.assertEqual(Translation.objects.count(), 12)

        # check that activity is correctly logged
        activity_logs = (
            AddonActivityLog.objects.filter(addon__name=addon.name)
            .order_by("created")
            .first()
        )
        self.assertIn(
            f"{ts_component.full_slug}: Add missing languages: Added German",
            activity_logs.details["result"],
        )
        self.assertIn(
            f"{ts_component.full_slug}: Add missing languages: Added Italian",
            activity_logs.details["result"],
        )

        # Add one language
        language = Language.objects.get(code="af")
        self.component.add_new_language(language, None)
        self.assertEqual(
            Translation.objects.filter(
                language=language, component__project=self.component.project
            ).count(),
            3,
        )

        # Trigger post update signal, should do nothing
        addon.post_update(self.component, "", False)
        self.assertEqual(Translation.objects.count(), 15)

    def test_language_consistency_missing_activity_log_after_component_delete(
        self,
    ) -> None:
        self.component.new_lang = "add"
        self.component.new_base = "po/hello.pot"
        self.component.save()
        ts_component = self.create_ts(
            name="TS",
            new_lang="add",
            new_base="ts/cs.ts",
            project=self.component.project,
        )

        addon = LanguageConsistencyAddon.create(project=self.project)
        activity_log = AddonActivityLog.objects.create(
            addon=addon.instance,
            component=self.component,
            event=AddonEvent.EVENT_POST_ADD,
            pending=True,
        )

        self.component.delete()

        language_consistency(
            addon.instance.id,
            [
                Language.objects.get(code="de").id,
                Language.objects.get(code="it").id,
            ],
            project_id=self.project.id,
            activity_log_id=activity_log.id,
        )

        self.assertSetEqual(
            set(
                Translation.objects.filter(component=ts_component).values_list(
                    "language__code", flat=True
                )
            ),
            {"cs", "de", "en", "it"},
        )


class GitSquashAddonTest(ViewTestCase):
    def create(self, mode: str, sitewide: bool = False):
        self.assertTrue(GitSquashAddon.can_install(component=self.component))
        component = None if sitewide else self.component
        if sitewide:
            # This is not needed in real life as installation will happen
            # in a different request so local caching does not apply
            self.component.drop_addons_cache()
        return GitSquashAddon.create(
            component=component, configuration={"squash": mode}
        )

    def edit(self, *, repeated: bool = False) -> None:
        for lang in ("cs", "de"):
            self.change_unit("Nazdar svete!\n", "Hello, world!\n", language=lang)
            self.component.commit_pending("test", None)
            self.change_unit(
                "Diky za pouziti Weblate.",
                "Thank you for using Weblate.",
                lang,
                user=self.anotheruser,
            )
            self.component.commit_pending("test", None)

        # Add commit on the same unit, that is touched by anotheruser
        if repeated:
            self.change_unit(
                "Danke für die Benutzung von Weblate.",
                "Thank you for using Weblate.",
                language="de",
            )
            self.component.commit_pending("test", None)

    def test_squash(
        self,
        mode: str = "all",
        expected: int = 1,
        *,
        sitewide: bool = False,
        repeated: bool = False,
    ) -> None:
        addon = self.create(mode=mode, sitewide=sitewide)
        repo = self.component.repository
        self.assertEqual(repo.count_outgoing(), 0)
        # Test no-op behavior
        addon.post_commit(self.component, True)
        # Make some changes
        self.edit(repeated=repeated)
        self.assertEqual(repo.count_outgoing(), expected)

    def test_squash_sitewide(self) -> None:
        self.test_squash(sitewide=True)

    def test_languages(self) -> None:
        self.test_squash("language", 2)

    def test_files(self) -> None:
        self.test_squash("file", 2)

    def test_mo(self) -> None:
        GenerateMoAddon.create(component=self.component)
        self.test_squash("file", 3)

    def test_author(self) -> None:
        self.test_squash("author", 2)
        # Add commit which can not be squashed
        self.change_unit("Diky za pouzivani Weblate.", "Thank you for using Weblate.")
        self.component.commit_pending("test", None)
        self.assertEqual(self.component.repository.count_outgoing(), 3)

    def test_multiple_authors_on_same_file(self) -> None:
        self.test_squash("author", 3, repeated=True)

    def test_commit_message(self) -> None:
        commit_message = "Squashed commit message"
        GitSquashAddon.create(
            component=self.component,
            configuration={"squash": "all", "commit_message": commit_message},
        )

        self.edit()

        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn(commit_message, commit)
        self.assertEqual(self.component.repository.count_outgoing(), 1)

    def test_append_trailers(self) -> None:
        GitSquashAddon.create(
            component=self.component,
            configuration={"squash": "all", "append_trailers": True},
        )

        self.edit()

        commit = self.component.repository.show(self.component.repository.last_revision)

        expected_trailers = (
            "    Translate-URL: http://example.com/projects/test/test/cs/\n"
            "    Translate-URL: http://example.com/projects/test/test/de/\n"
            "    Translation: Test/Test\n"
        )
        self.assertIn(expected_trailers, commit)
        self.assertEqual(self.component.repository.count_outgoing(), 1)


class TestRemoval(ComponentTestCase):
    def install(
        self,
        sitewide: bool = False,
        project: bool = False,
        category: Category | None = None,
    ):
        self.assertTrue(RemoveComments.can_install(component=self.component))
        self.assertTrue(RemoveSuggestions.can_install(component=self.component))
        addon_component: Component | None = None
        addon_project: Project | None = None
        addon_category: Category | None = None
        if sitewide:
            pass
        elif project:
            addon_project = self.project
        elif category is not None:
            addon_category = category
        else:
            addon_component = self.component
        return (
            RemoveSuggestions.create(
                configuration={"age": 7},
                component=addon_component,
                project=addon_project,
                category=addon_category,
            ),
            RemoveComments.create(
                configuration={"age": 7},
                component=addon_component,
                project=addon_project,
                category=addon_category,
            ),
        )

    def assert_count(self, comments=0, suggestions=0) -> None:
        self.assertEqual(Comment.objects.count(), comments)
        self.assertEqual(Suggestion.objects.count(), suggestions)

    def test_noop(self) -> None:
        suggestions, comments = self.install()
        suggestions.daily(self.component)
        comments.daily(self.component)
        self.assert_count()

    def add_content(self) -> None:
        unit = self.get_unit()
        unit.comment_set.create(user=None, comment="comment")
        unit.suggestion_set.create(user=None, target="suggestion")

    def test_current(self) -> None:
        suggestions, comments = self.install()
        self.add_content()
        suggestions.daily(self.component)
        comments.daily(self.component)
        self.assert_count(1, 1)

    @staticmethod
    def age_content() -> None:
        old = timezone.now() - timedelta(days=60)
        Comment.objects.all().update(timestamp=old)
        Suggestion.objects.all().update(timestamp=old)

    def test_old(self) -> None:
        suggestions, comments = self.install()
        self.add_content()
        self.age_content()
        suggestions.daily(self.component)
        comments.daily(self.component)
        self.assert_count()

    def test_votes(self) -> None:
        suggestions, comments = self.install()
        self.add_content()
        self.age_content()
        Vote.objects.create(
            user=self.user, suggestion=Suggestion.objects.all()[0], value=1
        )
        suggestions.daily(self.component)
        comments.daily(self.component)
        self.assert_count(suggestions=1)

    def test_daily(self) -> None:
        self.install()
        self.add_content()
        self.age_content()
        daily_addons()
        # Ensure the add-on is executed
        daily_addons(modulo=False)
        self.assert_count()

    def test_daily_project(self) -> None:
        self.install(project=True)
        self.add_content()
        self.age_content()
        daily_addons()
        daily_addons(modulo=False)
        self.assert_count()

    def test_daily_sitewide(self) -> None:
        self.install(sitewide=True)
        self.add_content()
        self.age_content()
        daily_addons()
        # Ensure the add-on is executed
        daily_addons(modulo=False)
        self.assert_count()

    def test_daily_category(self) -> None:
        category = self.create_category(self.project)
        self.component.category = category
        self.component.save()
        self.install(category=category)
        self.add_content()
        self.age_content()
        daily_addons()
        daily_addons(modulo=False)
        self.assert_count()

    def test_old_category_direct(self) -> None:
        """Test removal addon daily method works with category kwarg."""
        category = self.create_category(self.project)
        self.component.category = category
        self.component.save()
        suggestions, comments = self.install(category=category)
        self.add_content()
        self.age_content()
        suggestions.daily(category=category)
        comments.daily(category=category)
        self.assert_count()


class AutoTranslateAddonTest(ComponentTestCase):
    def test_auto(self) -> None:
        self.assertTrue(AutoTranslateAddon.can_install(component=self.component))
        addon = AutoTranslateAddon.create(
            component=self.component,
            configuration={
                "component": "",
                "q": "state:<translated",
                "auto_source": "mt",
                "engines": [],
                "threshold": 80,
                "mode": "translate",
            },
        )
        with patch(
            "weblate.addons.autotranslate.auto_translate_component.delay_on_commit"
        ) as mocked:
            addon.component_update(self.component)

        mocked.assert_called_once_with(
            self.component.pk,
            mode="translate",
            q="state:<translated",
            auto_source="mt",
            engines=[],
            threshold=80,
            source_component_id=None,
        )

    def test_auto_change_event_normalizes_blank_component(self) -> None:
        addon = AutoTranslateAddon.create(
            project=self.project,
            configuration={
                "component": "",
                "q": "state:<translated",
                "auto_source": "others",
                "engines": [],
                "threshold": 80,
                "mode": "translate",
            },
        )

        with patch(
            "weblate.addons.autotranslate.auto_translate.delay_on_commit"
        ) as mocked:
            addon.trigger_autotranslate(
                user_id=self.user.id,
                translation_id=self.translation.id,
                unit_ids=[1, 2],
            )

        mocked.assert_called_once_with(
            mode="translate",
            q="state:<translated",
            auto_source="others",
            engines=[],
            threshold=80,
            source_component_id=None,
            user_id=self.user.id,
            unit_ids=[1, 2],
            translation_id=self.translation.id,
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_auto_change_event(self) -> None:
        component_1 = self.create_po_new_base(name="Component 1", project=self.project)
        component_1.allow_translation_propagation = False
        component_1.save()
        component_2 = self.create_po_new_base(name="Component 2", project=self.project)
        component_2.allow_translation_propagation = False
        component_2.save()
        AutoTranslateAddon.create(
            project=self.project,
            configuration={
                "component": None,
                "q": "has:comment AND state:<translated",
                "auto_source": "others",
                "engines": ["weblate"],
                "threshold": 80,
                "mode": "translate",
            },
        )
        for component in (component_1, component_2):
            component.source_translation.add_unit(
                None, context="", source="one", target=None, author=self.user
            )

        translation_1 = component_1.translation_set.get(language_code="cs")
        unit_1 = translation_1.unit_set.get(source="one")
        unit_1.translate(self.user, "jeden", STATE_TRANSLATED)

        translation_2 = component_2.translation_set.get(language_code="cs")
        unit_2 = translation_2.unit_set.get(source="one")
        Comment.objects.create(unit=unit_2, comment="Foo")
        change = unit_2.change_set.latest("timestamp")

        addon_change.run([change.pk])

        unit_2 = translation_2.unit_set.get(source="one")
        self.assertEqual(unit_2.target, "jeden")


class AddonConfigurationUnitTest(SimpleTestCase):
    def test_base_addon_configuration_normalizes_stored_values(self) -> None:
        addon = TypedConfigAddon.__new__(TypedConfigAddon)
        addon.instance = SimpleNamespace(configuration={"count": "5"})

        self.assertEqual(addon.stored_configuration["count"], "5")
        self.assertEqual(addon.get_configuration(), {"count": 5})
        self.assertEqual(addon.configuration, {"count": 5})

    def test_base_addon_configuration_defaults_missing_legacy_values(self) -> None:
        addon = TypedConfigAddon.__new__(TypedConfigAddon)
        addon.instance = SimpleNamespace(configuration={})

        self.assertEqual(addon.get_configuration(), {"count": 0})

    def test_trigger_autotranslate_normalizes_blank_component_for_translation_task(
        self,
    ) -> None:
        addon = AutoTranslateAddon.__new__(AutoTranslateAddon)
        addon.instance = SimpleNamespace(
            configuration={
                "component": "",
                "q": "state:<translated",
                "auto_source": "others",
                "engines": [],
                "threshold": 80,
                "mode": "translate",
            }
        )

        with patch(
            "weblate.addons.autotranslate.auto_translate.delay_on_commit"
        ) as mocked:
            addon.trigger_autotranslate(user_id=1, translation_id=2, unit_ids=[3, 4])

        mocked.assert_called_once_with(
            mode="translate",
            q="state:<translated",
            auto_source="others",
            engines=[],
            threshold=80,
            source_component_id=None,
            user_id=1,
            unit_ids=[3, 4],
            translation_id=2,
        )

    def test_trigger_autotranslate_normalizes_blank_component_for_component_task(
        self,
    ) -> None:
        addon = AutoTranslateAddon.__new__(AutoTranslateAddon)
        addon.instance = SimpleNamespace(
            configuration={
                "component": "",
                "q": "state:<translated",
                "auto_source": "mt",
                "engines": [],
                "threshold": 80,
                "mode": "translate",
            }
        )

        with patch(
            "weblate.addons.autotranslate.auto_translate_component.delay_on_commit"
        ) as mocked:
            addon.trigger_autotranslate(component=SimpleNamespace(pk=123))

        mocked.assert_called_once_with(
            123,
            mode="translate",
            q="state:<translated",
            auto_source="mt",
            engines=[],
            threshold=80,
            source_component_id=None,
        )

    def test_get_configuration_normalizes_legacy_filter_configuration(self) -> None:
        addon = AutoTranslateAddon.__new__(AutoTranslateAddon)
        addon.instance = SimpleNamespace(
            configuration={
                "auto_source": "others",
                "filter_type": "comments",
                "mode": "translate",
            }
        )

        self.assertEqual(
            addon.get_configuration(),
            {
                "auto_source": "others",
                "component": None,
                "engines": [],
                "mode": "translate",
                "q": "has:comment",
                "threshold": 80,
            },
        )

    def test_get_settings_form_data_normalizes_legacy_filter_configuration(
        self,
    ) -> None:
        addon = AutoTranslateAddon.__new__(AutoTranslateAddon)
        addon.instance = SimpleNamespace(
            configuration={
                "auto_source": "others",
                "filter_type": "comments",
                "mode": "translate",
            }
        )

        self.assertEqual(
            addon.get_settings_form_data(),
            {
                "auto_source": "others",
                "component": None,
                "engines": [],
                "mode": "translate",
                "q": "has:comment",
                "threshold": 80,
            },
        )

    def test_get_configuration_ignores_component_for_mt(self) -> None:
        addon = AutoTranslateAddon.__new__(AutoTranslateAddon)
        addon.instance = SimpleNamespace(
            configuration={
                "component": 123,
                "q": "state:<translated",
                "auto_source": "mt",
                "engines": ["weblate"],
                "threshold": 80,
                "mode": "translate",
            }
        )

        self.assertEqual(
            addon.get_configuration(),
            {
                "auto_source": "mt",
                "component": None,
                "engines": ["weblate"],
                "mode": "translate",
                "q": "state:<translated",
                "threshold": 80,
            },
        )

    def test_get_configuration_ignores_threshold_for_others(self) -> None:
        addon = AutoTranslateAddon.__new__(AutoTranslateAddon)
        addon.instance = SimpleNamespace(
            configuration={
                "component": "",
                "q": "state:<translated",
                "auto_source": "others",
                "threshold": 50,
                "mode": "translate",
            }
        )

        self.assertEqual(
            addon.get_configuration(),
            {
                "auto_source": "others",
                "component": None,
                "engines": [],
                "mode": "translate",
                "q": "state:<translated",
                "threshold": DEFAULT_AUTO_TRANSLATE_THRESHOLD,
            },
        )

    def test_generate_file_form_serializes_configuration(self) -> None:
        addon = GenerateFileAddon.__new__(GenerateFileAddon)
        addon.instance = SimpleNamespace(component=None, project=None)
        form = GenerateForm(
            None,
            addon,
            data={
                "filename": "stats-{{ language_code }}.txt",
                "template": "{{ language_code }}",
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.serialize_form(),
            {
                "filename": "stats-{{ language_code }}.txt",
                "template": "{{ language_code }}",
            },
        )

    def test_generate_file_runtime_configuration_is_normalized(self) -> None:
        addon = GenerateFileAddon.__new__(GenerateFileAddon)
        addon.instance = SimpleNamespace(
            configuration={
                "filename": "stats-{{ language_code }}.txt",
                "template": "{{ language_code }}",
            }
        )

        self.assertEqual(
            addon.configuration,
            {
                "filename": "stats-{{ language_code }}.txt",
                "template": "{{ language_code }}",
            },
        )

    def test_properties_sort_form_serializes_configuration(self) -> None:
        addon = PropertiesSortAddon.__new__(PropertiesSortAddon)
        addon.instance = SimpleNamespace()
        form = PropertiesSortAddonForm(
            None,
            addon,
            data={"case_sensitive": "on"},
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.serialize_form(), {"case_sensitive": True})

    def test_properties_sort_configuration_defaults_missing_values(self) -> None:
        addon = PropertiesSortAddon.__new__(PropertiesSortAddon)
        addon.instance = SimpleNamespace(configuration={})

        self.assertEqual(addon.get_configuration(), {"case_sensitive": False})

    def test_git_squash_form_serializes_configuration(self) -> None:
        addon = GitSquashAddon.__new__(GitSquashAddon)
        addon.instance = SimpleNamespace()
        form = GitSquashForm(
            None,
            addon,
            data={
                "squash": "language",
                "append_trailers": "",
                "commit_message": "Squashed translations",
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.serialize_form(),
            {
                "squash": "language",
                "append_trailers": False,
                "commit_message": "Squashed translations",
            },
        )

    def test_git_squash_configuration_defaults_missing_values(self) -> None:
        addon = GitSquashAddon.__new__(GitSquashAddon)
        addon.instance = SimpleNamespace(configuration={})

        self.assertEqual(
            addon.get_configuration(),
            {
                "squash": "all",
                "append_trailers": True,
                "commit_message": "",
            },
        )


class BulkEditAddonTest(ViewTestCase):
    def test_bulk(self) -> None:
        label = self.project.label_set.create(name="test", color="navy")
        self.assertTrue(BulkEditAddon.can_install(component=self.component))
        addon = BulkEditAddon.create(
            component=self.component,
            configuration={
                "q": "state:translated",
                "state": -1,
                "add_labels": ["test"],
                "remove_labels": [],
                "add_flags": "",
                "remove_flags": "",
            },
        )
        addon.component_update(self.component)
        self.assertEqual(label.unit_set.count(), 1)

    def test_create(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        label = self.project.label_set.create(name="test", color="navy")
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.flags.bulk"},
            follow=True,
        )
        self.assertContains(response, "Configure add-on")
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.flags.bulk",
                "form": "1",
                "q": "state:translated",
                "state": -1,
                "add_labels": [label.pk],
                "remove_labels": [],
                "add_flags": "",
                "remove_flags": "",
            },
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")


class CDNJSAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_json_mono()

    @override_settings(LOCALIZE_CDN_URL=None)
    def test_noconfigured(self) -> None:
        self.assertFalse(CDNJSAddon.can_install(component=self.component))

    @tempdir_setting("LOCALIZE_CDN_PATH")
    @override_settings(LOCALIZE_CDN_URL="http://localhost/")
    def test_cdn(self) -> None:
        self.make_manager()
        self.assertTrue(CDNJSAddon.can_install(component=self.component))

        # Install addon
        addon = CDNJSAddon.create(
            component=self.component,
            configuration={
                "threshold": 0,
                "files": "",
                "cookie_name": "django_languages",
                "css_selector": ".l10n",
            },
        )

        # Check generated files
        self.assertTrue(os.path.isdir(addon.cdn_path("")))
        jsname = addon.cdn_path("weblate.js")
        self.assertTrue(os.path.isfile(jsname))

        # Translate some content
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.component.commit_pending("test", None)

        # Check translation files
        content = Path(jsname).read_text(encoding="utf-8")
        self.assertIn(".l10n", content)
        self.assertIn('"cs"', content)
        self.assertTrue(os.path.isfile(addon.cdn_path("cs.json")))

        # Configuration
        response = self.client.get(addon.instance.get_absolute_url())
        self.assertContains(response, addon.cdn_js_url)

    @tempdir_setting("LOCALIZE_CDN_PATH")
    @override_settings(LOCALIZE_CDN_URL="http://localhost/")
    def test_extract(self) -> None:
        self.make_manager()
        self.assertTrue(CDNJSAddon.can_install(component=self.component))
        self.assertEqual(
            Unit.objects.filter(translation__component=self.component).count(), 8
        )

        # Install addon
        CDNJSAddon.create(
            component=self.component,
            configuration={
                "threshold": 0,
                "files": "html/en.html",
                "cookie_name": "django_languages",
                "css_selector": "*",
            },
        )

        # Verify strings
        self.assertEqual(
            Unit.objects.filter(translation__component=self.component).count(), 14
        )

    @tempdir_setting("LOCALIZE_CDN_PATH")
    @override_settings(LOCALIZE_CDN_URL="http://localhost/")
    def test_extract_broken(self) -> None:
        self.make_manager()
        self.assertTrue(CDNJSAddon.can_install(component=self.component))
        self.assertEqual(
            Unit.objects.filter(translation__component=self.component).count(), 8
        )

        # Install addon
        CDNJSAddon.create(
            component=self.component,
            configuration={
                "threshold": 0,
                "files": "html/missing.html",
                "cookie_name": "django_languages",
                "css_selector": "*",
            },
        )

        # Verify strings
        self.assertEqual(
            Unit.objects.filter(translation__component=self.component).count(), 8
        )
        # The error should be there
        self.assertTrue(self.component.alert_set.filter(name="CDNAddonError").exists())

    @tempdir_setting("LOCALIZE_CDN_PATH")
    @override_settings(LOCALIZE_CDN_URL="http://localhost/")
    def test_extract_refuses_outside_repository(self) -> None:
        self.make_manager()
        self.assertTrue(CDNJSAddon.can_install(component=self.component))
        self.assertEqual(
            Unit.objects.filter(translation__component=self.component).count(), 8
        )

        CDNJSAddon.create(
            component=self.component,
            configuration={
                "threshold": 0,
                "files": "../../../../../etc/hosts",
                "cookie_name": "django_languages",
                "css_selector": "*",
            },
        )

        self.assertEqual(
            Unit.objects.filter(translation__component=self.component).count(), 8
        )
        alert = self.component.alert_set.get(name="CDNAddonError")
        self.assertIn("parent directory", alert.details["occurrences"][0]["error"])

    @tempdir_setting("LOCALIZE_CDN_PATH")
    @override_settings(
        LOCALIZE_CDN_URL="http://localhost/", ALLOWED_ASSET_DOMAINS=[".allowed.com"]
    )
    def test_extract_refuses_disallowed_remote_domain(self) -> None:
        self.make_manager()
        self.assertTrue(CDNJSAddon.can_install(component=self.component))
        self.assertEqual(
            Unit.objects.filter(translation__component=self.component).count(), 8
        )

        CDNJSAddon.create(
            component=self.component,
            configuration={
                "threshold": 0,
                "files": "https://blocked.example.com/messages.html",
                "cookie_name": "django_languages",
                "css_selector": "*",
            },
        )

        self.assertEqual(
            Unit.objects.filter(translation__component=self.component).count(), 8
        )
        alert = self.component.alert_set.get(name="CDNAddonError")
        self.assertIn("domain is not allowed", alert.details["occurrences"][0]["error"])

    @responses.activate
    @tempdir_setting("LOCALIZE_CDN_PATH")
    @override_settings(
        LOCALIZE_CDN_URL="http://localhost/", ALLOWED_ASSET_DOMAINS=[".allowed.com"]
    )
    def test_extract_refuses_disallowed_remote_redirect_domain(self) -> None:
        self.make_manager()
        self.assertTrue(CDNJSAddon.can_install(component=self.component))
        self.assertEqual(
            Unit.objects.filter(translation__component=self.component).count(), 8
        )

        responses.add(
            responses.GET,
            "https://cdn.allowed.com/messages.html",
            status=302,
            headers={"Location": "https://blocked.example.com/messages.html"},
        )
        responses.add(
            responses.GET,
            "https://blocked.example.com/messages.html",
            status=200,
            body="<html><body><div class='l10n'>Blocked</div></body></html>",
        )

        CDNJSAddon.create(
            component=self.component,
            configuration={
                "threshold": 0,
                "files": "https://cdn.allowed.com/messages.html",
                "cookie_name": "django_languages",
                "css_selector": "*",
            },
        )

        self.assertEqual(
            Unit.objects.filter(translation__component=self.component).count(), 8
        )
        alert = self.component.alert_set.get(name="CDNAddonError")
        self.assertIn("domain is not allowed", alert.details["occurrences"][0]["error"])
        self.assertNotIn(
            "https://blocked.example.com/messages.html",
            [call.request.url for call in responses.calls],
        )


class SiteWideAddonsTest(ViewTestCase):
    def create_component(self):
        return self.create_java()

    def test_gettext(self) -> None:
        MsgmergeAddon.create()
        # This is not needed in real life as installation will happen
        # in a different request so local caching does not apply
        self.component.drop_addons_cache()
        rev = self.component.repository.last_revision

        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.get_translation().commit_pending("test", None)

        self.assertNotEqual(rev, self.component.repository.last_revision)


class TargetChangeAddonTest(ComponentTestCase):
    def create_component(self):
        return self.create_json_mono(suffix="mono-sync")

    def update_unit_from_repo(self) -> Unit:
        unit = self.get_unit("Hello, world!\n")
        unit.translate(self.user, ["Nazdar svete!"], STATE_TRANSLATED)

        request = self.get_request()
        self.component.do_push(request)

        translation = self.get_translation("cs")
        updated_json_content = """
        {
            "hello": "Nazdar svete! edit",
            "orangutan": "",
            "try": "",
            "thanks": ""
        }
        """

        # edit the translation on remote repo
        with tempfile.TemporaryDirectory() as tempdir:
            repo = self.component.repository.__class__.clone(
                self.format_local_path(self.git_repo_path),
                tempdir,
                "main",
                component=self.component,
            )
            translation_remote_file = os.path.join(tempdir, translation.filename)
            Path(translation_remote_file).write_text(
                updated_json_content, encoding="utf-8"
            )
            with repo.lock:
                repo.set_committer("Toast", "toast@example.net")
                repo.commit(
                    "Simulate commit directly into remote repo",
                    "Toast <test@example.net>",
                    files=[translation_remote_file],
                )
                repo.push("")

        # pull changes from remote, check unit has been updated
        translation.do_update(request)
        unit.refresh_from_db()
        self.assertEqual(unit.target, "Nazdar svete! edit")
        return unit

    def test_fuzzy_string_from_repo(self) -> None:
        self.assertTrue(TargetRepoUpdateAddon.can_install(component=self.component))
        TargetRepoUpdateAddon.create(component=self.component)
        unit = self.update_unit_from_repo()
        self.assertEqual(unit.state, STATE_NEEDS_REWRITING)

    def test_non_fuzzy_string_from_repo(self) -> None:
        unit = self.update_unit_from_repo()
        self.assertEqual(unit.state, STATE_TRANSLATED)


class TasksTest(TestCase):
    def test_cleanup_addon_activity_log(self) -> None:
        cleanup_addon_activity_log()


class BaseWebhookTests:
    addon_configuration: ClassVar[dict]
    WEBHOOK_CLS: type[BaseAddon]
    WEBHOOK_URL: str

    def setUp(self) -> None:
        super().setUp()
        self.reset_addon_configuration()

    def reset_addon_configuration(self) -> None:
        self.addon_configuration["events"] = [str(ActionEvents.NEW)]

    def count_requests(self) -> int:
        return len(responses.calls)

    def reset_calls(self) -> None:
        responses.calls.reset()

    def do_translation_added_test(
        self, response_code=None, expected_calls: int = 1, **responses_kwargs
    ) -> None:
        """Install addon, edit unit and assert outgoing calls."""
        self.WEBHOOK_CLS.create(configuration=self.addon_configuration)
        if response_code:
            responses_kwargs |= {"status": response_code}
        responses.add(responses.POST, self.WEBHOOK_URL, **responses_kwargs)

        self.edit_unit(
            "Hello, world!\n", "Nazdar svete!\n"
        )  # triggers ActionEvents.NEW event
        unit_to_delete = self.get_unit("Orangutan has %d banana")
        self.translation.delete_unit(
            None, unit_to_delete
        )  # triggers ActionEvents.STRING_REMOVE event
        self.assertEqual(self.count_requests(), expected_calls)

    @responses.activate
    def test_bulk_changes(self) -> None:
        """Test bulk change create via the propagate() method."""
        # create another component in project with same units as self.component
        self.create_po(
            new_base="po/project.pot", project=self.project, name="Component B1"
        )
        # listen to propagate change event
        self.addon_configuration["events"].append(ActionEvents.PROPAGATED_EDIT)

        self.WEBHOOK_CLS.create(
            configuration=self.addon_configuration, project=self.project
        )
        self.component.drop_addons_cache()
        responses.add(responses.POST, self.WEBHOOK_URL, status=200)

        # create translation for unit and similar units across project
        self.change_unit("Nazdar svete!\n", "Hello, world!\n", "cs")
        self.assertEqual(self.count_requests(), 2)

    @responses.activate
    def test_translation_added(self) -> None:
        """Test translation added and translation edited action change."""
        self.addon_configuration["events"].append(ActionEvents.CHANGE)
        self.do_translation_added_test(response_code=200)
        self.reset_calls()
        self.edit_unit("Hello, world!\n", "Nazdar svete edit!\n")
        self.assertEqual(self.count_requests(), 1)

    @responses.activate
    def test_announcement(self) -> None:
        """Test project and site wide events."""
        self.addon_configuration["events"].append(ActionEvents.ANNOUNCEMENT)
        self.WEBHOOK_CLS.create(configuration=self.addon_configuration)
        self.WEBHOOK_CLS.create(
            configuration=self.addon_configuration, project=self.project
        )

        self.reset_calls()
        Announcement.objects.create(user=self.user, message="Site-wide")
        # Only site-wide add-on should receive this
        self.assertEqual(self.count_requests(), 1)

        self.reset_calls()
        Announcement.objects.create(
            user=self.user, message="Project-wide", project=self.project
        )
        # Both site-wide and project-wide add-ons should receive this
        self.assertEqual(self.count_requests(), 2)

    @responses.activate
    def test_component_scopes(self) -> None:
        """Test webhook addon installed at component level."""
        secondary_url = f"{self.WEBHOOK_URL}-2"
        component1 = self.component
        component2 = self.create_po(
            new_base="po/project.pot", project=self.project, name="Secondary component"
        )
        config1 = self.addon_configuration.copy()
        config2 = self.addon_configuration.copy() | {"webhook_url": secondary_url}

        self.WEBHOOK_CLS.create(configuration=config1, component=component1)
        self.WEBHOOK_CLS.create(configuration=config2, component=component2)

        resp1 = responses.post(self.WEBHOOK_URL, status=200)
        resp2 = responses.post(secondary_url, status=200)
        translation1 = self.get_translation()
        translation2 = component2.translation_set.get(language__code="cs")

        # delete similar units to avoid propagation of changes
        translation1.unit_set.filter(source="Thank you for using Weblate.").delete()
        translation2.unit_set.filter(source="Hello, world!\n").delete()

        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", translation=translation1)
        self.edit_unit(
            "Thank you for using Weblate.",
            "Díky za používání Weblate.",
            translation=translation2,
        )

        self.assertEqual(len(resp1.calls), 1)
        self.assertEqual(len(resp2.calls), 1)

    @responses.activate
    def test_project_scopes(self) -> None:
        """Test webhook addon installed at project level."""
        secondary_url = f"{self.WEBHOOK_URL}-2"
        project_a = self.project
        component_a1 = self.component
        component_a2 = self.create_po(
            new_base="po/project.pot", project=project_a, name="Component A2"
        )

        project_b = self.create_project(name="Test 2", slug="project2")
        component_b1 = self.create_po(
            new_base="po/project.pot", project=project_b, name="Component B1"
        )

        config_a = self.addon_configuration.copy()
        config_b = self.addon_configuration.copy() | {"webhook_url": secondary_url}

        self.WEBHOOK_CLS.create(configuration=config_a, project=project_a)
        self.WEBHOOK_CLS.create(configuration=config_b, project=project_b)

        resp_a = responses.post(self.WEBHOOK_URL, status=200)
        resp_b = responses.post(secondary_url, status=200)

        translation_a1 = component_a1.translation_set.get(language__code="cs")
        translation_a2 = component_a2.translation_set.get(language__code="cs")
        translation_b1 = component_b1.translation_set.get(language__code="cs")

        # delete similar units between components to avoir propagation
        translation_a1.unit_set.filter(source="Thank you for using Weblate.").delete()
        translation_a2.unit_set.filter(source="Hello, world!\n").delete()

        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", translation=translation_a1)
        self.edit_unit(
            "Thank you for using Weblate.",
            "Díky za používání Weblate.",
            translation=translation_a2,
        )
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", translation=translation_b1)

        self.assertEqual(len(resp_a.calls), 2)
        self.assertEqual(len(resp_b.calls), 1)

    @responses.activate
    def test_site_wide_scope(self) -> None:
        """Test webhook addon installed site-wide."""
        project_b = self.create_project(name="Test 2", slug="project2")
        component_b1 = self.create_po(
            new_base="po/project.pot", project=project_b, name="Component B1"
        )

        self.WEBHOOK_CLS.create(configuration=self.addon_configuration)
        responses.add(responses.POST, self.WEBHOOK_URL, status=200)

        translation_a1 = self.get_translation()
        translation_b1 = component_b1.translation_set.get(language__code="cs")
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", translation=translation_a1)
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", translation=translation_b1)

        self.assertEqual(self.count_requests(), 2)

    @responses.activate
    def test_connection_error(self) -> None:
        """Test connection error when during message delivery."""
        self.do_translation_added_test(body=requests.ConnectionError())


class WebhooksAddonTest(BaseWebhookTests, ViewTestCase):
    """Test for Webhook Addon."""

    WEBHOOK_CLS = WebhookAddon
    WEBHOOK_URL = "https://example.com/webhooks"

    addon_configuration: ClassVar[dict] = {
        "webhook_url": WEBHOOK_URL,
        "events": [],
    }

    @responses.activate
    def test_invalid_response(self) -> None:
        """Test invalid response from client."""
        self.do_translation_added_test(response_code=301)

    @responses.activate
    def test_webhook_signature_prefix(self) -> None:
        """Test webhook signature features."""
        self.addon_configuration["secret"] = "whsec_secret-string"
        self.do_translation_added_test(response_code=200)

        wh_request = responses.calls[0].request
        wh_utils = Webhook("whsec_secret-string")
        wh_utils.verify(wh_request.body, wh_request.headers)

        # This should be equivalent
        wh_utils = Webhook("secret-string")
        wh_utils.verify(wh_request.body, wh_request.headers)

        # Verify that different secret fails
        with self.assertRaises(WebhookVerificationError):
            wh_utils = Webhook("public-string")
            wh_utils.verify(wh_request.body, wh_request.headers)

    @responses.activate
    def test_webhook_signature(self) -> None:
        """Test webhook signature features."""
        self.addon_configuration["secret"] = "secret-string"
        self.do_translation_added_test(response_code=200)

        wh_request = responses.calls[0].request
        wh_utils = Webhook("secret-string")

        # valid request
        wh_utils.verify(wh_request.body, wh_request.headers)

        # valid request with bytes
        Webhook(base64.b64decode("secret-string")).verify(
            wh_request.body, wh_request.headers
        )

        wh_headers = dict(wh_request.headers)

        # valid request with multiple signatures (space separated)
        new_headers = wh_headers.copy()
        new_headers["webhook-signature"] = (
            f"v1,Ceo5qEr07ixe2NLpvHk3FH9bwy/WavXrAFQ/9tdO6mc= v2,Gur4pLd03kjn8RYtBm5eJ1aZx/CbVfSdTq/2gNhA8= {new_headers['webhook-signature']}"
        )
        wh_utils.verify(wh_request.body, new_headers)

        #  "Invalid Signature Headers"
        with self.assertRaises(WebhookVerificationError):
            new_headers = wh_headers.copy()
            new_headers["webhook-signature"] = (
                f"{new_headers['webhook-signature'][:-5]}xxxxx"
            )
            wh_utils.verify(wh_request.body, new_headers)

        #  "Missing required headers"
        with self.assertRaises(WebhookVerificationError):
            new_headers = wh_headers.copy()
            del new_headers["webhook-signature"]
            wh_utils.verify(wh_request.body, new_headers)

        #  "Invalid secret"
        with self.assertRaises(WebhookVerificationError):
            Webhook("xxxx-xxxx-xxxx").verify(wh_request.body, wh_headers)

        #  "Invalid format of timestamp"
        with self.assertRaises(WebhookVerificationError):
            new_headers = wh_headers.copy()
            new_headers["webhook-timestamp"] = "NaN"
            wh_utils.verify(wh_request.body, new_headers)

        #  "Outdated headers timestamp"
        with self.assertRaises(WebhookVerificationError):
            new_headers = wh_headers.copy()
            new_headers["webhook-timestamp"] = str(
                (timezone.now() - timedelta(minutes=6)).timestamp()
            )
            wh_utils.verify(wh_request.body, new_headers)

        #  "Invalid future timestamp"
        with self.assertRaises(WebhookVerificationError):
            new_headers = wh_headers.copy()
            new_headers["webhook-timestamp"] = str(
                (timezone.now() + timedelta(minutes=6)).timestamp()
            )
            wh_utils.verify(wh_request.body, new_headers)

    def test_form(self) -> None:
        """Test WebhooksAddonForm."""
        self.user.is_superuser = True
        self.user.save()
        # Missing url param
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.webhook.webhook",
                "form": "1",
            },
            follow=True,
        )
        self.assertNotContains(response, "Installed 1 add-on")

        # empty secret
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.webhook.webhook",
                "form": "1",
                "webhook_url": "https://example.com/webhooks",
                "secret": "",
            },
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")

        # delete addon
        addon_id = Addon.objects.get(component=self.component).id
        response = self.client.post(
            reverse("addon-detail", kwargs={"pk": addon_id}),
            {"delete": "weblate.webhook.webhook"},
            follow=True,
        )
        self.assertContains(response, "No add-ons currently installed")

        # invalid secret
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.webhook.webhook",
                "form": "1",
                "webhook_url": "https://example.com/webhooks",
                "events": [ActionEvents.NEW],
                "secret": "xxxx-xx",
            },
            follow=True,
        )
        self.assertContains(response, "Invalid base64 encoded string")

        # valid secret
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.webhook.webhook",
                "form": "1",
                "webhook_url": "https://example.com/webhooks",
                "secret": "xxxx-xxxx-xxxx-xxxx-xxxx-xxxx-xxxx-xxxx-xxxx",
                "events": [ActionEvents.NEW],
            },
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")

    def test_form_blocks_private_webhook_target_by_default(self) -> None:
        self.user.is_superuser = True
        self.user.save()

        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.webhook.webhook",
                "form": "1",
                "webhook_url": "http://localhost/hook",
                "events": [ActionEvents.NEW],
            },
            follow=True,
        )

        self.assertContains(response, "internal or non-public address")
        self.assertFalse(
            Addon.objects.filter(
                component=self.component, name="weblate.webhook.webhook"
            ).exists()
        )

    @override_settings(WEBHOOK_RESTRICT_PRIVATE=False)
    def test_form_allows_private_webhook_target_when_restriction_disabled(self) -> None:
        self.user.is_superuser = True
        self.user.save()

        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.webhook.webhook",
                "form": "1",
                "webhook_url": "http://localhost/hook",
                "events": [ActionEvents.NEW],
            },
            follow=True,
        )

        self.assertContains(response, "Installed 1 add-on")

    @override_settings(WEBHOOK_PRIVATE_ALLOWLIST=["localhost"])
    def test_form_allows_private_webhook_target_when_allowlisted(self) -> None:
        self.user.is_superuser = True
        self.user.save()

        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.webhook.webhook",
                "form": "1",
                "webhook_url": "http://localhost/hook",
                "events": [ActionEvents.NEW],
            },
            follow=True,
        )

        self.assertContains(response, "Installed 1 add-on")

    @responses.activate
    def test_jsonschema_error(self) -> None:
        """Test payload schema validation error."""
        with patch(
            "weblate.addons.webhooks.validate_schema",
            side_effect=jsonschema.exceptions.ValidationError("message"),
        ):
            self.do_translation_added_test(expected_calls=0)

    @responses.activate
    def test_category_in_payload(self) -> None:
        """Test webhook payload includes category field when available."""
        self.project.add_user(self.user, "Administration")
        self.addon_configuration["events"] = [ActionEvents.RENAME_COMPONENT]
        self.WEBHOOK_CLS.create(
            configuration=self.addon_configuration, component=self.component
        )
        parent_category = Category.objects.create(
            name="Parent Category", slug="parent-category", project=self.project
        )
        child_category = Category.objects.create(
            name="Child Category",
            slug="child-category",
            category=parent_category,
            project=self.project,
        )
        sub_category = Category.objects.create(
            name="Sub Category",
            slug="sub-category",
            category=child_category,
            project=self.project,
        )
        self.component.category = sub_category
        self.component.save()

        responses.add(responses.POST, "https://example.com/webhooks", status=200)
        self.client.post(
            reverse("rename", kwargs={"path": self.component.get_url_path()}),
            {
                "name": "New name",
                "slug": "new-name",
                "project": self.project.pk,
                "category": sub_category.pk,
            },
        )

        request_body = json.loads(cast("bytes", responses.calls[0].request.body))
        self.assertIn("child-category", request_body["category"])
        self.assertIn("parent-category", request_body["category"])
        self.assertIn("sub-category", request_body["category"])

    @responses.activate
    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("127.0.0.1", 80))],
    )
    def test_private_webhook_target_is_blocked(self, mocked_getaddrinfo) -> None:
        self.WEBHOOK_CLS.create(configuration=self.addon_configuration)

        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")

        mocked_getaddrinfo.assert_called_once()
        self.assertEqual(mocked_getaddrinfo.call_args.args[0], "example.com")
        self.assertEqual(self.count_requests(), 0)

        activity_log = AddonActivityLog.objects.filter(
            addon__name=self.WEBHOOK_CLS.name
        ).latest("created")
        self.assertTrue(activity_log.details["error"])
        self.assertIn("result", activity_log.details)
        self.assertNotIsInstance(activity_log.details["result"], dict)
        self.assertIsInstance(activity_log.details["result"], str)
        self.assertTrue(activity_log.details["result"])


class SlackWebhooksAddonsTest(BaseWebhookTests, ViewTestCase):
    WEBHOOK_CLS = SlackWebhookAddon
    WEBHOOK_URL = "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"  # kingfisher:ignore

    addon_configuration: ClassVar[dict] = {
        "webhook_url": WEBHOOK_URL,
        "events": [str(ActionEvents.NEW)],
    }

    @responses.activate
    def test_invalid_response(self) -> None:
        """Test invalid response from client."""
        self.do_translation_added_test(response_code=410, body=b"channel_is_archived")


class FedoraMessagingAddonTestCase(BaseWebhookTests, ViewTestCase):
    WEBHOOK_CLS = FedoraMessagingAddon
    # Not really used
    WEBHOOK_URL = "https://example.com/webhooks"
    addon_configuration: ClassVar[dict] = {
        "amqp_host": "nonexisting.example.com",
        "events": [str(ActionEvents.NEW)],
    }

    def setUp(self) -> None:
        super().setUp()
        self.patcher = patch("fedora_messaging.api._twisted_publish_wrapper")
        self.mock_class = self.patcher.start()

    def tearDown(self) -> None:
        del self.mock_class
        self.patcher.stop()
        del self.patcher
        super().tearDown()

    def count_requests(self) -> int:
        return self.mock_class.call_count

    def reset_calls(self) -> None:
        self.patcher.stop()
        self.mock_class = self.patcher.start()

    def test_topic(self):
        for change in Change.objects.all():
            self.assertIsNotNone(FedoraMessagingAddon.get_change_topic(change))

    def test_body(self):
        for change in Change.objects.all():
            self.assertIsNotNone(FedoraMessagingAddon.get_change_body(change))

    def test_headers(self):
        for change in Change.objects.all():
            self.assertIsNotNone(FedoraMessagingAddon.get_change_headers(change))

    def test_component_scopes(self) -> None:
        pass

    def test_project_scopes(self) -> None:
        pass

    def test_form(self) -> None:
        """Test FedoraMessagingAddonForm."""
        self.user.is_superuser = True
        self.user.save()
        params = self.addon_configuration.copy()
        params["name"] = self.WEBHOOK_CLS.name
        params["form"] = "1"

        # Wrong scope
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            params,
            follow=True,
        )
        self.assertNotContains(response, "Installed 1 add-on")
        response = self.client.post(
            reverse("addons", kwargs=self.kw_project_path),
            params,
            follow=True,
        )
        self.assertNotContains(response, "Installed 1 add-on")

        # Install
        response = self.client.post(
            reverse("manage-addons"),
            params,
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")

        # delete addon
        addon_id = Addon.objects.get(name=self.WEBHOOK_CLS.name).id
        response = self.client.post(
            reverse("addon-detail", kwargs={"pk": addon_id}),
            {"delete": "weblate.webhook.webhook"},
            follow=True,
        )
        self.assertContains(response, "No add-ons currently installed")

        # missing certs for SSL
        params["amqp_ssl"] = "1"
        response = self.client.post(
            reverse("manage-addons"),
            params,
            follow=True,
        )
        self.assertContains(
            response, "The SSL certificates have to be provided for SSL connection."
        )
        self.assertNotContains(response, "Installed 1 add-on")

        # certs but no SSL
        del params["amqp_ssl"]
        params["ca_cert"] = "x"
        params["client_key"] = "x"
        params["client_cert"] = "x"
        response = self.client.post(
            reverse("manage-addons"),
            params,
            follow=True,
        )
        self.assertContains(
            response, "The SSL certificates are not used without a SSL connection."
        )
        self.assertNotContains(response, "Installed 1 add-on")

        # Install with SSL
        params["amqp_ssl"] = "1"
        response = self.client.post(
            reverse("manage-addons"),
            params,
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")


class TestCommand(ComponentTestCase):
    def test_list_addons(self) -> None:
        output = StringIO()
        call_command("list_addons", stdout=output)
        self.assertIn(".. _addon-event-add-on-installation:", output.getvalue())
        self.assertIn("Common add-on parameters", output.getvalue())

        with self.assertRaises(FileNotFoundError):
            call_command("list_addons", "-o", "missing_fileXXX.rst", stdout=StringIO())

    def test_list_addons_split_output(self) -> None:
        with (
            tempfile.NamedTemporaryFile(suffix=".rst", delete=False) as events_handle,
            tempfile.NamedTemporaryFile(suffix=".rst", delete=False) as addons_handle,
            tempfile.NamedTemporaryFile(
                suffix=".rst", delete=False
            ) as parameters_handle,
        ):
            events_path = Path(events_handle.name)
            addons_path = Path(addons_handle.name)
            parameters_path = Path(parameters_handle.name)
        self.addCleanup(events_path.unlink)
        self.addCleanup(addons_path.unlink)
        self.addCleanup(parameters_path.unlink)

        call_command(
            "list_addons",
            "--sections",
            "events",
            "-o",
            events_path,
            stdout=StringIO(),
        )
        call_command(
            "list_addons",
            "--sections",
            "addons",
            "-o",
            addons_path,
            stdout=StringIO(),
        )
        call_command(
            "list_addons",
            "--sections",
            "parameters",
            "-o",
            parameters_path,
            stdout=StringIO(),
        )

        events_content = events_path.read_text(encoding="utf-8")
        addons_content = addons_path.read_text(encoding="utf-8")
        parameters_content = parameters_path.read_text(encoding="utf-8")

        self.assertIn("Events that trigger add-ons", events_content)
        self.assertIn(".. _addon-event-add-on-installation:", events_content)
        self.assertNotIn("Built-in add-ons", events_content)
        self.assertNotIn("Common add-on parameters", events_content)

        self.assertIn("Built-in add-ons", addons_content)
        self.assertNotIn(".. _addon-event-add-on-installation:", addons_content)
        self.assertNotIn("Common add-on parameters", addons_content)
        self.assertNotIn("Customize XML output", addons_content)

        self.assertIn("Common add-on parameters", parameters_content)
        self.assertIn(".. _addon-choice-engines:", parameters_content)
        self.assertNotIn("Built-in add-ons", parameters_content)
        self.assertNotIn("Events that trigger add-ons", parameters_content)
