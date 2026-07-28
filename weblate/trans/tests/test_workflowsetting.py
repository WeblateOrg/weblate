# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for categories."""

from weblate.lang.models import Language
from weblate.trans.models import (
    Category,
    ComponentLink,
    Project,
    Translation,
    WorkflowSetting,
)
from weblate.trans.tests.test_views import FixtureComponentTestCase
from weblate.utils.stats import CategoryLanguage, ProjectLanguage


class WorkflowSettingsTestCase(FixtureComponentTestCase):
    def assert_workflow(self, **kwargs) -> None:
        self.assertFalse(self.translation.enable_review)
        self.assertTrue(self.translation.enable_suggestions)

        workflowsetting = WorkflowSetting.objects.create(
            translation_review=True, enable_suggestions=False, **kwargs
        )
        translation = Translation.objects.get(pk=self.translation.pk)
        self.assertFalse(translation.enable_review)
        self.assertFalse(translation.enable_suggestions)

        self.project.translation_review = True
        self.project.save()
        translation = Translation.objects.get(pk=translation.pk)
        self.assertTrue(translation.enable_review)
        self.assertFalse(translation.enable_suggestions)

        workflowsetting.translation_review = False
        workflowsetting.save()
        translation = Translation.objects.get(pk=translation.pk)
        self.assertFalse(translation.enable_review)
        self.assertFalse(translation.enable_suggestions)

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
