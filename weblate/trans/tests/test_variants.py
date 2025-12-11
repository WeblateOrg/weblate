# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for variants."""

from django.urls import reverse

from weblate.trans.models import Variant
from weblate.trans.tests.test_views import ViewTestCase


class VariantTest(ViewTestCase):
    def create_component(self):
        return self.create_android()

    def add_variants(self, suffix: str = "") -> None:
        request = self.get_request()
        translation = self.component.source_translation
        translation.add_unit(request, f"bar{suffix}", "Default string", None)
        translation.add_unit(request, "barMin", "Min string", None)
        translation.add_unit(request, "barShort", "Short string", None)

    def test_edit_component(self, suffix: str = "") -> None:
        self.add_variants()
        self.assertEqual(Variant.objects.count(), 0)
        self.component.variant_regex = "(Min|Short|Max)$"
        self.component.save()
        self.assertEqual(Variant.objects.count(), 1)
        self.assertEqual(Variant.objects.get().unit_set.count(), 6)
        self.component.variant_regex = ""
        self.component.save()
        self.assertEqual(Variant.objects.count(), 0)

    def test_add_units(self, suffix: str = "") -> None:
        self.component.variant_regex = "(Min|Short|Max)$"
        self.component.save()
        self.assertEqual(Variant.objects.count(), 0)
        self.add_variants(suffix)
        self.assertEqual(Variant.objects.count(), 1)
        self.assertEqual(Variant.objects.get().unit_set.count(), 6)

    def test_edit_component_suffix(self) -> None:
        self.test_edit_component("Max")

    def test_add_units_suffix(self) -> None:
        self.test_add_units("Max")

    def test_variants_inner(self) -> None:
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
        for key in units:
            translation.add_unit(request, key, "Test string", None)
        self.assertEqual(Variant.objects.count(), 1)
        self.assertEqual(Variant.objects.get().unit_set.count(), 10)

    def test_variants_flag(self, code: str = "en") -> None:
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

    def test_variants_flag_delete(self, code: str = "en") -> None:
        self.add_variants()
        self.assertEqual(Variant.objects.count(), 0)
        translation = self.component.translation_set.get(language_code=code)

        unit = translation.unit_set.get(context="barMin")
        unit.extra_flags = "variant:'Default string'"
        unit.save()
        self.assertEqual(Variant.objects.count(), 1)
        self.assertEqual(Variant.objects.get().unit_set.count(), 4)

        translation.delete_unit(None, unit)
        self.assertEqual(Variant.objects.count(), 0)

    def test_variants_flag_translation(self) -> None:
        self.test_variants_flag("cs")

    def test_add_variant_unit(self) -> None:
        self.make_manager()
        translation = self.component.translation_set.get(language_code="cs")
        source = self.component.translation_set.get(language_code="en")
        base = source.unit_set.get(source="Thank you for using Weblate.")
        response = self.client.post(
            reverse("new-unit", kwargs={"path": source.get_url_path()}),
            {
                "context": "variantial",
                "source_0": "Source",
                "variant": base.id,
            },
            follow=True,
        )
        self.assertContains(response, "New string has been added")

        unit = translation.unit_set.get(context="variantial")
        self.assertEqual(
            unit.source_unit.extra_flags,
            f'variant:"{base.source}"',
        )
        variants = unit.defined_variants.all()
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0].unit_set.count(), 4)
        self.assertEqual(Variant.objects.count(), 1)

        base = source.unit_set.get(source="Hello, world!\n")
        response = self.client.post(
            reverse("new-unit", kwargs={"path": source.get_url_path()}),
            {"context": "variant2", "source_0": "Source", "variant": base.id},
            follow=True,
        )
        self.assertContains(response, "New string has been added")
        unit = translation.unit_set.get(context="variant2")
        self.assertEqual(unit.source_unit.extra_flags, r'variant:"Hello, world!\n"')
        variants = unit.defined_variants.all()
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0].unit_set.count(), 4)
        self.assertEqual(Variant.objects.count(), 2)
