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
from django.core.servers.basehttp import FileWrapper
from django.utils.translation import ugettext as _
import django.utils.translation
from django.template import RequestContext, loader
from django.http import (
    HttpResponse, HttpResponseRedirect, HttpResponseNotFound, Http404
)
from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required, permission_required, user_passes_test
)
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q, Count, Sum
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse
from django.contrib.sites.models import Site
from django.utils.safestring import mark_safe

from weblate.trans.models import (
    Project, SubProject, Translation, Unit, Suggestion, Check,
    Dictionary, Change, Comment, get_versions
)
from weblate.lang.models import Language
from weblate.trans.checks import CHECKS
from weblate.trans.forms import (
    TranslationForm, UploadForm, SimpleUploadForm, ExtraUploadForm, SearchForm,
    MergeForm, AutoForm, WordForm, DictUploadForm, ReviewForm, LetterForm,
    AntispamForm, CommentForm
)
from weblate.trans.util import join_plural
from weblate.accounts.models import Profile, send_notification_email
import weblate

from whoosh.analysis import StandardAnalyzer, StemmingAnalyzer
import datetime
import logging
import os.path
import json
import csv
from xml.etree import ElementTree
import urllib2


# See https://code.djangoproject.com/ticket/6027
class FixedFileWrapper(FileWrapper):
    def __iter__(self):
        self.filelike.seek(0)
        return self

logger = logging.getLogger('weblate')


def home(request):
    '''
    Home page of Weblate showing list of projects, stats
    and user links if logged in.
    '''
    projects = Project.objects.all_acl(request.user)
    acl_projects = projects
    if projects.count() == 1:
        projects = SubProject.objects.filter(project=projects[0])

    # Warn about not filled in username (usually caused by migration of
    # users from older system
    if not request.user.is_anonymous() and request.user.get_full_name() == '':
        messages.warning(
            request,
            _('Please set your full name in your profile.')
        )

    # Load user translations if user is authenticated
    usertranslations = None
    if request.user.is_authenticated():
        profile = request.user.get_profile()

        usertranslations = Translation.objects.filter(
            language__in=profile.languages.all()
        ).order_by(
            'subproject__project__name', 'subproject__name'
        )

    # Some stats
    top_translations = Profile.objects.order_by('-translated')[:10]
    top_suggestions = Profile.objects.order_by('-suggested')[:10]
    last_changes = Change.objects.filter(
        translation__subproject__project__in=acl_projects,
    ).order_by( '-timestamp')[:10]

    return render_to_response('index.html', RequestContext(request, {
        'projects': projects,
        'top_translations': top_translations,
        'top_suggestions': top_suggestions,
        'last_changes': last_changes,
        'last_changes_rss': reverse('rss'),
        'usertranslations': usertranslations,
    }))


def show_checks(request):
    '''
    List of failing checks.
    '''
    allchecks = Check.objects.filter(
        ignore=False
    ).values('check').annotate(count=Count('id'))
    return render_to_response('checks.html', RequestContext(request, {
        'checks': allchecks,
        'title': _('Failing checks'),
    }))


def show_check(request, name):
    '''
    Details about failing check.
    '''
    try:
        check = CHECKS[name]
    except KeyError:
        raise Http404('No check matches the given query.')

    checks = Check.objects.filter(
        check=name, ignore=False
    ).values('project__slug').annotate(count=Count('id'))

    return render_to_response('check.html', RequestContext(request, {
        'checks': checks,
        'title': check.name,
        'check': check,
    }))


def show_check_project(request, name, project):
    '''
    Show checks failing in a project.
    '''
    prj = get_object_or_404(Project, slug=project)
    prj.check_acl(request)
    try:
        check = CHECKS[name]
    except KeyError:
        raise Http404('No check matches the given query.')
    units = Unit.objects.none()
    if check.target:
        langs = Check.objects.filter(
            check=name, project=prj, ignore=False
        ).values_list('language', flat=True).distinct()
        for lang in langs:
            checks = Check.objects.filter(
                check=name, project=prj, language=lang, ignore=False
            ).values_list('checksum', flat=True)
            res = Unit.objects.filter(
                checksum__in=checks,
                translation__language=lang,
                translation__subproject__project=prj,
                translated=True
            ).values(
                'translation__subproject__slug',
                'translation__subproject__project__slug'
            ).annotate(count=Count('id'))
            units |= res
    if check.source:
        checks = Check.objects.filter(
            check=name,
            project=prj,
            language=None,
            ignore=False
        ).values_list(
            'checksum', flat=True
        )
        for subproject in prj.subproject_set.all():
            lang = subproject.translation_set.all()[0].language
            res = Unit.objects.filter(
                checksum__in=checks,
                translation__language=lang,
                translation__subproject=subproject
            ).values(
                'translation__subproject__slug',
                'translation__subproject__project__slug'
            ).annotate(count=Count('id'))
            units |= res

    return render_to_response('check_project.html', RequestContext(request, {
        'checks': units,
        'title': '%s/%s' % (prj.__unicode__(), check.name),
        'check': check,
        'project': prj,
    }))


def show_check_subproject(request, name, project, subproject):
    '''
    Show checks failing in a subproject.
    '''
    subprj = get_object_or_404(
        SubProject,
        slug=subproject,
        project__slug=project
    )
    subprj.check_acl(request)
    try:
        check = CHECKS[name]
    except KeyError:
        raise Http404('No check matches the given query.')
    units = Unit.objects.none()
    if check.target:
        langs = Check.objects.filter(
            check=name,
            project=subprj.project,
            ignore=False
        ).values_list(
            'language', flat=True
        ).distinct()
        for lang in langs:
            checks = Check.objects.filter(
                check=name,
                project=subprj.project,
                language=lang,
                ignore=False
            ).values_list('checksum', flat=True)
            res = Unit.objects.filter(
                translation__subproject=subprj,
                checksum__in=checks,
                translation__language=lang,
                translated=True
            ).values(
                'translation__language__code'
            ).annotate(count=Count('id'))
            units |= res
    source_checks = []
    if check.source:
        checks = Check.objects.filter(
            check=name, project=subprj.project,
            language=None,
            ignore=False
        ).values_list('checksum', flat=True)
        lang = subprj.translation_set.all()[0].language
        res = Unit.objects.filter(
            translation__subproject=subprj,
            checksum__in=checks,
            translation__language=lang
        ).count()
        if res > 0:
            source_checks.append(res)
    return render_to_response(
        'check_subproject.html',
        RequestContext(request, {
            'checks': units,
            'source_checks': source_checks,
            'anychecks': len(units) + len(source_checks) > 0,
            'title': '%s/%s' % (subprj.__unicode__(), check.name),
            'check': check,
            'subproject': subprj,
        })
    )


