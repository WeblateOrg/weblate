from django.shortcuts import render_to_response, get_object_or_404
from django.utils.translation import ugettext_lazy, ugettext as _
from django.template import RequestContext
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import messages

from trans.models import Project, SubProject, Translation, Unit, Suggestion
from trans.forms import TranslationForm
from util import is_plural, split_plural, join_plural
import logging

logger = logging.getLogger('weblate')

def home(request):
    projects = Project.objects.all()

    return render_to_response('index.html', RequestContext(request, {
        'projects': projects,
        'title': settings.SITE_TITLE,
    }))

def show_project(request, project):
    obj = get_object_or_404(Project, slug = project)

    return render_to_response('project.html', RequestContext(request, {
        'object': obj,
        'title': '%s @ %s' % (obj.__unicode__(), settings.SITE_TITLE),
    }))

def show_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug = subproject, project__slug = project)

    return render_to_response('subproject.html', RequestContext(request, {
        'object': obj,
        'title': '%s @ %s' % (obj.__unicode__(), settings.SITE_TITLE),
    }))

def show_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project)

    return render_to_response('translation.html', RequestContext(request, {
        'object': obj,
        'title': '%s @ %s' % (obj.__unicode__(), settings.SITE_TITLE),
    }))

def download_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project)

    store = obj.get_store()
    mime = store.Mimetypes[0]
    ext = store.Extensions[0]
    filename = '%s-%s-%s.%s' % (project, subproject, lang, ext)

    response = HttpResponse(mimetype = mime)
    response['Content-Disposition'] = 'attachment; filename=%s' % filename

    return response

def translate(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project)

    # Check where we are
    rqtype = request.REQUEST.get('type', 'all')
    direction = request.REQUEST.get('dir', 'forward')
    pos = request.REQUEST.get('oldpos', '-1')
    try:
        pos = int(pos)
    except:
        pos = -1

    unit = None

    # Any form submitted?
    if request.method == 'POST':
        form = TranslationForm(request.POST)
        if form.is_valid():
            obj.check_sync()
            try:
                unit = Unit.objects.get(checksum = form.cleaned_data['checksum'], translation = obj)
                if 'suggest' in request.POST:
                    Suggestion.objects.create(
                        target = join_plural(form.cleaned_data['target']),
                        checksum = unit.checksum,
                        language = unit.translation.language,
                        project = unit.translation.subproject.project,
                        user = request.user)
                elif not request.user.is_authenticated():
                    messages.add_message(request, messages.ERROR, _('You need to login to be able to save translations!'))
                else:
                    unit.target = join_plural(form.cleaned_data['target'])
                    unit.fuzzy = form.cleaned_data['fuzzy']
                    unit.save_backend(request)

                # Check and save
                return HttpResponseRedirect('%s?type=%s&oldpos=%d' % (obj.get_translate_url(), rqtype, pos))
            except Unit.DoesNotExist:
                logger.error('message %s disappeared!', form.cleaned_data['checksum'])
                messages.add_message(request, messages.ERROR, _('Message you wanted to translate is no longer available!'))

    # Handle suggestions
    if 'accept' in request.GET or 'delete' in request.GET:
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
        return HttpResponseRedirect('%s?type=%s&oldpos=%d&dir=stay' % (obj.get_translate_url(), rqtype, pos))

    # If we failed to get unit above or on no POST
    if unit is None:
        # What unit to show
        if direction == 'stay':
            units = obj.unit_set.filter(position = pos)
        elif direction == 'back':
            units = obj.unit_set.filter_type(rqtype).filter(position__lt = pos)
        else:
            units = obj.unit_set.filter_type(rqtype).filter(position__gt = pos)

        try:
            unit = units[0]
        except IndexError:
            messages.add_message(request, messages.INFO, _('You have reached end of translating.'))
            return HttpResponseRedirect(obj.get_absolute_url())

        # Prepare form
        form = TranslationForm(initial = {
            'checksum': unit.checksum,
            'target': unit.get_target_plurals(),
            'fuzzy': unit.fuzzy,
        })

    total = obj.unit_set.all().count()

    return render_to_response('translate.html', RequestContext(request, {
        'object': obj,
        'title': '%s @ %s' % (obj.__unicode__(), settings.SITE_TITLE),
        'unit': unit,
        'oldpos': pos,
        'total': total,
        'type': rqtype,
        'form': form,
    }))
