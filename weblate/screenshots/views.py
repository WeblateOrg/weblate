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

import difflib

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView
from PIL import Image

from weblate.screenshots.forms import ScreenshotEditForm, ScreenshotForm, SearchForm
from weblate.screenshots.models import Screenshot
from weblate.trans.models import Unit
from weblate.utils import messages
from weblate.utils.locale import c_locale
from weblate.utils.search import parse_query
from weblate.utils.views import ComponentViewMixin

try:
    with c_locale():
        from tesserocr import RIL, PyTessBaseAPI
    HAS_OCR = True
except ImportError:
    HAS_OCR = False


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
            raise PermissionDenied()
        self._add_form = ScreenshotForm(component, request.POST, request.FILES)
        if self._add_form.is_valid():
            obj = Screenshot.objects.create(
                user=request.user, **self._add_form.cleaned_data
            )
            request.user.profile.increase_count("uploaded")

            try_add_source(request, obj)
            messages.success(
                request,
                _(
                    "Screenshot has been uploaded, "
                    "you can now assign it to source strings."
                ),
            )
            return redirect(obj)
        messages.error(
            request, _("Failed to upload screenshot, please fix errors below.")
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
        raise PermissionDenied()

    kwargs = {"project": component.project.slug, "component": component.slug}

    obj.delete()

    messages.success(request, _("Screenshot %s has been deleted.") % obj.name)

    return redirect("screenshots", **kwargs)


def get_screenshot(request, pk):
    obj = get_object_or_404(Screenshot, pk=pk)
    if not request.user.has_perm("screenshot.edit", obj.translation.component):
        raise PermissionDenied()
    return obj


@require_POST
@login_required
def remove_source(request, pk):
    obj = get_screenshot(request, pk)

    obj.units.remove(request.POST["source"])

    messages.success(request, _("Source has been removed."))

    return redirect(obj)


def search_results(code, obj, units=None):
    if units is None:
        units = []
    else:
        units = units.exclude(id__in=obj.units.values_list("id", flat=True))

    results = [
        {
            "text": unit.source_string,
            "pk": unit.pk,
            "context": unit.context,
            "location": unit.location,
            "assigned": unit.screenshots.count(),
        }
        for unit in units
    ]

    return JsonResponse(data={"responseCode": code, "results": results})


@login_required
@require_POST
def search_source(request, pk):
    obj = get_screenshot(request, pk)
    translation = obj.translation

    form = SearchForm(request.POST)
    if not form.is_valid():
        return search_results(400, obj)
    return search_results(
        200,
        obj,
        translation.unit_set.filter(
            parse_query(form.cleaned_data["q"], project=translation.component.project)
        ),
    )


def ocr_extract(api, image, strings):
    """Extract closes matches from an image."""
    api.SetImage(image)
    for item in api.GetComponentImages(RIL.TEXTLINE, True):
        api.SetRectangle(item[1]["x"], item[1]["y"], item[1]["w"], item[1]["h"])
        ocr_result = api.GetUTF8Text()
        parts = [ocr_result] + ocr_result.split("|") + ocr_result.split()
        for part in parts:
            yield from difflib.get_close_matches(part, strings, cutoff=0.9)
    api.Clear()


@login_required
@require_POST
def ocr_search(request, pk):
    obj = get_screenshot(request, pk)
    if not HAS_OCR:
        return search_results(500, obj)
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

    results = set()

    # Extract and match strings
    with c_locale(), PyTessBaseAPI() as api:
        for image in (original_image, scaled_image):
            for match in ocr_extract(api, image, strings):
                results.add(sources[match])

    # Close images
    original_image.close()
    scaled_image.close()

    return search_results(200, obj, translation.unit_set.filter(pk__in=results))


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
