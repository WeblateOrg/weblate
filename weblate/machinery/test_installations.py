# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.core.exceptions import ValidationError

from weblate.machinery.models import (
    MachineryExclusion,
    MachineryInstallation,
    applicable_installations,
    resolve_installation,
    selected_machinery_settings,
)
from weblate.trans.models import Project
from weblate.trans.tests.test_views import FixtureComponentTestCase
from weblate.workspaces.models import Workspace


class InstallationTest(FixtureComponentTestCase):
    def test_unconfigured_engine_has_one_installation_per_scope(self) -> None:
        MachineryExclusion.objects.create(project=self.project, engine="weblate")
        MachineryInstallation.objects.create(project=self.project, engine="weblate")
        with self.assertRaises(ValidationError):
            MachineryInstallation.objects.create(project=self.project, engine="weblate")

    def test_internal_installation_requires_excluding_inherited(self) -> None:
        site, _ = MachineryInstallation.objects.get_or_create(
            engine="weblate-translation-memory",
            project=None,
            workspace=None,
        )
        with self.assertRaises(ValidationError):
            MachineryInstallation.objects.create(
                project=self.project, engine=site.engine
            )
        local = MachineryInstallation.objects.create(
            project=self.project, engine=site.engine, enabled=False
        )
        with self.assertRaises(ValidationError):
            local.enabled = True
            local.save(update_fields=["enabled"])
        exclusion = MachineryExclusion.objects.create(
            project=self.project, installation=site
        )
        local.save(update_fields=["enabled"])
        exclusion_id = exclusion.pk
        with self.assertRaises(ValidationError):
            exclusion.delete()
        self.assertTrue(MachineryExclusion.objects.filter(pk=exclusion_id).exists())
        with self.assertRaises(ValidationError):
            MachineryExclusion.objects.filter(pk=exclusion_id).delete()
        self.assertTrue(MachineryExclusion.objects.filter(pk=exclusion_id).exists())

    def test_internal_overlap_after_enabling_or_workspace_move(self) -> None:
        site, _ = MachineryInstallation.objects.get_or_create(
            engine="weblate-translation-memory",
            project=None,
            workspace=None,
        )
        site.enabled = False
        site.save(update_fields=["enabled"])
        local = MachineryInstallation.objects.create(
            project=self.project, engine=site.engine
        )
        with self.assertRaises(ValidationError):
            site.enabled = True
            site.save(update_fields=["enabled"])
        site.enabled = False

        workspace = Workspace.objects.create(name="Machinery workspace")
        shared = MachineryInstallation.objects.create(
            workspace=workspace, engine=site.engine
        )
        with self.assertRaises(ValidationError):
            self.project.workspace = workspace
            self.project.save(update_fields=["workspace"])
        self.project.workspace = None
        MachineryExclusion.objects.create(project=self.project, engine=shared.engine)
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        self.assertEqual(local.project_id, self.project.pk)

    def test_workspace_exclusion_required_for_internal_replacement(self) -> None:
        site, _ = MachineryInstallation.objects.get_or_create(
            engine="weblate-translation-memory",
            project=None,
            workspace=None,
        )
        workspace = Workspace.objects.create(name="Machinery workspace")
        with self.assertRaises(ValidationError):
            MachineryInstallation.objects.create(
                workspace=workspace, engine=site.engine
            )
        exclusion = MachineryExclusion.objects.create(
            workspace=workspace, installation=site
        )
        MachineryInstallation.objects.create(workspace=workspace, engine=site.engine)
        with self.assertRaises(ValidationError):
            MachineryExclusion.objects.filter(pk=exclusion.pk).delete()
        self.assertTrue(MachineryExclusion.objects.filter(pk=exclusion.pk).exists())

    def test_installation_limit_includes_paused_rows(self) -> None:
        count = MachineryInstallation.objects.filter(project=self.project).count()
        first = None
        for index in range(20 - count):
            installation = MachineryInstallation.objects.create(
                project=self.project, engine="deepl", enabled=index % 2 == 0
            )
            if first is None:
                first = installation
        with self.assertRaises(ValidationError):
            MachineryInstallation.objects.create(project=self.project, engine="deepl")
        if first is not None:
            first.slug = "updated"
            first.save(update_fields=["slug"])

    def test_inheritance_and_selectors(self) -> None:
        def visible_openai() -> list[int]:
            return [
                item.pk
                for item in applicable_installations(self.project)
                if item.engine == "openai"
            ]

        workspace = Workspace.objects.create(name="Machinery workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        site = MachineryInstallation.objects.create(engine="openai", slug="site")
        shared = MachineryInstallation.objects.create(
            engine="openai", slug="shared", workspace=workspace
        )
        local = MachineryInstallation.objects.create(
            engine="openai", slug="local", project=self.project
        )
        self.assertEqual(visible_openai(), [site.pk, shared.pk, local.pk])
        self.assertEqual(resolve_installation("openai:shared", self.project), shared)
        self.assertEqual(
            resolve_installation(f"openai:{local.pk}", self.project), local
        )
        with self.assertRaisesRegex(ValueError, "openai:<id>"):
            resolve_installation("openai", self.project)
        with self.assertRaisesRegex(ValueError, "openai:<id>"):
            selected_machinery_settings(self.project, ["openai"])
        self.assertEqual(
            list(selected_machinery_settings(self.project, ["openai:site"])),
            [site.selector],
        )

        MachineryExclusion.objects.create(project=self.project, installation=site)
        MachineryExclusion.objects.create(workspace=workspace, engine="openai")
        self.assertEqual(visible_openai(), [shared.pk, local.pk])
        MachineryExclusion.objects.create(project=self.project, engine="openai")
        self.assertEqual(visible_openai(), [local.pk])
        self.assertEqual(resolve_installation("openai", self.project), local)
        local.enabled = False
        local.save(update_fields=["enabled"])
        self.assertEqual(visible_openai(), [])
        self.assertEqual(
            selected_machinery_settings(self.project, [site.selector, "openai"]), {}
        )

    def test_slug_is_unique_in_inheritance_chain(self) -> None:
        workspace = Workspace.objects.create(name="Machinery workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        MachineryInstallation.objects.create(
            engine="openai", slug="preferred", workspace=workspace
        )
        with self.assertRaises(ValidationError):
            MachineryInstallation.objects.create(
                engine="deepl", slug="preferred", project=self.project
            )
        other = Project.objects.create(
            name="Other project",
            slug="other-machinery-project",
            web="https://example.com/",
        )
        MachineryInstallation.objects.create(
            engine="deepl", slug="preferred", project=other
        )
        with self.assertRaises(ValidationError):
            other.workspace = workspace
            other.save(update_fields=["workspace"])
