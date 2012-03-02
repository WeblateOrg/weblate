from django.shortcuts import render_to_response
from django.template import RequestContext

from accounts.forms import ProfileForm

def profile(request):

    if request.method == 'POST':
        form = ProfileForm(request.POST)
    else:
        form = ProfileForm(instance = request.user.get_profile())

    return render_to_response('profile.html', RequestContext(request, {'form': form}))
