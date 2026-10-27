# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Seed screenshot files and references on the release schema before upgrading."""

from __future__ import annotations

import hashlib
import json
from io import BytesIO

from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image

Screenshot = apps.get_model("screenshots", "Screenshot")
ScreenshotUnit = Screenshot.units.through
Translation = apps.get_model("trans", "Translation")
User = apps.get_model(settings.AUTH_USER_MODEL)
translation = Translation.objects.get(component__slug="test", language__code="cs")
unit = translation.unit_set.get(source="Hello, world!\n")
user = User.objects.bulk_create([User(username="screenshot-extension-upgrade")])[0]
# ruff: ignore[private-member-access]
storage = Screenshot._meta.get_field("image").storage

png = BytesIO()
Image.new("RGB", (2, 2), "red").save(png, format="PNG")
jpeg = BytesIO()
Image.new("RGB", (2, 2), "red").save(jpeg, format="JPEG")
cases = (
    ("collision.png", png.getvalue(), False),
    ("collision.pngrawtrue", png.getvalue(), True),
    ("collision.html", png.getvalue(), True),
    ("no-extension", png.getvalue(), True),
    ("wrong.jpg", png.getvalue(), True),
    ("matching.jpeg", jpeg.getvalue(), False),
    ("invalid.html", b"<html>not an image</html>", False),
    ("missing.pngrawtrue", None, False),
)
manifest = []
unit_links = []
for filename, content, repair in cases:
    name = f"screenshots/extension-upgrade-{filename}"
    storage.delete(name)
    if content is not None:
        assert storage.save(name, ContentFile(content)) == name
    screenshot = Screenshot.objects.bulk_create(
        [Screenshot(name=filename, image=name, translation=translation, user=user)]
    )[0]
    unit_links.append(ScreenshotUnit(screenshot_id=screenshot.pk, unit_id=unit.pk))
    manifest.append(
        {
            "pk": screenshot.pk,
            "name": filename,
            "image": name,
            "translation_id": translation.pk,
            "user_id": user.pk,
            "unit_id": unit.pk,
            "timestamp": screenshot.timestamp.isoformat(),
            "digest": hashlib.sha256(content).hexdigest()
            if content is not None
            else None,
            "repair": repair,
        }
    )
    if filename == "collision.pngrawtrue":
        shared = Screenshot.objects.bulk_create(
            [
                Screenshot(
                    name="Shared image", image=name, translation=translation, user=user
                )
            ]
        )[0]
        unit_links.append(ScreenshotUnit(screenshot_id=shared.pk, unit_id=unit.pk))
        manifest.append(
            {
                **manifest[-1],
                "pk": shared.pk,
                "name": shared.name,
                "timestamp": shared.timestamp.isoformat(),
            }
        )

# Avoid screenshot assignment signals refreshing alerts seeded by other scripts.
ScreenshotUnit.objects.bulk_create(unit_links)

storage.delete("screenshot-extension-upgrade.json")
storage.save(
    "screenshot-extension-upgrade.json", ContentFile(json.dumps(manifest).encode())
)
