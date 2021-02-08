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

"""Test for settings management."""

from django.test.utils import modify_settings
from django.urls import reverse

from weblate.trans.models import Change, Component, Project
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import create_test_billing


class SettingsTest(ViewTestCase):
    def test_project_denied(self):
        url = reverse("settings", kwargs=self.kw_project)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_project(self):
        self.project.add_user(self.user, "@Administration")
        self.project.component_set.update(license="MIT")
        url = reverse("settings", kwargs=self.kw_project)
        response = self.client.get(url)
        self.assertContains(response, "Settings")
        data = response.context["form"].initial
        data["web"] = "https://example.com/test/"
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Settings saved")
        self.assertEqual(
            Project.objects.get(pk=self.project.pk).web, "https://example.com/test/"
        )

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    def test_change_access(self):
        self.project.add_user(self.user, "@Administration")
        url = reverse("settings", kwargs=self.kw_project)

        # Get initial form data
        response = self.client.get(url)
        data = response.context["form"].initial
        data["access_control"] = Project.ACCESS_PROTECTED

        # No permissions
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "error_1_id_access_control")

        # Allow editing by creating billing plan
        billing = create_test_billing(self.user)
        billing.projects.add(self.project)

        # Editing should now work, but components do not have a license
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You must specify a license for these components")

        # Set component license
        self.project.component_set.update(license="MIT")

        # Editing should now work
        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, url)

        # Verify change has been done
        project = Project.objects.get(pk=self.project.pk)
        self.assertEqual(project.access_control, Project.ACCESS_PROTECTED)
        self.assertTrue(
            project.change_set.filter(action=Change.ACTION_ACCESS_EDIT).exists()
        )

    def test_component_denied(self):
        url = reverse("settings", kwargs=self.kw_component)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_component(self):
        self.project.add_user(self.user, "@Administration")
        url = reverse("settings", kwargs=self.kw_component)
        response = self.client.get(url)
        self.assertContains(response, "Settings")
        data = {}
        data.update(response.context["form"].initial)
        data["license"] = "MIT"
        data["enforced_checks"] = ["same", "duplicate"]
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Settings saved")
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.license, "MIT")
        self.assertEqual(component.enforced_checks, ["same", "duplicate"])

    def test_shared_component(self):
        self.project.add_user(self.user, "@Administration")
        url = reverse("settings", kwargs=self.kw_component)

        # Create extra project
        other = Project.objects.create(name="Other", slug="other")

        response = self.client.get(url)
        self.assertContains(response, "Settings")
        data = {}
        data.update(response.context["form"].initial)
        data["links"] = other.pk
        del data["enforced_checks"]

        # Can not add link to non owned project
        response = self.client.post(url, data, follow=True)
        self.assertNotContains(response, "Settings saved")
        response = self.client.get(other.get_absolute_url())
        self.assertNotContains(response, self.component.get_absolute_url())

        # Add link to owned project
        other.add_user(self.user, "@Administration")
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Settings saved")
        response = self.client.get(other.get_absolute_url())
        self.assertContains(response, self.component.get_absolute_url())