def show_languages(request):
    return render_to_response('languages.html', RequestContext(request, {
        'languages': Language.objects.have_translation(),
        'title': _('Languages'),
    }))


def show_language(request, lang):
    obj = get_object_or_404(Language, code=lang)
    last_changes = Change.objects.filter(
        translation__language=obj
    ).order_by('-timestamp')[:10]
    dicts = Dictionary.objects.filter(
        language=obj
    ).values_list('project', flat=True).distinct()

    return render_to_response('language.html', RequestContext(request, {
        'object': obj,
        'last_changes': last_changes,
        'last_changes_rss': reverse('rss-language', kwargs={'lang': obj.code}),
        'dicts': Project.objects.filter(id__in=dicts),
    }))


def show_dictionaries(request, project):
    obj = get_object_or_404(Project, slug=project)
    obj.check_acl(request)
    dicts = Translation.objects.filter(
        subproject__project=obj
    ).values_list('language', flat=True).distinct()

    return render_to_response('dictionaries.html', RequestContext(request, {
        'title': _('Dictionaries'),
        'dicts': Language.objects.filter(id__in=dicts),
        'project': obj,
    }))


@login_required
@permission_required('trans.change_dictionary')
def edit_dictionary(request, project, lang):
    prj = get_object_or_404(Project, slug=project)
    prj.check_acl(request)
    lang = get_object_or_404(Language, code=lang)
    word = get_object_or_404(
        Dictionary,
        project=prj,
        language=lang,
        id=request.GET.get('id')
    )

    if request.method == 'POST':
        form = WordForm(request.POST)
        if form.is_valid():
            word.source = form.cleaned_data['source']
            word.target = form.cleaned_data['target']
            word.save()
            return HttpResponseRedirect(reverse(
                'weblate.trans.views.show_dictionary',
                kwargs={'project': prj.slug, 'lang': lang.code}
            ))
    else:
        form = WordForm(
            initial={'source': word.source, 'target': word.target}
        )

    return render_to_response('edit_dictionary.html', RequestContext(request, {
        'title': _('%(language)s dictionary for %(project)s') %
        {'language': lang, 'project': prj},
        'project': prj,
        'language': lang,
        'form': form,
    }))


@login_required
@permission_required('trans.delete_dictionary')
def delete_dictionary(request, project, lang):
    prj = get_object_or_404(Project, slug=project)
    prj.check_acl(request)
    lang = get_object_or_404(Language, code=lang)
    word = get_object_or_404(
        Dictionary,
        project=prj,
        language=lang,
        id=request.POST.get('id')
    )

    word.delete()

    return HttpResponseRedirect(reverse(
        'weblate.trans.views.show_dictionary',
        kwargs={'project': prj.slug, 'lang': lang.code})
    )


@login_required
@permission_required('trans.upload_dictionary')
def upload_dictionary(request, project, lang):
    prj = get_object_or_404(Project, slug=project)
    prj.check_acl(request)
    lang = get_object_or_404(Language, code=lang)

    if request.method == 'POST':
        form = DictUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                count = Dictionary.objects.upload(
                    prj,
                    lang,
                    request.FILES['file'],
                    form.cleaned_data['overwrite']
                )
                if count == 0:
                    messages.warning(
                        request,
                        _('No words to import found in file.')
                    )
                else:
                    messages.info(
                        request,
                        _('Imported %d words from file.') % count
                    )
            except Exception as e:
                messages.error(
                    request,
                    _('File content merge failed: %s' % unicode(e))
                )
        else:
            messages.error(request, _('Failed to process form!'))
    else:
        messages.error(request, _('Failed to process form!'))
    return HttpResponseRedirect(reverse(
        'weblate.trans.views.show_dictionary',
        kwargs={'project': prj.slug, 'lang': lang.code}
    ))


def download_dictionary(request, project, lang):
    '''
    Exports dictionary.
    '''
    prj = get_object_or_404(Project, slug=project)
    prj.check_acl(request)
    lang = get_object_or_404(Language, code=lang)

    # Parse parameters
    export_format = None
    if 'format' in request.GET:
        export_format = request.GET['format']
    if not export_format in ['csv', 'po']:
        export_format = 'csv'

    # Grab all words
    words = Dictionary.objects.filter(
        project=prj,
        language=lang
    ).order_by('source')

    if export_format == 'csv':
        response = HttpResponse(mimetype='text/csv; charset=utf-8')
        filename = 'dictionary-%s-%s.csv' % (prj.slug, lang.code)
        response['Content-Disposition'] = 'attachment; filename=%s' % filename

        writer = csv.writer(response)

        for word in words.iterator():
            writer.writerow((
                word.source.encode('utf8'), word.target.encode('utf8')
            ))

        return response
    elif export_format == 'po':
        from translate.storage.po import pounit, pofile

        response = HttpResponse(mimetype='text/x-po; charset=utf-8')
        filename = 'dictionary-%s-%s.po' % (prj.slug, lang.code)
        response['Content-Disposition'] = 'attachment; filename=%s' % filename

        store = pofile()

        site = Site.objects.get_current()
        store.updateheader(
            add=True,
            language=lang.code,
            x_generator='Weblate %s' % weblate.VERSION,
            project_id_version='%s dictionary for %s' % (lang.name, prj.name),
            language_team='%s <http://%s%s>' % (
                lang.name,
                site.domain,
                reverse(
                    'weblate.trans.views.show_dictionary',
                    kwargs={'project': prj.slug, 'lang': lang.code}
                ),
            )
        )

        for word in words.iterator():
            unit = pounit(word.source)
            unit.target = word.target
            store.addunit(unit)

        store.savefile(response)

        return response


