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
from unittest import SkipTest

from django.urls import reverse

import weblate.screenshots.views
from weblate.screenshots.models import Screenshot
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.utils.db import using_postgresql

TEST_SCREENSHOT = get_test_file("screenshot.png")


class ViewTest(FixtureTestCase):
    @classmethod
    def _databases_support_transactions(cls):
        # This is workaroud for MySQL as FULL TEXT index does not work
        # well inside a transaction, so we avoid using transactions for
        # tests. Otherwise we end up with no matches for the query.
        # See https://dev.mysql.com/doc/refman/5.6/en/innodb-fulltext-index.html
        if not using_postgresql():
            return False
        return super()._databases_support_transactions()

    def test_list_empty(self):
        response = self.client.get(reverse("screenshots", kwargs=self.kw_component))
        self.assertContains(response, "Screenshots")

    def do_upload(self, **kwargs):
        with open(TEST_SCREENSHOT, "rb") as handle:
            data = {
                "image": handle,
                "name": "Obrazek",
                "translation": self.component.source_translation.pk,
            }
            data.update(kwargs)
            return self.client.post(
                reverse("screenshots", kwargs=self.kw_component), data, follow=True
            )

    def test_upload_denied(self):
        response = self.do_upload()
        self.assertEqual(response.status_code, 403)

    def test_upload(self):
        self.make_manager()
        response = self.do_upload()
        self.assertContains(response, "Obrazek")
        self.assertEqual(Screenshot.objects.count(), 1)

    def test_upload_fail(self):
        self.make_manager()
        response = self.do_upload(name="")
        self.assertContains(response, "Failed to upload screenshot")
        response = self.do_upload(image="")
        self.assertContains(response, "Failed to upload screenshot")

    def test_upload_source(self):
        self.make_manager()
        source = self.component.source_translation.unit_set.all()[0]
        response = self.do_upload(source=source.pk)
        self.assertContains(response, "Obrazek")
        self.assertEqual(Screenshot.objects.count(), 1)
        screenshot = Screenshot.objects.all()[0]
        self.assertEqual(screenshot.name, "Obrazek")
        self.assertEqual(screenshot.units.count(), 1)

    def test_upload_source_invalid(self):
        self.make_manager()
        response = self.do_upload(source="wrong")
        self.assertContains(response, "Obrazek")

    def test_edit(self):
        self.make_manager()
        self.do_upload()
        screenshot = Screenshot.objects.all()[0]
        response = self.client.post(
            screenshot.get_absolute_url(), {"name": "Picture"}, follow=True
        )
        self.assertContains(response, "Picture")
        self.assertEqual(Screenshot.objects.all()[0].name, "Picture")

    def test_delete(self):
        self.make_manager()
        self.do_upload()
        screenshot = Screenshot.objects.all()[0]
        self.client.post(reverse("screenshot-delete", kwargs={"pk": screenshot.pk}))
        self.assertEqual(Screenshot.objects.count(), 0)

    def extract_pk(self, data):
        return int(data.split('data-pk="')[1].split('"')[0])

    def test_source_manipulations(self):
        self.make_manager()
        self.do_upload()
        screenshot = Screenshot.objects.all()[0]

        # Search for string
        response = self.client.post(
            reverse("screenshot-js-search", kwargs={"pk": screenshot.pk}),
            {"q": "hello"},
        )
        data = response.json()
        self.assertEqual(data["responseCode"], 200)
        self.assertIn('<a class="add-string', data["results"])

        source_pk = self.extract_pk(data["results"])

        self.assertEqual(
            source_pk,
            self.component.source_translation.unit_set.search("hello").get().pk,
        )

        # Add found string
        response = self.client.post(
            reverse("screenshot-js-add", kwargs={"pk": screenshot.pk}),
            {"source": source_pk},
        )
        data = response.json()
        self.assertEqual(data["responseCode"], 200)
        self.assertEqual(data["status"], True)
        self.assertEqual(screenshot.units.count(), 1)

        # Updated listing
        response = self.client.get(
            reverse("screenshot-js-get", kwargs={"pk": screenshot.pk})
        )
        self.assertContains(response, "Hello")

        # Remove added string
        self.client.post(
            reverse("screenshot-remove-source", kwargs={"pk": screenshot.pk}),
            {"source": source_pk},
        )
        self.assertEqual(screenshot.units.count(), 0)

    def test_ocr(self):
        if not weblate.screenshots.views.HAS_OCR:
            raise SkipTest("OCR not supported")
        self.make_manager()
        self.do_upload()
        screenshot = Screenshot.objects.all()[0]

        # Search for string
        response = self.client.post(
            reverse("screenshot-js-ocr", kwargs={"pk": screenshot.pk})
        )
        data = response.json()

        self.assertEqual(data["responseCode"], 200)
        # We should find at least one string
        self.assertIn('<a class="add-string', data["results"])

    def test_ocr_disabled(self):
        orig = weblate.screenshots.views.HAS_OCR
        weblate.screenshots.views.HAS_OCR = False
        try:
            self.make_manager()
            self.do_upload()
            screenshot = Screenshot.objects.all()[0]

            # Search for string
            response = self.client.post(
                reverse("screenshot-js-ocr", kwargs={"pk": screenshot.pk})
            )
            data = response.json()

            self.assertEqual(data["responseCode"], 500)
        finally:
            weblate.screenshots.views.HAS_OCR = orig

    def test_translation_manipulations(self):
        self.make_manager()
        translation = self.component.translation_set.get(language_code="cs")
        self.do_upload(translation=translation.pk)
        screenshot = Screenshot.objects.all()[0]

        # Search for string
        response = self.client.post(
            reverse("screenshot-js-search", kwargs={"pk": screenshot.pk}),
            {"q": "hello"},
        )
        data = response.json()
        self.assertEqual(data["responseCode"], 200)
        self.assertIn('<a class="add-string', data["results"])

        source_pk = self.extract_pk(data["results"])
        self.assertEqual(source_pk, translation.unit_set.search("hello").get().pk)

        # Add found string
        response = self.client.post(
            reverse("screenshot-js-add", kwargs={"pk": screenshot.pk}),
            {"source": source_pk},
        )
        data = response.json()
        self.assertEqual(data["responseCode"], 200)
        self.assertEqual(data["status"], True)
        self.assertEqual(screenshot.units.count(), 1)

        # Updated listing
        response = self.client.get(
            reverse("screenshot-js-get", kwargs={"pk": screenshot.pk})
        )
        self.assertContains(response, "Hello")

        # Remove added string
        self.client.post(
            reverse("screenshot-remove-source", kwargs={"pk": screenshot.pk}),
            {"source": source_pk},
        )
        self.assertEqual(screenshot.units.count(), 0)
