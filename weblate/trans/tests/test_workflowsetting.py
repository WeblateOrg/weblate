# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for categories."""

from weblate.lang.models import Language
from weblate.trans.models import Translation, WorkflowSetting
from weblate.trans.tests.test_views import ViewTestCase


class WorkflowSettinTestCase(ViewTestCase):
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