def show_dictionary(request, project, lang):
    prj = get_object_or_404(Project, slug=project)
    prj.check_acl(request)
    lang = get_object_or_404(Language, code=lang)

    if (request.method == 'POST'
            and request.user.has_perm('trans.add_dictionary')):
        form = WordForm(request.POST)
        if form.is_valid():
            Dictionary.objects.create(
                project=prj,
                language=lang,
                source=form.cleaned_data['source'],
                target=form.cleaned_data['target']
            )
        return HttpResponseRedirect(request.get_full_path())
    else:
        form = WordForm()

    uploadform = DictUploadForm()

    words = Dictionary.objects.filter(
        project=prj, language=lang
    ).order_by('source')

    limit = request.GET.get('limit', 25)
    page = request.GET.get('page', 1)

    letterform = LetterForm(request.GET)

    if letterform.is_valid() and letterform.cleaned_data['letter'] != '':
        words = words.filter(
            source__istartswith=letterform.cleaned_data['letter']
        )
        letter = letterform.cleaned_data['letter']
    else:
        letter = ''

    paginator = Paginator(words, limit)

    try:
        words = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        words = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        words = paginator.page(paginator.num_pages)

    return render_to_response('dictionary.html', RequestContext(request, {
        'title': _('%(language)s dictionary for %(project)s') %
        {'language': lang, 'project': prj},
        'project': prj,
        'language': lang,
        'words': words,
        'form': form,
        'uploadform': uploadform,
        'letterform': letterform,
        'letter': letter,
    }))


def show_engage(request, project, lang=None):
    # Get project object
    obj = get_object_or_404(Project, slug=project)
    obj.check_acl(request)

    # Handle language parameter
    language = None
    if lang is not None:
        try:
            django.utils.translation.activate(lang)
        except:
            # Ignore failure on activating language
            pass
        try:
            language = Language.objects.get(code=lang)
        except Language.DoesNotExist:
            pass

    context = {
        'object': obj,
        'project': obj.name,
        'languages': obj.get_language_count(),
        'total': obj.get_total(),
        'percent': obj.get_translated_percent(language),
        'url': obj.get_absolute_url(),
        'language': language,
    }

    # Render text
    if language is None:
        status_text = _(
            '<a href="%(url)s">Translation project for %(project)s</a> '
            'currently contains %(total)s strings for translation and is '
            '<a href="%(url)s">being translated into %(languages)s languages'
            '</a>. Overall, these translations are %(percent)s%% complete.'
        )
    else:
        # Translators: line of text in engagement widget, please use your
        # language name instead of English
        status_text = _(
            '<a href="%(url)s">Translation project for %(project)s</a> into '
            'English currently contains %(total)s strings for translation and '
            'is %(percent)s%% complete.'
        )
        if 'English' in status_text:
            status_text = status_text.replace('English', language.name)

    context['status_text'] = mark_safe(status_text % context)

    return render_to_response('engage.html', RequestContext(request, context))


def show_project(request, project):
    obj = get_object_or_404(Project, slug=project)
    obj.check_acl(request)

    dicts = Dictionary.objects.filter(
        project=obj
    ).values_list(
        'language', flat=True
    ).distinct()

    last_changes = Change.objects.filter(
        translation__subproject__project=obj
    ).order_by('-timestamp')[:10]

    return render_to_response('project.html', RequestContext(request, {
        'object': obj,
        'dicts': Language.objects.filter(id__in=dicts),
        'last_changes': last_changes,
        'last_changes_rss': reverse(
            'rss-project',
            kwargs={'project': obj.slug}
        ),
    }))


def show_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug=subproject, project__slug=project)
    obj.check_acl(request)

    last_changes = Change.objects.filter(
        translation__subproject=obj
    ).order_by('-timestamp')[:10]

    return render_to_response('subproject.html', RequestContext(request, {
        'object': obj,
        'last_changes': last_changes,
        'last_changes_rss': reverse(
            'rss-subproject',
            kwargs={'subproject': obj.slug, 'project': obj.project.slug}
        ),
    }))


@login_required
@permission_required('trans.automatic_translation')
def auto_translation(request, project, subproject, lang):
    obj = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    obj.check_acl(request)
    obj.commit_pending()
    autoform = AutoForm(obj, request.POST)
    change = None
    if not obj.subproject.locked and autoform.is_valid():
        if autoform.cleaned_data['inconsistent']:
            units = obj.unit_set.filter_type('inconsistent', obj)
        elif autoform.cleaned_data['overwrite']:
            units = obj.unit_set.all()
        else:
            units = obj.unit_set.filter(translated=False)

        sources = Unit.objects.filter(
            translation__language=obj.language,
            translated=True
        )
        if autoform.cleaned_data['subproject'] == '':
            sources = sources.filter(
                translation__subproject__project=obj.subproject.project
            ).exclude(
                translation=obj
            )
        else:
            subprj = SubProject.objects.get(
                project=obj.subproject.project,
                slug=autoform.cleaned_data['subproject']
            )
            sources = sources.filter(translation__subproject=subprj)

        for unit in units.iterator():
            update = sources.filter(checksum=unit.checksum)
            if update.exists():
                # Get first entry
                update = update[0]
                # No save if translation is same
                if unit.fuzzy == update.fuzzy and unit.target == update.target:
                    continue
                # Copy translation
                unit.fuzzy = update.fuzzy
                unit.target = update.target
                # Create signle change object for whole merge
                if change is None:
                    change = Change.objects.create(
                        unit=unit,
                        translation=unit.translation,
                        user=request.user
                    )
                # Save unit to backend
                unit.save_backend(request, False, False)

        messages.info(request, _('Automatic translation completed.'))
    else:
        messages.error(request, _('Failed to process form!'))

    return HttpResponseRedirect(obj.get_absolute_url())


