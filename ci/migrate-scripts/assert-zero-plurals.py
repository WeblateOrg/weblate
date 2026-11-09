# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify duplicate cleanup preserves references and unrelated definitions."""

from __future__ import annotations

from django.apps import apps

Plural = apps.get_model("lang", "Plural")
Translation = apps.get_model("trans", "Translation")

translations = Translation.objects.filter(
    component__project__slug="zero-plural-upgrade"
).select_related("plural")
assert translations.count() == 6
zero = Plural.objects.get(language__code="qaa_ZERO", source=3)
assert zero.number == 3
# Normal post-migrate language setup synchronizes zero plurals to their baseline.
assert zero.formula == "n==0 ? 0 : n==1 ? 1 : 2"
for index in range(3):
    translation = translations.get(component__slug=f"plural-{index}")
    assert translation.plural_id == zero.pk
    assert translation.filename == f"plural-{index}.po"
singleton = translations.get(component__slug="plural-3").plural
assert singleton.language.code == "qab_ZERO"
assert singleton.source == 3
assert singleton.number == 3
assert singleton.formula == "n==0 ? 0 : n==1 ? 1 : 2"
manual = translations.filter(component__slug__in=["plural-4", "plural-5"])
assert len({translation.plural_id for translation in manual}) == 2
assert all(translation.plural.source == 2 for translation in manual)
