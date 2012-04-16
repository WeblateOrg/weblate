from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings
from django.contrib import messages
from django.utils.translation import ugettext as _
from django.http import HttpResponseRedirect
from django.core.mail import mail_admins
from django.contrib.auth.decorators import login_required

from weblate.accounts.models import set_lang
from weblate.accounts.forms import ProfileForm, UserForm, ContactForm

@login_required
def profile(request):

    if request.method == 'POST':
        form = ProfileForm(request.POST, instance = request.user.get_profile())
        userform = UserForm(request.POST, instance = request.user)
        if form.is_valid() and userform.is_valid():
            form.save()
            userform.save()
            set_lang(request.user, request = request, user = request.user)
            # Need to redirect to allow language change
            response = HttpResponseRedirect('/accounts/profile/')
            response.set_cookie(settings.LANGUAGE_COOKIE_NAME, request.user.get_profile().language)
            return response
    else:
        form = ProfileForm(instance = request.user.get_profile())
        userform = UserForm(instance = request.user)

    response = render_to_response('profile.html', RequestContext(request, {
        'form': form,
        'userform': userform,
        'title': _('User profile'),
        }))
    response.set_cookie(settings.LANGUAGE_COOKIE_NAME, request.user.get_profile().language)
    return response

def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            mail_admins(
                form.cleaned_data['subject'],
                'Message from %s <%s>:\n\n%s' % (
                    form.cleaned_data['name'],
                    form.cleaned_data['email'],
                    form.cleaned_data['message']
                ))
            messages.info(request, _('Message has been sent to administrator.'))
            return HttpResponseRedirect('/')
    else:
        initial = {}
        if request.user.is_authenticated():
            initial['name'] = request.user.get_full_name()
            initial['email'] = request.user.email
        if 'subject' in request.GET:
            initial['subject'] = request.GET['subject']
        form = ContactForm(initial = initial)

    return render_to_response('contact.html', RequestContext(request, {
        'form': form,
        'title': _('Contact'),
    }))