def review_source(request, project, subproject):
    '''
    Listing of source strings to review.
    '''
    obj = get_object_or_404(SubProject, slug=subproject, project__slug=project)
    obj.check_acl(request)

    if not obj.translation_set.exists():
        raise Http404('No translation exists in this subproject.')

    # Grab first translation in subproject
    # (this assumes all have same source strings)
    source = obj.translation_set.all()[0]

    # Grab search type and page number
    rqtype = request.GET.get('type', 'all')
    limit = request.GET.get('limit', 50)
    page = request.GET.get('page', 1)

    # Fiter units
    sources = source.unit_set.filter_type(rqtype, source)

    paginator = Paginator(sources, limit)

    try:
        sources = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        sources = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        sources = paginator.page(paginator.num_pages)

    return render_to_response('source-review.html', RequestContext(request, {
        'object': obj,
        'source': source,
        'sources': sources,
        'title': _('Review source strings in %s') % obj.__unicode__(),
    }))


def show_source(request, project, subproject):
    '''
    Show source strings summary and checks.
    '''
    obj = get_object_or_404(SubProject, slug=subproject, project__slug=project)
    obj.check_acl(request)
    if not obj.translation_set.exists():
        raise Http404('No translation exists in this subproject.')

    # Grab first translation in subproject
    # (this assumes all have same source strings)
    source = obj.translation_set.all()[0]

    return render_to_response('source.html', RequestContext(request, {
        'object': obj,
        'source': source,
        'title': _('Source strings in %s') % obj.__unicode__(),
    }))


def show_translation(request, project, subproject, lang):
    obj = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    obj.check_acl(request)
    last_changes = Change.objects.filter(
        translation=obj
    ).order_by('-timestamp')[:10]

    # Check locks
    obj.is_locked(request)

    # How much is user allowed to configure upload?
    if request.user.has_perm('trans.author_translation'):
        form = ExtraUploadForm()
    elif request.user.has_perm('trans.overwrite_translation'):
        form = UploadForm()
    else:
        form = SimpleUploadForm()

    # Is user allowed to do automatic translation?
    if request.user.has_perm('trans.automatic_translation'):
        autoform = AutoForm(obj)
    else:
        autoform = None

    # Search form for everybody
    search_form = SearchForm()

    # Review form for logged in users
    if request.user.is_anonymous():
        review_form = None
    else:
        review_form = ReviewForm(
            initial={
                'date': datetime.date.today() - datetime.timedelta(days=31)
            }
        )

    return render_to_response('translation.html', RequestContext(request, {
        'object': obj,
        'form': form,
        'autoform': autoform,
        'search_form': search_form,
        'review_form': review_form,
        'last_changes': last_changes,
        'last_changes_rss': reverse(
            'rss-translation',
            kwargs={
                'lang': obj.language.code,
                'subproject': obj.subproject.slug,
                'project': obj.subproject.project.slug
            }
        ),
    }))


@login_required
@permission_required('trans.commit_translation')
def commit_project(request, project):
    obj = get_object_or_404(Project, slug=project)
    obj.check_acl(request)
    obj.commit_pending()

    messages.info(request, _('All pending translations were committed.'))

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.commit_translation')
def commit_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug=subproject, project__slug=project)
    obj.check_acl(request)
    obj.commit_pending()

    messages.info(request, _('All pending translations were committed.'))

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.commit_translation')
def commit_translation(request, project, subproject, lang):
    obj = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    obj.check_acl(request)
    obj.commit_pending()

    messages.info(request, _('All pending translations were committed.'))

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.update_translation')
def update_project(request, project):
    obj = get_object_or_404(Project, slug=project)
    obj.check_acl(request)

    if obj.do_update(request):
        messages.info(request, _('All repositories were updated.'))

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.update_translation')
def update_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug=subproject, project__slug=project)
    obj.check_acl(request)

    if obj.do_update(request):
        messages.info(request, _('All repositories were updated.'))

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.update_translation')
def update_translation(request, project, subproject, lang):
    obj = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    obj.check_acl(request)

    if obj.do_update(request):
        messages.info(request, _('All repositories were updated.'))

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.push_translation')
def push_project(request, project):
    obj = get_object_or_404(Project, slug=project)
    obj.check_acl(request)

    if obj.do_push(request):
        messages.info(request, _('All repositories were pushed.'))

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.push_translation')
def push_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug=subproject, project__slug=project)
    obj.check_acl(request)

    if obj.do_push(request):
        messages.info(request, _('All repositories were pushed.'))

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.push_translation')
def push_translation(request, project, subproject, lang):
    obj = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    obj.check_acl(request)

    if obj.do_push(request):
        messages.info(request, _('All repositories were pushed.'))

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.reset_translation')
def reset_project(request, project):
    obj = get_object_or_404(Project, slug=project)
    obj.check_acl(request)

    if obj.do_reset(request):
        messages.info(request, _('All repositories have been reset.'))

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.reset_translation')
def reset_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug=subproject, project__slug=project)
    obj.check_acl(request)

    if obj.do_reset(request):
        messages.info(request, _('All repositories have been reset.'))

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.reset_translation')
def reset_translation(request, project, subproject, lang):
    obj = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    obj.check_acl(request)

    if obj.do_reset(request):
        messages.info(request, _('All repositories have been reset.'))

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.lock_translation')
def lock_translation(request, project, subproject, lang):
    obj = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    obj.check_acl(request)

    if not obj.is_user_locked(request):
        obj.create_lock(request.user, True)
        messages.info(request, _('Translation is now locked for you.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
def update_lock(request, project, subproject, lang):
    obj = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    obj.check_acl(request)

    if not obj.is_user_locked(request):
        obj.update_lock_time()

    return HttpResponse('ok')


@login_required
@permission_required('trans.lock_translation')
def unlock_translation(request, project, subproject, lang):
    obj = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    obj.check_acl(request)

    if not obj.is_user_locked(request):
        obj.create_lock(None)
        messages.info(
            request,
            _('Translation is now open for translation updates.')
        )

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.lock_subproject')
def lock_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug=subproject, project__slug=project)
    obj.check_acl(request)

    obj.commit_pending()

    obj.locked = True
    obj.save()

    messages.info(
        request,
        _('Subproject is now locked for translation updates!')
    )

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.lock_subproject')
def unlock_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug=subproject, project__slug=project)
    obj.check_acl(request)

    obj.locked = False
    obj.save()

    messages.info(
        request,
        _('Subproject is now open for translation updates.')
    )

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.lock_subproject')
def lock_project(request, project):
    obj = get_object_or_404(Project, slug=project)
    obj.check_acl(request)

    obj.commit_pending()

    for subproject in obj.subproject_set.all():
        subproject.locked = True
        subproject.save()

    messages.info(
        request,
        _('All subprojects are now locked for translation updates!')
    )

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.lock_subproject')
def unlock_project(request, project):
    obj = get_object_or_404(Project, slug=project)
    obj.check_acl(request)

    for subproject in obj.subproject_set.all():
        subproject.locked = False
        subproject.save()

    messages.info(request, _('Project is now open for translation updates.'))

    return HttpResponseRedirect(obj.get_absolute_url())


