#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Test for variants."""


from django.urls import reverse

from weblate.trans.tests.test_views import ViewTestCase


class LabelTest(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.make_manager()
        self.labels_url = reverse("labels", kwargs=self.kw_project)

    def test_create(self):
        response = self.client.post(
            self.labels_url, {"name": "Test label", "color": "orange"}, follow=True
        )
        self.assertRedirects(response, self.labels_url)
        self.assertContains(response, "Test label")
        self.assertTrue(self.project.label_set.filter(name="Test label").exists())

    def test_edit(self):
        self.test_create()
        label = self.project.label_set.get()
        response = self.client.post(
            reverse(
                "label_edit", kwargs={"project": self.project.slug, "pk": label.pk}
            ),
            {"name": "Renamed label", "color": "orange"},
            follow=True,
        )
        self.assertRedirects(response, self.labels_url)
        self.assertContains(response, "Renamed label")
        self.assertTrue(self.project.label_set.filter(name="Renamed label").exists())

    def test_delete(self):
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

    def test_assign(self):
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
