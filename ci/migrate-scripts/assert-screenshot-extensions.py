# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify repaired files and screenshot relationships after a populated upgrade."""

from __future__ import annotations

import hashlib
import json

from django.apps import apps

Screenshot = apps.get_model("screenshots", "Screenshot")
# ruff: ignore[private-member-access]
storage = Screenshot._meta.get_field("image").storage
with storage.open("screenshot-extension-upgrade.json", "rb") as handle:
    manifest = json.load(handle)

destinations = {}
for original in manifest:
    screenshot = Screenshot.objects.get(pk=original["pk"])
    assert screenshot.name == original["name"]
    assert screenshot.translation_id == original["translation_id"]
    assert screenshot.user_id == original["user_id"]
    assert screenshot.timestamp.isoformat() == original["timestamp"]
    assert list(screenshot.units.values_list("pk", flat=True)) == [original["unit_id"]]
    if original["repair"]:
        assert screenshot.image.name != original["image"]
        assert screenshot.image.name.endswith(".png")
    else:
        assert screenshot.image.name == original["image"]
    if original["digest"] is not None:
        with storage.open(screenshot.image.name, "rb") as handle:
            assert hashlib.sha256(handle.read()).hexdigest() == original["digest"]
        assert storage.exists(original["image"])
    else:
        assert not storage.exists(screenshot.image.name)
    previous = destinations.setdefault(original["image"], screenshot.image.name)
    assert previous == screenshot.image.name

assert len(set(destinations.values())) == len(destinations)
