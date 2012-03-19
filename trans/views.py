from django.shortcuts import render_to_response, get_object_or_404
from django.core.servers.basehttp import FileWrapper
from django.utils.translation import ugettext_lazy, ugettext as _
from django.template import RequestContext, loader
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseNotAllowed, HttpResponseNotFound
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q

from trans.models import Project, SubProject, Translation, Unit, Suggestion, Check
from lang.models import Language
from trans.forms import TranslationForm, UploadForm, SimpleUploadForm, SearchForm
from util import is_plural, split_plural, join_plural
from accounts.models import Profile
import logging
import itertools
import os.path

# See https://code.djangoproject.com/ticket/6027
class FixedFileWrapper(FileWrapper):
    def __iter__(self):
        self.filelike.seek(0)
        return self

logger = logging.getLogger('weblate')

def home(request):
    projects = Project.objects.all()

    # Load user translations if user is authenticated
    usertranslations = None
    if request.user.is_authenticated():
        profile = request.user.get_profile()

        usertranslations = Translation.objects.filter(language__in = profile.languages.all()).order_by('subproject__project__name', 'subproject__name')

    # Some stats
    top_translations = Profile.objects.order_by('-translated')[:10]
    top_suggestions = Profile.objects.order_by('-suggested')[:10]

    return render_to_response('index.html', RequestContext(request, {
        'projects': projects,
        'top_translations': top_translations,
        'top_suggestions': top_suggestions,
        'usertranslations': usertranslations,
    }))

def show_languages(request):
    return render_to_response('languages.html', RequestContext(request, {
        'languages': Language.objects.all(),
        'title': _('Languages'),
    }))

def show_language(request, lang):
    obj = get_object_or_404(Language, code = lang)

    return render_to_response('language.html', RequestContext(request, {
        'object': obj,
    }))

def show_project(request, project):
    obj = get_object_or_404(Project, slug = project)

    return render_to_response('project.html', RequestContext(request, {
        'object': obj,
    }))

def show_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug = subproject, project__slug = project)

    return render_to_response('subproject.html', RequestContext(request, {
        'object': obj,
    }))

def show_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project)
    if request.user.has_perm('trans.overwrite_translation'):
        form = UploadForm()
    else:
        form = SimpleUploadForm()
    search_form = SearchForm()

    return render_to_response('translation.html', RequestContext(request, {
        'object': obj,
        'form': form,
        'search_form': search_form,
    }))

def download_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project)

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