def download_translation(request, project, subproject, lang):
    obj = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    obj.check_acl(request)

    # Retrieve ttkit store to get extension and mime type
    store = obj.get_store()
    srcfilename = obj.get_filename()

    if store.Mimetypes is None:
        # Properties files do not expose mimetype
        mime = 'text/plain'
    else:
        mime = store.Mimetypes[0]

    if store.Extensions is None:
        # Typo in translate-toolkit 1.9, see
        # https://github.com/translate/translate/pull/10
        if hasattr(store, 'Exensions'):
            ext = store.Exensions[0]
        else:
            ext = 'txt'
    else:
        ext = store.Extensions[0]

    # Construct file name (do not use real filename as it is usually not
    # that useful)
    filename = '%s-%s-%s.%s' % (project, subproject, lang, ext)

    # Django wrapper for sending file
    wrapper = FixedFileWrapper(file(srcfilename))

    response = HttpResponse(wrapper, mimetype=mime)

    # Fill in response headers
    response['Content-Disposition'] = 'attachment; filename=%s' % filename
    response['Content-Length'] = os.path.getsize(srcfilename)

    return response


def bool2str(val):
    if val:
        return 'on'
    return ''


def parse_search_url(request):
    # Check where we are
    rqtype = request.REQUEST.get('type', 'all')
    direction = request.REQUEST.get('dir', 'forward')
    pos = request.REQUEST.get('pos', '-1')
    try:
        pos = int(pos)
    except:
        pos = -1

    # Pre-process search form
    if request.method == 'POST':
        search_form = SearchForm(request.POST)
    else:
        search_form = SearchForm(request.GET)
    if search_form.is_valid():
        search_query = search_form.cleaned_data['q']
        search_type = search_form.cleaned_data['search']
        if search_type == '':
            search_type = 'ftx'
        search_source = search_form.cleaned_data['src']
        search_target = search_form.cleaned_data['tgt']
        search_context = search_form.cleaned_data['ctx']
        # Sane defaults
        if not search_context and not search_source and not search_target:
            search_source = True
            search_target = True

        search_url = '&q=%s&src=%s&tgt=%s&ctx=%s&search=%s' % (
            search_query,
            bool2str(search_source),
            bool2str(search_target),
            bool2str(search_context),
            search_type,
        )
    else:
        search_query = ''
        search_type = 'ftx'
        search_source = True
        search_target = True
        search_context = False
        search_url = ''

    if 'date' in request.REQUEST:
        search_url += '&date=%s' % request.REQUEST['date']

    return (
        rqtype,
        direction,
        pos,
        search_query,
        search_type,
        search_source,
        search_target,
        search_context,
        search_url
    )


def get_filter_name(rqtype, search_query):
    '''
    Returns name of current filter.
    '''
    if search_query != '':
        return _('Search for "%s"') % search_query
    if rqtype == 'all':
        return None
    elif rqtype == 'fuzzy':
        return _('Fuzzy strings')
    elif rqtype == 'untranslated':
        return _('Untranslated strings')
    elif rqtype == 'suggestions':
        return _('Strings with suggestions')
    elif rqtype == 'allchecks':
        return _('Strings with any failing checks')
    elif rqtype in CHECKS:
        return CHECKS[rqtype].name
    else:
        return None


