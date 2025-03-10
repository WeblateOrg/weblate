# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import difflib
import os
from contextlib import contextmanager
from typing import TYPE_CHECKING

import sentry_sdk
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.translation import gettext
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from weblate.auth.models import AuthenticatedHttpRequest
from weblate.logger import LOGGER
from weblate.screenshots.forms import ScreenshotEditForm, ScreenshotForm, SearchForm
from weblate.screenshots.models import Screenshot
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Component, Unit
from weblate.utils import messages
from weblate.utils.data import data_dir
from weblate.utils.lock import WeblateLock
from weblate.utils.requests import request
from weblate.utils.search import parse_query
from weblate.utils.views import PathViewMixin

if TYPE_CHECKING:
    from tesserocr import PyTessBaseAPI

    from weblate.auth.models import AuthenticatedHttpRequest
    from weblate.lang.models import Language


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
    "nb_NO": "nor",  # Norwegian
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


def ensure_tesseract_language(lang: str) -> None:
    """
    Ensure that tesseract trained data is present for a language.

    It also always includes eng (English) and osd (Orientation and script detection).
    """
    tessdata = data_dir("cache", "tesseract")

    # Operate with a lock held to avoid concurrent downloads
    with (
        WeblateLock(
            lock_path=data_dir("home"),
            scope="screenshots:tesseract-download",
            key=0,
            slug="screenshots:tesseract-download",
            timeout=600,
        ),
        sentry_sdk.start_span(op="ocr.models"),
    ):
        if not os.path.isdir(tessdata):
            os.makedirs(tessdata)

        for code in (lang, "eng", "osd"):
            filename = f"{code}.traineddata"
            full_name = os.path.join(tessdata, filename)
            if os.path.exists(full_name):
                continue

            url = TESSERACT_URL.format(filename)

            LOGGER.debug("downloading tesseract data %s", url)

            with sentry_sdk.start_span(op="ocr.download", name=url):
                response = request("GET", url, allow_redirects=True)

            with open(full_name, "xb") as handle:
                handle.write(response.content)


def try_add_source(request: AuthenticatedHttpRequest, obj) -> bool:
    if "source" not in request.POST:
        return False

    try:
        source = obj.translation.unit_set.get(pk=int(request.POST["source"]))
    except (Unit.DoesNotExist, ValueError):
        return False

    obj.units.add(source)
    return True


class ScreenshotList(PathViewMixin, ListView):
    paginate_by = 25
    model = Screenshot
    supported_path_types = (Component,)
    _add_form = None

    def get_queryset(self):
        return (
            Screenshot.objects.filter(translation__component=self.path_object)
            .prefetch_related("translation__language")
            .order()
        )

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["object"] = self.path_object
        if self.request.user.has_perm("screenshot.add", self.path_object):
            if self._add_form is not None:
                result["add_form"] = self._add_form
            else:
                result["add_form"] = ScreenshotForm(self.path_object)
        return result

    def post(self, request: AuthenticatedHttpRequest, **kwargs):
        component = self.path_object
        if not request.user.has_perm("screenshot.add", component):
            raise PermissionDenied
        self._add_form = ScreenshotForm(component, request.POST, request.FILES)
        if self._add_form.is_valid():
            obj = Screenshot.objects.create(
                user=request.user, **self._add_form.cleaned_data
            )
            request.user.profile.increase_count("uploaded")
            obj.change_set.create(
                action=ActionEvents.SCREENSHOT_ADDED,
                user=request.user,
                target=obj.name,
            )

            try_add_source(request, obj)
            messages.success(
                request,
                gettext(
                    "Screenshot has been uploaded, "
                    "you can now assign it to source strings."
                ),
            )
            return redirect(obj)
        messages.error(
            request, gettext("Could not upload screenshot, please fix errors below.")
        )
        return self.get(request, **kwargs)


class ScreenshotDetail(DetailView):
    model = Screenshot
    _edit_form = None
    request: AuthenticatedHttpRequest

    def get_object(self, *args, **kwargs):
        obj = super().get_object(*args, **kwargs)
        self.request.user.check_access_component(obj.translation.component)
        return obj

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        component = result["object"].translation.component
        if self.request.user.has_perm("screenshot.edit", component):
            if self._edit_form is not None:
                result["edit_form"] = self._edit_form
            else:
                result["edit_form"] = ScreenshotEditForm(instance=result["object"])
        # Blank list for search results, this is populated later via JavaScript
        result["units"] = []
        result["search_query"] = ""
        return result

    def post(self, request: AuthenticatedHttpRequest, **kwargs):
        obj = self.get_object()
        if request.user.has_perm("screenshot.edit", obj.translation):
            self._edit_form = ScreenshotEditForm(
                request.POST, request.FILES, instance=obj
            )
            if self._edit_form.is_valid():
                if request.FILES:
                    obj.user = request.user
                    request.user.profile.increase_count("uploaded")
                    obj.change_set.create(
                        action=ActionEvents.SCREENSHOT_UPLOADED,
                        user=request.user,
                        target=obj.name,
                    )
                self._edit_form.save()
            else:
                return self.get(request, **kwargs)
        return redirect(obj)


