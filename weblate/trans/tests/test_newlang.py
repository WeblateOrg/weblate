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

"""Test for adding new language."""

from django.core import mail
from django.urls import reverse

from weblate.auth.models import Permission, Role
from weblate.utils.ratelimit import reset_rate_limit

from .test_views import ViewTestCase


class NewLangTest(ViewTestCase):
    expected_lang_code = "pt_BR"

    def setUp(self):
        super().setUp()
        self.reset_rate()

    def reset_rate(self):
        reset_rate_limit("language", user=self.user)

    def create_component(self):
        return self.create_po_new_base(new_lang="add")

    def test_no_permission(self):
        # Remove permission to add translations
        Role.objects.get(name="Power user").permissions.remove(
            Permission.objects.get(codename="translation.add")
        )

        # Test there is no add form
        response = self.client.get(reverse("component", kwargs=self.kw_component))
        self.assertContains(response, "Start new translation")
        self.assertContains(response, "permission to start a new translation")

        # Test adding fails
        response = self.client.post(
            reverse("new-language", kwargs=self.kw_component), {"lang": "af"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            self.component.translation_set.filter(language__code="af").exists()
        )

    def test_none(self):
        self.component.new_lang = "none"
        self.component.save()

        response = self.client.get(reverse("component", kwargs=self.kw_component))
        self.assertContains(response, "Start new translation")
        self.assertNotContains(response, "/new-lang/")

    def test_url(self):
        self.component.new_lang = "url"
        self.component.save()
        self.project.instructions = "http://example.com/instructions"
        self.project.save()

        response = self.client.get(reverse("component", kwargs=self.kw_component))
        self.assertContains(response, "Start new translation")
        self.assertContains(response, "http://example.com/instructions")

    def test_contact(self):
        # Make admin to receive notifications
        self.project.add_user(self.anotheruser, "@Administration")

        self.component.new_lang = "contact"
        self.component.save()

        response = self.client.get(reverse("component", kwargs=self.kw_component))
        self.assertContains(response, "Start new translation")
        self.assertContains(response, "/new-lang/")

        response = self.client.post(
            reverse("new-language", kwargs=self.kw_component), {"lang": "af"}
        )
        self.assertRedirects(response, self.component.get_absolute_url())

        # Verify mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject, "[Weblate] New language request in Test/Test"
        )

    def test_add(self):
        # Make admin to receive notifications
        self.project.add_user(self.anotheruser, "@Administration")

        self.assertFalse(
            self.component.translation_set.filter(language__code="af").exists()
        )

        response = self.client.get(reverse("component", kwargs=self.kw_component))
        self.assertContains(response, "Start new translation")
        self.assertContains(response, "/new-lang/")

        lang = {"lang": "af"}
        response = self.client.post(
            reverse("new-language", kwargs=self.kw_component), lang
        )
        lang.update(self.kw_component)
        self.assertRedirects(response, reverse("translation", kwargs=lang))
        self.assertTrue(
            self.component.translation_set.filter(language__code="af").exists()
        )

        # Verify mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject, "[Weblate] New language added to Test/Test"
        )

        # Not selected language
        self.reset_rate()
        response = self.client.post(
            reverse("new-language", kwargs=self.kw_component), {"lang": ""}, follow=True
        )
        self.assertContains(response, "Please fix errors in the form")

        # Existing language
        self.reset_rate()
        response = self.client.post(
            reverse("new-language", kwargs=self.kw_component),
            {"lang": "af"},
            follow=True,
        )
        self.assertContains(response, "Please fix errors in the form")

    def test_add_owner(self):
        self.component.project.add_user(self.user, "@Administration")
        # None chosen
        response = self.client.post(
            reverse("new-language", kwargs=self.kw_component), follow=True
        )
        self.assertContains(response, "Please fix errors in the form")
        # One chosen
        self.reset_rate()
        response = self.client.post(
            reverse("new-language", kwargs=self.kw_component),
            {"lang": "af"},
            follow=True,
        )
        self.assertNotContains(response, "Please fix errors in the form")
        # More chosen
        self.reset_rate()
        response = self.client.post(
            reverse("new-language", kwargs=self.kw_component),
            {"lang": ["nl", "fr", "uk"]},
            follow=True,
        )
        self.assertNotContains(response, "Please fix errors in the form")
        self.assertEqual(
            self.component.translation_set.filter(
                language__code__in=("af", "nl", "fr", "uk")
            ).count(),
            4,
        )

    def test_add_rejected(self):
        self.component.project.add_user(self.user, "@Administration")
        self.component.language_regex = "^cs$"
        self.component.save()
        # One chosen
        response = self.client.post(
            reverse("new-language", kwargs=self.kw_component),
            {"lang": "af"},
            follow=True,
        )
        self.assertContains(
            response, "The given language is filtered by the language filter."
        )

    def test_add_code(self):
        def perform(style, code, expected):
            self.component.language_code_style = style
            self.component.save()

            self.assertFalse(
                self.component.translation_set.filter(language__code=code).exists(),
                f"Translation with code {code} already exists",
            )
            self.reset_rate()
            self.client.post(
                reverse("new-language", kwargs=self.kw_component), {"lang": code}
            )
            translation = self.component.translation_set.get(language__code=code)
            self.assertEqual(translation.language_code, expected)
            translation.remove(self.user)

        perform("", "pt_BR", self.expected_lang_code)
        perform("posix", "pt_BR", "pt_BR")
        perform("posix_long", "ms", "ms_MY")
        perform("bcp", "pt_BR", "pt-BR")
        perform("bcp_long", "ms", "ms-MY")
        perform("android", "pt_BR", "pt-rBR")

        self.project.language_aliases = "ia_FOO:ia"
        self.project.save()
        perform("android", "ia", "ia_FOO")


class AndroidNewLangTest(NewLangTest):
    expected_lang_code = "pt-rBR"

    def create_component(self):
        return self.create_android(new_lang="add")
