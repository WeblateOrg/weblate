from django.shortcuts import render_to_response, get_object_or_404
from django.utils.translation import ugettext_lazy, ugettext as _
from django.template import RequestContext
from django.conf import settings
from django.http import HttpResponseRedirect
from django.contrib import messages

from trans.models import Project, SubProject, Translation, Unit
from trans.forms import TranslationForm

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

    # Any form submitted?
    if request.method == 'POST':
        form = TranslationForm(request.POST)
        if form.is_valid():
            obj.check_sync()
            unit = Unit.objects.get(checksum = form.cleaned_data['checksum'], translation = obj)
            unit.target = form.cleaned_data['target']
            unit.fuzzy = form.cleaned_data['fuzzy']
            unit.save_backend(request)

            # Check and save
            return HttpResponseRedirect('%s?type=%s&oldpos=%d' % (obj.get_translate_url(), rqtype, pos))

    else:
        # What unit to show
        if direction == 'back':
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
            'target': unit.target,
            'fuzzy': unit.fuzzy,
        })

    total = obj.unit_set.all().count()

    return render_to_response('translate.html', RequestContext(request, {
        'object': obj,
        'title': '%s @ %s' % (obj.__unicode__(), settings.SITE_TITLE),
        'unit': unit,
        'total': total,
        'type': rqtype,
        'form': form,
    }))