@require_POST
@login_required
def delete_screenshot(request: AuthenticatedHttpRequest, pk):
    obj = get_object_or_404(Screenshot, pk=pk)
    component = obj.translation.component
    if not request.user.has_perm("screenshot.delete", obj.translation):
        raise PermissionDenied

    obj.delete()

    messages.success(request, gettext("Screenshot %s has been deleted.") % obj.name)

    return redirect("screenshots", path=component.get_url_path())


def get_screenshot(request: AuthenticatedHttpRequest, pk):
    obj = get_object_or_404(Screenshot, pk=pk)
    if not request.user.has_perm("screenshot.edit", obj.translation.component):
        raise PermissionDenied
    return obj


@require_POST
@login_required
def remove_source(request: AuthenticatedHttpRequest, pk):
    obj = get_screenshot(request, pk)

    obj.units.remove(request.POST["source"])

    messages.success(request, gettext("Source has been removed."))

    return redirect(obj)


def search_results(request: AuthenticatedHttpRequest, code, obj, units=None):
    if units is None:
        units = []
    else:
        units = (
            units.exclude(id__in=obj.units.values_list("id", flat=True))
            .prefetch_full()
            .count_screenshots()
        )

    return JsonResponse(
        data={
            "responseCode": code,
            "results": render_to_string(
                "screenshots/screenshot_sources_search.html",
                {
                    "object": obj,
                    "units": units,
                    "user": request.user,
                    "search_query": "",
                },
            ),
        }
    )


@login_required
@require_POST
def search_source(request: AuthenticatedHttpRequest, pk):
    obj = get_screenshot(request, pk)
    translation = obj.translation

    form = SearchForm(request.POST)
    if not form.is_valid():
        return search_results(request, 400, obj)
    return search_results(
        request,
        200,
        obj,
        translation.unit_set.filter(
            parse_query(form.cleaned_data["q"], project=translation.component.project)
        ),
    )


def ocr_get_strings(api, image: str, resolution: int = 72):
    from tesserocr import RIL, iterate_level

    try:
        api.SetImageFile(image)
    except RuntimeError:
        pass
    else:
        api.SetSourceResolution(resolution)

        with sentry_sdk.start_span(op="ocr.recognize", name=image):
            api.Recognize()

        with sentry_sdk.start_span(op="ocr.iterate", name=image):
            iterator = api.GetIterator()
            level = RIL.TEXTLINE
            for r in iterate_level(iterator, level):
                with sentry_sdk.start_span(op="ocr.text", name=image):
                    try:
                        yield r.GetUTF8Text(level)
                    except RuntimeError:
                        continue
    finally:
        api.Clear()


def ocr_extract(api, image: str, strings, resolution: int):
    """Extract closes matches from an image."""
    for ocr_result in ocr_get_strings(api, image, resolution):
        parts = [ocr_result, *ocr_result.split("|"), *ocr_result.split()]
        for part in parts:
            yield from difflib.get_close_matches(part, strings, cutoff=0.9)


@contextmanager
def get_tesseract(language: Language) -> PyTessBaseAPI:
    from tesserocr import OEM, PSM, PyTessBaseAPI

    # Get matching language
    try:
        tess_language = TESSERACT_LANGUAGES[language.code]
    except KeyError:
        try:
            tess_language = TESSERACT_LANGUAGES[language.base_code]
        except KeyError:
            tess_language = "eng"

    ensure_tesseract_language(tess_language)

    with PyTessBaseAPI(
        path=data_dir("cache", "tesseract") + "/",
        psm=PSM.SPARSE_TEXT_OSD,
        oem=OEM.LSTM_ONLY,
        lang=tess_language,
    ) as api:
        yield api


@login_required
@require_POST
def ocr_search(request: AuthenticatedHttpRequest, pk):
    from PIL import Image

    obj = get_screenshot(request, pk)
    translation = obj.translation

    # Find all our strings
    sources = dict(translation.unit_set.values_list("source", "pk"))
    strings = tuple(sources.keys())

    # Extract and match strings
    with Image.open(obj.image.path), get_tesseract(translation.language) as api:
        results = {
            sources[match]
            for resolution in (72, 300)
            for match in ocr_extract(api, obj.image.path, strings, resolution)
        }

    return search_results(
        request, 200, obj, translation.unit_set.filter(pk__in=results)
    )


@login_required
@require_POST
def add_source(request: AuthenticatedHttpRequest, pk):
    obj = get_screenshot(request, pk)
    result = try_add_source(request, obj)
    return JsonResponse(data={"responseCode": 200, "status": result})


@login_required
def get_sources(request: AuthenticatedHttpRequest, pk):
    obj = get_screenshot(request, pk)
    return render(
        request,
        "screenshots/screenshot_sources_body.html",
        {"object": obj, "search_query": ""},
    )
