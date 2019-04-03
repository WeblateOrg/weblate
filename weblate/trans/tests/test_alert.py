# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

"""Test for alerts"""

from django.test.utils import override_settings

from weblate.trans.tests.test_views import ViewTestCase


class AlertTest(ViewTestCase):
    def create_component(self):
        return self._create_component(
            'po',
            'po-duplicates/*.dpo',
        )

    def test_duplicates(self):
        self.assertEqual(self.component.alert_set.count(), 3)
        alert = self.component.alert_set.get(name='DuplicateLanguage')
        self.assertEqual(
            alert.details['occurrences'][0]['language_code'],
            'cs',
        )
        alert = self.component.alert_set.get(name='DuplicateString')
        self.assertEqual(
            alert.details['occurrences'][0]['source'],
            'Thank you for using Weblate.'
        )
        alert = self.component.alert_set.get(name='MissingLicense')

    def test_view(self):
        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, 'Duplicated translation')

    def test_license(self):
        def has_license_alert(component):
            return component.alert_set.filter(name='MissingLicense').exists()

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
        with override_settings(LOGIN_REQUIRED_URLS=['some']):
            component.update_alerts()
            self.assertFalse(has_license_alert(component))

        # Set license
        component.license = 'license'
        component.update_alerts()
        self.assertFalse(has_license_alert(component))

    def test_monolingual(self):
        component = self.component
        component.update_alerts()
        self.assertFalse(
            component.alert_set.filter(name='MonolingualTranslation').exists()
        )


class MonolingualAlertTest(ViewTestCase):
    def create_component(self):
        return self.create_po_mono()

    def test_monolingual(self):
        def has_monolingual_alert(component):
            return component.alert_set.filter(
                name='MonolingualTranslation'
            ).exists()

        component = self.component
        component.update_alerts()
        self.assertFalse(has_monolingual_alert(component))

        self.component.template = ''
        self.component.save()
        self.assertTrue(has_monolingual_alert(component))
