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

"""Test for AJAX/JS views."""


import json

from django.urls import reverse

import weblate.machinery
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.classloader import load_class


class JSViewsTest(FixtureTestCase):
    """Testing of AJAX/JS views."""

    @staticmethod
    def ensure_dummy_mt():
        """Ensure we have dummy mt installed."""
        if "dummy" in weblate.machinery.MACHINE_TRANSLATION_SERVICES:
            return
        name = "weblate.machinery.dummy.DummyTranslation"
        service = load_class(name, "TEST")()
        weblate.machinery.MACHINE_TRANSLATION_SERVICES[service.mtid] = service

    def test_translate(self):
        self.ensure_dummy_mt()
        unit = self.get_unit()
        response = self.client.post(
            reverse("js-translate", kwargs={"unit_id": unit.id, "service": "dummy"})
        )
        self.assertContains(response, "Ahoj")
        data = json.loads(response.content.decode())
        self.assertEqual(
            data["translations"],
            [
                {
                    "quality": 100,
                    "service": "Dummy",
                    "text": "Nazdar světe!",
                    "source": "Hello, world!\n",
                },
                {
                    "quality": 100,
                    "service": "Dummy",
                    "text": "Ahoj světe!",
                    "source": "Hello, world!\n",
                },
            ],
        )

        # Invalid service
        response = self.client.post(
            reverse("js-translate", kwargs={"unit_id": unit.id, "service": "invalid"})
        )
        self.assertEqual(response.status_code, 404)

    def test_memory(self):
        unit = self.get_unit()
        url = reverse("js-memory", kwargs={"unit_id": unit.id})
        # Missing param
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        # Valid query
        response = self.client.post(url, {"q": "a"})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertEqual(data["service"], "Weblate Translation Memory")

    def test_get_unit_translations(self):
        unit = self.get_unit()
        response = self.client.get(
            reverse("js-unit-translations", kwargs={"unit_id": unit.id})
        )
        self.assertContains(response, 'href="/translate/')
