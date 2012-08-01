from django.shortcuts import render_to_response, get_object_or_404
from django.views.decorators.cache import cache_page
from django.conf import settings
from django.core.servers.basehttp import FileWrapper
from django.utils.translation import ugettext as _
from django.template import RequestContext, loader
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseNotFound, Http404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q, Count, Sum
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse

from weblate.trans.models import Project, SubProject, Translation, Unit, Suggestion, Check, Dictionary, Change, get_versions
from weblate.lang.models import Language
from weblate.trans.checks import CHECKS
from weblate.trans.forms import TranslationForm, UploadForm, SimpleUploadForm, ExtraUploadForm, SearchForm, MergeForm, AutoForm, WordForm, DictUploadForm, ReviewForm, LetterForm, AntispamForm
from weblate.trans.util import join_plural
from weblate.accounts.models import Profile

from whoosh.analysis import StandardAnalyzer, StemmingAnalyzer
import datetime
import logging
import os.path
import json
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
    projects = Project.objects.all()

    # Warn about not filled in username (usually caused by migration of
    # users from older system
    if not request.user.is_anonymous() and request.user.get_full_name() == '':
        messages.warning(request, _('Please set your full name in your profile.'))

    # Load user translations if user is authenticated
    usertranslations = None
    if request.user.is_authenticated():
        profile = request.user.get_profile()

        usertranslations = Translation.objects.filter(language__in = profile.languages.all()).order_by('subproject__project__name', 'subproject__name')

    # Some stats
    top_translations = Profile.objects.order_by('-translated')[:10]
    top_suggestions = Profile.objects.order_by('-suggested')[:10]
    last_changes = Change.objects.order_by('-timestamp')[:10]

    return render_to_response('index.html', RequestContext(request, {
        'projects': projects,
        'top_translations': top_translations,
        'top_suggestions': top_suggestions,
        'last_changes': last_changes,
        'usertranslations': usertranslations,
    }))

