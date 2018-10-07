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

from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404, redirect
from django.utils.encoding import force_text
from django.utils.translation import ugettext as _, ungettext
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from weblate.utils import messages
from weblate.formats.exporters import get_exporter
from weblate.trans.models import Translation, Dictionary, Change, Unit
from weblate.lang.models import Language
from weblate.utils.site import get_site_url
from weblate.utils.errors import report_error
from weblate.trans.util import render, redirect_next, redirect_param
from weblate.trans.forms import WordForm, DictUploadForm, LetterForm
from weblate.utils.views import get_project, import_message
from weblate.utils.views import get_paginator


def dict_title(prj, lang):
    """Return dictionary title."""
    return _('%(language)s dictionary for %(project)s') % {
        'language': lang,
        'project': prj
    }


@never_cache
def show_dictionaries(request, project):
    obj = get_project(request, project)
    dicts = Translation.objects.filter(
        component__project=obj
    ).values_list('language', flat=True).distinct()

    return render(
        request,
        'dictionaries.html',
        {
            'title': _('Dictionaries'),
            'dicts': Language.objects.filter(id__in=dicts),
            'project': obj,
        }
    )


@never_cache
def edit_dictionary(request, project, lang, pk):
    prj = get_project(request, project)
    if not request.user.has_perm('glossary.edit', prj):
        raise PermissionDenied()
    lang = get_object_or_404(Language, code=lang)
    word = get_object_or_404(
        Dictionary,
        project=prj,
        language=lang,
        id=pk,
    )

    if request.method == 'POST':
        form = WordForm(request.POST)
        if form.is_valid():
            word.edit(
                request,
                form.cleaned_data['source'],
                form.cleaned_data['target']
            )
            return redirect(
                'show_dictionary',
                project=prj.slug,
                lang=lang.code
            )
    else:
        form = WordForm(
            initial={'source': word.source, 'target': word.target}
        )

    last_changes = Change.objects.last_changes(request.user).filter(
        dictionary=word,
    )[:10]

    return render(
        request,
        'edit_dictionary.html',
        {
            'title': dict_title(prj, lang),
            'project': prj,
            'language': lang,
            'form': form,
            'last_changes': last_changes,
            'last_changes_url': urlencode({
                'project': prj.slug,
                'lang': lang.code,
                'glossary': 1
            }),
        }
    )


@require_POST
def delete_dictionary(request, project, lang, pk):
    prj = get_project(request, project)
    if not request.user.has_perm('glossary.delete', prj):
        raise PermissionDenied()

    lang = get_object_or_404(Language, code=lang)
    word = get_object_or_404(
        Dictionary,
        project=prj,
        language=lang,
        id=pk
    )

    word.delete()

    params = {}
    for param in ('letter', 'limit', 'page'):
        if param in request.POST:
            params[param] = request.POST[param]

    if params:
        param = '?' + urlencode(params)
    else:
        param = ''

    return redirect_param(
        'show_dictionary',
        param,
        project=prj.slug,
        lang=lang.code
    )


@require_POST
def upload_dictionary(request, project, lang):
    prj = get_project(request, project)
    if not request.user.has_perm('glossary.upload', prj):
        raise PermissionDenied()
    lang = get_object_or_404(Language, code=lang)

    form = DictUploadForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            count = Dictionary.objects.upload(
                request,
                prj,
                lang,
                request.FILES['file'],
                form.cleaned_data['method']
            )
            import_message(
                request, count,
                _('No words to import found in file.'),
                ungettext(
                    'Imported %d word from the uploaded file.',
                    'Imported %d words from the uploaded file.',
                    count
                )
            )
        except Exception as error:
            report_error(error, request)
            messages.error(
                request, _('File upload has failed: %s') % force_text(error)
            )
    else:
        messages.error(request, _('Failed to process form!'))
    return redirect(
        'show_dictionary',
        project=prj.slug,
        lang=lang.code
    )


@never_cache
def download_dictionary(request, project, lang):
    """Export dictionary into various formats."""
    prj = get_project(request, project)
    lang = get_object_or_404(Language, code=lang)

    # Parse parameters
    export_format = None
    if 'format' in request.GET:
        export_format = request.GET['format']
    if export_format not in ('csv', 'po', 'tbx', 'xliff'):
        export_format = 'csv'

    # Grab all words
    words = Dictionary.objects.filter(
        project=prj,
        language=lang
    ).order_by(Lower('source'))

    # Translate toolkit based export
    exporter = get_exporter(export_format)(
        prj, lang,
        get_site_url(reverse(
            'show_dictionary',
            kwargs={'project': prj.slug, 'lang': lang.code}
        )),
        fieldnames=('source', 'target'),
    )

    # Add words
    for word in words.iterator():
        exporter.add_dictionary(word)

    # Save to response
    return exporter.get_response(
        'glossary-{project}-{language}.{extension}'
    )


def add_dictionary(request, unit_id):
    unit = get_object_or_404(Unit, pk=int(unit_id))
    request.user.check_access(unit.translation.component.project)

    prj = unit.translation.component.project
    lang = unit.translation.language

    code = 403
    results = ''
    words = []

    if request.method == 'POST' and request.user.has_perm('glossary.add', prj):
        form = WordForm(request.POST)
        if form.is_valid():
            word = Dictionary.objects.create(
                request.user,
                project=prj,
                language=lang,
                source=form.cleaned_data['source'],
                target=form.cleaned_data['target']
            )
            words = form.cleaned_data['words']
            words.append(word.id)
            code = 200
            results = render_to_string(
                'glossary-embed.html',
                {
                    'glossary': (
                        Dictionary.objects.get_words(unit) |
                        Dictionary.objects.filter(project=prj, pk__in=words)
                    ),
                    'unit': unit,
                    'user': request.user,
                }
            )

    return JsonResponse(
        data={
            'responseCode': code,
            'results': results,
            'words': ','.join([str(x) for x in words])
        }
    )


@never_cache
def show_dictionary(request, project, lang):
    prj = get_project(request, project)
    lang = get_object_or_404(Language, code=lang)

    if request.method == 'POST' and request.user.has_perm('glossary.add', prj):
        form = WordForm(request.POST)
        if form.is_valid():
            Dictionary.objects.create(
                request.user,
                project=prj,
                language=lang,
                source=form.cleaned_data['source'],
                target=form.cleaned_data['target']
            )
        return redirect_next(
            request.POST.get('next'), request.get_full_path()
        )
    else:
        form = WordForm()

    uploadform = DictUploadForm()

    words = Dictionary.objects.filter(
        project=prj, language=lang
    ).order_by(Lower('source'))

    letterform = LetterForm(request.GET)

    if letterform.is_valid() and letterform.cleaned_data['letter'] != '':
        words = words.filter(
            source__istartswith=letterform.cleaned_data['letter']
        )
        letter = letterform.cleaned_data['letter']
    else:
        letter = ''

    words = get_paginator(request, words)

    last_changes = Change.objects.last_changes(request.user).filter(
        dictionary__project=prj,
        dictionary__language=lang
    )[:10]

    return render(
        request,
        'dictionary.html',
        {
            'title': dict_title(prj, lang),
            'project': prj,
            'language': lang,
            'page_obj': words,
            'form': form,
            'query_string': 'letter={}'.format(letter) if letter else '',
            'uploadform': uploadform,
            'letterform': letterform,
            'letter': letter,
            'last_changes': last_changes,
            'last_changes_url': urlencode({
                'project': prj.slug,
                'lang': lang.code,
                'glossary': 1
            }),
        }
    )