def translate(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project)

    if request.user.is_authenticated():
        profile = request.user.get_profile()
    else:
        profile = None

    secondary = None

    # Check where we are
    rqtype = request.REQUEST.get('type', 'all')
    direction = request.REQUEST.get('dir', 'forward')
    pos = request.REQUEST.get('pos', '-1')
    try:
        pos = int(pos)
    except:
        pos = -1

    unit = None

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

    # Any form submitted?
    if request.method == 'POST':
        form = TranslationForm(request.POST)
        if form.is_valid():
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
                    Suggestion.objects.create(
                        target = join_plural(form.cleaned_data['target']),
                        checksum = unit.checksum,
                        language = unit.translation.language,
                        project = unit.translation.subproject.project,
                        user = user)
                    # Update suggestion stats
                    if profile is not None:
                        profile.suggested += 1
                        profile.save()
                elif not request.user.is_authenticated():
                    # We accept translations only from authenticated
                    messages.add_message(request, messages.ERROR, _('You need to log in to be able to save translations!'))
                elif not request.user.has_perm('trans.save_translation'):
                    # Need privilege to save
                    messages.add_message(request, messages.ERROR, _('You don\'t have privileges to save translations!'))
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
                        messages.add_message(request, messages.ERROR, _('Some checks have failed on your translation!'))
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
                messages.add_message(request, messages.ERROR, _('Message you wanted to translate is no longer available!'))

    # Handle accepting/deleting suggestions
    if 'accept' in request.GET or 'delete' in request.GET:
        # Check for authenticated users
        if not request.user.is_authenticated():
            messages.add_message(request, messages.ERROR, _('You need to log in to be able to manage suggestions!'))
            return HttpResponseRedirect('%s?type=%s&pos=%d&dir=stay%s' % (
                obj.get_translate_url(),
                rqtype,
                pos,
                search_url
            ))

        # Parse suggestion ID
        if 'accept' in request.GET:
            if not request.user.has_perm('trans.accept_suggestion'):
                messages.add_message(request, messages.ERROR, _('You do not have privilege to accept suggestions!'))
                return HttpResponseRedirect('%s?type=%s&pos=%d&dir=stay%s' % (
                    obj.get_translate_url(),
                    rqtype,
                    pos,
                    search_url
                ))
            sugid = request.GET['accept']
        else:
            if not request.user.has_perm('trans.delete_suggestion'):
                messages.add_message(request, messages.ERROR, _('You do not have privilege to delete suggestions!'))
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
            messages.add_message(request, messages.ERROR, _('Invalid suggestion!'))

        # Redirect to same entry for possible editing
        return HttpResponseRedirect('%s?type=%s&pos=%d&dir=stay%s' % (
            obj.get_translate_url(),
            rqtype,
            pos,
            search_url
        ))

    # If we failed to get unit above or on no POST
    if unit is None:

        # Apply search conditions
        if search_query != '':
            if search_exact:
                query = Q()
                if search_source:
                    query |= Q(source = search_query)
                if search_target:
                    query |= Q(target = search_query)
                if search_context:
                    query |= Q(context = search_query)
                units = units.filter(query)
            else:
                units = obj.unit_set.none()
                if search_source:
                    units |= obj.unit_set.search(search_query, Language.objects.get(code = 'en'))
                if search_target:
                    units |= obj.unit_set.search(search_query, obj.language)
                if search_context:
                    units |= obj.unit_set.search(search_query, None)
            if direction == 'stay':
                units = units.filter(position = pos)
            elif direction == 'back':
                units = units.filter(position__lt = pos).order_by('-position')
            else:
                units = units.filter(position__gt = pos)
        else:
            # What unit set is about to show
            if direction == 'stay':
                units = obj.unit_set.filter(position = pos)
            elif direction == 'back':
                units = obj.unit_set.filter_type(rqtype).filter(position__lt = pos).order_by('-position')
            else:
                units = obj.unit_set.filter_type(rqtype).filter(position__gt = pos)

        # Grab actual unit
        try:
            unit = units[0]
        except IndexError:
            messages.add_message(request, messages.INFO, _('You have reached end of translating.'))
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

    return render_to_response('translate.html', RequestContext(request, {
        'object': obj,
        'unit': unit,
        'total': total,
        'type': rqtype,
        'form': form,
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
    unit = get_object_or_404(Unit, pk = int(unit_id))
    words = Unit.objects.get_similar_list(unit.get_source_plurals()[0])
    similar = Unit.objects.none()
    cnt = min(len(words), 5)
    # Try to find 10 similar string, remove up to 5 words
    while similar.count() < 10 and cnt > 0 and len(words) - cnt < 5:
        for search in itertools.combinations(words, cnt):
            similar |= Unit.objects.search(search, Language.objects.get(code = 'en')).filter(
                translation__subproject__project = unit.translation.subproject.project,
                translation__language = unit.translation.language).exclude(id = unit.id)
        cnt -= 1

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

    return render_to_response('similar.html', RequestContext(request, {
        'similar': similar,
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
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project)

    if request.method == 'POST':
        if request.user.has_perm('trans.overwrite_translation'):
            form = UploadForm(request.POST, request.FILES)
        else:
            form = SimpleUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                ret = obj.merge_upload(request, request.FILES['file'], form.cleaned_data['overwrite'])
                if ret:
                    messages.add_message(request, messages.INFO, _('File content successfully merged into translation.'))
                else:
                    messages.add_message(request, messages.INFO, _('There were no new strings in uploaded file.'))
            except Exception, e:
                messages.add_message(request, messages.ERROR, _('File content merge failed: %s' % unicode(e)))

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
