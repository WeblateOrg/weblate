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
    obj = get_object_or_404(Language, language__code = lang, subproject__slug = subproject, subproject__project__slug = project)

    return render_to_response('translation.html', RequestContext(request, {
        'object': obj,
        'title': '%s @ Weblate' % (obj.__unicode__()),
    }))

