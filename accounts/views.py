# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.shortcuts import render_to_response, get_object_or_404, redirect
from django.template import RequestContext
from django.conf import settings
from django.contrib import messages
from django.utils.translation import ugettext as _
from django.contrib.auth.decorators import login_required
from django.core.mail.message import EmailMultiAlternatives
from django.utils import translation
from django.contrib.auth.models import User
from django.contrib.auth.views import login, logout
from django.views.generic import TemplateView
from urllib import urlencode

from accounts.forms import (
    RegistrationForm, PasswordForm, PasswordChangeForm, EmailForm, ResetForm
)
from social.backends.utils import load_backends
from social.apps.django_app.utils import BACKENDS
from social.apps.django_app.views import complete

from accounts.models import set_lang, Profile
from trans.models import Change, Project
from accounts.forms import (
    ProfileForm, SubscriptionForm, UserForm, ContactForm
)
from weblate import appsettings


class RegistrationTemplateView(TemplateView):
    '''
    Class for rendering registration pages.
    '''
    def get_context_data(self, **kwargs):
        '''
        Creates context for rendering page.
        '''
        context = super(RegistrationTemplateView, self).get_context_data(
            **kwargs
        )
        context['title'] = _('User registration')
        return context


def mail_admins_sender(subject, message, sender, fail_silently=False,
                       connection=None, html_message=None):
    '''
    Sends a message to the admins, as defined by the ADMINS setting.
    '''
    if not settings.ADMINS:
        return

    mail = EmailMultiAlternatives(
        u'%s%s' % (settings.EMAIL_SUBJECT_PREFIX, subject),
        message, sender, [a[1] for a in settings.ADMINS],
        connection=connection
    )

    if html_message:
        mail.attach_alternative(html_message, 'text/html')

    mail.send(fail_silently=fail_silently)


@login_required
def user_profile(request):

    profile = request.user.get_profile()

    if request.method == 'POST':
        # Read params
        form = ProfileForm(
            request.POST,
            instance=profile
        )
        subscriptionform = SubscriptionForm(
            request.POST,
            instance=profile
        )
        userform = UserForm(
            request.POST,
            instance=request.user
        )
        if (form.is_valid()
                and userform.is_valid()
                and subscriptionform.is_valid()):
            # Save changes
            form.save()
            subscriptionform.save()
            userform.save()

            # Change language
            set_lang(request.user, request=request, user=request.user)

            # Redirect after saving (and possibly changing language)
            response = redirect('profile')

            # Set language cookie and activate new language (for message below)
            lang_code = profile.language
            response.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang_code)
            translation.activate(lang_code)

            messages.info(request, _('Your profile has been updated.'))

            return response
    else:
        form = ProfileForm(
            instance=profile
        )
        subscriptionform = SubscriptionForm(
            instance=profile
        )
        userform = UserForm(
            instance=request.user
        )

    social = request.user.social_auth.all()
    social_names = [assoc.provider for assoc in social]
    new_backends = [
        x for x in load_backends(BACKENDS).keys()
        if x == 'email' or x not in social_names
    ]

    response = render_to_response(
        'accounts/profile.html',
        RequestContext(
            request,
            {
                'form': form,
                'userform': userform,
                'subscriptionform': subscriptionform,
                'profile': profile,
                'title': _('User profile'),
                'licenses': Project.objects.exclude(license=''),
                'associated': social,
                'new_backends': new_backends,
            }
        )
    )
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        profile.language
    )
    return response


def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            mail_admins_sender(
                form.cleaned_data['subject'],
                'Message from %s <%s>:\n\n%s' % (
                    form.cleaned_data['name'],
                    form.cleaned_data['email'],
                    form.cleaned_data['message']
                ),
                form.cleaned_data['email'],
            )
            messages.info(
                request,
                _('Message has been sent to administrator.')
            )
            return redirect('home')
    else:
        initial = {}
        if request.user.is_authenticated():
            initial['name'] = request.user.get_full_name()
            initial['email'] = request.user.email
        if 'subject' in request.GET:
            initial['subject'] = request.GET['subject']
        form = ContactForm(initial=initial)

    return render_to_response(
        'accounts/contact.html',
        RequestContext(
            request,
            {
                'form': form,
                'title': _('Contact'),
            }
        )
    )


