# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for categories."""

from __future__ import annotations

from datetime import timedelta
from itertools import product

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from weblate.auth.data import SELECTION_ALL
from weblate.auth.models import Group, Role
from weblate.lang.models import Language
from weblate.trans.forms import TranslationForm
from weblate.trans.models import (
    Category,
    ComponentLink,
    PendingUnitChange,
    Project,
    Translation,
    WorkflowSetting,
)
from weblate.trans.models.project import CommitPolicyChoices
from weblate.trans.tests.test_views import FixtureComponentTestCase
from weblate.utils.state import STATE_APPROVED, STATE_FUZZY, STATE_TRANSLATED
from weblate.utils.stats import CategoryLanguage, ProjectLanguage


class WorkflowSettingsTestCase(FixtureComponentTestCase):
    def test_commit_policy_form_help(self) -> None:
        self.project.commit_policy = CommitPolicyChoices.APPROVED_ONLY
        self.project.translation_review = True
        self.project.source_review = True
        self.project.save()
        for is_source, review in product((False, True), (False, True)):
            with self.subTest(is_source=is_source, review=review):
                translation = (
                    self.component.source_translation if is_source else self.translation
                )
                WorkflowSetting.objects.update_or_create(
                    project=self.project,
                    language=translation.language,
                    defaults={"translation_review": review},
                )
                translation = Translation.objects.get(pk=translation.pk)
                unit = translation.unit_set.order_by("pk")[0]
                form = TranslationForm(self.user, unit)
                for name in ("fuzzy", "review"):
                    self.assertEqual(
                        "only approved translations" in form.fields[name].help_text,
                        review,
                    )
        self.assertIn(
            "For languages with reviews enabled",
            self.project.get_commit_policy_description(),
        )

    def test_commit_policy_effective_reviews(self) -> None:
        self.project.commit_policy = CommitPolicyChoices.APPROVED_ONLY
        self.project.save()
        for is_source, project_review, global_review, local_review in product(
            (False, True), (False, True), (None, False, True), (None, False, True)
        ):
            with self.subTest(
                is_source=is_source,
                project_review=project_review,
                global_review=global_review,
                local_review=local_review,
            ):
                self.project.source_review = project_review if is_source else False
                self.project.translation_review = (
                    project_review if not is_source else False
                )
                self.project.save()
                translation = (
                    self.component.source_translation if is_source else self.translation
                )
                WorkflowSetting.objects.all().delete()
                for project_id, review in (
                    (None, global_review),
                    (self.project.pk, local_review),
                ):
                    if review is not None:
                        WorkflowSetting.objects.create(
                            project_id=project_id,
                            language=translation.language,
                            translation_review=review,
                        )
                translation = Translation.objects.get(pk=translation.pk)
                override = local_review if local_review is not None else global_review
                enabled = project_review and override is not False
                self.assertEqual(translation.enable_review, enabled)
                self.assertEqual(
                    Translation.objects.with_review()
                    .filter(pk=translation.pk)
                    .exists(),
                    enabled,
                )
                unit = translation.unit_set.order_by("pk")[0]
                for state in (STATE_TRANSLATED, STATE_FUZZY, STATE_APPROVED):
                    unit.state = state
                    blocked = enabled and state != STATE_APPROVED
                    self.assertEqual(unit.is_blocked_by_commit_policy, blocked)
                    change = PendingUnitChange.objects.create(
                        unit=unit,
                        author=self.user,
                        state=state,
                        timestamp=timezone.now() - timedelta(hours=2),
                    )
                    with CaptureQueriesContext(connection) as queries:
                        self.assertEqual(
                            PendingUnitChange.objects.for_translation(
                                translation
                            ).exists(),
                            not blocked,
                        )
                        PendingUnitChange.objects.detailed_count(translation)
                    # The effective review setting is already cached on translation.
                    for query in queries:
                        self.assertNotIn("trans_workflowsetting", query["sql"])
                    for obj in (translation, self.component, self.project):
                        counts = PendingUnitChange.objects.detailed_count(obj)
                        self.assertEqual(
                            counts["eligible_for_commit"], int(not blocked)
                        )
                        self.assertEqual(counts["commit_policy_skipped"], int(blocked))
                    self.assertEqual(
                        PendingUnitChange.objects.find_committable_components(hours=1)
                        .filter(pk=self.component.pk)
                        .exists(),
                        not blocked,
                    )
                    change.delete()

    def assert_workflow(self, **kwargs) -> None:
        self.assertFalse(self.translation.enable_review)
        self.assertTrue(self.translation.enable_suggestions)
        self.assertFalse(self.translation.restrict_direct_editing)

        workflowsetting = WorkflowSetting.objects.create(
            translation_review=True,
            enable_suggestions=False,
            restrict_direct_editing=True,
            **kwargs,
        )
        translation = Translation.objects.get(pk=self.translation.pk)
        self.assertFalse(translation.enable_review)
        self.assertFalse(translation.enable_suggestions)
        self.assertTrue(translation.restrict_direct_editing)

        self.project.translation_review = True
        self.project.save()
        translation = Translation.objects.get(pk=translation.pk)
        self.assertTrue(translation.enable_review)
        self.assertFalse(translation.enable_suggestions)
        self.assertTrue(translation.restrict_direct_editing)

        workflowsetting.translation_review = False
        workflowsetting.restrict_direct_editing = False
        workflowsetting.save()
        translation = Translation.objects.get(pk=translation.pk)
        self.assertFalse(translation.enable_review)
        self.assertFalse(translation.enable_suggestions)
        self.assertFalse(translation.restrict_direct_editing)

    def test_project(self) -> None:
        self.assert_workflow(project=self.project, language=self.translation.language)

    def test_language(self) -> None:
        self.assert_workflow(language=self.translation.language)

    def test_both(self) -> None:
        WorkflowSetting.objects.create(
            translation_review=False,
            enable_suggestions=True,
            language=self.translation.language,
        )
        self.assert_workflow(project=self.project, language=self.translation.language)

    def test_other(self) -> None:
        WorkflowSetting.objects.create(
            translation_review=False,
            enable_suggestions=True,
            language=Language.objects.get(code="de"),
            project=self.project,
        )
        self.assert_workflow(project=self.project, language=self.translation.language)

    def test_category_language_review_matches_project_language(self) -> None:
        category = Category.objects.create(
            project=self.project, name="Workflow", slug="workflow"
        )
        self.component.category = category
        self.component.save(update_fields=["category"])
        target_language = self.translation.language
        source_language = self.component.source_language

        for language, setting_name in (
            (source_language, "source_review"),
            (target_language, "translation_review"),
        ):
            for project_enabled in (False, True):
                for workflow_enabled in (None, False, True):
                    with self.subTest(
                        language=language.code,
                        project_enabled=project_enabled,
                        workflow_enabled=workflow_enabled,
                    ):
                        self.project.source_review = False
                        self.project.translation_review = False
                        setattr(self.project, setting_name, project_enabled)
                        self.project.save(
                            update_fields=["source_review", "translation_review"]
                        )
                        WorkflowSetting.objects.filter(
                            project=self.project, language=language
                        ).delete()
                        if workflow_enabled is not None:
                            WorkflowSetting.objects.create(
                                project=self.project,
                                language=language,
                                translation_review=workflow_enabled,
                            )

                        project_language = ProjectLanguage(self.project, language)
                        category_language = CategoryLanguage(category, language)
                        expected = project_enabled and workflow_enabled is not False
                        self.assertEqual(project_language.enable_review, expected)
                        self.assertEqual(category_language.enable_review, expected)
                        self.assertEqual(category_language.stats.has_review, expected)

    def test_language_wrappers_restrict_direct_editing(self) -> None:
        category = Category.objects.create(
            project=self.project,
            name="Restricted workflow wrappers",
            slug="restricted-workflow-wrappers",
        )
        self.component.category = category
        self.component.save(update_fields=["category"])

        project_language = ProjectLanguage(self.project, self.translation.language)
        category_language = CategoryLanguage(category, self.translation.language)
        self.assertFalse(project_language.restrict_direct_editing)
        self.assertFalse(category_language.restrict_direct_editing)

        WorkflowSetting.objects.create(
            project=self.project,
            language=self.translation.language,
            restrict_direct_editing=True,
        )

        project_language = ProjectLanguage(self.project, self.translation.language)
        category_language = CategoryLanguage(category, self.translation.language)
        self.assertTrue(project_language.restrict_direct_editing)
        self.assertTrue(category_language.restrict_direct_editing)

    def test_restrict_direct_editing_permissions(self) -> None:
        category = Category.objects.create(
            project=self.project,
            name="Restricted workflow permissions",
            slug="restricted-workflow-permissions",
        )
        self.component.category = category
        self.component.save(update_fields=["category"])

        group = Group.objects.create(
            name="Workflow actions", language_selection=SELECTION_ALL
        )
        group.projects.add(self.project)
        group.roles.add(
            Role.objects.get(name="Automatic translation"),
            Role.objects.get(name="Bulk editing"),
        )
        self.user.groups.add(group)
        self.user.clear_permissions_cache()

        project_language = ProjectLanguage(self.project, self.translation.language)
        category_language = CategoryLanguage(category, self.translation.language)
        for obj in (self.translation, project_language, category_language):
            with self.subTest(obj=obj):
                self.assertTrue(self.user.has_perm("unit.edit", obj))
                self.assertTrue(self.user.has_perm("translation.auto", obj))
                self.assertTrue(self.user.has_perm("unit.bulk_edit", obj))

        WorkflowSetting.objects.create(
            project=self.project,
            language=self.translation.language,
            restrict_direct_editing=True,
        )

        translation = Translation.objects.get(pk=self.translation.pk)
        project_language = ProjectLanguage(self.project, translation.language)
        category_language = CategoryLanguage(category, translation.language)
        for obj in (translation, project_language, category_language):
            with self.subTest(obj=obj):
                self.assertFalse(self.user.has_perm("unit.edit", obj))
                self.assertTrue(self.user.has_perm("translation.auto", obj))
                self.assertFalse(self.user.has_perm("unit.bulk_edit", obj))

        self.project.add_user(self.user, "Administration")
        self.user.clear_permissions_cache()
        for obj in (translation, project_language, category_language):
            with self.subTest(obj=obj):
                self.assertTrue(self.user.has_perm("unit.edit", obj))
                self.assertTrue(self.user.has_perm("translation.auto", obj))
                self.assertTrue(self.user.has_perm("unit.bulk_edit", obj))

    def test_shared_category_source_language_review(self) -> None:
        project = Project.objects.create(
            name="Shared workflow",
            slug="shared-workflow",
            source_review=True,
            translation_review=False,
        )
        category = Category.objects.create(
            project=project, name="Shared category", slug="shared-category"
        )
        ComponentLink.objects.create(
            component=self.component, project=project, category=category
        )

        source = CategoryLanguage(category, self.component.source_language)
        target = CategoryLanguage(category, self.translation.language)
        self.assertIn(self.component.source_language_id, category.source_language_ids)
        self.assertTrue(source.enable_review)
        self.assertTrue(source.stats.has_review)
        self.assertFalse(target.enable_review)
        self.assertFalse(target.stats.has_review)
