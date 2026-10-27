# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager, suppress
from datetime import timedelta
from functools import partial
from time import sleep
from typing import TYPE_CHECKING, TypedDict
from uuid import uuid4

import httpx2
from django.db import transaction
from django.utils import timezone

from weblate.logger import LOGGER
from weblate.utils.celery import store_task_metadata
from weblate.utils.data import data_dir
from weblate.utils.lock import WeblateLock
from weblate.utils.requests import fetch_url
from weblate.utils.tracing import start_span

if TYPE_CHECKING:
    from collections.abc import Generator

    from PIL import Image
    from tesserocr import PyTessBaseAPI

    from weblate.lang.models import Language
    from weblate.screenshots.models import Screenshot, ScreenshotOCR


TESSERACT_LANGUAGES = {
    "af": "afr",  # Afrikaans
    "am": "amh",  # Amharic
    "ar": "ara",  # Arabic
    "as": "asm",  # Assamese
    "az": "aze",  # Azerbaijani
    "az@Cyrl": "aze_cyrl",  # Azerbaijani - Cyrillic
    "be": "bel",  # Belarusian
    "bn": "ben",  # Bengali
    "bo": "bod",  # Tibetan
    "bs": "bos",  # Bosnian
    "bg": "bul",  # Bulgarian
    "ca": "cat",  # Catalan; Valencian
    "ceb": "ceb",  # Cebuano
    "cs": "ces",  # Czech
    "zh_Hans": "chi_sim",  # Chinese - Simplified
    "zh_Hant": "chi_tra",  # Chinese - Traditional
    "chr": "chr",  # Cherokee
    "cy": "cym",  # Welsh
    "da": "dan",  # Danish
    "de": "deu",  # German
    "dz": "dzo",  # Dzongkha
    "el": "ell",  # Greek, Modern (1453-)
    "en": "eng",  # English
    "enm": "enm",  # English, Middle (1100-1500)
    "eo": "epo",  # Esperanto
    "et": "est",  # Estonian
    "eu": "eus",  # Basque
    "fa": "fas",  # Persian
    "fi": "fin",  # Finnish
    "fr": "fra",  # French
    "frk": "frk",  # German Fraktur
    "frm": "frm",  # French, Middle (ca. 1400-1600)
    "ga": "gle",  # Irish
    "gl": "glg",  # Galician
    "grc": "grc",  # Greek, Ancient (-1453)
    "gu": "guj",  # Gujarati
    "ht": "hat",  # Haitian; Haitian Creole
    "he": "heb",  # Hebrew
    "hi": "hin",  # Hindi
    "hr": "hrv",  # Croatian
    "hu": "hun",  # Hungarian
    "iu": "iku",  # Inuktitut
    "id": "ind",  # Indonesian
    "is": "isl",  # Icelandic
    "it": "ita",  # Italian
    #    "": "ita_old",  # Italian - Old
    "jv": "jav",  # Javanese
    "ja": "jpn",  # Japanese
    "kn": "kan",  # Kannada
    "ka": "kat",  # Georgian
    #    "": "kat_old",  # Georgian - Old
    "kk": "kaz",  # Kazakh
    "km": "khm",  # Central Khmer
    "ky": "kir",  # Kirghiz; Kyrgyz
    "ko": "kor",  # Korean
    "ku": "kur",  # Kurdish
    "lo": "lao",  # Lao
    "la": "lat",  # Latin
    "lv": "lav",  # Latvian
    "lt": "lit",  # Lithuanian
    "ml": "mal",  # Malayalam
    "mr": "mar",  # Marathi
    "mk": "mkd",  # Macedonian
    "mt": "mlt",  # Maltese
    "ms": "msa",  # Malay
    "my": "mya",  # Burmese
    "ne": "nep",  # Nepali
    "nl": "nld",  # Dutch; Flemish
    "nb": "nor",  # Norwegian
    "nb_NO": "nor",
    #    "": "ori",  # Oriya
    "pa": "pan",  # Panjabi; Punjabi
    "pl": "pol",  # Polish
    "pt": "por",  # Portuguese
    "ps": "pus",  # Pushto; Pashto
    "ro": "ron",  # Romanian; Moldavian; Moldovan
    "ru": "rus",  # Russian
    "sa": "san",  # Sanskrit
    "si": "sin",  # Sinhala; Sinhalese
    "sk": "slk",  # Slovak
    "sl": "slv",  # Slovenian
    "es": "spa",  # Spanish; Castilian
    #    "": "spa_old",  # Spanish; Castilian - Old
    "sq": "sqi",  # Albanian
    "sr": "srp",  # Serbian
    "sr_Latn": "srp_latn",  # Serbian - Latin
    "sw": "swa",  # Swahili
    "sv": "swe",  # Swedish
    "syr": "syr",  # Syriac
    "ta": "tam",  # Tamil
    "te": "tel",  # Telugu # codespell:ignore te
    "tg": "tgk",  # Tajik
    "tl": "tgl",  # Tagalog
    "th": "tha",  # Thai # codespell:ignore tha
    "ti": "tir",  # Tigrinya
    "tr": "tur",  # Turkish
    "ug": "uig",  # Uighur; Uyghur
    "uk": "ukr",  # Ukrainian
    "ur": "urd",  # Urdu
    "uz_Latn": "uzb",  # Uzbek
    "uz": "uzb_cyrl",  # Uzbek - Cyrillic
    "vi": "vie",  # Vietnamese # codespell:ignore vie
    "yi": "yid",  # Yiddish
}

