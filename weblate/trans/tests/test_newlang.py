# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for adding new language."""

from django.core import mail
from django.urls import reverse

from weblate.auth.models import Permission, Role
from weblate.utils.ratelimit import reset_rate_limit

from .test_views import ViewTestCase


class NewLangTest(ViewTestCase):
    expected_lang_code = "pt_BR"

    def setUp(self) -> None:
        super().setUp()
        self.reset_rate()

    def reset_rate(self) -> None:
        reset_rate_limit("language", user=self.user)

    def create_component(self):
        return self.create_po_new_base(new_lang="add")

    def test_no_permission(self) -> None:
        # Remove permission to add translations
        Role.objects.get(name="Power user").permissions.remove(
            Permission.objects.get(codename="translation.add")
        )

        # Test there is no add form
        response = self.client.get(self.component.get_absolute_url())
        self.assertNotContains(response, "Start new translation")
        self.assertNotContains(response, "/new-lang/")

        # Test adding fails
        response = self.client.post(
            reverse("new-language", kwargs=self.kw_component),
            {"lang": "af"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            self.component.translation_set.filter(language__code="af").exists()
        )

    def test_none(self) -> None:
        self.component.new_lang = "none"
        self.component.save()

        response = self.client.get(self.component.get_absolute_url())
        self.assertNotContains(response, "Start new translation")
        self.assertNotContains(response, "/new-lang/")

    def test_url(self) -> None:
        self.component.new_lang = "url"
        self.component.save()
        self.project.instructions = "http://example.com/instructions"
        self.project.save()

        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "Start new translation")
        self.assertContains(response, "http://example.com/instructions")

    def test_contact(self) -> None:
        # Make admin to receive notifications
        self.project.add_user(self.anotheruser, "Administration")

        self.component.new_lang = "contact"
        self.component.save()

        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "Start new translation")
        self.assertContains(response, "/new-lang/")

        response = self.client.post(
            reverse("new-language", kwargs=self.kw_component),
            {"lang": "af"},
        )
        self.assertRedirects(response, self.component.get_absolute_url())

        # Verify mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject, "[Weblate] New language request in Test/Test"
        )

    def test_add(self) -> None:
        # Make admin to receive notifications
        self.project.add_user(self.anotheruser, "Administration")

        self.assertFalse(
            self.component.translation_set.filter(language__code="af").exists()
        )

        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "Start new translation")
        self.assertContains(response, "/new-lang/")

        lang = {"lang": "af"}
        response = self.client.post(
            reverse("new-language", kwargs=self.kw_component),
            lang,
        )
        translation = self.component.translation_set.get(language__code="af")
        self.assertRedirects(response, translation.get_absolute_url())

        # Verify mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject, "[Weblate] New language added to Test/Test"
        )

        # Not selected language
        self.reset_rate()
        response = self.client.post(
            reverse("new-language", kwargs=self.kw_component),
            {"lang": ""},
            follow=True,
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

    def test_add_owner(self) -> None:
        self.component.project.add_user(self.user, "Administration")
        # None chosen
        response = self.client.post(
            reverse("new-language", kwargs=self.kw_component),
            follow=True,
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

    def test_add_rejected(self) -> None:
        self.component.project.add_user(self.user, "Administration")
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

    def test_add_code(self) -> None:
        def perform(style, code, expected) -> None:
            self.component.language_code_style = style
            self.component.save()

            self.assertFalse(
                self.component.translation_set.filter(language__code=code).exists(),
                msg=f"Translation with code {code} already exists",
            )
            self.reset_rate()
            self.client.post(
                reverse("new-language", kwargs=self.kw_component),
                {"lang": code},
            )
            translation = self.component.translation_set.get(language__code=code)
            self.assertEqual(translation.language_code, expected)
            translation.remove(self.user)

        perform("", "pt_BR", self.expected_lang_code)
        perform("posix", "pt_BR", "pt_BR")
        perform("posix_long", "ms", "ms_MY")
        perform("posix_long_lowercase", "ms", "ms_my")
        perform("bcp", "pt_BR", "pt-BR")
        perform("bcp_long", "ms", "ms-MY")
        perform("android", "pt_BR", "pt-rBR")
        perform("linux_lowercase", "pt_BR", "pt_br")
        perform("linux_lowercase", "zh_Hant", "zh_tw")
        perform("posix_lowercase", "pt_BR", "pt_br")
        perform("posix_lowercase", "zh_Hant", "zh_hant")

        self.project.language_aliases = "ia_FOO:ia"
        self.project.save()
        perform("android", "ia", "ia_FOO")


class AndroidNewLangTest(NewLangTest):
    expected_lang_code = "pt-rBR"

    def create_component(self):
        return self.create_android(new_lang="add")