def user_page(request, user):
    '''
    User details page.
    '''
    user = get_object_or_404(User, username=user)
    profile = get_object_or_404(Profile, user=user)

    # Projects user is allowed to see
    acl_projects = Project.objects.all_acl(request.user)

    # Filter all user activity
    all_changes = Change.objects.filter(
        user=user,
        translation__subproject__project__in=acl_projects,
    )

    # Last user activity
    last_changes = all_changes[:10]

    # Filter where project is active
    user_projects_ids = set(all_changes.values_list(
        'translation__subproject__project', flat=True
    ))
    user_projects = Project.objects.filter(id__in=user_projects_ids)

    return render_to_response(
        'accounts/user.html',
        RequestContext(
            request,
            {
                'page_profile': profile,
                'page_user': user,
                'last_changes': last_changes,
                'last_changes_url': urlencode({'user': user.username}),
                'user_projects': user_projects,
            }
        )
    )


def weblate_login(request):
    '''
    Login handler, just wrapper around login.
    '''

    # Redirect logged in users to profile
    if request.user.is_authenticated():
        return redirect('profile')

    if 'message' in request.GET:
        messages.info(request, request.GET['message'])

    return login(
        request,
        template_name='accounts/login.html',
        extra_context={
            'login_backends': [
                x for x in load_backends(BACKENDS).keys() if x != 'email'
            ],
            'title': _('Login'),
        }
    )


@login_required
def weblate_logout(request):
    '''
    Logout handler, just wrapper around standard logout.
    '''
    messages.info(request, _('Thanks for using Weblate!'))

    return logout(
        request,
        next_page=settings.LOGIN_URL,
    )


def register(request):
    '''
    Registration form.
    '''
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid() and appsettings.REGISTRATION_OPEN:
            return complete(request, 'email')
    else:
        form = RegistrationForm()

    return render_to_response(
        'accounts/register.html',
        RequestContext(
            request,
            {
                'registration_backends': [
                    x for x in load_backends(BACKENDS).keys() if x != 'email'
                ],
                'title': _('User registration'),
                'form': form,
            }
        )
    )


@login_required
def email_login(request):
    '''
    Connect email.
    '''
    if request.method == 'POST':
        form = EmailForm(request.POST)
        if form.is_valid():
            return complete(request, 'email')
    else:
        form = EmailForm()

    return render_to_response(
        'accounts/email.html',
        RequestContext(
            request,
            {
                'title': _('Register email'),
                'form': form,
            }
        )
    )


@login_required
def password(request):
    '''
    Password change / set form.
    '''

    do_change = False

    if request.user.has_usable_password():
        if request.method == 'POST':
            change_form = PasswordChangeForm(request.POST)
            if change_form.is_valid():
                cur_password = change_form.cleaned_data['password']
                if request.user.check_password(cur_password):
                    do_change = True
                else:
                    messages.error(
                        request,
                        _('You have entered invalid password.')
                    )
        else:
            change_form = PasswordChangeForm()
    else:
        do_change = True
        change_form = None

    if request.method == 'POST':
        form = PasswordForm(request.POST)
        if form.is_valid() and do_change:

            # Clear flag forcing user to set password
            if 'show_set_password' in request.session:
                del request.session['show_set_password']

            request.user.set_password(
                form.cleaned_data['password1']
            )
            request.user.save()
            messages.info(
                request,
                _('Your password has been changed.')
            )
            return redirect('profile')
    else:
        form = PasswordForm()

    return render_to_response(
        'accounts/password.html',
        RequestContext(
            request,
            {
                'title': _('Change password'),
                'change_form': change_form,
                'form': form,
            }
        )
    )


def reset_password(request):
    '''
    Password reset handling.
    '''
    if request.method == 'POST':
        form = ResetForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data['email']
            user.set_unusable_password()
            user.save()
            return complete(request, 'email')
    else:
        form = ResetForm()

    return render_to_response(
        'accounts/reset.html',
        RequestContext(
            request,
            {
                'title': _('Password reset'),
                'form': form,
            }
        )
    )
