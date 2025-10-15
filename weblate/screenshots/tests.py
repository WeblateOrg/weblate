# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os.path
import tempfile
from difflib import get_close_matches
from itertools import chain
from shutil import copyfile
from unittest.mock import patch

import requests
from django.core.files import File
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from weblate.lang.models import Language
from weblate.screenshots.models import Screenshot
from weblate.screenshots.views import get_tesseract, ocr_get_strings
from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import create_test_user, get_test_file
from weblate.utils.db import TransactionsTestMixin

TEST_SCREENSHOT = get_test_file("screenshot.png")


class ViewTest(TransactionsTestMixin, FixtureTestCase):
    def test_list_empty(self) -> None:
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
                reverse("screenshots", kwargs=self.kw_component),
                data,
                follow=True,
            )

    def test_upload_denied(self) -> None:
        response = self.do_upload()
        self.assertEqual(response.status_code, 403)

    def test_upload(self) -> None:
        self.make_manager()
        response = self.do_upload()
        self.assertContains(response, "Obrazek")
        self.assertEqual(Screenshot.objects.count(), 1)

    def test_upload_fail(self) -> None:
        self.make_manager()
        response = self.do_upload(name="")
        self.assertContains(response, "Could not upload screenshot")
        response = self.do_upload(image="")
        self.assertContains(response, "Could not upload screenshot")

    def test_upload_source(self) -> None:
        self.make_manager()
        source = self.component.source_translation.unit_set.all()[0]
        response = self.do_upload(source=source.pk)
        self.assertContains(response, "Obrazek")
        self.assertEqual(Screenshot.objects.count(), 1)
        screenshot = Screenshot.objects.all()[0]
        self.assertEqual(screenshot.name, "Obrazek")
        self.assertEqual(screenshot.units.count(), 1)

    def test_upload_source_invalid(self) -> None:
        self.make_manager()
        response = self.do_upload(source="wrong")
        self.assertContains(response, "Obrazek")

    def test_edit(self) -> None:
        self.make_manager()
        self.do_upload()
        screenshot = Screenshot.objects.all()[0]
        response = self.client.post(
            screenshot.get_absolute_url(), {"name": "Picture"}, follow=True
        )
        self.assertContains(response, "Picture")
        self.assertEqual(Screenshot.objects.all()[0].name, "Picture")

    def test_delete(self) -> None:
        self.make_manager()
        self.do_upload()
        screenshot = Screenshot.objects.all()[0]
        response = self.client.post(
            reverse("screenshot-delete", kwargs={"pk": screenshot.pk})
        )
        self.assertEqual(Screenshot.objects.count(), 0)
        self.assertRedirects(response, reverse("screenshots", kwargs=self.kw_component))

    def extract_pk(self, data):
        return int(data.split('data-pk="')[1].split('"')[0])

    def test_source_manipulations(self) -> None:
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

    def test_ocr_backend(self) -> None:
        # Extract strings
        with get_tesseract(Language.objects.get(code="en")) as api:
            result = list(ocr_get_strings(api, TEST_SCREENSHOT, 72))

        # Reverse logic would make sense here, but we want to use same order as in views.py
        matches = list(
            chain.from_iterable(
                get_close_matches(part, ["Hello, world!\n"], cutoff=0.9)
                for part in result
            )
        )

        self.assertTrue(
            matches, f"Could not find string in tesseract results: {result}"
        )

    def test_ocr(self) -> None:
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
        self.assertIn(
            '<a class="add-string',
            data["results"],
            "OCR recognition not working, no recognized strings found",
        )

    def test_translation_manipulations(self) -> None:
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

    @patch("weblate.screenshots.forms.requests.get")
    def test_upload_with_image_url(self, mock_get) -> None:
        with open(TEST_SCREENSHOT, "rb") as img_handle:
            mock_get.return_value.status_code = 200
            mock_get.return_value.content = img_handle.read()
            mock_get.return_value.headers = {"Content-Type": "image/png"}

        self.make_manager()
        response = self.do_upload(
            image="", image_url="https://example.com/test-image.png"
        )
        self.assertContains(response, "Obrazek")
        self.assertEqual(Screenshot.objects.count(), 1)

    @patch("weblate.screenshots.forms.requests.get")
    def test_image_url_download_failure(self, mock_requests_get):
        """Test handling of image download failures."""
        mock_requests_get.side_effect = requests.RequestException("Network error")
        self.make_manager()
        response = self.do_upload(
            image="", image_url="https://example.com/broken-image.png"
        )
        self.assertContains(
            response, ">Unable to download image from the provided URL (network error)"
        )

    def test_no_image_or_url_validation(self):
        """Test validation when neither image nor URL is provided."""
        self.make_manager()
        response = self.do_upload(image="")
        self.assertContains(
            response, "You need to provide either image file or image URL."
        )

    @patch("weblate.screenshots.forms.requests.get")
    def test_both_image_and_url_provided(self, mock_requests_get):
        """Test that providing both image file and URL prioritizes the file."""
        self.make_manager()
        self.do_upload(image_url="https://example.com/should-be-ignored.png")
        # screenshot from URL should not be downloaded
        mock_requests_get.assert_not_called()
        self.assertEqual(Screenshot.objects.count(), 1)

    @patch("weblate.screenshots.forms.requests.get")
    def test_invalid_image_url_content_type(self, mock_requests_get):
        self.make_manager()
        # Mock a non-image content type
        mock_requests_get.return_value.status_code = 200
        mock_requests_get.return_value.content = b"Not an image content"
        mock_requests_get.return_value.headers = {"Content-Type": "text/html"}
        response = self.do_upload(
            image="", image_url="https://example.com/not-an-image.png"
        )
        self.assertContains(response, "The uploaded image was invalid.")

    @patch("weblate.screenshots.forms.requests.get")
    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_disallowed_image_url_domain(self, mock_requests_get):
        """Test validation when image URL domain is not allowed."""
        self.make_manager()
        response = self.do_upload(
            image="", image_url="https://example.com/not-allowed-image.png"
        )
        mock_requests_get.assert_not_called()
        self.assertContains(response, "Image URL domain is not allowed.")


