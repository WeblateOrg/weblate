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

"""Test for alerts."""

from django.test.utils import override_settings
from django.urls import reverse

from weblate.lang.models import Language
from weblate.trans.tests.test_views import ViewTestCase


class AlertTest(ViewTestCase):
    def create_component(self):
        return self._create_component("po", "po-duplicates/*.dpo")

    def test_duplicates(self):
        self.assertEqual(
            set(self.component.alert_set.values_list("name", flat=True)),
            {
                "DuplicateLanguage",
                "DuplicateString",
                "MissingLicense",
                "BrokenBrowserURL",
                "BrokenProjectURL",
            },
        )
        alert = self.component.alert_set.get(name="DuplicateLanguage")
        self.assertEqual(alert.details["occurrences"][0]["language_code"], "cs")
        alert = self.component.alert_set.get(name="DuplicateString")
        self.assertEqual(
            alert.details["occurrences"][0]["source"], "Thank you for using Weblate."
        )

    def test_unused_enforced(self):
        self.assertEqual(
            set(self.component.alert_set.values_list("name", flat=True)),
            {
                "DuplicateLanguage",
                "DuplicateString",
                "MissingLicense",
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
                "MissingLicense",
                "BrokenBrowserURL",
                "BrokenProjectURL",
                "UnusedEnforcedCheck",
            },
        )

    def test_dismiss(self):
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("dismiss-alert", kwargs=self.kw_component),
            {"dismiss": "BrokenBrowserURL"},
        )
        self.assertRedirects(response, self.component.get_absolute_url() + "#alerts")
        self.assertTrue(self.component.alert_set.get(name="BrokenBrowserURL").dismissed)

    def test_view(self):
        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "Duplicated translation")

    def test_license(self):
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

    def test_monolingual(self):
        component = self.component
        component.update_alerts()
        self.assertFalse(
            component.alert_set.filter(name="MonolingualTranslation").exists()
        )


class LanguageAlertTest(ViewTestCase):
    def create_component(self):
        return self.create_po_new_base(new_lang="add")

    def test_ambiguous_language(self):
        component = self.component
        self.assertFalse(component.alert_set.filter(name="AmbiguousLanguage").exists())
        self.component.add_new_language(
            Language.objects.get(code="ku"), self.get_request()
        )
        self.component.update_alerts()
        self.assertTrue(component.alert_set.filter(name="AmbiguousLanguage").exists())


class MonolingualAlertTest(ViewTestCase):
    def create_component(self):
        return self.create_po_mono()

    def test_monolingual(self):
        self.assertFalse(
            self.component.alert_set.filter(name="MonolingualTranslation").exists()
        )

    def test_false_bilingual(self):
        component = self._create_component(
            "po-mono", "po-mono/*.po", project=self.project, name="bimono"
        )
        self.assertTrue(
            component.alert_set.filter(name="MonolingualTranslation").exists()
        )
