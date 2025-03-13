# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import TestCase
from django.urls import reverse

from .models import Setting, SettingCategory
from .views import CustomCSSView


class SettingsTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        CustomCSSView.drop_cache()

    def test_blank(self) -> None:
        response = self.client.get(reverse("css-custom"))
        self.assertEqual(response.content.decode().strip(), "")

    def test_cache(self) -> None:
        Setting.objects.create(
            category=SettingCategory.UI, name="hide_footer", value=True
        )
        response = self.client.get(reverse("css-custom"))
        self.assertNotEqual(response.content.decode().strip(), "")
        # Delete all UI settings
        Setting.objects.filter(category=SettingCategory.UI).delete()
        # The response should be cached
        response = self.client.get(reverse("css-custom"))
        self.assertNotEqual(response.content.decode().strip(), "")
        # Invalidate cache
        CustomCSSView.drop_cache()
        response = self.client.get(reverse("css-custom"))
        self.assertEqual(response.content.decode().strip(), "")

    def test_split_colors(self) -> None:
        self.assertEqual([None, None], CustomCSSView.split_colors(""))
        self.assertEqual([None, None], CustomCSSView.split_colors(None))
        self.assertEqual(["#ffffff", "#ffffff"], CustomCSSView.split_colors("#ffffff"))
        self.assertEqual(
            ["#ffffff", "#000000"], CustomCSSView.split_colors("#ffffff,#000000")
        )