class ScreenshotVCSTest(APITestCase, RepoTestCase):
    """Test class for syncing vcs screenshots in weblate."""

    def setUp(self) -> None:
        super().setUp()
        self.user = create_test_user()
        self.user.is_superuser = True
        self.user.save()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.user.auth_token.key)
        self.client.login(username="testuser", password="testpassword")

        self.component = self._create_component(
            "json",
            "intermediate/*.json",
            screenshot_filemask="*.png",
        )

        # Add a screenshot linked to the component
        shot = Screenshot.objects.create(
            name="test-update",
            translation=self.component.source_translation,
            repository_filename="test-update.png",
        )
        with open(TEST_SCREENSHOT, "rb") as handle:
            data = handle.read()
            half_data_size = len(data) // 2
            with tempfile.NamedTemporaryFile(suffix="png") as temp_file:
                temp_file.write(data[:half_data_size])
                temp_file.flush()
                temp_file.seek(0)
                shot.image.save("test-update", File(temp_file))

    def test_update_screenshots_from_repo(self) -> None:
        repository = self.component.repository
        last_revision = repository.last_revision
        existing_ss_size = Screenshot.objects.filter(
            translation__component=self.component,
            repository_filename="test-update.png",
        )[0].image.size

        copyfile(TEST_SCREENSHOT, os.path.join(repository.path, "test-update.png"))
        with repository.lock:
            repository.set_committer("Second Bar", "second@example.net")
            filenames = ["test-update.png"]
            repository.commit(
                "Test commit", "Foo Bar <foo@bar.com>", timezone.now(), filenames
            )
            self.component.trigger_post_update(
                previous_head=last_revision,
                skip_push=True,
            )

        # Verify that screenshot has been updated after the signal.
        self.assertEqual(
            Screenshot.objects.filter(
                translation__component=self.component,
                repository_filename="test-update.png",
            ).count(),
            1,
        )
        updated_ss_size = Screenshot.objects.filter(
            translation__component=self.component,
            repository_filename="test-update.png",
        )[0].image.size
        self.assertNotEqual(existing_ss_size, updated_ss_size)

    def test_add_screenshots_from_repo(self) -> None:
        repository = self.component.repository
        last_revision = repository.last_revision

        copyfile(TEST_SCREENSHOT, os.path.join(repository.path, "test.png"))
        with repository.lock:
            repository.set_committer("Second Bar", "second@example.net")
            filenames = ["test.png"]
            repository.commit(
                "Test commit", "Foo Bar <foo@bar.com>", timezone.now(), filenames
            )
            self.component.trigger_post_update(
                previous_head=last_revision,
                skip_push=True,
            )

        # Verify that screenshot has been added after the signal.
        self.assertEqual(
            Screenshot.objects.filter(
                translation__component=self.component,
                repository_filename="test.png",
            ).count(),
            1,
        )
