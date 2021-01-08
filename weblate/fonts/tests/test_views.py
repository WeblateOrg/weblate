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
from django.urls import reverse

from weblate.fonts.models import Font, FontGroup
from weblate.fonts.tests.utils import FONT, FontTestCase
from weblate.lang.models import Language


class FontViewTest(FontTestCase):
    @property
    def fonts_url(self):
        return reverse("fonts", kwargs=self.kw_project)

    def test_noperm(self):
        font = self.add_font()
        response = self.client.get(self.fonts_url)
        self.assertContains(response, font.family)
        self.assertNotContains(response, "Add font")

    def test_manage(self):
        self.user.is_superuser = True
        self.user.save()

        # Validate the form is there
        response = self.client.get(self.fonts_url)
        self.assertContains(response, "Add font")

        # Upload font
        with open(FONT, "rb") as handle:
            response = self.client.post(self.fonts_url, {"font": handle}, follow=True)
            self.assertContains(response, "Droid Sans Fallback")
        font = Font.objects.get()
        self.assertContains(
            self.client.get(font.get_absolute_url()), "Droid Sans Fallback"
        )

        # Create font group
        response = self.client.post(
            self.fonts_url, {"name": "font-group", "font": font.pk}, follow=True
        )
        self.assertContains(response, "font-group")
        group = FontGroup.objects.get()
        self.assertContains(self.client.get(group.get_absolute_url()), "font-group")

        # Add override
        language = Language.objects.all()[0]
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
