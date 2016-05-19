# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import sys

from django.core.exceptions import PermissionDenied
from django.utils.translation import ugettext as _, ungettext
from django.utils.encoding import force_text
from django.shortcuts import redirect
from django.http import Http404
from django.views.decorators.http import require_POST

from weblate.trans import messages
from weblate.trans.util import report_error
from weblate.trans.forms import get_upload_form
from weblate.trans.views.helper import (
    get_translation, import_message, download_translation_file
)
from weblate.trans.permissions import (
    can_author_translation, can_overwrite_translation,
    can_upload_translation,
)


def download_translation_format(request, project, subproject, lang, fmt):
    obj = get_translation(request, project, subproject, lang)

    return download_translation_file(obj, fmt)


def download_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    return download_translation_file(obj)


def download_language_pack(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    if not obj.supports_language_pack():
        raise Http404('Language pack download not supported')

    return download_translation_file(
        obj,
        obj.subproject.file_format_cls.language_pack
    )


@require_POST
def upload_translation(request, project, subproject, lang):
    '''
    Handling of translation uploads.
    '''
    obj = get_translation(request, project, subproject, lang)

    if not can_upload_translation(request.user, obj):
        raise PermissionDenied()

    # Check method and lock
    if obj.is_locked(request.user):
        messages.error(request, _('Access denied.'))
        return redirect(obj)

    # Get correct form handler based on permissions
    form = get_upload_form(request.user, obj.subproject.project)(
        request.POST, request.FILES
    )

    # Check form validity
    if not form.is_valid():
        messages.error(request, _('Please fix errors in the form.'))
        return redirect(obj)

    # Create author name
    author = None
    if (can_author_translation(request.user, obj.subproject.project) and
            form.cleaned_data['author_name'] != '' and
            form.cleaned_data['author_email'] != ''):
        author = '%s <%s>' % (
            form.cleaned_data['author_name'],
            form.cleaned_data['author_email']
        )

    # Check for overwriting
    overwrite = False
    if can_overwrite_translation(request.user, obj.subproject.project):
        overwrite = form.cleaned_data['overwrite']

    # Do actual import
    try:
        ret, count = obj.merge_upload(
            request,
            request.FILES['file'],
            overwrite,
            author,
            merge_header=form.cleaned_data['merge_header'],
            merge_comments=form.cleaned_data['merge_comments'],
            method=form.cleaned_data['method'],
            fuzzy=form.cleaned_data['fuzzy'],
        )
        import_message(
            request, count,
            _('No strings were imported from the uploaded file.'),
            ungettext(
                'Processed %d string from the uploaded files.',
                'Processed %d strings from the uploaded files.',
                count
            )
        )
        if not ret:
            messages.warning(
                request,
                _('There were no new strings in uploaded file!')
            )
    except Exception as error:
        messages.error(
            request, _('File content merge failed: %s') % force_text(error)
        )
        report_error(error, sys.exc_info(), request)

    return redirect(obj)