def translate(request, project, subproject, lang):
    obj = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    obj.check_acl(request)

    # Check locks
    project_locked, user_locked, own_lock = obj.is_locked(request, True)
    locked = project_locked or user_locked

    if request.user.is_authenticated():
        profile = request.user.get_profile()
        antispam = None
    else:
        profile = None
        antispam = AntispamForm()

    secondary = None
    unit = None

    rqtype, direction, pos, search_query, search_type, search_source, search_target, search_context, search_url = parse_search_url(request)

    # Any form submitted?
    if request.method == 'POST':

        # Antispam protection
        if not request.user.is_authenticated():
            antispam = AntispamForm(request.POST)
            if not antispam.is_valid():
                # Silently redirect to next entry
                return HttpResponseRedirect('%s?type=%s&pos=%d%s' % (
                    obj.get_translate_url(),
                    rqtype,
                    pos,
                    search_url
                ))

        form = TranslationForm(request.POST)
        if form.is_valid() and not project_locked:
            # Check whether translation is not outdated
            obj.check_sync()
            try:
                try:
                    unit = Unit.objects.get(
                        checksum=form.cleaned_data['checksum'],
                        translation=obj
                    )
                except Unit.MultipleObjectsReturned:
                    # Possible temporary inconsistency caused by ongoing update
                    # of repo, let's pretend everyting is okay
                    unit = Unit.objects.filter(
                        checksum=form.cleaned_data['checksum'],
                        translation=obj
                    )[0]
                if 'suggest' in request.POST:
                    # Handle suggesion saving
                    user = request.user
                    if isinstance(user, AnonymousUser):
                        user = None
                    if form.cleaned_data['target'] == len(form.cleaned_data['target']) * ['']:
                        messages.error(request, _('Your suggestion is empty!'))
                        # Stay on same entry
                        return HttpResponseRedirect(
                            '%s?type=%s&pos=%d&dir=stay%s' % (
                                obj.get_translate_url(),
                                rqtype,
                                pos,
                                search_url
                            )
                        )
                    # Create the suggestion
                    sug = Suggestion.objects.create(
                        target=join_plural(form.cleaned_data['target']),
                        checksum=unit.checksum,
                        language=unit.translation.language,
                        project=unit.translation.subproject.project,
                        user=user)
                    # Record in change
                    Change.objects.create(
                        unit=unit,
                        action=Change.ACTION_SUGGESTION,
                        translation=unit.translation,
                        user=user
                    )
                    # Invalidate counts cache
                    unit.translation.invalidate_cache('suggestions')
                    # Invite user to become translator if there is nobody else
                    recent_changes = Change.objects.content().filter(
                        translation=unit.translation,
                    ).exclude(
                        user=None
                    ).order_by('-timestamp')
                    if recent_changes.count() == 0 or True:
                        messages.info(
                            request,
                            _('There is currently no active translator for this translation, please consider becoming a translator as your suggestion might otherwise remain unreviewed.')
                        )
                    # Notify subscribed users
                    subscriptions = Profile.objects.subscribed_new_suggestion(
                        obj.subproject.project,
                        obj.language,
                        request.user
                    )
                    for subscription in subscriptions:
                        subscription.notify_new_suggestion(obj, sug, unit)
                    # Update suggestion stats
                    if profile is not None:
                        profile.suggested += 1
                        profile.save()
                elif not request.user.is_authenticated():
                    # We accept translations only from authenticated
                    messages.error(
                        request,
                        _('You need to log in to be able to save translations!')
                    )
                elif not request.user.has_perm('trans.save_translation'):
                    # Need privilege to save
                    messages.error(
                        request,
                        _('You don\'t have privileges to save translations!')
                    )
                elif not user_locked:
                    # Remember old checks
                    oldchecks = set(
                        unit.active_checks().values_list('check', flat=True)
                    )
                    # Update unit and save it
                    unit.target = join_plural(form.cleaned_data['target'])
                    unit.fuzzy = form.cleaned_data['fuzzy']
                    saved = unit.save_backend(request)

                    if saved:
                        # Get new set of checks
                        newchecks = set(
                            unit.active_checks().values_list('check', flat=True)
                        )
                        # Did we introduce any new failures?
                        if newchecks > oldchecks:
                            # Show message to user
                            messages.error(
                                request,
                                _('Some checks have failed on your translation!')
                            )
                            # Stay on same entry
                            return HttpResponseRedirect(
                                '%s?type=%s&pos=%d&dir=stay%s' % (
                                    obj.get_translate_url(),
                                    rqtype,
                                    pos,
                                    search_url
                                )
                            )

                # Redirect to next entry
                return HttpResponseRedirect('%s?type=%s&pos=%d%s' % (
                    obj.get_translate_url(),
                    rqtype,
                    pos,
                    search_url
                ))
            except Unit.DoesNotExist:
                logger.error(
                    'message %s disappeared!',
                    form.cleaned_data['checksum']
                )
                messages.error(
                    request,
                    _('Message you wanted to translate is no longer available!')
                )

    # Handle translation merging
    if 'merge' in request.GET and not locked:
        if not request.user.has_perm('trans.save_translation'):
            # Need privilege to save
            messages.error(
                request,
                _('You don\'t have privileges to save translations!')
            )
        else:
            try:
                mergeform = MergeForm(request.GET)
                if mergeform.is_valid():
                    try:
                        unit = Unit.objects.get(
                            checksum=mergeform.cleaned_data['checksum'],
                            translation=obj
                        )
                    except Unit.MultipleObjectsReturned:
                        # Possible temporary inconsistency caused by ongoing
                        # update of repo, let's pretend everyting is okay
                        unit = Unit.objects.filter(
                            checksum=mergeform.cleaned_data['checksum'],
                            translation=obj
                        )[0]

                    merged = Unit.objects.get(
                        pk=mergeform.cleaned_data['merge']
                    )

                    if unit.checksum != merged.checksum:
                        messages.error(
                            request,
                            _('Can not merge different messages!')
                        )
                    else:
                        # Store unit
                        unit.target = merged.target
                        unit.fuzzy = merged.fuzzy
                        saved = unit.save_backend(request)
                        # Update stats if there was change
                        if saved:
                            profile.translated += 1
                            profile.save()
                        # Redirect to next entry
                        return HttpResponseRedirect('%s?type=%s&pos=%d%s' % (
                            obj.get_translate_url(),
                            rqtype,
                            pos,
                            search_url
                        ))
            except Unit.DoesNotExist:
                logger.error(
                    'message %s disappeared!',
                    form.cleaned_data['checksum']
                )
                messages.error(
                    request,
                    _('Message you wanted to translate is no longer available!')
                )

    # Handle accepting/deleting suggestions
    if not locked and ('accept' in request.GET or 'delete' in request.GET):
        # Check for authenticated users
        if not request.user.is_authenticated():
            messages.error(request, _('You need to log in to be able to manage suggestions!'))
            return HttpResponseRedirect('%s?type=%s&pos=%d&dir=stay%s' % (
                obj.get_translate_url(),
                rqtype,
                pos,
                search_url
            ))

        # Parse suggestion ID
        if 'accept' in request.GET:
            if not request.user.has_perm('trans.accept_suggestion'):
                messages.error(request, _('You do not have privilege to accept suggestions!'))
                return HttpResponseRedirect('%s?type=%s&pos=%d&dir=stay%s' % (
                    obj.get_translate_url(),
                    rqtype,
                    pos,
                    search_url
                ))
            sugid = request.GET['accept']
        else:
            if not request.user.has_perm('trans.delete_suggestion'):
                messages.error(request, _('You do not have privilege to delete suggestions!'))
                return HttpResponseRedirect('%s?type=%s&pos=%d&dir=stay%s' % (
                    obj.get_translate_url(),
                    rqtype,
                    pos,
                    search_url
                ))
            sugid = request.GET['delete']
        try:
            sugid = int(sugid)
            suggestion = Suggestion.objects.get(pk=sugid)
        except:
            suggestion = None

        if suggestion is not None:
            if 'accept' in request.GET:
                # Accept suggesiont
                suggestion.accept(request)
            # Invalidate caches
            for unit in Unit.objects.filter(checksum=suggestion.checksum):
                unit.translation.invalidate_cache('suggestions')
            # Delete suggestion in both cases (accepted ones are no longer
            # needed)
            suggestion.delete()
        else:
            messages.error(request, _('Invalid suggestion!'))

        # Redirect to same entry for possible editing
        return HttpResponseRedirect('%s?type=%s&pos=%d&dir=stay%s' % (
            obj.get_translate_url(),
            rqtype,
            pos,
            search_url
        ))

    reviewform = ReviewForm(request.GET)

    if reviewform.is_valid():
        allunits = obj.unit_set.review(
            reviewform.cleaned_data['date'],
            request.user
        )
        # Review
        if direction == 'stay':
            units = allunits.filter(position=pos)
        elif direction == 'back':
            units = allunits.filter(position__lt=pos).order_by('-position')
        else:
            units = allunits.filter(position__gt=pos)
    elif search_query != '':
        # Apply search conditions
        if search_type == 'exact':
            query = Q()
            if search_source:
                query |= Q(source=search_query)
            if search_target:
                query |= Q(target=search_query)
            if search_context:
                query |= Q(context=search_query)
            allunits = obj.unit_set.filter(query)
        elif search_type == 'substring':
            query = Q()
            if search_source:
                query |= Q(source__icontains=search_query)
            if search_target:
                query |= Q(target__icontains=search_query)
            if search_context:
                query |= Q(context__icontains=search_query)
            allunits = obj.unit_set.filter(query)
        else:
            allunits = obj.unit_set.search(
                search_query,
                search_source,
                search_context,
                search_target
            )
        if direction == 'stay':
            units = obj.unit_set.filter(position=pos)
        elif direction == 'back':
            units = allunits.filter(position__lt=pos).order_by('-position')
        else:
            units = allunits.filter(position__gt=pos)
    elif 'checksum' in request.GET:
        allunits = obj.unit_set.filter(checksum=request.GET['checksum'])
        units = allunits
    else:
        allunits = obj.unit_set.filter_type(rqtype, obj)
        # What unit set is about to show
        if direction == 'stay':
            units = obj.unit_set.filter(position=pos)
        elif direction == 'back':
            units = allunits.filter(position__lt=pos).order_by('-position')
        else:
            units = allunits.filter(position__gt=pos)


    # If we failed to get unit above or on no POST
    if unit is None:
        # Grab actual unit
        try:
            unit = units[0]
        except IndexError:
            messages.info(request, _('You have reached end of translating.'))
            return HttpResponseRedirect(obj.get_absolute_url())

        # Show secondary languages for logged in users
        if profile:
            secondary_langs = profile.secondary_languages.exclude(
                id=unit.translation.language.id
            )
            project = unit.translation.subproject.project
            secondary = Unit.objects.filter(
                checksum=unit.checksum,
                translated=True,
                translation__subproject__project=project,
                translation__language__in=secondary_langs,
            )
            # distinct('target') works with Django 1.4 so let's emulate that
            # based on presumption we won't get too many results
            targets = {}
            res = []
            for lang in secondary:
                if lang.target in targets:
                    continue
                targets[lang.target] = 1
                res.append(lang)
            secondary = res

        # Prepare form
        form = TranslationForm(initial={
            'checksum': unit.checksum,
            'target': (unit.translation.language, unit.get_target_plurals()),
            'fuzzy': unit.fuzzy,
        })

    total = obj.unit_set.all().count()
    filter_count = allunits.count()

    return render_to_response(
        'translate.html',
        RequestContext(request, {
            'object': obj,
            'unit': unit,
            'last_changes': unit.change_set.all()[:10],
            'total': total,
            'type': rqtype,
            'filter_name': get_filter_name(rqtype, search_query),
            'filter_count': filter_count,
            'filter_pos': filter_count + 1 - units.count(),
            'form': form,
            'antispam': antispam,
            'comment_form': CommentForm(),
            'target_language': obj.language.code.replace('_', '-').lower(),
            'update_lock': own_lock,
            'secondary': secondary,
            'search_query': search_query,
            'search_url': search_url,
            'search_source': bool2str(search_source),
            'search_type': search_type,
            'search_target': bool2str(search_target),
            'search_context': bool2str(search_context),
            'locked': locked,
            'user_locked': user_locked,
            'project_locked': project_locked,
        },
    ))


