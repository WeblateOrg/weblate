# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import difflib
import os
import tempfile
from contextlib import contextmanager, suppress
from time import sleep
from typing import TYPE_CHECKING, ClassVar, cast

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext, ngettext
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView
from PIL import Image
from requests import ConnectionError as RequestsConnectionError
from requests import HTTPError, RequestException, Timeout
from tesserocr import OEM, PSM, RIL, PyTessBaseAPI, iterate_level

from weblate.logger import LOGGER
from weblate.screenshots.forms import (
    ScreenshotEditForm,
    ScreenshotForm,
    ScreenshotListSearchForm,
    SearchForm,
)
from weblate.screenshots.models import Screenshot
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Component, Unit
from weblate.trans.util import redirect_next
from weblate.utils import messages
from weblate.utils.data import data_dir
from weblate.utils.lock import WeblateLock
from weblate.utils.requests import fetch_url
from weblate.utils.search import parse_query
from weblate.utils.tracing import start_span
from weblate.utils.validators import PIL_FORMATS
from weblate.utils.views import PathViewMixin

if TYPE_CHECKING:
    from collections.abc import Generator

    from django.http import HttpResponse

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
TESSERACT_DOWNLOAD_ATTEMPTS = 3
TESSERACT_DOWNLOAD_TIMEOUT = 30


def is_retryable_tesseract_download_error(error: RequestException) -> bool:
    if isinstance(error, (RequestsConnectionError, Timeout)):
        return True
    if not isinstance(error, HTTPError) or error.response is None:
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
                        allow_redirects=True,
                        timeout=TESSERACT_DOWNLOAD_TIMEOUT,
                    )
            except RequestException as error:
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


def add_sources(request: AuthenticatedHttpRequest, obj) -> dict[str, int | bool]:
    sources = request.POST.getlist("source")
    if not sources:
        return {"status": False, "added": 0, "skipped": 0, "invalid": 0}

    source_ids: list[int] = []
    seen: set[int] = set()
    skipped = 0
    invalid = 0
    for source in sources:
        try:
            source_id = int(source)
        except ValueError:
            invalid += 1
            continue
        if source_id in seen:
            skipped += 1
            continue
        seen.add(source_id)
        source_ids.append(source_id)

    existing = set(obj.units.filter(pk__in=source_ids).values_list("pk", flat=True))
    units = obj.translation.unit_set.in_bulk(source_ids)
    units_to_add: list[Unit] = []
    for source_id in source_ids:
        unit = units.get(source_id)
        if unit is None:
            invalid += 1
            continue
        if source_id in existing:
            skipped += 1
            continue
        units_to_add.append(unit)
        existing.add(source_id)

    obj.add_units(units_to_add, user=request.user)
    added = len(units_to_add)

    return {
        "status": added > 0,
        "added": added,
        "skipped": skipped,
        "invalid": invalid,
    }


def try_add_source(request: AuthenticatedHttpRequest, obj) -> bool:
    return bool(add_sources(request, obj)["status"])