def show_checks(request):
    '''
    List of failing checks.
    '''
    return render_to_response('checks.html', RequestContext(request, {
        'checks': Check.objects.filter(ignore = False).values('check').annotate(count = Count('id')),
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

    return render_to_response('check.html', RequestContext(request, {
        'checks': Check.objects.filter(check = name, ignore = False).values('project__slug').annotate(count = Count('id')),
        'title': check.name,
        'check': check,
    }))

def show_check_project(request, name, project):
    '''
    Show checks failing in a project.
    '''
    prj = get_object_or_404(Project, slug = project)
    try:
        check = CHECKS[name]
    except KeyError:
        raise Http404('No check matches the given query.')
    langs = Check.objects.filter(check = name, project = prj, ignore = False).values_list('language', flat = True).distinct()
    units = Unit.objects.none()
    for lang in langs:
        checks = Check.objects.filter(check = name, project = prj, language = lang, ignore = False).values_list('checksum', flat = True)
        res = Unit.objects.filter(checksum__in = checks, translation__language = lang, translation__subproject__project = prj, translated = True).values('translation__subproject__slug', 'translation__subproject__project__slug').annotate(count = Count('id'))
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
    subprj = get_object_or_404(SubProject, slug = subproject, project__slug = project)
    try:
        check = CHECKS[name]
    except KeyError:
        raise Http404('No check matches the given query.')
    langs = Check.objects.filter(check = name, project = subprj.project, ignore = False).values_list('language', flat = True).distinct()
    units = Unit.objects.none()
    for lang in langs:
        checks = Check.objects.filter(check = name, project = subprj.project, language = lang, ignore = False).values_list('checksum', flat = True)
        res = Unit.objects.filter(translation__subproject = subprj, checksum__in = checks, translation__language = lang, translated = True).values('translation__language__code').annotate(count = Count('id'))
        units |= res
    return render_to_response('check_subproject.html', RequestContext(request, {
        'checks': units,
        'title': '%s/%s' % (subprj.__unicode__(), check.name),
        'check': check,
        'subproject': subprj,
    }))

def show_languages(request):
    return render_to_response('languages.html', RequestContext(request, {
        'languages': Language.objects.have_translation(),
        'title': _('Languages'),
    }))

def show_language(request, lang):
    obj = get_object_or_404(Language, code = lang)

    return render_to_response('language.html', RequestContext(request, {
        'object': obj,
    }))

def show_dictionaries(request, project):
    obj = get_object_or_404(Project, slug = project)
    dicts = Translation.objects.filter(subproject__project = obj).values_list('language', flat = True).distinct()

    return render_to_response('dictionaries.html', RequestContext(request, {
        'title': _('Dictionaries'),
        'dicts': Language.objects.filter(id__in = dicts),
        'project': obj,
    }))

@login_required
@permission_required('trans.change_dictionary')
def edit_dictionary(request, project, lang):
    prj = get_object_or_404(Project, slug = project)
    lang = get_object_or_404(Language, code = lang)
    word = get_object_or_404(Dictionary, project = prj, language = lang, id = request.GET.get('id'))

    if request.method == 'POST':
        form = WordForm(request.POST)
        if form.is_valid():
            word.source = form.cleaned_data['source']
            word.target = form.cleaned_data['target']
            word.save()
            return HttpResponseRedirect(reverse('weblate.trans.views.show_dictionary', kwargs = {'project': prj.slug, 'lang': lang.code}))
    else:
        form = WordForm(initial = {'source': word.source, 'target': word.target })

    return render_to_response('edit_dictionary.html', RequestContext(request, {
        'title': _('%(language)s dictionary for %(project)s') % {'language': lang, 'project': prj},
        'project': prj,
        'language': lang,
        'form': form,
    }))

@login_required
@permission_required('trans.delete_dictionary')
def delete_dictionary(request, project, lang):
    prj = get_object_or_404(Project, slug = project)
    lang = get_object_or_404(Language, code = lang)
    word = get_object_or_404(Dictionary, project = prj, language = lang, id = request.POST.get('id'))

    word.delete()

    return HttpResponseRedirect(reverse('weblate.trans.views.show_dictionary', kwargs = {'project': prj.slug, 'lang': lang.code}))

@login_required
@permission_required('trans.upload_dictionary')
def upload_dictionary(request, project, lang):
    prj = get_object_or_404(Project, slug = project)
    lang = get_object_or_404(Language, code = lang)

    if request.method == 'POST':
        form = DictUploadForm(request.POST, request.FILES)
        if form.is_valid():
            count = Dictionary.objects.upload(prj, lang, request.FILES['file'], form.cleaned_data['overwrite'])
            if count == 0:
                messages.warning(request, _('No words to import found in file.'))
            else:
                messages.info(request, _('Imported %d words from file.') % count)
        else:
            messages.error(request, _('Failed to process form!'))
    else:
        messages.error(request, _('Failed to process form!'))
    return HttpResponseRedirect(reverse('weblate.trans.views.show_dictionary', kwargs = {'project': prj.slug, 'lang': lang.code}))

def show_dictionary(request, project, lang):
    prj = get_object_or_404(Project, slug = project)
    lang = get_object_or_404(Language, code = lang)

    if request.method == 'POST' and request.user.has_perm('trans.add_dictionary'):
        form = WordForm(request.POST)
        if form.is_valid():
            Dictionary.objects.create(
                project = prj,
                language = lang,
                source = form.cleaned_data['source'],
                target = form.cleaned_data['target']
            )
        return HttpResponseRedirect(request.get_full_path())
    else:
        form = WordForm()

    uploadform = DictUploadForm()

    words = Dictionary.objects.filter(project = prj, language = lang).order_by('source')

    limit = request.GET.get('limit', 25)
    page = request.GET.get('page', 1)

    letterform = LetterForm(request.GET)

    if letterform.is_valid() and letterform.cleaned_data['letter'] != '':
        words = words.filter(source__istartswith = letterform.cleaned_data['letter'])

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
        'title': _('%(language)s dictionary for %(project)s') % {'language': lang, 'project': prj},
        'project': prj,
        'language': lang,
        'words': words,
        'form': form,
        'uploadform': uploadform,
        'letterform': letterform,
        'letter': letterform.cleaned_data['letter'],
    }))

def show_engage(request, project):
    obj = get_object_or_404(Project, slug = project)

    return render_to_response('engage.html', RequestContext(request, {
        'object': obj,
    }))

def show_project(request, project):
    obj = get_object_or_404(Project, slug = project)
    dicts = Dictionary.objects.filter(project = obj).values_list('language', flat = True).distinct()
    last_changes = Change.objects.filter(unit__translation__subproject__project = obj).order_by('-timestamp')[:10]

    return render_to_response('project.html', RequestContext(request, {
        'object': obj,
        'dicts': Language.objects.filter(id__in = dicts),
        'last_changes': last_changes,
    }))

