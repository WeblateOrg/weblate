# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for inherited enforced checks."""

from __future__ import annotations

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test.utils import captureOnCommitCallbacks

from weblate.trans.models import Category, Component, Project, Unit
from weblate.trans.tests.test_views import ComponentTestCase
from weblate.utils.state import STATE_NEEDS_REWRITING, STATE_TRANSLATED
from weblate.workspaces.models import Workspace


class EnforcedChecksInheritanceTest(ComponentTestCase):
    """Test enforced checks inheritance across workspace/project/category/component."""

    def setUp(self) -> None:
        super().setUp()
        self.workspace = Workspace.objects.create(name="Test workspace")
        Project.objects.filter(pk=self.project.pk).update(workspace=self.workspace)
        self.category = Category.objects.create(
            name="Test category",
            slug="test-category",
            project=self.project,
        )
        Component.objects.filter(pk=self.component.pk).update(
            category=self.category,
            inherit_enforced_checks=True,
        )
        self.component = Component.objects.get(pk=self.component.pk)

    def get_same_check_unit(self) -> Unit:
        unit = Unit.objects.filter(
            check__name="same", translation__component=self.component
        ).first()
        assert unit is not None
        return unit

    def test_workspace_inheritance(self) -> None:
        Workspace.objects.filter(pk=self.workspace.pk).update(enforced_checks=["same"])
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.effective_enforced_checks, ["same"])
        self.assertEqual(component.get_effective_setting("enforced_checks"), ["same"])

    def test_project_inherits_workspace(self) -> None:
        Workspace.objects.filter(pk=self.workspace.pk).update(enforced_checks=["same"])
        project = Project.objects.get(pk=self.project.pk)
        self.assertEqual(project.effective_enforced_checks, ["same"])

    def test_project_stops_inheriting_workspace(self) -> None:
        Workspace.objects.filter(pk=self.workspace.pk).update(
            enforced_checks=["duplicate"]
        )
        Project.objects.filter(pk=self.project.pk).update(
            inherit_enforced_checks=False,
            enforced_checks=["same"],
        )
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.effective_enforced_checks, ["same"])

    def test_category_inherits_project(self) -> None:
        Project.objects.filter(pk=self.project.pk).update(
            inherit_enforced_checks=False,
            enforced_checks=["same"],
        )
        category = Category.objects.get(pk=self.category.pk)
        self.assertEqual(category.effective_enforced_checks, ["same"])
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.effective_enforced_checks, ["same"])

    def test_category_stops_inheriting_project(self) -> None:
        Project.objects.filter(pk=self.project.pk).update(
            inherit_enforced_checks=False,
            enforced_checks=["duplicate"],
        )
        Category.objects.filter(pk=self.category.pk).update(
            inherit_enforced_checks=False,
            enforced_checks=["same"],
        )
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.effective_enforced_checks, ["same"])

    def test_component_local_override(self) -> None:
        Project.objects.filter(pk=self.project.pk).update(
            inherit_enforced_checks=False,
            enforced_checks=["duplicate"],
        )
        Component.objects.filter(pk=self.component.pk).update(
            inherit_enforced_checks=False,
            enforced_checks=["same"],
        )
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.effective_enforced_checks, ["same"])

    def test_component_inherits_when_local_empty(self) -> None:
        Project.objects.filter(pk=self.project.pk).update(
            inherit_enforced_checks=False,
            enforced_checks=["same"],
        )
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.enforced_checks, [])
        self.assertEqual(component.effective_enforced_checks, ["same"])

    def test_enforce_from_workspace(self) -> None:
        unit = self.get_same_check_unit()
        Unit.objects.filter(pk=unit.pk).update(state=STATE_TRANSLATED)
        Workspace.objects.filter(pk=self.workspace.pk).update(enforced_checks=["same"])
        component = Component.objects.get(pk=self.component.pk)
        component.update_enforced_checks()
        unit.refresh_from_db()
        self.assertEqual(unit.state, STATE_NEEDS_REWRITING)

    def test_enforce_from_project(self) -> None:
        unit = self.get_same_check_unit()
        Unit.objects.filter(pk=unit.pk).update(state=STATE_TRANSLATED)
        Project.objects.filter(pk=self.project.pk).update(
            inherit_enforced_checks=False,
            enforced_checks=["same"],
        )
        component = Component.objects.get(pk=self.component.pk)
        component.update_enforced_checks()
        unit.refresh_from_db()
        self.assertEqual(unit.state, STATE_NEEDS_REWRITING)

    def test_enforce_from_category(self) -> None:
        unit = self.get_same_check_unit()
        Unit.objects.filter(pk=unit.pk).update(state=STATE_TRANSLATED)
        Category.objects.filter(pk=self.category.pk).update(
            inherit_enforced_checks=False,
            enforced_checks=["same"],
        )
        component = Component.objects.get(pk=self.component.pk)
        component.update_enforced_checks()
        unit.refresh_from_db()
        self.assertEqual(unit.state, STATE_NEEDS_REWRITING)

    def test_component_without_inheritance_not_enforced(self) -> None:
        unit = self.get_same_check_unit()
        Unit.objects.filter(pk=unit.pk).update(state=STATE_TRANSLATED)
        Project.objects.filter(pk=self.project.pk).update(
            inherit_enforced_checks=False,
            enforced_checks=["same"],
        )
        Component.objects.filter(pk=self.component.pk).update(
            inherit_enforced_checks=False,
            enforced_checks=[],
        )
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.effective_enforced_checks, [])
        component.update_enforced_checks()
        unit.refresh_from_db()
        self.assertEqual(unit.state, STATE_TRANSLATED)

    @patch("weblate.trans.tasks.update_enforced_checks.delay_on_commit")
    def test_workspace_save_schedules_updates(self, mock_delay) -> None:
        self.workspace.enforced_checks = ["same"]
        with captureOnCommitCallbacks(execute=True):
            self.workspace.save(update_fields=["enforced_checks"])
        scheduled = {call.args[0] for call in mock_delay.call_args_list}
        self.assertIn(self.component.pk, scheduled)

    @patch("weblate.trans.tasks.update_enforced_checks.delay_on_commit")
    def test_project_save_schedules_updates(self, mock_delay) -> None:
        self.project.inherit_enforced_checks = False
        self.project.enforced_checks = ["same"]
        with captureOnCommitCallbacks(execute=True):
            self.project.save(
                update_fields=["enforced_checks", "inherit_enforced_checks"]
            )
        scheduled = {call.args[0] for call in mock_delay.call_args_list}
        self.assertIn(self.component.pk, scheduled)

    @patch("weblate.trans.tasks.update_enforced_checks.delay_on_commit")
    def test_category_save_schedules_updates(self, mock_delay) -> None:
        self.category.inherit_enforced_checks = False
        self.category.enforced_checks = ["same"]
        with captureOnCommitCallbacks(execute=True):
            self.category.save(
                update_fields=["enforced_checks", "inherit_enforced_checks"]
            )
        scheduled = {call.args[0] for call in mock_delay.call_args_list}
        self.assertIn(self.component.pk, scheduled)

    def test_component_clean_rejects_unknown_check(self) -> None:
        self.component.enforced_checks = ["does-not-exist"]
        with self.assertRaisesMessage(
            ValidationError, "Unsupported enforced check: does-not-exist"
        ):
            self.component.full_clean()

    def test_project_clean_rejects_unknown_check(self) -> None:
        self.project.enforced_checks = ["does-not-exist"]
        with self.assertRaisesMessage(
            ValidationError, "Unsupported enforced check: does-not-exist"
        ):
            self.project.full_clean()

    def test_category_clean_rejects_unknown_check(self) -> None:
        self.category.enforced_checks = ["does-not-exist"]
        with self.assertRaisesMessage(
            ValidationError, "Unsupported enforced check: does-not-exist"
        ):
            self.category.full_clean()

    def test_workspace_clean_rejects_unknown_check(self) -> None:
        self.workspace.enforced_checks = ["does-not-exist"]
        with self.assertRaisesMessage(
            ValidationError, "Unsupported enforced check: does-not-exist"
        ):
            self.workspace.full_clean()

    def test_clean_accepts_known_checks(self) -> None:
        self.workspace.enforced_checks = ["same", "duplicate"]
        self.workspace.full_clean()
