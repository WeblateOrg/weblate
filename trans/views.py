from django.shortcuts import render_to_response, get_object_or_404
from django.core.servers.basehttp import FileWrapper
from django.utils.translation import ugettext_lazy, ugettext as _
from django.template import RequestContext, loader
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseNotAllowed, HttpResponseNotFound
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt

from trans.models import Project, SubProject, Translation, Unit, Suggestion
from lang.models import Language
from trans.forms import TranslationForm, UploadForm, SearchForm
from util import is_plural, split_plural, join_plural
from accounts.models import Profile
import logging
import os.path

logger = logging.getLogger('weblate')

def home(request):
    projects = Project.objects.all()

    usertranslations = None
    if request.user.is_authenticated():
        profile = request.user.get_profile()

        usertranslations = Translation.objects.filter(language__in = profile.languages.all()).order_by('subproject__project__name', 'subproject__name')

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
    form = UploadForm()
    search_form = SearchForm()

    return render_to_response('translation.html', RequestContext(request, {
        'object': obj,
        'form': form,
        'search_form': search_form,
    }))

def download_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project)

    store = obj.get_store()
    srcfilename = obj.get_filename()
    mime = store.Mimetypes[0]
    ext = store.Extensions[0]
    filename = '%s-%s-%s.%s' % (project, subproject, lang, ext)

    wrapper = FileWrapper(file(srcfilename))

    response = HttpResponse(wrapper, mimetype = mime)
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
    pos = request.REQUEST.get('oldpos', '-1')
    try:
        pos = int(pos)
    except:
        pos = -1

    unit = None

    if request.method == 'POST':
        s = SearchForm(request.POST)
    else:
        s = SearchForm(request.GET)
    if s.is_valid():
        search_query = s.cleaned_data['q']
        search_source = s.cleaned_data['src']
        search_target = s.cleaned_data['tgt']
        search_context = s.cleaned_data['ctx']
        search_url = '&q=%s&src=%s&tgt=%s&ctx=%s' % (
            search_query,
            bool2str(search_source),
            bool2str(search_target),
            bool2str(search_context)
        )
    else:
        search_query = ''
        search_source = True
        search_target = True
        search_context = True
        search_url = ''

    # Any form submitted?
    if request.method == 'POST':
        form = TranslationForm(request.POST)
        if form.is_valid():
            obj.check_sync()
            try:
                try:
                    unit = Unit.objects.get(checksum = form.cleaned_data['checksum'], translation = obj)
                except Unit.MultipleObjectsReturned:
                    # Possible temporary inconsistency caused by ongoing update of repo,
                    # let's pretend everyting is okay
                    unit = Unit.objects.filter(checksum = form.cleaned_data['checksum'], translation = obj)[0]
                if 'suggest' in request.POST:
                    user = request.user
                    if isinstance(user, AnonymousUser):
                        user = None
                    Suggestion.objects.create(
                        target = join_plural(form.cleaned_data['target']),
                        checksum = unit.checksum,
                        language = unit.translation.language,
                        project = unit.translation.subproject.project,
                        user = user)
                    if profile is not None:
                        profile.suggested += 1
                        profile.save()
                elif not request.user.is_authenticated():
                    messages.add_message(request, messages.ERROR, _('You need to login to be able to save translations!'))
                else:
                    unit.target = join_plural(form.cleaned_data['target'])
                    unit.fuzzy = form.cleaned_data['fuzzy']
                    unit.save_backend(request)
                    if profile is not None:
                        profile.translated += 1
                        profile.save()

                # Check and save
                return HttpResponseRedirect('%s?type=%s&oldpos=%d%s' % (
                    obj.get_translate_url(),
                    rqtype,
                    pos,
                    search_url
                ))
            except Unit.DoesNotExist:
                logger.error('message %s disappeared!', form.cleaned_data['checksum'])
                messages.add_message(request, messages.ERROR, _('Message you wanted to translate is no longer available!'))

    # Handle suggestions
    if 'accept' in request.GET or 'delete' in request.GET:
        if not request.user.is_authenticated():
            messages.add_message(request, messages.ERROR, _('You need to login to be able to manage suggestions!'))
            return HttpResponseRedirect('%s?type=%s&oldpos=%d&dir=stay%s' % (
                obj.get_translate_url(),
                rqtype,
                pos,
                search_url
            ))
        if 'accept' in request.GET:
            sugid = request.GET['accept']
        else:
            sugid = request.GET['delete']
        try:
            sugid = int(sugid)
            suggestion = Suggestion.objects.get(pk = sugid)
        except:
            suggestion = None

        if suggestion is not None:
            if 'accept' in request.GET:
                suggestion.accept(request)
            suggestion.delete()
        else:
            messages.add_message(request, messages.ERROR, _('Invalid suggestion!'))
        return HttpResponseRedirect('%s?type=%s&oldpos=%d&dir=stay%s' % (
            obj.get_translate_url(),
            rqtype,
            pos,
            search_url
        ))

    # If we failed to get unit above or on no POST
    if unit is None:
        # What unit to show
        if direction == 'stay':
            units = obj.unit_set.filter(position = pos)
        elif direction == 'back':
            units = obj.unit_set.filter_type(rqtype).filter(position__lt = pos).order_by('-position')
        else:
            units = obj.unit_set.filter_type(rqtype).filter(position__gt = pos)
        if search_query != '':
            query = Q()
            if search_source:
                query |= Q(source__icontains = search_query)
            units = units.filter(query)

        try:
            unit = units[0]
        except IndexError:
            messages.add_message(request, messages.INFO, _('You have reached end of translating.'))
            return HttpResponseRedirect(obj.get_absolute_url())

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
        'secondary': secondary,
        'search_query': search_query,
        'search_url': search_url,
        'search_query': search_query,
        'search_source': bool2str(search_source),
        'search_target': bool2str(search_target),
        'search_context': bool2str(search_context),
    }))

def get_string(request, checksum):
    units = Unit.objects.filter(checksum = checksum)
    if units.count() == 0:
        return HttpResponse('')

    return HttpResponse(units[0].get_source_plurals()[0])

@login_required
def upload_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project)

    if request.method == 'POST':
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                ret = obj.merge_upload(request, request.FILES['file'], form.cleaned_data['overwrite'])
                if ret:
                    messages.add_message(request, messages.INFO, _('File content successfully merged into translation.'))
                else:
                    messages.add_message(request, messages.INFO, _('There were no new strings in uploaded file.'))
            except Exception, e:
                messages.add_message(request, messages.ERROR, _('File content merge failed: %s' % str(e)))

    return HttpResponseRedirect(obj.get_absolute_url())

@csrf_exempt
def update_subproject(request, project, subproject):
    if not settings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    obj = get_object_or_404(SubProject, slug = subproject, project__slug = project)
    obj.update_branch()
    obj.create_translations()
    return HttpResponse('updated')

def not_found(request):
    t = loader.get_template('404.html')
    return HttpResponseNotFound(t.render(RequestContext(request, {
        'request_path': request.path,
        'title': _('Page Not Found'),
        'projects': Project.objects.all(),
    })))