def show_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug = subproject, project__slug = project)
    last_changes = Change.objects.filter(unit__translation__subproject = obj).order_by('-timestamp')[:10]

    if obj.locked:
        messages.error(request, _('This translation is currently locked for updates!'))

    return render_to_response('subproject.html', RequestContext(request, {
        'object': obj,
        'last_changes': last_changes,
    }))

@login_required
@permission_required('trans.automatic_translation')
def auto_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project, enabled = True)
    obj.commit_pending()
    autoform = AutoForm(obj, request.POST)
    change = None
    if not obj.subproject.locked and autoform.is_valid():
        if autoform.cleaned_data['inconsistent']:
            units = obj.unit_set.filter_type('inconsistent', obj)
        elif autoform.cleaned_data['overwrite']:
            units = obj.unit_set.all()
        else:
            units = obj.unit_set.filter(translated = False)

        sources = Unit.objects.filter(translation__language = obj.language, translated = True)
        if autoform.cleaned_data['subproject'] == '':
            sources = sources.filter(translation__subproject__project = obj.subproject.project).exclude(translation = obj)
        else:
            subprj = SubProject.objects.get(project = obj.subproject.project, slug = autoform.cleaned_data['subproject'])
            sources = sources.filter(translation__subproject = subprj)

        for unit in units.iterator():
            update = sources.filter(checksum = unit.checksum)
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
                    change = Change.objects.create(unit = unit, user = request.user)
                # Save unit to backend
                unit.save_backend(request, False, False)

        messages.info(request, _('Automatic translation completed.'))
    else:
        messages.error(request, _('Failed to process form!'))

    return HttpResponseRedirect(obj.get_absolute_url())

def show_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project, enabled = True)
    last_changes = Change.objects.filter(unit__translation = obj).order_by('-timestamp')[:10]

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
        review_form = ReviewForm(initial = {'date': datetime.date.today() - datetime.timedelta(days = 31)})

    return render_to_response('translation.html', RequestContext(request, {
        'object': obj,
        'form': form,
        'autoform': autoform,
        'search_form': search_form,
        'review_form': review_form,
        'last_changes': last_changes,
    }))