TESSERACT_URL = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/{}"
TESSERACT_DOWNLOAD_ATTEMPTS = 3
TESSERACT_DOWNLOAD_TIMEOUT = 30


def is_retryable_tesseract_download_error(error: httpx2.HTTPError) -> bool:
    if isinstance(
        error,
        (
            httpx2.NetworkError,
            httpx2.ProxyError,
            httpx2.RemoteProtocolError,
            httpx2.TimeoutException,
        ),
    ):
        return True
    if not isinstance(error, httpx2.HTTPStatusError):
        return False
    return error.response.status_code == 429 or error.response.status_code >= 500


def download_tesseract_data(url: str, full_name: str) -> None:
    temporary_name: str | None = None
    try:
        for attempt in range(1, TESSERACT_DOWNLOAD_ATTEMPTS + 1):
            try:
                with start_span(op="ocr.download", name=url):
                    response = fetch_url(
                        "GET",
                        url,
                        follow_redirects=True,
                        timeout=TESSERACT_DOWNLOAD_TIMEOUT,
                    )
            except httpx2.HTTPError as error:
                if (
                    attempt == TESSERACT_DOWNLOAD_ATTEMPTS
                    or not is_retryable_tesseract_download_error(error)
                ):
                    raise
                LOGGER.warning(
                    "Tesseract data download failed, retrying (%d/%d): %s",
                    attempt,
                    TESSERACT_DOWNLOAD_ATTEMPTS,
                    error,
                )
                sleep(2 ** (attempt - 1))
                continue

            with tempfile.NamedTemporaryFile(
                dir=os.path.dirname(full_name),
                prefix=f".{os.path.basename(full_name)}.",
                delete=False,
            ) as handle:
                temporary_name = handle.name
                handle.write(response.content)
            os.replace(temporary_name, full_name)
            temporary_name = None
            return
    finally:
        if temporary_name is not None:
            with suppress(FileNotFoundError):
                os.unlink(temporary_name)


def ensure_tesseract_language(lang: str) -> None:
    """
    Ensure that tesseract trained data is present for a language.

    It also always includes eng (English) and osd (Orientation and script detection).
    """
    tessdata = data_dir("cache", "tesseract")

    # Operate with a lock held to avoid concurrent downloads
    with (
        WeblateLock(
            scope="screenshots:tesseract:download",
            key=0,
            slug="screenshots:tesseract:download",
            timeout=600,
        ),
        start_span(op="ocr.models"),
    ):
        os.makedirs(tessdata, exist_ok=True)

        for code in (lang, "eng", "osd"):
            filename = f"{code}.traineddata"
            full_name = os.path.join(tessdata, filename)
            if os.path.exists(full_name):
                continue

            url = TESSERACT_URL.format(filename)

            LOGGER.debug("downloading tesseract data %s", url)

            download_tesseract_data(url, full_name)


@contextmanager
def get_tesseract(language: Language) -> Generator[PyTessBaseAPI]:
    from tesserocr import (  # ruff: ignore[import-outside-top-level]
        OEM,
        PSM,
        PyTessBaseAPI,
    )

    tess_language = get_tesseract_language(language)

    ensure_tesseract_language(tess_language)

    with PyTessBaseAPI(
        path=f"{data_dir('cache', 'tesseract')}/",
        psm=PSM.SPARSE_TEXT_OSD,
        oem=OEM.LSTM_ONLY,
        lang=tess_language,
    ) as api:
        yield api


def get_tesseract_language(language: Language) -> str:
    try:
        tess_language = TESSERACT_LANGUAGES[language.code]
    except KeyError:
        try:
            tess_language = TESSERACT_LANGUAGES[language.base_code]
        except KeyError:
            tess_language = "eng"

    return tess_language


# Bump when changing recognition options, trained-data selection, or cache shape.
OCR_ALGORITHM_VERSION = 1
OCR_QUEUE_TIMEOUT = 30 * 60


