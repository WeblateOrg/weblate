from django.shortcuts import render_to_response
from django.template import RequestContext

from accounts.forms import ProfileForm, UserForm

def profile(request):

    if request.method == 'POST':
        form = ProfileForm(request.POST, instance = request.user.get_profile())
        userform = UserForm(request.POST, instance = request.user)
        if form.is_valid() and userform.is_valid():
            form.save()
            userform.save()
    else:
        form = ProfileForm(instance = request.user.get_profile())
        userform = UserForm(instance = request.user)

    return render_to_response('profile.html', RequestContext(request, {
        'form': form,
        'userform': userform,
        }))
