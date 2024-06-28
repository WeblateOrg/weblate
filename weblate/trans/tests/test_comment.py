# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for comment views."""

from django.urls import reverse

from weblate.trans.models import Comment
from weblate.trans.tests.test_views import FixtureTestCase


class CommentViewTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.translation = self.component.translation_set.get(language_code="cs")

    def test_add_target_comment(self) -> None:
        unit = self.get_unit()

        # Add comment
        response = self.client.post(
            reverse("comment", kwargs={"pk": unit.id}),
            {"comment": "New target testing comment", "scope": "translation"},
        )
        self.assertRedirects(response, unit.get_absolute_url())

        # Check it is shown on page
        response = self.client.get(unit.get_absolute_url())
        self.assertContains(response, "New target testing comment")

        # Reload from database
        unit = self.get_unit()
        translation = self.component.translation_set.get(language_code="cs")
        # Check number of comments
        self.assertTrue(unit.has_comment)
        self.assertEqual(translation.stats.comments, 1)

    def test_add_source_comment(self) -> None:
        unit = self.get_unit()

        # Add comment
        response = self.client.post(
            reverse("comment", kwargs={"pk": unit.id}),
            {"comment": "New source testing comment", "scope": "global"},
        )
        self.assertRedirects(response, unit.get_absolute_url())

        # Check it is shown on page
        response = self.client.get(unit.get_absolute_url())
        self.assertContains(response, "New source testing comment")

        # Reload from database
        unit = self.get_unit()
        translation = self.component.translation_set.get(language_code="cs")
        # Check number of comments
        self.assertFalse(unit.has_comment)
        self.assertEqual(translation.stats.comments, 0)

    def test_add_source_report(self) -> None:
        unit = self.get_unit()

        # Add comment
        response = self.client.post(
            reverse("comment", kwargs={"pk": unit.id}),
            {"comment": "New issue testing comment", "scope": "report"},
        )
        self.assertRedirects(response, unit.get_absolute_url())

        # Check it is shown on page
        response = self.client.get(unit.get_absolute_url())
        self.assertNotContains(response, "New source testing comment")

        # Enable reviews
        self.project.source_review = True
        self.project.save(update_fields=["source_review"])

        # Add comment
        response = self.client.post(
            reverse("comment", kwargs={"pk": unit.id}),
            {"comment": "New issue testing comment", "scope": "report"},
        )
        self.assertRedirects(response, unit.get_absolute_url())

        # Check it is shown on page
        response = self.client.get(unit.get_absolute_url())
        self.assertContains(response, "New issue testing comment")
        self.assertContains(response, "Source needs review")

        # Reload from database
        unit = self.get_unit()
        translation = self.component.translation_set.get(language_code="cs")
        # Check number of comments
        self.assertFalse(unit.has_comment)
        self.assertEqual(translation.stats.comments, 0)

    def test_delete_comment(self, **kwargs) -> None:
        unit = self.get_unit()
        self.make_manager()

        # Add comment
        response = self.client.post(
            reverse("comment", kwargs={"pk": unit.id}),
            {"comment": "New target testing comment", "scope": "translation"},
        )

        comment = Comment.objects.all()[0]
        response = self.client.post(
            reverse("delete-comment", kwargs={"pk": comment.pk}), kwargs
        )
        self.assertRedirects(response, unit.get_absolute_url())

    def test_spam_comment(self) -> None:
        self.test_delete_comment(spam=1)

    def test_resolve_comment(self) -> None:
        unit = self.get_unit()
        self.make_manager()

        # Add comment
        response = self.client.post(
            reverse("comment", kwargs={"pk": unit.id}),
            {"comment": "New target testing comment", "scope": "translation"},
        )

        comment = Comment.objects.all()[0]
        response = self.client.post(
            reverse("resolve-comment", kwargs={"pk": comment.pk})
        )
        self.assertRedirects(response, unit.get_absolute_url())

        comment.refresh_from_db()
        self.assertTrue(comment.resolved)
        self.assertFalse(comment.unit.has_comment)
