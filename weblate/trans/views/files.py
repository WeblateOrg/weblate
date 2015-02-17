# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

from django.utils.translation import ugettext as _, ungettext
from django.shortcuts import redirect
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import Http404

from weblate.trans.forms import get_upload_form
from weblate.trans.views.helper import get_translation


def download_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    srcfilename = obj.get_filename()

    # Construct file name (do not use real filename as it is usually not
    # that useful)
    filename = '%s-%s-%s.%s' % (project, subproject, lang, obj.store.extension)

    # Create response
    with open(srcfilename) as handle:
        response = HttpResponse(
            handle.read(),
            content_type=obj.store.mimetype
        )

    # Fill in response headers
    response['Content-Disposition'] = 'attachment; filename=%s' % filename

    return response


def download_language_pack(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)
    if not obj.supports_language_pack():
        raise Http404('Language pack download not supported')

    filename, mime = obj.store.get_language_pack_meta()

    # Create response
    response = HttpResponse(
        obj.store.get_language_pack(),
        content_type=mime
    )

    # Fill in response headers
    response['Content-Disposition'] = 'attachment; filename=%s' % filename

    return response


@login_required
@permission_required('trans.upload_translation')
def upload_translation(request, project, subproject, lang):
    '''
    Handling of translation uploads.
    '''
    obj = get_translation(request, project, subproject, lang)

    # Check method and lock
    if obj.is_locked(request) or request.method != 'POST':
        messages.error(request, _('Access denied.'))
        return redirect(obj)

    # Get correct form handler based on permissions
    form = get_upload_form(request)(request.POST, request.FILES)

    # Check form validity
    if not form.is_valid():
        messages.error(request, _('Please fix errors in the form.'))
        return redirect(obj)

    # Create author name
    author = None
    if (request.user.has_perm('trans.author_translation') and
            form.cleaned_data['author_name'] != '' and
            form.cleaned_data['author_email'] != ''):
        author = '%s <%s>' % (
            form.cleaned_data['author_name'],
            form.cleaned_data['author_email']
        )

    # Check for overwriting
    overwrite = False
    if request.user.has_perm('trans.overwrite_translation'):
        overwrite = form.cleaned_data['overwrite']

    # Do actual import
    try:
        ret, count = obj.merge_upload(
            request,
            request.FILES['file'],
            overwrite,
            author,
            merge_header=form.cleaned_data['merge_header'],
            method=form.cleaned_data['method']
        )
        if ret:
            messages.success(
                request,
                ungettext(
                    'File content successfully merged into translation, '
                    'processed %d string.',
                    'File content successfully merged into translation, '
                    'processed %d strings.',
                    count
                ) % count
            )
        else:
            messages.info(
                request,
                ungettext(
                    'There were no new strings in uploaded file, '
                    'processed %d string.',
                    'There were no new strings in uploaded file, '
                    'processed %d strings.',
                    count
                ) % count
            )
    except Exception as error:
        messages.error(
            request,
            _('File content merge failed: %s' % unicode(error))
        )

    return redirect(obj)