class ScreenshotList(PathViewMixin, ListView):  # type: ignore[misc]
    paginate_by = 48
    model = Screenshot
    supported_path_types = (Component,)
    _add_form = None

    sort_ordering: ClassVar[dict[str, tuple[str, ...]]] = {
        "name": ("name", "pk"),
        "-name": ("-name", "pk"),
        "-timestamp": ("-timestamp", "name", "pk"),
        "timestamp": ("timestamp", "name", "pk"),
        "language": ("translation__language__name", "name", "pk"),
        "-language": ("-translation__language__name", "name", "pk"),
        "-strings": ("-strings_count", "name", "pk"),
        "strings": ("strings_count", "name", "pk"),
    }
    search_preset_queries: ClassVar[tuple[str, ...]] = (
        "",
        "has:string",
        "NOT has:string",
        "has:repository",
        "has:repository AND NOT has:string",
    )

    def get_search_presets(self) -> list[dict[str, str]]:
        labels = {
            "": gettext("All screenshots"),
            "has:string": gettext("Assigned screenshots"),
            "NOT has:string": gettext("Unassigned screenshots"),
            "has:repository": gettext("Repository screenshots"),
            "has:repository AND NOT has:string": gettext(
                "Unassigned repository screenshots"
            ),
        }
        sort_by = ""
        if self.search_form.is_valid():
            sort_by = self.search_form.cleaned_data["sort_by"]

        result = []
        for query in self.search_preset_queries:
            params = []
            if query:
                params.append(("q", query))
            if sort_by and sort_by != "name":
                params.append(("sort_by", sort_by))
            result.append(
                {
                    "label": labels[query],
                    "query": query,
                    "query_string": urlencode(params),
                }
            )
        return result

    def setup(self, *args, **kwargs) -> None:
        super().setup(*args, **kwargs)
        data = self.request.GET.copy()
        if "q" not in data and data.get("assigned") == "0":
            data["q"] = "NOT has:string"
        self.search_form = ScreenshotListSearchForm(data=data)

    def get_queryset(self):
        result = (
            Screenshot.objects.filter(translation__component=self.path_object)
            .prefetch_related(
                "translation__component__category",
                "translation__component__project",
                "translation__language",
            )
            .annotate(strings_count=Count("units", distinct=True))
            .order()
        )
        if self.search_form.is_valid():
            if query := self.search_form.cleaned_data["q"]:
                filters, annotations = parse_query(
                    query,
                    parser="screenshot",
                    project=self.path_object.project,
                    component=self.path_object,
                )
                result = result.annotate(**annotations).filter(filters).distinct()
            sort_by = self.search_form.cleaned_data["sort_by"]
        else:
            sort_by = "name"
        return result.order_by(*self.sort_ordering[sort_by])

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["object"] = self.path_object
        result["add_form_active"] = self._add_form is not None
        result["search_form"] = self.search_form
        result["active_query"] = ""
        result["active_query_label"] = gettext("Filters")
        result["sort_query"] = "name"
        result["sort_name"] = self.search_form.sort_choices["name"]
        result["sort_choices"] = self.search_form.sort_choices
        result["sort_desc"] = False
        result["query_string"] = ""
        result["search_items"] = []
        if self.search_form.is_valid():
            result["active_query"] = self.search_form.cleaned_data["q"]
            result["sort_query"] = self.search_form.cleaned_data["sort_by"]
            result["sort_name"] = self.search_form.sort_choices[
                result["sort_query"].removeprefix("-")
            ]
            result["sort_desc"] = result["sort_query"].startswith("-")
            result["query_string"] = self.search_form.urlencode()
            result["search_items"] = self.search_form.items()
        result["screenshot_search_presets"] = self.get_search_presets()
        for preset in result["screenshot_search_presets"]:
            if preset["query"] == result["active_query"]:
                result["active_query_label"] = preset["label"]
                break
        screenshots = Screenshot.objects.filter(translation__component=self.path_object)
        source_units = self.path_object.source_translation.unit_set
        source_strings_with_screenshots = (
            source_units.filter(screenshots__isnull=False).distinct().count()
        )
        source_strings_total = source_units.count()
        result["screenshot_summary"] = {
            "total": screenshots.count(),
            "unassigned": screenshots.filter(units__isnull=True).count(),
            "source_strings_with_screenshots": source_strings_with_screenshots,
            "source_strings_without_screenshots": (
                source_strings_total - source_strings_with_screenshots
            ),
            "source_translation": self.path_object.source_translation,
            "with_query": "has:screenshot",
            "without_query": "NOT has:screenshot",
            "assigned_query": urlencode({"q": "has:string"}),
            "unassigned_query": urlencode({"q": "NOT has:string"}),
        }
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
                action=ActionEvents.SCREENSHOT_UPLOADED,
                user=request.user,
                target=obj.name,
            )

            try_add_source(request, obj)
            messages.success(
                request,
                gettext(
                    "Screenshot has been uploaded. "
                    "Search for source strings or find strings in the image."
                ),
            )
            next_url = request.POST.get("next") or request.GET.get("next")
            return redirect_next(next_url, obj)
        messages.error(
            request, gettext("Could not upload screenshot, please fix errors below.")
        )
        return self.get(request, **kwargs)


class ScreenshotBaseView(DetailView):
    model = Screenshot
    request: AuthenticatedHttpRequest

    def get_queryset(self):
        return Screenshot.objects.filter_access(self.request.user)

    def get_object(self, *args, **kwargs):
        obj = super().get_object(*args, **kwargs)
        self.request.user.check_access_component(obj.translation.component)
        return obj


