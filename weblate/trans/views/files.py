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
from __future__ import unicode_literals

import sys

from django.core.exceptions import PermissionDenied
from django.utils.translation import ugettext as _, ungettext
from django.utils.encoding import force_text
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.trans.forms import get_upload_form, DownloadForm
from weblate.trans.views.helper import (
    get_translation, download_translation_file, show_form_errors,
)


def download_translation_format(request, project, component, lang):
    obj = get_translation(request, project, component, lang)

    form = DownloadForm(request.GET)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect(obj)

    units = obj.unit_set.search(
        form.cleaned_data,
        translation=obj,
    )

    return download_translation_file(obj, form.cleaned_data['format'], units)


def download_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)

    return download_translation_file(obj)


@require_POST
def upload_translation(request, project, component, lang):
    """Handling of translation uploads."""
    obj = get_translation(request, project, component, lang)

    if not request.user.has_perm('upload.perform', obj):
        raise PermissionDenied()

    # Check method and lock
    if obj.component.locked:
        messages.error(request, _('Access denied.'))
        return redirect(obj)

    # Get correct form handler based on permissions
    form = get_upload_form(
        request.user, obj,
        request.POST, request.FILES
    )

    # Check form validity
    if not form.is_valid():
        messages.error(request, _('Please fix errors in the form.'))
        show_form_errors(request, form)
        return redirect(obj)

    # Create author name
    author = None
    if (request.user.has_perm('upload.authorship', obj) and
            form.cleaned_data['author_name'] != '' and
            form.cleaned_data['author_email'] != ''):
        author = '{0} <{1}>'.format(
            form.cleaned_data['author_name'],
            form.cleaned_data['author_email']
        )

    # Check for overwriting
    overwrite = False
    if request.user.has_perm('upload.overwrite', obj):
        overwrite = form.cleaned_data['upload_overwrite']

    # Do actual import
    try:
        not_found, skipped, accepted, total = obj.merge_upload(
            request,
            request.FILES['file'],
            overwrite,
            author,
            merge_header=form.cleaned_data['merge_header'],
            method=form.cleaned_data['method'],
            fuzzy=form.cleaned_data['fuzzy'],
        )
        if total == 0:
            message = _('No strings were imported from the uploaded file.')
        else:
            message = ungettext(
                'Processed {0} string from the uploaded files '
                '(skipped: {1}, not found: {2}, updated: {3}).',
                'Processed {0} strings from the uploaded files '
                '(skipped: {1}, not found: {2}, updated: {3}).',
                total
            ).format(total, skipped, not_found, accepted)
        if accepted == 0:
            messages.warning(request, message)
        else:
            messages.success(request, message)
    except Exception as error:
        messages.error(
            request, _('File content merge failed: %s') % force_text(error)
        )
        report_error(error, sys.exc_info(), request)

    return redirect(obj)
