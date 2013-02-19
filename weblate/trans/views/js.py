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
from django.views.decorators.cache import cache_page
from weblate.trans import appsettings
from django.template import RequestContext
from django.http import HttpResponse
from django.contrib.auth.decorators import permission_required
from django.db.models import Q

from weblate.trans.models import Unit, Check, Dictionary
from weblate.trans.views.edit import parse_search_url
from weblate.trans.decorators import any_permission_required
from weblate.trans.views.helper import get_project, get_subproject, get_translation

from whoosh.analysis import StandardAnalyzer, StemmingAnalyzer
import logging
import json
from xml.etree import ElementTree
import urllib2

logger = logging.getLogger('weblate')


def get_string(request, checksum):
    '''
    AJAX handler for getting raw string.
    '''
    units = Unit.objects.filter(checksum=checksum)
    if units.count() == 0:
        return HttpResponse('')
    units[0].check_acl(request)

    return HttpResponse(units[0].get_source_plurals()[0])


def get_similar(request, unit_id):
    '''
    AJAX handler for getting similar strings.
    '''
    unit = get_object_or_404(Unit, pk=int(unit_id))
    unit.check_acl(request)

    similar_units = Unit.objects.similar(unit)

    # distinct('target') works with Django 1.4 so let's emulate that
    # based on presumption we won't get too many results
    targets = {}
    res = []
    for similar in similar_units:
        if similar.target in targets:
            continue
        targets[similar.target] = 1
        res.append(similar)
    similar = res

    return render_to_response('js/similar.html', RequestContext(request, {
        'similar': similar,
    }))


def get_other(request, unit_id):
    '''
    AJAX handler for same strings in other subprojects.
    '''
    unit = get_object_or_404(Unit, pk=int(unit_id))
    unit.check_acl(request)

    other = Unit.objects.same(unit)

    rqtype, direction, pos, search_query, search_type, search_source, search_target, search_context, search_url = parse_search_url(request)

    return render_to_response('js/other.html', RequestContext(request, {
        'other': other,
        'unit': unit,
        'type': rqtype,
        'search_url': search_url,
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
    }))


@permission_required('trans.ignore_check')
def ignore_check(request, check_id):
    obj = get_object_or_404(Check, pk=int(check_id))
    obj.project.check_acl(request)
    # Mark check for ignoring
    obj.ignore = True
    obj.save()
    # Invalidate caches
    for unit in Unit.objects.filter(checksum=obj.checksum):
        unit.translation.invalidate_cache()
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
    obj = get_subproject(request, subproject, project)

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


# Cache this page for one month, it should not really change much
@cache_page(30 * 24 * 3600)
def js_config(request):
    '''
    Generates settings for javascript. Includes things like
    API keys for translaiton services or list of languages they
    support.
    '''
    # Apertium support
    if appsettings.MT_APERTIUM_KEY is not None and appsettings.MT_APERTIUM_KEY != '':
        try:
            listpairs = urllib2.urlopen('http://api.apertium.org/json/listPairs?key=%s' % appsettings.MT_APERTIUM_KEY)
            pairs = listpairs.read()
            parsed = json.loads(pairs)
            apertium_langs = [p['targetLanguage'] for p in parsed['responseData'] if p['sourceLanguage'] == 'en']
        except Exception as e:
            logger.error('failed to get supported languages from Apertium, using defaults (%s)', str(e))
            apertium_langs = ['gl', 'ca', 'es', 'eo']
    else:
        apertium_langs = None

    # Microsoft translator support
    if appsettings.MT_MICROSOFT_KEY is not None and appsettings.MT_MICROSOFT_KEY != '':
        try:
            listpairs = urllib2.urlopen('http://api.microsofttranslator.com/V2/Http.svc/GetLanguagesForTranslate?appID=%s' % appsettings.MT_MICROSOFT_KEY)
            data = listpairs.read()
            parsed = ElementTree.fromstring(data)
            microsoft_langs = [p.text for p in parsed.getchildren()]
        except Exception as e:
            logger.error('failed to get supported languages from Microsoft, using defaults (%s)', str(e))
            microsoft_langs = [
                'ar', 'bg', 'ca', 'zh-CHS', 'zh-CHT', 'cs', 'da', 'nl', 'en',
                'et', 'fi', 'fr', 'de', 'el', 'ht', 'he', 'hi', 'mww', 'hu',
                'id', 'it', 'ja', 'ko', 'lv', 'lt', 'no', 'fa', 'pl', 'pt',
                'ro', 'ru', 'sk', 'sl', 'es', 'sv', 'th', 'tr', 'uk', 'vi'
            ]
    else:
        microsoft_langs = None

    return render_to_response(
        'js/config.js',
        RequestContext(
            request,
            {
                'apertium_langs': apertium_langs,
                'microsoft_langs': microsoft_langs,
            }
        ),
        mimetype='application/javascript'
    )
