# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.urls import reverse

from weblate.fonts.models import Font, FontGroup
from weblate.fonts.tests.utils import FONT, FontTestCase
from weblate.lang.models import Language


class FontViewTest(FontTestCase):
    @property
    def fonts_url(self):
        return reverse("fonts", kwargs=self.kw_project)

    def test_noperm(self) -> None:
        font = self.add_font()
        response = self.client.get(self.fonts_url)
        self.assertContains(response, font.family)
        self.assertNotContains(response, "Add font")

    def test_manage(self) -> None:
        self.user.is_superuser = True
        self.user.save()

        # Validate the form is there
        response = self.client.get(self.fonts_url)
        self.assertContains(response, "Add font")

        # Upload font
        with open(FONT, "rb") as handle:
            response = self.client.post(self.fonts_url, {"font": handle}, follow=True)
            self.assertContains(response, "Kurinto Sans")
        font = Font.objects.get()
        self.assertContains(self.client.get(font.get_absolute_url()), "Kurinto Sans")

        # Create font group
        response = self.client.post(
            self.fonts_url, {"name": "font-group", "font": font.pk}, follow=True
        )
        self.assertContains(response, "font-group")
        group = FontGroup.objects.get()
        self.assertContains(self.client.get(group.get_absolute_url()), "font-group")

        # Add override
        language = Language.objects.get(code="zh_Hant")
        response = self.client.post(
            group.get_absolute_url(),
            {"language": language.pk, "font": font.pk},
            follow=True,
        )
        self.assertContains(response, language.name)
        override = group.fontoverride_set.get()

        # Remove override
        self.client.post(
            group.get_absolute_url(), {"override": override.pk}, follow=True
        )
        self.assertEqual(group.fontoverride_set.count(), 0)

        # Remove group
        self.client.post(group.get_absolute_url())
        self.assertEqual(FontGroup.objects.count(), 0)

        # Remove font
        self.client.post(font.get_absolute_url())
        self.assertEqual(Font.objects.count(), 0)
