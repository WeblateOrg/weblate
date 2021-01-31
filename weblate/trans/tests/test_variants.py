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

"""Test for variants."""

from weblate.trans.models import Variant
from weblate.trans.tests.test_views import ViewTestCase


class VariantTest(ViewTestCase):
    def create_component(self):
        return self.create_android()

    def add_variants(self, suffix: str = ""):
        request = self.get_request()
        translation = self.component.source_translation
        translation.add_units(
            request,
            [
                (f"bar{suffix}", "Default string", None),
                ("barMin", "Min string", None),
                ("barShort", "Short string", None),
            ],
        )

    def test_edit_component(self, suffix: str = ""):
        self.add_variants()
        self.assertEqual(Variant.objects.count(), 0)
        self.component.variant_regex = "(Min|Short|Max)$"
        self.component.save()
        self.assertEqual(Variant.objects.count(), 1)
        self.assertEqual(Variant.objects.get().unit_set.count(), 6)
        self.component.variant_regex = ""
        self.component.save()
        self.assertEqual(Variant.objects.count(), 0)

    def test_add_units(self, suffix: str = ""):
        self.component.variant_regex = "(Min|Short|Max)$"
        self.component.save()
        self.assertEqual(Variant.objects.count(), 0)
        self.add_variants(suffix)
        self.assertEqual(Variant.objects.count(), 1)
        self.assertEqual(Variant.objects.get().unit_set.count(), 6)

    def test_edit_component_suffix(self):
        self.test_edit_component("Max")

    def test_add_units_suffix(self):
        self.test_add_units("Max")

    def test_variants_inner(self):
        self.component.variant_regex = (
            "//(SCRTEXT_S|SCRTEXT_M|SCRTEXT_L|REPTEXT|DDTEXT)"
        )
        self.component.save()
        units = (
            "DTEL///ABSD/DE_INTEND_POSTBACKGR//SCRTEXT_M 00001",
            "DTEL///ABSD/DE_INTEND_POSTBACKGR//REPTEXT 00001",
            "DTEL///ABSD/DE_INTEND_POSTBACKGR//SCRTEXT_L 00001",
            "DTEL///ABSD/DE_INTEND_POSTBACKGR//SCRTEXT_S 00001",
            "DTEL///ABSD/DE_INTEND_POSTBACKGR//DDTEXT 00001",
        )
        request = self.get_request()
        translation = self.component.source_translation
        translation.add_units(request, [(key, "Test string", None) for key in units])
        self.assertEqual(Variant.objects.count(), 1)
        self.assertEqual(Variant.objects.get().unit_set.count(), 10)

    def test_variants_flag(self, code: str = "en"):
        self.add_variants()
        self.assertEqual(Variant.objects.count(), 0)
        translation = self.component.translation_set.get(language_code=code)

        unit = translation.unit_set.get(context="barMin")
        unit.extra_flags = "variant:'Default string'"
        unit.save()
        self.assertEqual(Variant.objects.count(), 1)
        self.assertEqual(Variant.objects.get().unit_set.count(), 4)

        unit = translation.unit_set.get(context="barShort")
        unit.extra_flags = "variant:'Default string'"
        unit.save()
        self.assertEqual(Variant.objects.count(), 1)
        self.assertEqual(Variant.objects.get().unit_set.count(), 6)

        unit = translation.unit_set.get(context="barMin")
        unit.extra_flags = ""
        unit.save()
        self.assertEqual(Variant.objects.count(), 1)
        self.assertEqual(Variant.objects.get().unit_set.count(), 4)

        unit = translation.unit_set.get(context="barShort")
        unit.extra_flags = ""
        unit.save()
        self.assertEqual(Variant.objects.count(), 0)

    def test_variants_flag_translation(self):
        self.test_variants_flag("cs")
