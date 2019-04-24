# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from weblate.trans.models.change import Change
from weblate.trans.forms import ReportsForm
from weblate.trans.util import redirect_param
from weblate.utils.views import get_component, show_form_errors


RST_HEADING = ' '.join([
    '=' * 40,
    '=' * 40,
    '=' * 20,
    '=' * 20,
    '=' * 20,
    '=' * 20,
    '=' * 20,
    '=' * 20,
    '=' * 20,
    '=' * 20,
    '=' * 20,
    '=' * 20,
    '=' * 20,
    '=' * 20,
    '=' * 20,
    '=' * 20,
    '=' * 20,
])

HTML_HEADING = '<table>\n<tr>{0}</tr>'


def generate_credits(component, start_date, end_date):
    """Generate credits data for given component."""

    result = []

    for translation in component.translation_set.all():
        authors = Change.objects.authors_list(
            translation,
            (start_date, end_date),
        )
        if not authors:
            continue
        result.append({translation.language.name: sorted(set(authors))})

    return result


@login_required
@require_POST
def get_credits(request, project, component):
    """View for credits"""
    obj = get_component(request, project, component)

    if not request.user.has_perm('reports.view', obj):
        raise PermissionDenied()

    form = ReportsForm(request.POST)

    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, '#reports')

    data = generate_credits(
        obj,
        form.cleaned_data['start_date'],
        form.cleaned_data['end_date'],
    )

    if form.cleaned_data['style'] == 'json':
        return JsonResponse(data=data, safe=False)

    if form.cleaned_data['style'] == 'html':
        start = '<table>'
        row_start = '<tr>'
        language_format = '<th>{0}</th>'
        translator_start = '<td><ul>'
        translator_format = '<li><a href="mailto:{0}">{1}</a></li>'
        translator_end = '</ul></td>'
        row_end = '</tr>'
        mime = 'text/html'
        end = '</table>'
    else:
        start = ''
        row_start = ''
        language_format = '* {0}\n'
        translator_start = ''
        translator_format = '    * {1} <{0}>'
        translator_end = ''
        row_end = ''
        mime = 'text/plain'
        end = ''

    result = []

    result.append(start)

    for language in data:
        name, translators = language.popitem()
        result.append(row_start)
        result.append(language_format.format(name))
        result.append(
            ''.join((
                translator_start,
                '\n'.join(
                    [translator_format.format(*t) for t in translators]
                ),
                translator_end,
            ))
        )
        result.append(row_end)

    result.append(end)

    return HttpResponse(
        '\n'.join(result),
        content_type='{0}; charset=utf-8'.format(mime),
    )


def generate_counts(component, start_date, end_date):
    """Generate credits data for given component."""

    result = {}

    for translation in component.translation_set.all():
        authors = Change.objects.content().filter(
            translation=translation,
            timestamp__range=(start_date, end_date),
        ).values_list(
            'author__email', 'author__full_name', 'unit__num_words', 'action',
            'target', 'unit__source',
        )
        for email, name, src_words, action, target, source in authors:
            if src_words is None:
                continue
            if email not in result:
                result[email] = {
                    'name': name,
                    'email': email,

                    't_chars': 0,
                    't_words': 0,
                    'chars': 0,
                    'words': 0,
                    'count': 0,

                    't_chars_new': 0,
                    't_words_new': 0,
                    'chars_new': 0,
                    'words_new': 0,
                    'count_new': 0,

                    't_chars_edit': 0,
                    't_words_edit': 0,
                    'chars_edit': 0,
                    'words_edit': 0,
                    'count_edit': 0,
                }
            src_chars = len(source)
            tgt_chars = len(target)
            tgt_words = len(target.split())

            result[email]['chars'] += src_chars
            result[email]['words'] += src_words
            result[email]['t_chars'] += tgt_chars
            result[email]['t_words'] += tgt_words
            result[email]['count'] += 1

            if action == Change.ACTION_NEW:
                result[email]['t_chars_new'] += tgt_chars
                result[email]['t_words_new'] += tgt_words
                result[email]['chars_new'] += src_chars
                result[email]['words_new'] += src_words
                result[email]['count_new'] += 1
            else:
                result[email]['t_chars_edit'] += tgt_chars
                result[email]['t_words_edit'] += tgt_words
                result[email]['chars_edit'] += src_chars
                result[email]['words_edit'] += src_words
                result[email]['count_edit'] += 1

    return list(result.values())


@login_required
@require_POST
def get_counts(request, project, component):
    """View for work counts"""
    obj = get_component(request, project, component)

    if not request.user.has_perm('reports.view', obj):
        raise PermissionDenied()

    form = ReportsForm(request.POST)

    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, '#reports')

    data = generate_counts(
        obj,
        form.cleaned_data['start_date'],
        form.cleaned_data['end_date'],
    )

    if form.cleaned_data['style'] == 'json':
        return JsonResponse(data=data, safe=False)

    headers = (
        'Name',
        'Email',
        'Count total',
        'Source words total',
        'Source chars total',
        'Target words total',
        'Target chars total',

        'Count new',
        'Source words new',
        'Source chars new',
        'Target words new',
        'Target chars new',

        'Count edited',
        'Source words edited',
        'Source chars edited',
        'Target words edited',
        'Target chars edited',
    )

    if form.cleaned_data['style'] == 'html':
        start = HTML_HEADING.format(
            ''.join(['<th>{0}</th>'.format(h) for h in headers])
        )
        row_start = '<tr>'
        cell_name = cell_count = '<td>{0}</td>\n'
        row_end = '</tr>'
        mime = 'text/html'
        end = '</table>'
    else:
        start = '{0}\n{1} {2}\n{0}'.format(
            RST_HEADING,
            ' '.join(['{0:40}'.format(h) for h in headers[:2]]),
            ' '.join(['{0:20}'.format(h) for h in headers[2:]]),
        )
        row_start = ''
        cell_name = '{0:40} '
        cell_count = '{0:20} '
        row_end = ''
        mime = 'text/plain'
        end = RST_HEADING

    result = []

    result.append(start)

    for item in data:
        if row_start:
            result.append(row_start)
        result.append(
            ''.join((
                cell_name.format(item['name']),
                cell_name.format(item['email']),

                cell_count.format(item['count']),
                cell_count.format(item['words']),
                cell_count.format(item['chars']),
                cell_count.format(item['t_words']),
                cell_count.format(item['t_chars']),

                cell_count.format(item['count_new']),
                cell_count.format(item['words_new']),
                cell_count.format(item['chars_new']),
                cell_count.format(item['t_words_new']),
                cell_count.format(item['t_chars_new']),

                cell_count.format(item['count_edit']),
                cell_count.format(item['words_edit']),
                cell_count.format(item['chars_edit']),
                cell_count.format(item['t_words_edit']),
                cell_count.format(item['t_chars_edit']),
            ))
        )
        if row_end:
            result.append(row_end)

    result.append(end)

    return HttpResponse(
        '\n'.join(result),
        content_type='{0}; charset=utf-8'.format(mime),
    )