class ScreenshotView(ScreenshotBaseView):
    def get(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> FileResponse:  # type: ignore[override]
        obj = self.get_object()
        with Image.open(obj.image.open(), formats=PIL_FORMATS) as image:
            content_type = Image.MIME[cast("str", image.format)]
        return FileResponse(
            obj.image.open(),
            as_attachment=False,
            filename=os.path.basename(obj.image.name),
            content_type=content_type,
        )


class ScreenshotDetail(ScreenshotBaseView):
    _edit_form = None

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

    def post(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> HttpResponse:
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
                return self.get(request, *args, **kwargs)
        return redirect(obj)


@require_POST
@login_required
def delete_screenshot(request: AuthenticatedHttpRequest, pk):
    obj = get_object_or_404(Screenshot.objects.filter_access(request.user), pk=pk)
    component = obj.translation.component
    if not request.user.has_perm("screenshot.delete", obj.translation):
        raise PermissionDenied

    obj.delete()

    messages.success(request, gettext("Screenshot %s has been deleted.") % obj.name)

    return redirect_next(
        request.POST.get("next"),
        reverse("screenshots", kwargs={"path": component.get_url_path()}),
    )


def get_screenshot(request: AuthenticatedHttpRequest, pk):
    obj = get_object_or_404(Screenshot.objects.filter_access(request.user), pk=pk)
    if not request.user.has_perm("screenshot.edit", obj.translation.component):
        raise PermissionDenied
    return obj


@require_POST
@login_required
def remove_source(request: AuthenticatedHttpRequest, pk):
    obj = get_screenshot(request, pk)

    try:
        unit = obj.translation.unit_set.get(pk=int(request.POST["source"]))
    except (Unit.DoesNotExist, ValueError):
        messages.error(request, gettext("Invalid unit."))
        return redirect(obj)

    obj.remove_unit(unit, user=request.user)

    messages.success(request, gettext("Source has been removed."))

    return redirect(obj)


def search_results(
    request: AuthenticatedHttpRequest,
    code,
    obj,
    units=None,
    *,
    error: str | None = None,
):
    if units is None:
        units = []
        count = 0
    else:
        units = (
            units.exclude(id__in=obj.units.values_list("id", flat=True))
            .prefetch_full()
            .count_screenshots()
        )
        count = len(units)

    data = {
        "responseCode": code,
        "count": count,
        "summary": ngettext(
            "%(count)s matching source string found.",
            "%(count)s matching source strings found.",
            count,
        )
        % {"count": count},
        "empty": gettext("No new matching source strings found."),
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
    if error is not None:
        data["error"] = error
    return JsonResponse(data=data)


@login_required
@require_POST
def search_source(request: AuthenticatedHttpRequest, pk):
    obj = get_screenshot(request, pk)
    translation = obj.translation

    form = SearchForm(request.POST)
    if not form.is_valid():
        return search_results(request, 400, obj)
    filters, annotations = parse_query(
        form.cleaned_data["q"], project=translation.component.project
    )
    return search_results(
        request,
        200,
        obj,
        translation.unit_set.annotate(**annotations).filter(filters),
    )


def ocr_get_strings(api, *, image: Image.Image, filename: str, resolution: int = 72):

    try:
        api.SetImage(image)
    except RuntimeError:
        pass
    else:
        api.SetSourceResolution(resolution)

        with start_span(op="ocr.recognize", name=filename):
            api.Recognize()

        with start_span(op="ocr.iterate", name=filename):
            iterator = api.GetIterator()
            level = RIL.TEXTLINE
            for r in iterate_level(iterator, level):
                with start_span(op="ocr.text", name=filename):
                    try:
                        yield r.GetUTF8Text(level)
                    except RuntimeError:
                        continue
    finally:
        api.Clear()


def ocr_extract(
    api,
    *,
    image: Image.Image,
    filename: str,
    strings: tuple[str, ...],
    resolution: int,
):
    """Extract closes matches from an image."""
    for ocr_result in ocr_get_strings(
        api, image=image, filename=filename, resolution=resolution
    ):
        parts = [ocr_result, *ocr_result.split("|"), *ocr_result.split()]
        for part in parts:
            yield from difflib.get_close_matches(part, strings, cutoff=0.9)


@contextmanager
def get_tesseract(language: Language) -> Generator[PyTessBaseAPI]:

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
        path=f"{data_dir('cache', 'tesseract')}/",
        psm=PSM.SPARSE_TEXT_OSD,
        oem=OEM.LSTM_ONLY,
        lang=tess_language,
    ) as api:
        yield api


@login_required
@require_POST
def ocr_search(request: AuthenticatedHttpRequest, pk):

    obj = get_screenshot(request, pk)
    translation = obj.translation

    # Find all our strings
    sources = dict(translation.unit_set.values_list("source", "pk"))
    strings = tuple(sources.keys())

    # Extract and match strings
    try:
        with Image.open(obj.image.path, formats=PIL_FORMATS) as image:
            image.load()
    except OSError as error:
        LOGGER.warning(
            "Skipping OCR for unreadable screenshot %s: %s", obj.image.path, error
        )
        return search_results(request, 200, obj)

    ocr_image = cast("Image.Image", image)

    try:
        with get_tesseract(translation.language) as api:
            results = {
                sources[match]
                for resolution in (72, 300)
                for match in ocr_extract(
                    api,
                    image=ocr_image,
                    filename=obj.image.path,
                    strings=strings,
                    resolution=resolution,
                )
            }
    except RequestException as error:
        LOGGER.warning("Could not download Tesseract data: %s", error)
        return search_results(
            request,
            503,
            obj,
            error=gettext("OCR data could not be downloaded. Please try again later."),
        )
    finally:
        ocr_image.close()

    return search_results(
        request, 200, obj, translation.unit_set.filter(pk__in=results)
    )


@login_required
@require_POST
def add_source(request: AuthenticatedHttpRequest, pk):
    obj = get_screenshot(request, pk)
    return JsonResponse(data={"responseCode": 200, **add_sources(request, obj)})


@login_required
def get_sources(request: AuthenticatedHttpRequest, pk):
    obj = get_screenshot(request, pk)
    return render(
        request,
        "screenshots/screenshot_sources_body.html",
        {"object": obj, "search_query": ""},
    )
