# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for variants."""

from django.urls import reverse

from weblate.trans.tests.test_views import ViewTestCase


class LabelTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.make_manager()
        self.labels_url = reverse("labels", kwargs=self.kw_project)

    def test_create(self) -> None:
        response = self.client.post(
            self.labels_url,
            {
                "name": "Test label",
                "description": "Test description for Test Label",
                "color": "orange",
                "project": self.project.pk,
            },
            follow=True,
        )
        self.assertRedirects(response, self.labels_url)
        self.assertContains(response, "Test label")
        self.assertTrue(self.project.label_set.filter(name="Test label").exists())

    def test_create_duplicate(self) -> None:
        self.test_create()
        response = self.client.post(
            self.labels_url,
            {
                "name": "Test label",
                "description": "Test description for Test Label",
                "color": "orange",
                "project": self.project.pk,
            },
            follow=True,
        )
        self.assertContains(
            response, "Label with this Project and Label name already exists."
        )
        self.assertEqual(self.project.label_set.filter(name="Test label").count(), 1)

    def test_edit_name(self) -> None:
        self.test_create()
        label = self.project.label_set.get()
        response = self.client.post(
            reverse(
                "label_edit", kwargs={"project": self.project.slug, "pk": label.pk}
            ),
            {
                "name": "Renamed label",
                "description": "Test description for Test Label",
                "color": "orange",
                "project": self.project.pk,
            },
            follow=True,
        )
        self.assertRedirects(response, self.labels_url)
        self.assertContains(response, "Renamed label")
        self.assertTrue(self.project.label_set.filter(name="Renamed label").exists())

    def test_edit_description(self) -> None:
        self.test_create()
        label = self.project.label_set.get()
        response = self.client.post(
            reverse(
                "label_edit", kwargs={"project": self.project.slug, "pk": label.pk}
            ),
            {
                "name": "Test label",
                "description": "Edited description for Test Label",
                "color": "orange",
                "project": self.project.pk,
            },
            follow=True,
        )
        self.assertRedirects(response, self.labels_url)
        self.assertContains(response, "Test label")
        self.assertTrue(
            self.project.label_set.filter(
                description="Edited description for Test Label"
            ).exists()
        )

    def test_delete(self) -> None:
        self.test_create()
        label = self.project.label_set.get()
        response = self.client.post(
            reverse(
                "label_delete", kwargs={"project": self.project.slug, "pk": label.pk}
            ),
            follow=True,
        )
        self.assertRedirects(response, self.labels_url)
        self.assertNotContains(response, "Test label")
        self.assertFalse(self.project.label_set.filter(name="Test label").exists())

    def test_assign(self) -> None:
        self.test_create()
        label = self.project.label_set.get()
        unit = self.get_unit().source_unit
        self.client.post(
            reverse("edit_context", kwargs={"pk": unit.pk}),
            {"explanation": "", "extra_flags": "", "labels": label.pk},
        )
        translation = self.get_translation()
        self.assertEqual(getattr(translation.stats, "label:Test label"), 1)

        self.client.post(
            reverse("edit_context", kwargs={"pk": unit.pk}),
            {"explanation": "", "extra_flags": ""},
        )
        translation = self.get_translation()
        self.assertEqual(getattr(translation.stats, "label:Test label"), 0)

    def test_delete_assigned(self) -> None:
        self.test_create()
        label = self.project.label_set.get()
        unit = self.get_unit().source_unit
        self.client.post(
            reverse("edit_context", kwargs={"pk": unit.pk}),
            {"explanation": "", "extra_flags": "", "labels": label.pk},
        )
        translation = self.get_translation()
        self.assertEqual(getattr(translation.stats, "label:Test label"), 1)

        label.delete()

        translation = self.get_translation()
        with self.assertRaises(AttributeError):
            getattr(translation.stats, "label:Test label")
