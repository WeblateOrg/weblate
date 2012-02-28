from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext

from trans.models import Project, SubProject, Translation, Unit

def show_project(request, project):
    obj = get_object_or_404(Project, slug = project)

    return render_to_response('project.html', RequestContext(request, {
        'object': obj,
        'title': '%s @ Weblate' % (obj.__unicode__()),
    }))

def show_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug = subproject, project__slug = project)

    return render_to_response('subproject.html', RequestContext(request, {
        'object': obj,
        'title': '%s @ Weblate' % (obj.__unicode__()),
    }))

def show_translation(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project)

    return render_to_response('translation.html', RequestContext(request, {
        'object': obj,
        'title': '%s @ Weblate' % (obj.__unicode__()),
    }))

def translate(request, project, subproject, lang):
    obj = get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project)

    rqtype = request.REQUEST.get('type', 'all')
    pos = request.REQUEST.get('oldpos', '-1')
    try:
        pos = int(pos)
    except:
        pos = -1
    unit = obj.unit_set.filter_type(rqtype).filter(position__gt = pos)[0]
    total = obj.unit_set.all().count()

    return render_to_response('translate.html', RequestContext(request, {
        'object': obj,
        'title': '%s @ Weblate' % (obj.__unicode__()),
        'unit': unit,
        'total': total,
        'type': rqtype,
    }))
