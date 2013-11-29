# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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

from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.http import HttpResponse, HttpResponseBadRequest
from django.contrib.auth.decorators import permission_required
from django.db.models import Q
from django.core.urlresolvers import reverse

from weblate.trans.models import Unit, Check, Dictionary
from weblate.trans.machine import MACHINE_TRANSLATION_SERVICES
from weblate.trans.decorators import any_permission_required
from weblate.trans.views.helper import get_project, get_subproject, get_translation

from whoosh.analysis import StandardAnalyzer, StemmingAnalyzer
from urllib import urlencode
import json


def get_string(request, checksum):
    '''
    AJAX handler for getting raw string.
    '''
    units = Unit.objects.filter(checksum=checksum)
    if units.count() == 0:
        return HttpResponse('')
    units[0].check_acl(request)

    return HttpResponse(units[0].get_source_plurals()[0])


@permission_required('trans.use_mt')
def translate(request, unit_id):
    '''
    AJAX handler for translating.
    '''
    unit = get_object_or_404(Unit, pk=int(unit_id))
    unit.check_acl(request)

    service_name = request.GET.get('service', 'INVALID')

    if not service_name in MACHINE_TRANSLATION_SERVICES:
        return HttpResponseBadRequest('Invalid service specified')

    translation_service = MACHINE_TRANSLATION_SERVICES[service_name]

    # Error response
    response = {
        'responseStatus': 500,
        'service': translation_service.name,
        'responseDetails': '',
        'translations': [],
    }

    try:
        response['translations'] = translation_service.translate(
            unit.translation.language.code,
            unit.get_source_plurals()[0],
            unit,
            request.user
        )
        response['responseStatus'] = 200
    except Exception as exc:
        response['responseDetails'] = '%s: %s' % (
            exc.__class__.__name__,
            str(exc)
        )

    return HttpResponse(
        json.dumps(response),
        content_type='application/json'
    )


def get_other(request, unit_id):
    '''
    AJAX handler for same strings in other subprojects.
    '''
    unit = get_object_or_404(Unit, pk=int(unit_id))
    unit.check_acl(request)

    other = Unit.objects.same(unit)

    return render_to_response('js/other.html', RequestContext(request, {
        'other': other.select_related(),
        'unit': unit,
        'search_id': request.GET.get('sid', ''),
        'offset': request.GET.get('offset', ''),
    }))


def get_unit_changes(request, unit_id):
    '''
    Returns unit's recent changes.
    '''
    unit = get_object_or_404(Unit, pk=int(unit_id))
    unit.check_acl(request)

    return render_to_response('last-changes.html', RequestContext(request, {
        'last_changes': unit.change_set.all()[:10],
        'last_changes_rss': reverse(
            'rss-translation',
            kwargs=unit.translation.get_kwargs(),
        ),
        'last_changes_url': urlencode(unit.translation.get_kwargs()),
    }))


def get_dictionary(request, unit_id):
    '''
    Lists words from dictionary for current translation.
    '''
    unit = get_object_or_404(Unit, pk=int(unit_id))
    unit.check_acl(request)
    words = set()

    # Prepare analyzers
    # - standard analyzer simply splits words
    # - stemming extracts stems, to catch things like plurals
    analyzers = (StandardAnalyzer(), StemmingAnalyzer())

    # Extract words from all plurals and from context
    for text in unit.get_source_plurals() + [unit.context]:
        for analyzer in analyzers:
            words = words.union([token.text for token in analyzer(text)])

    # Grab all words in the dictionary
    dictionary = Dictionary.objects.filter(
        project=unit.translation.subproject.project,
        language=unit.translation.language
    )

    if len(words) == 0:
        # No extracted words, no dictionary
        dictionary = dictionary.none()
    else:
        # Build the query (can not use __in as we want case insensitive lookup)
        query = Q()
        for word in words:
            query |= Q(source__iexact=word)

        # Filter dictionary
        dictionary = dictionary.filter(query)

    return render_to_response('js/dictionary.html', RequestContext(request, {
        'dictionary': dictionary,
        'translation': unit.translation,
    }))


@permission_required('trans.ignore_check')
def ignore_check(request, check_id):
    obj = get_object_or_404(Check, pk=int(check_id))
    obj.project.check_acl(request)
    # Mark check for ignoring
    obj.set_ignore()
    # response for AJAX
    return HttpResponse('ok')


@any_permission_required(
    'trans.commit_translation',
    'trans.update_translation'
)
def git_status_project(request, project):
    obj = get_project(request, project)

    return render_to_response('js/git-status.html', RequestContext(request, {
        'object': obj,
    }))


@any_permission_required(
    'trans.commit_translation',
    'trans.update_translation'
)
def git_status_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    return render_to_response('js/git-status.html', RequestContext(request, {
        'object': obj,
    }))


@any_permission_required(
    'trans.commit_translation',
    'trans.update_translation'
)
def git_status_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    return render_to_response('js/git-status.html', RequestContext(request, {
        'object': obj,
    }))


def js_config(request):
    '''
    Generates settings for javascript. Includes things like
    translaiton services.
    '''
    # Machine translation
    machine_services = MACHINE_TRANSLATION_SERVICES.keys()

    return render_to_response(
        'js/config.js',
        RequestContext(
            request,
            {
                'machine_services': machine_services,
            }
        ),
        content_type='application/javascript'
    )


def get_detail(request, project, subproject, checksum):
    '''
    Returns source translation detail in all languages.
    '''
    subproject = get_subproject(request, project, subproject)
    units = Unit.objects.filter(
        checksum=checksum,
        translation__subproject=subproject
    )

    return render_to_response(
        'js/detail.html',
        RequestContext(
            request,
            {
                'units': units,
            }
        )
    )