@login_required
def comment(request, pk):
    '''
    Adds new comment.
    '''
    obj = get_object_or_404(Unit, pk=pk)
    obj.check_acl(request)
    if request.POST.get('type', '') == 'source':
        lang = None
    else:
        lang = obj.translation.language

    form = CommentForm(request.POST)

    if form.is_valid():
        new_comment = Comment.objects.create(
            user=request.user,
            checksum=obj.checksum,
            project=obj.translation.subproject.project,
            comment=form.cleaned_data['comment'],
            language=lang
        )
        Change.objects.create(
            unit=obj,
            action=Change.ACTION_COMMENT,
            translation=obj.translation,
            user=request.user
        )

        # Invalidate counts cache
        if lang is None:
            obj.translation.invalidate_cache('sourcecomments')
        else:
            obj.translation.invalidate_cache('targetcomments')
        messages.info(request, _('Posted new comment'))
        # Notify subscribed users
        subscriptions = Profile.objects.subscribed_new_comment(
            obj.translation.subproject.project,
            lang,
            request.user
        )
        for subscription in subscriptions:
            subscription.notify_new_comment(obj, new_comment)
        # Notify upstream
        if lang is None and obj.translation.subproject.report_source_bugs != '':
            send_notification_email(
                'en',
                obj.translation.subproject.report_source_bugs,
                'new_comment',
                obj.translation,
                {
                    'unit': obj,
                    'comment': new_comment,
                    'subproject': obj.translation.subproject,
                },
                from_email=request.user.email,
            )
    else:
        messages.error(request, _('Failed to add comment!'))

    return HttpResponseRedirect(obj.get_absolute_url())


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
        project = unit.translation.subproject.project,
        language = unit.translation.language
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