@login_required
@permission_required('trans.commit_translation')
def commit_project(request, project):
    obj = get_object_or_404(Project, slug = project)
    obj.commit_pending()

    messages.info(request, _('All pending translations were committed.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.commit_translation')
def commit_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug = subproject, project__slug = project)
    obj.commit_pending()

    messages.info(request, _('All pending translations were committed.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.commit_translation')
def commit_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project, enabled = True)
    obj.commit_pending()

    messages.info(request, _('All pending translations were committed.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.update_translation')
def update_project(request, project):
    obj = get_object_or_404(Project, slug = project)

    if obj.do_update(request):
        messages.info(request, _('All repositories were updated.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.update_translation')
def update_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug = subproject, project__slug = project)

    if obj.do_update(request):
        messages.info(request, _('All repositories were updated.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.update_translation')
def update_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project, enabled = True)

    if obj.do_update(request):
        messages.info(request, _('All repositories were updated.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.push_translation')
def push_project(request, project):
    obj = get_object_or_404(Project, slug = project)

    if obj.do_push(request):
        messages.info(request, _('All repositories were pushed.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.push_translation')
def push_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug = subproject, project__slug = project)

    if obj.do_push(request):
        messages.info(request, _('All repositories were pushed.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.push_translation')
def push_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project, enabled = True)

    if obj.do_push(request):
        messages.info(request, _('All repositories were pushed.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.reset_translation')
def reset_project(request, project):
    obj = get_object_or_404(Project, slug = project)

    if obj.do_reset(request):
        messages.info(request, _('All repositories have been reset.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.reset_translation')
def reset_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug = subproject, project__slug = project)

    if obj.do_reset(request):
        messages.info(request, _('All repositories have been reset.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.reset_translation')
def reset_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project, enabled = True)

    if obj.do_reset(request):
        messages.info(request, _('All repositories have been reset.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.lock_translation')
def lock_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project, enabled = True)

    if not obj.is_user_locked(request):
        obj.create_lock(request.user)

    messages.info(request, _('Translation is now locked for you.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.lock_translation')
def unlock_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project, enabled = True)

    if not obj.is_user_locked(request):
        obj.create_lock(None)

    messages.info(request, _('Translation is now open for translation updates.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.lock_subproject')
def lock_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug = subproject, project__slug = project)

    obj.commit_pending()

    obj.locked = True
    obj.save()

    messages.info(request, _('Subproject is now locked for translation updates!'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.lock_subproject')
def unlock_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug = subproject, project__slug = project)

    obj.locked = False
    obj.save()

    messages.info(request, _('Subproject is now open for translation updates.'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.lock_subproject')
def lock_project(request, project):
    obj = get_object_or_404(Project, slug = project)

    obj.commit_pending()

    for sp in obj.subproject_set.all():
        sp.locked = True
        sp.save()

    messages.info(request, _('All subprojects are now locked for translation updates!'))

    return HttpResponseRedirect(obj.get_absolute_url())

@login_required
@permission_required('trans.lock_subproject')
def unlock_project(request, project):
    obj = get_object_or_404(Project, slug = project)

    for sp in obj.subproject_set.all():
        sp.locked = False
        sp.save()

    messages.info(request, _('Project is now open for translation updates.'))

    return HttpResponseRedirect(obj.get_absolute_url())


def download_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project, enabled = True)

    # Retrieve ttkit store to get extension and mime type
    store = obj.get_store()
    srcfilename = obj.get_filename()
    mime = store.Mimetypes[0]
    ext = store.Extensions[0]

    # Construct file name (do not use real filename as it is usually not that useful)
    filename = '%s-%s-%s.%s' % (project, subproject, lang, ext)

    # Django wrapper for sending file
    wrapper = FixedFileWrapper(file(srcfilename))

    response = HttpResponse(wrapper, mimetype = mime)

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
        s = SearchForm(request.POST)
    else:
        s = SearchForm(request.GET)
    if s.is_valid():
        search_query = s.cleaned_data['q']
        search_exact = s.cleaned_data['exact']
        search_source = s.cleaned_data['src']
        search_target = s.cleaned_data['tgt']
        search_context = s.cleaned_data['ctx']
        search_url = '&q=%s&src=%s&tgt=%s&ctx=%s&exact=%s' % (
            search_query,
            bool2str(search_source),
            bool2str(search_target),
            bool2str(search_context),
            bool2str(search_exact),
        )
    else:
        search_query = ''
        search_exact = False
        search_source = True
        search_target = True
        search_context = True
        search_url = ''

    if 'date' in request.REQUEST:
        search_url += '&date=%s' % request.REQUEST['date']

    return (
        rqtype,
        direction,
        pos,
        search_query,
        search_exact,
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
        return _('Not translated strings')
    elif rqtype == 'suggestions':
        return _('Strings with suggestions')
    elif rqtype in CHECKS:
        return CHECKS[rqtype].name
    else:
        return None


def translate(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project, enabled = True)

    # Check locks
    locked = obj.is_locked(request)

    if request.user.is_authenticated():
        profile = request.user.get_profile()
        antispam = None
    else:
        profile = None
        antispam = AntispamForm()

    secondary = None
    unit = None

    rqtype, direction, pos, search_query, search_exact, search_source, search_target, search_context, search_url = parse_search_url(request)

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
        if form.is_valid() and not locked:
            # Check whether translation is not outdated
            obj.check_sync()
            try:
                try:
                    unit = Unit.objects.get(checksum = form.cleaned_data['checksum'], translation = obj)
                except Unit.MultipleObjectsReturned:
                    # Possible temporary inconsistency caused by ongoing update of repo,
                    # let's pretend everyting is okay
                    unit = Unit.objects.filter(checksum = form.cleaned_data['checksum'], translation = obj)[0]
                if 'suggest' in request.POST:
                    # Handle suggesion saving
                    user = request.user
                    if isinstance(user, AnonymousUser):
                        user = None
                    if form.cleaned_data['target'] == len(form.cleaned_data['target']) * ['']:
                        messages.error(request, _('Your suggestion is empty!'))
                        # Stay on same entry
                        return HttpResponseRedirect('%s?type=%s&pos=%d&dir=stay%s' % (
                            obj.get_translate_url(),
                            rqtype,
                            pos,
                            search_url
                        ))
                    # Create the suggestion
                    sug = Suggestion.objects.create(
                        target = join_plural(form.cleaned_data['target']),
                        checksum = unit.checksum,
                        language = unit.translation.language,
                        project = unit.translation.subproject.project,
                        user = user)
                    # Notify subscribed users
                    from weblate.accounts.models import Profile
                    subscriptions = Profile.objects.subscribed_new_suggestion(obj.subproject.project, obj.language)
                    for subscription in subscriptions:
                        subscription.notify_new_suggestion(obj, sug)
                    # Update suggestion stats
                    if profile is not None:
                        profile.suggested += 1
                        profile.save()
                elif not request.user.is_authenticated():
                    # We accept translations only from authenticated
                    messages.error(request, _('You need to log in to be able to save translations!'))
                elif not request.user.has_perm('trans.save_translation'):
                    # Need privilege to save
                    messages.error(request, _('You don\'t have privileges to save translations!'))
                else:
                    # Remember old checks
                    oldchecks = set(unit.active_checks().values_list('check', flat = True))
                    # Update unit and save it
                    unit.target = join_plural(form.cleaned_data['target'])
                    unit.fuzzy = form.cleaned_data['fuzzy']
                    unit.save_backend(request)

                    # Update stats
                    profile.translated += 1
                    profile.save()
                    # Get new set of checks
                    newchecks = set(unit.active_checks().values_list('check', flat = True))
                    # Did we introduce any new failures?
                    if newchecks > oldchecks:
                        # Show message to user
                        messages.error(request, _('Some checks have failed on your translation!'))
                        # Stay on same entry
                        return HttpResponseRedirect('%s?type=%s&pos=%d&dir=stay%s' % (
                            obj.get_translate_url(),
                            rqtype,
                            pos,
                            search_url
                        ))

                # Redirect to next entry
                return HttpResponseRedirect('%s?type=%s&pos=%d%s' % (
                    obj.get_translate_url(),
                    rqtype,
                    pos,
                    search_url
                ))
            except Unit.DoesNotExist:
                logger.error('message %s disappeared!', form.cleaned_data['checksum'])
                messages.error(request, _('Message you wanted to translate is no longer available!'))

    # Handle translation merging
    if 'merge' in request.GET:
        if not request.user.has_perm('trans.save_translation'):
            # Need privilege to save
            messages.error(request, _('You don\'t have privileges to save translations!'))
        else:
            try:
                mergeform = MergeForm(request.GET)
                if mergeform.is_valid():
                    try:
                        unit = Unit.objects.get(checksum = mergeform.cleaned_data['checksum'], translation = obj)
                    except Unit.MultipleObjectsReturned:
                        # Possible temporary inconsistency caused by ongoing update of repo,
                        # let's pretend everyting is okay
                        unit = Unit.objects.filter(checksum = mergeform.cleaned_data['checksum'], translation = obj)[0]

                    merged = Unit.objects.get(pk = mergeform.cleaned_data['merge'])

                    if unit.checksum != merged.checksum:
                        messages.error(request, _('Can not merge different messages!'))
                    else:
                        unit.target = merged.target
                        unit.fuzzy = merged.fuzzy
                        unit.save_backend(request)
                        # Update stats
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
                logger.error('message %s disappeared!', form.cleaned_data['checksum'])
                messages.error(request, _('Message you wanted to translate is no longer available!'))

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
            suggestion = Suggestion.objects.get(pk = sugid)
        except:
            suggestion = None

        if suggestion is not None:
            if 'accept' in request.GET:
                # Accept suggesiont
                suggestion.accept(request)
            # Delete suggestion in both cases (accepted ones are no longer needed)
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
        allunits = obj.unit_set.review(reviewform.cleaned_data['date'], request.user)
        # Review
        if direction == 'stay':
            units = allunits.filter(position = pos)
        elif direction == 'back':
            units = allunits.filter(position__lt = pos).order_by('-position')
        else:
            units = allunits.filter(position__gt = pos)
    elif search_query != '':
        # Apply search conditions
        if search_exact:
            query = Q()
            if search_source:
                query |= Q(source = search_query)
            if search_target:
                query |= Q(target = search_query)
            if search_context:
                query |= Q(context = search_query)
            allunits = obj.unit_set.filter(query)
        else:
            allunits = obj.unit_set.search(search_query, search_source, search_context, search_target)
        if direction == 'stay':
            units = obj.unit_set.filter(position = pos)
        elif direction == 'back':
            units = allunits.filter(position__lt = pos).order_by('-position')
        else:
            units = allunits.filter(position__gt = pos)
    else:
        allunits = obj.unit_set.filter_type(rqtype, obj)
        # What unit set is about to show
        if direction == 'stay':
            units = obj.unit_set.filter(position = pos)
        elif direction == 'back':
            units = allunits.filter(position__lt = pos).order_by('-position')
        else:
            units = allunits.filter(position__gt = pos)


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
            secondary = Unit.objects.filter(
                checksum = unit.checksum,
                translated = True,
                translation__subproject__project = unit.translation.subproject.project,
                translation__language__in = profile.secondary_languages.exclude(id = unit.translation.language.id)
            )
            # distinct('target') works with Django 1.4 so let's emulate that
            # based on presumption we won't get too many results
            targets = {}
            res = []
            for s in secondary:
                if s.target in targets:
                    continue
                targets[s.target] = 1
                res.append(s)
            secondary = res

        # Prepare form
        form = TranslationForm(initial = {
            'checksum': unit.checksum,
            'target': (unit.translation.language, unit.get_target_plurals()),
            'fuzzy': unit.fuzzy,
        })

    total = obj.unit_set.all().count()
    filter_count = allunits.count()

    return render_to_response('translate.html', RequestContext(request, {
        'object': obj,
        'unit': unit,
        'changes': unit.change_set.all()[:10],
        'total': total,
        'type': rqtype,
        'filter_name': get_filter_name(rqtype, search_query),
        'filter_count': filter_count,
        'filter_pos': filter_count + 1 - units.count(),
        'form': form,
        'antispam': antispam,
        'target_language': obj.language.code,
        'secondary': secondary,
        'search_query': search_query,
        'search_url': search_url,
        'search_query': search_query,
        'search_source': bool2str(search_source),
        'search_exact': bool2str(search_exact),
        'search_target': bool2str(search_target),
        'search_context': bool2str(search_context),
    }))

def get_string(request, checksum):
    '''
    AJAX handler for getting raw string.
    '''
    units = Unit.objects.filter(checksum = checksum)
    if units.count() == 0:
        return HttpResponse('')

    return HttpResponse(units[0].get_source_plurals()[0])

def get_similar(request, unit_id):
    '''
    AJAX handler for getting similar strings.
    '''
    unit = get_object_or_404(Unit, pk = int(unit_id))

    similar = Unit.objects.similar(unit)

    # distinct('target') works with Django 1.4 so let's emulate that
    # based on presumption we won't get too many results
    targets = {}
    res = []
    for s in similar:
        if s.target in targets:
            continue
        targets[s.target] = 1
        res.append(s)
    similar = res

    return render_to_response('js/similar.html', RequestContext(request, {
        'similar': similar,
    }))

def get_other(request, unit_id):
    '''
    AJAX handler for same strings in other subprojects.
    '''
    unit = get_object_or_404(Unit, pk = int(unit_id))

    other = Unit.objects.same(unit)

    rqtype, direction, pos, search_query, search_exact, search_source, search_target, search_context, search_url = parse_search_url(request)

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
    unit = get_object_or_404(Unit, pk = int(unit_id))
    # split to words
    ana = StandardAnalyzer()
    words_std = [token.text for token in ana(unit.get_source_plurals()[0])]
    # additionally extract stems, to catch things like plurals
    ana = StemmingAnalyzer()
    words_stem = [token.text for token in ana(unit.get_source_plurals()[0])]
    # join both lists
    words = set(words_std).union(words_stem)

    return render_to_response('js/dictionary.html', RequestContext(request, {
        'dictionary': Dictionary.objects.filter(
            project = unit.translation.subproject.project,
            language = unit.translation.language,
            source__in = words
        ),
    }))

@login_required
@permission_required('trans.ignore_check')
def ignore_check(request, check_id):
    obj = get_object_or_404(Check, pk = int(check_id))
    obj.ignore = True
    obj.save()
    return HttpResponse('ok')

@login_required
@permission_required('trans.upload_translation')
def upload_translation(request, project, subproject, lang):
    '''
    Handling of translation uploads.
    '''
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project, enabled = True)

    if not obj.subproject.locked and request.method == 'POST':
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
                ret = obj.merge_upload(request, request.FILES['file'], overwrite, author, merge_header = form.cleaned_data['merge_header'])
                if ret:
                    messages.info(request, _('File content successfully merged into translation.'))
                else:
                    messages.info(request, _('There were no new strings in uploaded file.'))
            except Exception, e:
                messages.error(request, _('File content merge failed: %s' % unicode(e)))

    return HttpResponseRedirect(obj.get_absolute_url())

def not_found(request):
    '''
    Error handler showing list of available projects.
    '''
    t = loader.get_template('404.html')
    return HttpResponseNotFound(t.render(RequestContext(request, {
        'request_path': request.path,
        'title': _('Page Not Found'),
        'projects': Project.objects.all(),
    })))

# Cache this page for one month, it should not really change much
@cache_page(30 * 24 * 3600)
def js_config(request):
    '''
    Generates settings for javascript. Includes things like
    API keys for translaiton services or list of languages they
    support.
    '''
    # Apertium support
    if settings.MT_APERTIUM_KEY is not None and settings.MT_APERTIUM_KEY != '':
        try:
            listpairs = urllib2.urlopen('http://api.apertium.org/json/listPairs?key=%s' % settings.MT_APERTIUM_KEY)
            pairs = listpairs.read()
            parsed = json.loads(pairs)
            apertium_langs = [p['targetLanguage'] for p in parsed['responseData'] if p['sourceLanguage'] == 'en']
        except Exception, e:
            logger.error('failed to get supported languages from Apertium, using defaults (%s)', str(e))
            apertium_langs = ['gl', 'ca', 'es', 'eo']
    else:
        apertium_langs = None

    # Microsoft translator support
    if settings.MT_MICROSOFT_KEY is not None and settings.MT_MICROSOFT_KEY != '':
        try:
            listpairs = urllib2.urlopen('http://api.microsofttranslator.com/V2/Http.svc/GetLanguagesForTranslate?appID=%s' % settings.MT_MICROSOFT_KEY)
            data = listpairs.read()
            parsed = ElementTree.fromstring(data)
            microsoft_langs = [p.text for p in parsed.getchildren()]
        except Exception, e:
            logger.error('failed to get supported languages from Microsoft, using defaults (%s)', str(e))
            microsoft_langs = ['ar','bg','ca','zh-CHS','zh-CHT','cs','da','nl','en','et','fi','fr','de','el','ht','he','hi','mww','hu','id','it','ja','ko','lv','lt','no','pl','pt','ro','ru','sk','sl','es','sv','th','tr','uk','vi']
    else:
        microsoft_langs = None

    return render_to_response('js/config.js', RequestContext(request, {
            'apertium_langs': apertium_langs,
            'microsoft_langs': microsoft_langs,
        }),
        mimetype = 'application/javascript')

def about(request):
    context = get_versions()
    totals =  Profile.objects.aggregate(Sum('translated'), Sum('suggested'))
    total_strings = 0
    for p in SubProject.objects.iterator():
        try:
            total_strings += p.translation_set.all()[0].total
        except Translation.DoesNotExist:
            pass
    context['title'] = _('About Weblate')
    context['total_translations'] = totals['translated__sum']
    context['total_suggestions'] = totals['suggested__sum']
    context['total_users'] = Profile.objects.count()
    context['total_strings'] = total_strings
    context['total_languages'] = Language.objects.filter(translation__total__gt = 0).distinct().count()

    return render_to_response('about.html', RequestContext(request, context))

@user_passes_test(lambda u: u.has_perm('trans.commit_translation') or u.has_perm('trans.update_translation'))
def git_status_project(request, project):
    obj = get_object_or_404(Project, slug = project)

    return render_to_response('js/git-status.html', RequestContext(request, {
        'object': obj,
    }))

@user_passes_test(lambda u: u.has_perm('trans.commit_translation') or u.has_perm('trans.update_translation'))
def git_status_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug = subproject, project__slug = project)

    return render_to_response('js/git-status.html', RequestContext(request, {
        'object': obj,
    }))

@user_passes_test(lambda u: u.has_perm('trans.commit_translation') or u.has_perm('trans.update_translation'))
def git_status_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project, enabled = True)

    return render_to_response('js/git-status.html', RequestContext(request, {
        'object': obj,
    }))
