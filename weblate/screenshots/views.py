# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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
from django.utils.translation import ugettext as _
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DetailView
from django.shortcuts import get_object_or_404, redirect, render

from PIL import Image

try:
    from tesserocr import PyTessBaseAPI, RIL
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

from weblate.screenshots.forms import ScreenshotForm
from weblate.screenshots.models import Screenshot
from weblate.trans.models import Source
from weblate.utils import messages
from weblate.utils.views import ComponentViewMixin


def try_add_source(request, obj):
    if 'source' not in request.POST or not request.POST['source'].isdigit():
        return False

    try:
        source = Source.objects.get(
            pk=request.POST['source'],
            component=obj.component
        )
        obj.sources.add(source)
        return True
    except Source.DoesNotExist:
        return False


class ScreenshotList(ListView, ComponentViewMixin):
    paginate_by = 25
    model = Screenshot
    _add_form = None

    def get_queryset(self):
        self.kwargs['component'] = self.get_component()
        return Screenshot.objects.filter(component=self.kwargs['component'])

    def get_context_data(self):
        result = super(ScreenshotList, self).get_context_data()
        component = self.kwargs['component']
        result['object'] = component
        if self.request.user.has_perm('screenshot.add', component):
            if self._add_form is not None:
                result['add_form'] = self._add_form
            else:
                result['add_form'] = ScreenshotForm()
        return result

    def post(self, request, **kwargs):
        component = self.get_component()
        if not request.user.has_perm('screenshot.add', component):
            raise PermissionDenied()
        self._add_form = ScreenshotForm(request.POST, request.FILES)
        if self._add_form.is_valid():
            obj = Screenshot.objects.create(
                component=component,
                user=request.user,
                **self._add_form.cleaned_data
            )
            request.user.profile.uploaded += 1
            request.user.profile.save(update_fields=['uploaded'])

            try_add_source(request, obj)
            messages.success(
                request,
                _(
                    'Screenshot has been uploaded, '
                    'you can now assign it to source strings.'
                )
            )
            return redirect(obj)
        messages.error(
            request,
            _('Failed to upload screenshot, please fix errors below.')
        )
        return self.get(request, **kwargs)


class ScreenshotDetail(DetailView):
    model = Screenshot
    _edit_form = None

    def get_object(self, *args, **kwargs):
        obj = super(ScreenshotDetail, self).get_object(*args, **kwargs)
        self.request.user.check_access(obj.component.project)
        return obj

    def get_context_data(self, **kwargs):
        result = super(ScreenshotDetail, self).get_context_data(**kwargs)
        component = result['object'].component
        if self.request.user.has_perm('screenshot.edit', component):
            if self._edit_form is not None:
                result['edit_form'] = self._edit_form
            else:
                result['edit_form'] = ScreenshotForm(instance=result['object'])
        return result

    def post(self, request, **kwargs):
        obj = self.get_object()
        if request.user.has_perm('screenshot.edit', obj.component):
            self._edit_form = ScreenshotForm(
                request.POST, request.FILES, instance=obj
            )
            if self._edit_form.is_valid():
                if request.FILES:
                    obj.user = request.user
                    request.user.profile.uploaded += 1
                    request.user.profile.save(update_fields=['uploaded'])
                self._edit_form.save()
            else:
                return self.get(request, **kwargs)
        return redirect(obj)


@require_POST
@login_required
def delete_screenshot(request, pk):
    obj = get_object_or_404(Screenshot, pk=pk)
    request.user.check_access(obj.component.project)
    if not request.user.has_perm('screenshot.delete', obj.component):
        raise PermissionDenied()

    kwargs = {
        'project': obj.component.project.slug,
        'component': obj.component.slug,
    }

    obj.delete()

    messages.success(request, _('Screenshot %s has been deleted.') % obj.name)

    return redirect('screenshots', **kwargs)


def get_screenshot(request, pk):
    obj = get_object_or_404(Screenshot, pk=pk)
    request.user.check_access(obj.component.project)
    if not request.user.has_perm('screenshot.edit', obj.component):
        raise PermissionDenied()
    return obj


@require_POST
@login_required
def remove_source(request, pk):
    obj = get_screenshot(request, pk)

    obj.sources.remove(request.POST['source'])

    messages.success(request, _('Source has been removed.'))

    return redirect(obj)


def search_results(code, obj, units=None):
    if units is None:
        units = []
    else:
        units = units.exclude(
            id_hash__in=obj.sources.values_list('id_hash', flat=True)
        )

    results = [
        {
            'text': unit.get_source_plurals()[0],
            'pk': unit.source_info.pk,
            'context': unit.context,
            'location': unit.location
        }
        for unit in units
    ]

    return JsonResponse(
        data={'responseCode': code, 'results': results}
    )


@login_required
@require_POST
def search_source(request, pk):
    obj = get_screenshot(request, pk)
    try:
        translation = obj.component.translation_set.all()[0]
    except IndexError:
        return search_results(500, obj)

    units = translation.unit_set.search(
        {
            'search': 'substring',
            'q': request.POST.get('q', ''),
            'type': 'all',
            'source': True,
            'context': True,
        },
        translation=translation,
    )

    return search_results(200, obj, units)


def ocr_extract(api, image, strings):
    """Extract closes matches from an image"""
    api.SetImage(image)
    for item in api.GetComponentImages(RIL.TEXTLINE, True):
        api.SetRectangle(
            item[1]['x'], item[1]['y'], item[1]['w'], item[1]['h']
        )
        ocr_result = api.GetUTF8Text()
        parts = [ocr_result] + ocr_result.split('|') + ocr_result.split()
        for part in parts:
            for match in difflib.get_close_matches(part, strings, cutoff=0.9):
                yield match


@login_required
@require_POST
def ocr_search(request, pk):
    obj = get_screenshot(request, pk)
    if not HAS_OCR:
        return search_results(500, obj)
    try:
        translation = obj.component.translation_set.all()[0]
    except IndexError:
        return search_results(500, obj)

    # Load image
    original_image = Image.open(obj.image.path)
    # Convert to greyscale
    original_image = original_image.convert("L")
    # Resize image (tesseract works best around 300dpi)
    scaled_image = original_image.copy().resize(
        [size * 4 for size in original_image.size],
        Image.BICUBIC
    )

    # Find all our strings
    sources = dict(translation.unit_set.values_list('source', 'pk'))
    strings = tuple(sources.keys())

    results = set()

    # Extract and match strings
    with PyTessBaseAPI() as api:
        for image in (original_image, scaled_image):
            for match in ocr_extract(api, image, strings):
                results.add(sources[match])

    return search_results(
        200,
        obj,
        translation.unit_set.filter(pk__in=results)
    )


@login_required
@require_POST
def add_source(request, pk):
    obj = get_screenshot(request, pk)
    result = try_add_source(request, obj)
    return JsonResponse(
        data={'responseCode': 200, 'status': result}
    )


@login_required
def get_sources(request, pk):
    obj = get_screenshot(request, pk)
    return render(
        request, 'screenshots/screenshot_sources_body.html',
        {'sources': obj.sources.all(), 'object': obj}
    )