@login_required
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


@login_required
@permission_required('trans.upload_translation')
def upload_translation(request, project, subproject, lang):
    '''
    Handling of translation uploads.
    '''
    obj = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    obj.check_acl(request)

    if not obj.is_locked(request) and request.method == 'POST':
        if request.user.has_perm('trans.author_translation'):
            form = ExtraUploadForm(request.POST, request.FILES)
        elif request.user.has_perm('trans.overwrite_translation'):
            form = UploadForm(request.POST, request.FILES)
        else:
            form = SimpleUploadForm(request.POST, request.FILES)
        if form.is_valid():
            if request.user.has_perm('trans.author_translation') and form.cleaned_data['author_name'] != '' and form.cleaned_data['author_email'] != '':
                author = '%s <%s>' % (form.cleaned_data['author_name'], form.cleaned_data['author_email'])
            else:
                author = None
            if request.user.has_perm('trans.overwrite_translation'):
                overwrite = form.cleaned_data['overwrite']
            else:
                overwrite = False
            try:
                ret = obj.merge_upload(request, request.FILES['file'], overwrite, author, merge_header=form.cleaned_data['merge_header'])
                if ret:
                    messages.info(request, _('File content successfully merged into translation.'))
                else:
                    messages.info(request, _('There were no new strings in uploaded file.'))
            except Exception as e:
                messages.error(request, _('File content merge failed: %s' % unicode(e)))

    return HttpResponseRedirect(obj.get_absolute_url())


def not_found(request):
    '''
    Error handler showing list of available projects.
    '''
    template = loader.get_template('404.html')
    return HttpResponseNotFound(
        template.render(RequestContext(request, {
            'request_path': request.path,
            'title': _('Page Not Found'),
            'projects': Project.objects.all_acl(request.user),
        }
    )))


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

    return render_to_response('js/config.js', RequestContext(request, {
            'apertium_langs': apertium_langs,
            'microsoft_langs': microsoft_langs,
        }),
        mimetype = 'application/javascript')


def about(request):
    context = {}
    versions = get_versions()
    totals =  Profile.objects.aggregate(Sum('translated'), Sum('suggested'))
    total_strings = 0
    for project in SubProject.objects.iterator():
        try:
            total_strings += project.translation_set.all()[0].total
        except Translation.DoesNotExist:
            pass
    context['title'] = _('About Weblate')
    context['total_translations'] = totals['translated__sum']
    context['total_suggestions'] = totals['suggested__sum']
    context['total_users'] = Profile.objects.count()
    context['total_strings'] = total_strings
    context['total_languages'] = Language.objects.filter(
        translation__total__gt=0
    ).distinct().count()
    context['total_checks'] = Check.objects.count()
    context['ignored_checks'] = Check.objects.filter(ignore=True).count()
    context['versions'] = versions

    return render_to_response('about.html', RequestContext(request, context))


@user_passes_test(lambda u: u.has_perm('trans.commit_translation') or u.has_perm('trans.update_translation'))
def git_status_project(request, project):
    obj = get_object_or_404(Project, slug=project)
    obj.check_acl(request)

    return render_to_response('js/git-status.html', RequestContext(request, {
        'object': obj,
    }))


@user_passes_test(lambda u: u.has_perm('trans.commit_translation') or u.has_perm('trans.update_translation'))
def git_status_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug=subproject, project__slug=project)
    obj.check_acl(request)

    return render_to_response('js/git-status.html', RequestContext(request, {
        'object': obj,
    }))


@user_passes_test(lambda u: u.has_perm('trans.commit_translation') or u.has_perm('trans.update_translation'))
def git_status_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code=lang, subproject__slug=subproject, subproject__project__slug=project, enabled=True)
    obj.check_acl(request)

    return render_to_response('js/git-status.html', RequestContext(request, {
        'object': obj,
    }))


def data_root(request):
    site = Site.objects.get_current()
    return render_to_response('data-root.html', RequestContext(request, {
        'site_domain': site.domain,
        'api_docs': weblate.get_doc_url('api', 'exports'),
        'rss_docs': weblate.get_doc_url('api', 'rss'),
        'projects': Project.objects.all_acl(request.user),
    }))


def data_project(request, project):
    obj = get_object_or_404(Project, slug=project)
    obj.check_acl(request)
    site = Site.objects.get_current()
    return render_to_response('data.html', RequestContext(request, {
        'object': obj,
        'site_domain': site.domain,
        'api_docs': weblate.get_doc_url('api', 'exports'),
        'rss_docs': weblate.get_doc_url('api', 'rss'),
    }))
