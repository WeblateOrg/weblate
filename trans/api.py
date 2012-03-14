from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseNotAllowed, HttpResponseNotFound
from trans.models import Project, SubProject, Translation, Unit, Suggestion, Check
from django.shortcuts import get_object_or_404

@csrf_exempt
def update_subproject(request, project, subproject):
    '''
    API hook for updating git repos.
    '''
    if not settings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    obj = get_object_or_404(SubProject, slug = subproject, project__slug = project)
    obj.update_branch()
    obj.create_translations()
    return HttpResponse('updated')
