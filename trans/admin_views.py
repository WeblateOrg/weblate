from trans.models import SubProject
from django.template import RequestContext
from django.shortcuts import render_to_response
from django.contrib.admin.views.decorators import staff_member_required

@staff_member_required
def report(request):
    return render_to_response("admin/report.html", RequestContext(request, {
        'subprojects': SubProject.objects.all()
    }))
