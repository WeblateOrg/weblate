# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import difflib

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.translation import gettext
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView
from PIL import Image

from weblate.screenshots.forms import ScreenshotEditForm, ScreenshotForm, SearchForm
from weblate.screenshots.models import Screenshot
from weblate.trans.models import Change, Unit
from weblate.utils import messages
from weblate.utils.locale import c_locale
from weblate.utils.search import parse_query
from weblate.utils.views import ComponentViewMixin

with c_locale():
    from tesserocr import OEM, PSM, RIL, PyTessBaseAPI

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
    "te": "tel",  # Telugu
    "tg": "tgk",  # Tajik
    "tl": "tgl",  # Tagalog
    "th": "tha",  # Thai
    "ti": "tir",  # Tigrinya
    "tr": "tur",  # Turkish
    "ug": "uig",  # Uighur; Uyghur
    "uk": "ukr",  # Ukrainian
    "ur": "urd",  # Urdu
    "uz_Latn": "uzb",  # Uzbek
    "uz": "uzb_cyrl",  # Uzbek - Cyrillic
    "vi": "vie",  # Vietnamese
    "yi": "yid",  # Yiddish
}


def try_add_source(request, obj):
    if "source" not in request.POST:
        return False

    try:
        source = obj.translation.unit_set.get(pk=int(request.POST["source"]))
    except (Unit.DoesNotExist, ValueError):
        return False

    obj.units.add(source)
    return True


class ScreenshotList(ListView, ComponentViewMixin):
    paginate_by = 25
    model = Screenshot
    _add_form = None

    def get_queryset(self):
        self.kwargs["component"] = self.get_component()
        return (
            Screenshot.objects.filter(translation__component=self.kwargs["component"])
            .prefetch_related("translation__language")
            .order()
        )

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        component = self.kwargs["component"]
        result["object"] = component
        if self.request.user.has_perm("screenshot.add", component):
            if self._add_form is not None:
                result["add_form"] = self._add_form
            else:
                result["add_form"] = ScreenshotForm(component)
        return result

    def post(self, request, **kwargs):
        component = self.get_component()
        if not request.user.has_perm("screenshot.add", component):
            raise PermissionDenied
        self._add_form = ScreenshotForm(component, request.POST, request.FILES)
        if self._add_form.is_valid():
            obj = Screenshot.objects.create(
                user=request.user, **self._add_form.cleaned_data
            )
            request.user.profile.increase_count("uploaded")
            obj.change_set.create(
                action=Change.ACTION_SCREENSHOT_ADDED,
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
            request, gettext("Failed to upload screenshot, please fix errors below.")
        )
        return self.get(request, **kwargs)


class ScreenshotDetail(DetailView):
    model = Screenshot
    _edit_form = None

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
        return result

    def post(self, request, **kwargs):
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
                        action=Change.ACTION_SCREENSHOT_UPLOADED,
                        user=request.user,
                        target=obj.name,
                    )
                self._edit_form.save()
            else:
                return self.get(request, **kwargs)
        return redirect(obj)


@require_POST
@login_required
def delete_screenshot(request, pk):
    obj = get_object_or_404(Screenshot, pk=pk)
    component = obj.translation.component
    if not request.user.has_perm("screenshot.delete", obj.translation):
        raise PermissionDenied

    kwargs = {"project": component.project.slug, "component": component.slug}

    obj.delete()

    messages.success(request, gettext("Screenshot %s has been deleted.") % obj.name)

    return redirect("screenshots", **kwargs)


def get_screenshot(request, pk):
    obj = get_object_or_404(Screenshot, pk=pk)
    if not request.user.has_perm("screenshot.edit", obj.translation.component):
        raise PermissionDenied
    return obj


@require_POST
@login_required
def remove_source(request, pk):
    obj = get_screenshot(request, pk)

    obj.units.remove(request.POST["source"])

    messages.success(request, gettext("Source has been removed."))

    return redirect(obj)


def search_results(request, code, obj, units=None):
    if units is None:
        units = []
    else:
        units = (
            units.exclude(id__in=obj.units.values_list("id", flat=True))
            .prefetch()
            .prefetch_full()
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
                },
            ),
        }
    )


@login_required
@require_POST
def search_source(request, pk):
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


def ocr_get_strings(api, image):
    api.SetImage(image)
    for item in api.GetComponentImages(RIL.TEXTLINE, True):
        api.SetRectangle(item[1]["x"], item[1]["y"], item[1]["w"], item[1]["h"])
        yield api.GetUTF8Text()
    api.Clear()


def ocr_extract(api, image, strings):
    """Extract closes matches from an image."""
    for ocr_result in ocr_get_strings(api, image):
        parts = [ocr_result, *ocr_result.split("|"), *ocr_result.split()]
        for part in parts:
            yield from difflib.get_close_matches(part, strings, cutoff=0.9)


@login_required
@require_POST
def ocr_search(request, pk):
    obj = get_screenshot(request, pk)
    translation = obj.translation

    # Load image
    original_image = Image.open(obj.image.path)
    # Convert to greyscale
    original_image = original_image.convert("L")
    # Resize image (tesseract works best around 300dpi)
    scaled_image = original_image.copy().resize(
        [size * 4 for size in original_image.size], Image.BICUBIC
    )

    # Find all our strings
    sources = dict(translation.unit_set.values_list("source", "pk"))
    strings = tuple(sources.keys())

    # Extract and match strings
    try:
        tess_language = TESSERACT_LANGUAGES[translation.language.code]
    except KeyError:
        try:
            tess_language = TESSERACT_LANGUAGES[translation.language.base_code]
        except KeyError:
            tess_language = "eng"
    with c_locale(), PyTessBaseAPI(
        psm=PSM.SPARSE_TEXT_OSD, oem=OEM.LSTM_ONLY, lang=tess_language
    ) as api:
        results = {
            sources[match]
            for image in (original_image, scaled_image)
            for match in ocr_extract(api, image, strings)
        }

    # Close images
    original_image.close()
    scaled_image.close()

    return search_results(
        request, 200, obj, translation.unit_set.filter(pk__in=results)
    )


@login_required
@require_POST
def add_source(request, pk):
    obj = get_screenshot(request, pk)
    result = try_add_source(request, obj)
    return JsonResponse(data={"responseCode": 200, "status": result})


@login_required
def get_sources(request, pk):
    obj = get_screenshot(request, pk)
    return render(
        request,
        "screenshots/screenshot_sources_body.html",
        {"sources": obj.units.order(), "object": obj},
    )
