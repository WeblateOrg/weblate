# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for alerts."""

from django.test.utils import override_settings
from django.urls import reverse

from weblate.lang.models import Language
from weblate.trans.models import Unit
from weblate.trans.tests.test_views import ViewTestCase


class AlertTest(ViewTestCase):
    def create_component(self):
        return self._create_component("po", "po-duplicates/*.dpo", manage_units=True)

    def test_duplicates(self) -> None:
        self.assertEqual(
            set(self.component.alert_set.values_list("name", flat=True)),
            {
                "DuplicateLanguage",
                "DuplicateString",
                "BrokenBrowserURL",
                "BrokenProjectURL",
            },
        )
        alert = self.component.alert_set.get(name="DuplicateLanguage")
        self.assertEqual(alert.details["occurrences"][0]["language_code"], "cs")
        alert = self.component.alert_set.get(name="DuplicateString")
        occurrences = alert.details["occurrences"]
        self.assertEqual(len(occurrences), 1)
        self.assertEqual(occurrences[0]["source"], "Thank you for using Weblate.")
        # There should be single unit
        unit = Unit.objects.filter(
            pk__in={item["unit_pk"] for item in occurrences}
        ).get()
        # Remove the unit
        unit.translation.delete_unit(None, unit)

        # The alert should have been removed now
        self.assertEqual(
            set(self.component.alert_set.values_list("name", flat=True)),
            {
                "DuplicateLanguage",
                "BrokenBrowserURL",
                "BrokenProjectURL",
            },
        )

    def test_unused_enforced(self) -> None:
        self.assertEqual(
            set(self.component.alert_set.values_list("name", flat=True)),
            {
                "DuplicateLanguage",
                "DuplicateString",
                "BrokenBrowserURL",
                "BrokenProjectURL",
            },
        )
        self.component.enforced_checks = ["es_format"]
        self.component.save()
        self.assertEqual(
            set(self.component.alert_set.values_list("name", flat=True)),
            {
                "DuplicateLanguage",
                "DuplicateString",
                "BrokenBrowserURL",
                "BrokenProjectURL",
                "UnusedEnforcedCheck",
            },
        )

    def test_dismiss(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("dismiss-alert", kwargs=self.kw_component),
            {"dismiss": "BrokenBrowserURL"},
        )
        self.assertRedirects(response, self.component.get_absolute_url() + "#alerts")
        self.assertTrue(self.component.alert_set.get(name="BrokenBrowserURL").dismissed)

    def test_view(self) -> None:
        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "Duplicated translation")

    @override_settings(LICENSE_REQUIRED=True)
    def test_license(self) -> None:
        def has_license_alert(component):
            return component.alert_set.filter(name="MissingLicense").exists()

        # No license and public project
        component = self.component
        component.update_alerts()
        self.assertTrue(has_license_alert(component))

        # Private project
        component.project.access_control = component.project.ACCESS_PRIVATE
        component.update_alerts()
        self.assertFalse(has_license_alert(component))

        # Public, but login required
        component.project.access_control = component.project.ACCESS_PUBLIC
        with override_settings(LOGIN_REQUIRED_URLS=["some"]):
            component.update_alerts()
            self.assertFalse(has_license_alert(component))

        # Filtered licenses
        with override_settings(LICENSE_FILTER=set()):
            component.update_alerts()
            self.assertFalse(has_license_alert(component))

        # Filtered licenses
        with override_settings(LICENSE_FILTER={"proprietary"}):
            component.update_alerts()
            self.assertTrue(has_license_alert(component))

        # Set license
        component.license = "license"
        component.update_alerts()
        self.assertFalse(has_license_alert(component))

    def test_monolingual(self) -> None:
        component = self.component
        component.update_alerts()
        self.assertFalse(
            component.alert_set.filter(name="MonolingualTranslation").exists()
        )

    def test_duplicate_mask(self) -> None:
        component = self.component
        self.assertFalse(component.alert_set.filter(name="DuplicateFilemask").exists())
        response = self.client.get(component.get_absolute_url())
        self.assertNotContains(
            response, "The following files were found multiple times"
        )

        other = self.create_link_existing()

        self.assertTrue(component.alert_set.filter(name="DuplicateFilemask").exists())
        response = self.client.get(component.get_absolute_url())
        self.assertContains(response, "The following files were found multiple times")

        other.delete()

        self.assertFalse(component.alert_set.filter(name="DuplicateFilemask").exists())


class LanguageAlertTest(ViewTestCase):
    def create_component(self):
        return self.create_po_new_base(new_lang="add")

    def test_ambiguous_language(self) -> None:
        component = self.component
        self.assertFalse(component.alert_set.filter(name="AmbiguousLanguage").exists())
        component.add_new_language(Language.objects.get(code="ku"), self.get_request())
        component.update_alerts()
        self.assertTrue(component.alert_set.filter(name="AmbiguousLanguage").exists())


class MonolingualAlertTest(ViewTestCase):
    def create_component(self):
        return self.create_po_mono()

    def test_monolingual(self) -> None:
        self.assertFalse(
            self.component.alert_set.filter(name="MonolingualTranslation").exists()
        )

    def test_false_bilingual(self) -> None:
        component = self._create_component(
            "po-mono", "po-mono/*.po", project=self.project, name="bimono"
        )
        self.assertTrue(
            component.alert_set.filter(name="MonolingualTranslation").exists()
        )
