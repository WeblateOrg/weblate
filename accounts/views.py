from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings
from django.utils.translation import ugettext as _

from accounts.forms import ProfileForm, UserForm, ContactForm

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

def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
    else:
        form = ContectForm()

    return render_to_response('contact.html', RequestContext(request, {
        'form': form,
        'title': '%s @ %s' % (_('Contact'), settings.SITE_TITLE),
    }))