def get_ocr_signature(screenshot: Screenshot) -> dict[str, str | int]:
    import tesserocr  # ruff: ignore[import-outside-top-level]

    return {
        "image": screenshot.image.name or "",
        "language": get_tesseract_language(screenshot.translation.language),
        "algorithm": OCR_ALGORITHM_VERSION,
        "tesserocr": tesserocr.__version__,
        "tesseract": tesserocr.tesseract_version(),
    }


def publish_ocr(
    screenshot_id: int, generation: str, task_id: str, translation_id: int
) -> None:
    from weblate.screenshots.models import ScreenshotOCR  # ruff: ignore[import-outside-top-level]
    from weblate.screenshots.tasks import recognize_screenshot  # ruff: ignore[import-outside-top-level]

    try:
        store_task_metadata(task_id, translation_id=translation_id, cancellable=False)
        recognize_screenshot.apply_async(
            kwargs={"screenshot_id": screenshot_id, "generation": generation},
            task_id=task_id,
            expires=OCR_QUEUE_TIMEOUT,
        )
    except Exception:
        LOGGER.exception("Could not queue screenshot text recognition")
        ScreenshotOCR.objects.filter(
            screenshot_id=screenshot_id, generation=generation, task_id=task_id
        ).update(error="failed")


def ensure_ocr(screenshot_id: int, *, retry: bool = False) -> ScreenshotOCR:
    """Reuse a current cache or publish one refresh after the transaction commits."""
    from weblate.screenshots.models import Screenshot, ScreenshotOCR  # ruff: ignore[import-outside-top-level]

    with transaction.atomic():
        screenshot = (
            Screenshot.objects.select_for_update(of=("self",))
            .select_related("translation__language")
            .get(pk=screenshot_id)
        )
        cache, _created = ScreenshotOCR.objects.get_or_create(screenshot=screenshot)
        signature = get_ocr_signature(screenshot)
        expired = cache.requested_at is not None and cache.requested_at < (
            timezone.now() - timedelta(seconds=OCR_QUEUE_TIMEOUT)
        )
        if (
            cache.signature != signature
            or (
                cache.data is None
                and (cache.task_id is None or (not cache.error and expired))
            )
            # Terminated workers cannot persist errors. An explicit retry also
            # supersedes pending work; generation checks reject late results.
            or (retry and (cache.error or cache.data is None))
        ):
            cache.signature = signature
            cache.generation = uuid4()
            cache.task_id = uuid4()
            cache.requested_at = timezone.now()
            cache.error = ""
            cache.data = None
            cache.save()
            transaction.on_commit(
                partial(
                    publish_ocr,
                    screenshot.pk,
                    str(cache.generation),
                    str(cache.task_id),
                    screenshot.translation_id,
                )
            )
    # Eager execution and publication failures can already have updated this row.
    # Replacements can delete the row after our lock is released.
    refreshed = ScreenshotOCR.objects.filter(
        screenshot_id=screenshot_id, generation=cache.generation
    ).first()
    if refreshed is None:
        return ensure_ocr(screenshot_id, retry=retry)
    cache = refreshed
    if cache.task_id is not None:
        # Recreate expired visibility metadata without scheduling duplicate work.
        store_task_metadata(
            str(cache.task_id),
            translation_id=screenshot.translation_id,
            cancellable=False,
        )
    return cache


def schedule_ocr(screenshot_id: int) -> None:
    """Schedule after commit, including explicit bulk-creation callers."""
    transaction.on_commit(partial(ensure_ocr, screenshot_id), robust=True)


class OCRWord(TypedDict):
    text: str
    box: tuple[int, int, int, int] | None


class OCRLine(OCRWord):
    words: list[OCRWord]


def ocr_get_lines(
    api: PyTessBaseAPI, *, image: Image.Image, filename: str, resolution: int
) -> list[OCRLine]:
    """Recognize lines and their words without losing original image coordinates."""
    from tesserocr import RIL, iterate_level  # ruff: ignore[import-outside-top-level]

    lines: list[OCRLine] = []
    try:
        try:
            api.SetImage(image)
        except RuntimeError:
            return lines
        api.SetSourceResolution(resolution)
        with start_span(op="ocr.recognize", name=filename):
            api.Recognize()
        iterator = api.GetIterator()
        if iterator is None:
            return lines
        for word in iterate_level(iterator, RIL.WORD):
            try:
                if not lines or word.IsAtBeginningOf(RIL.TEXTLINE):
                    lines.append(
                        {
                            "text": word.GetUTF8Text(RIL.TEXTLINE),
                            "box": word.BoundingBox(RIL.TEXTLINE),
                            "words": [],
                        }
                    )
                lines[-1]["words"].append(
                    {
                        "text": word.GetUTF8Text(RIL.WORD),
                        "box": word.BoundingBox(RIL.WORD),
                    }
                )
            except RuntimeError:
                continue
    finally:
        api.Clear()
    return lines
