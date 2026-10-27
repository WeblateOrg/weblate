# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os.path
from typing import TYPE_CHECKING, cast

import httpx2
from celery.schedules import crontab
from django.core.files.storage import DefaultStorage
from django.db import transaction
from PIL import Image

from weblate.logger import LOGGER
from weblate.screenshots.models import Screenshot, ScreenshotOCR
from weblate.screenshots.ocr import get_ocr_signature, get_tesseract, ocr_get_lines
from weblate.utils.celery import app
from weblate.utils.validators import PIL_FORMATS

if TYPE_CHECKING:
    from celery import Celery
    from django.core.files.storage import Storage


@app.task(trail=False, soft_time_limit=290, time_limit=300)
def recognize_screenshot(screenshot_id: int, generation: str) -> dict[str, str]:
    screenshot = (
        Screenshot.objects.select_related("translation__language")
        .filter(pk=screenshot_id)
        .first()
    )
    cache = ScreenshotOCR.objects.filter(
        screenshot_id=screenshot_id, generation=generation
    ).first()
    if (
        screenshot is None
        or cache is None
        or cache.signature != get_ocr_signature(screenshot)
    ):
        return {"status": "obsolete"}

    if cache.data is not None or cache.error:
        return {"status": "failed" if cache.error else "completed"}

    error = ""
    data = None
    try:
        with (
            screenshot.image.open("rb") as image_file,
            Image.open(image_file, formats=PIL_FORMATS) as image,
        ):
            image.load()
            with get_tesseract(screenshot.translation.language) as api:
                data = {
                    "width": image.width,
                    "height": image.height,
                    "passes": [
                        {
                            "resolution": resolution,
                            "lines": ocr_get_lines(
                                api,
                                image=image,
                                filename=screenshot.image.name or "",
                                resolution=resolution,
                            ),
                        }
                        for resolution in (72, 300)
                    ],
                }
    except httpx2.HTTPError:
        LOGGER.warning("Could not download Tesseract data", exc_info=True)
        error = "download"
    except Exception:
        LOGGER.exception("Could not recognize screenshot %s", screenshot_id)
        error = "failed"

    with transaction.atomic():
        current = (
            Screenshot.objects.select_for_update(of=("self",))
            .select_related("translation__language")
            .filter(pk=screenshot_id)
            .first()
        )
        if current is None or get_ocr_signature(current) != cache.signature:
            return {"status": "obsolete"}
        updated = ScreenshotOCR.objects.filter(
            screenshot_id=screenshot_id, generation=generation, task_id=cache.task_id
        ).update(data=data, error=error)
    return {"status": ("failed" if error else "completed") if updated else "obsolete"}


@app.task(trail=False)
def cleanup_screenshot_files() -> None:
    """Remove stale screenshots."""
    storage = cast("Storage", DefaultStorage())
    try:
        files = storage.listdir("screenshots")[1]
    except OSError:
        return
    for name in files:
        fullname = os.path.join("screenshots", name)
        if not Screenshot.objects.filter(image=fullname).exists():
            storage.delete(fullname)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender: Celery, **kwargs: object) -> None:
    sender.add_periodic_task(
        crontab(hour=0, minute=35),
        cleanup_screenshot_files.s(),
        name="screenshot-files-cleanup",
    )
