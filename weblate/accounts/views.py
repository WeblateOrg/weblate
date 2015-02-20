# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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

from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.cache import cache_page
from django.http import HttpResponse
from django.contrib.auth import logout
from django.conf import settings
from django.contrib import messages
from django.utils.translation import ugettext as _
from django.contrib.auth.decorators import login_required
from django.core.mail.message import EmailMultiAlternatives
from django.utils import translation
from django.contrib.auth.models import User
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from django.contrib.auth import update_session_auth_hash

from urllib import urlencode

from weblate.accounts.forms import (
    RegistrationForm, PasswordForm, PasswordChangeForm, EmailForm, ResetForm,
    LoginForm, HostingForm, CaptchaRegistrationForm
)
from social.backends.utils import load_backends
from social.apps.django_app.utils import BACKENDS
from social.apps.django_app.views import complete

import weblate
from weblate.accounts.avatar import get_avatar_image, get_fallback_avatar_url
from weblate.accounts.models import set_lang, remove_user, Profile
from weblate.trans.models import Change, Project, SubProject
from weblate.accounts.forms import (
    ProfileForm, SubscriptionForm, UserForm, ContactForm,
    SubscriptionSettingsForm
)
from weblate import appsettings

CONTACT_TEMPLATE = '''
Message from %(name)s <%(email)s>:

%(message)s
'''

HOSTING_TEMPLATE = '''
%(name)s <%(email)s> wants to host %(project)s

Project:    %(project)s
Website:    %(url)s
Repository: %(repo)s
Filemask:   %(mask)s

Additional message:

%(message)s
'''


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


def mail_admins_contact(request, subject, message, context, sender):
    '''
    Sends a message to the admins, as defined by the ADMINS setting.
    '''
    weblate.logger.info(
        'contact from from %s: %s',
        sender,
        subject,
    )
    if not settings.ADMINS:
        messages.error(
            request,
            _('Message could not be sent to administrator!')
        )
        weblate.logger.error(
            'ADMINS not configured, can not send message!'
        )
        return

    mail = EmailMultiAlternatives(
        u'%s%s' % (settings.EMAIL_SUBJECT_PREFIX, subject % context),
        message % context,
        to=[a[1] for a in settings.ADMINS],
        headers={'Reply-To': sender},
    )

    mail.send(fail_silently=False)

    messages.success(
        request,
        _('Message has been sent to administrator.')
    )


def deny_demo(request):
    """
    Denies editing of demo account on demo server.
    """
    messages.warning(
        request,
        _('You can not change demo account on the demo server.')
    )
    return redirect('profile')


@login_required
def user_profile(request):

    profile = request.user.profile

    form_classes = [
        ProfileForm,
        SubscriptionForm,
        SubscriptionSettingsForm,
    ]

    if request.method == 'POST':
        # Parse POST params
        forms = [form(request.POST, instance=profile) for form in form_classes]
        forms.append(UserForm(request.POST, instance=request.user))

        if appsettings.DEMO_SERVER and request.user.username == 'demo':
            return deny_demo(request)

        if min([form.is_valid() for form in forms]):
            # Save changes
            for form in forms:
                form.save()

            # Change language
            set_lang(request, request.user.profile)

            # Redirect after saving (and possibly changing language)
            response = redirect('profile')

            # Set language cookie and activate new language (for message below)
            lang_code = profile.language
            response.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang_code)
            translation.activate(lang_code)

            messages.success(request, _('Your profile has been updated.'))

            return response
    else:
        forms = [form(instance=profile) for form in form_classes]
        forms.append(UserForm(instance=request.user))

    social = request.user.social_auth.all()
    social_names = [assoc.provider for assoc in social]
    all_backends = set(load_backends(BACKENDS).keys())
    new_backends = [
        x for x in all_backends
        if x == 'email' or x not in social_names
    ]
    license_projects = SubProject.objects.filter(
        project__in=Project.objects.all_acl(request.user)
    ).exclude(
        license=''
    )

    response = render(
        request,
        'accounts/profile.html',
        {
            'form': forms[0],
            'subscriptionform': forms[1],
            'subscriptionsettingsform': forms[2],
            'userform': forms[3],
            'profile': profile,
            'title': _('User profile'),
            'licenses': license_projects,
            'associated': social,
            'new_backends': new_backends,
        }
    )
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        profile.language
    )
    return response


@login_required
def user_remove(request):
    if appsettings.DEMO_SERVER and request.user.username == 'demo':
        return deny_demo(request)

    if request.method == 'POST':
        remove_user(request.user)

        logout(request)

        messages.success(
            request,
            _('Your account has been removed.')
        )

        return redirect('home')

    return render(
        request,
        'accounts/removal.html',
    )


def get_initial_contact(request):
    '''
    Fills in initial contact form fields from request.
    '''
    initial = {}
    if request.user.is_authenticated():
        initial['name'] = request.user.first_name
        initial['email'] = request.user.email
    return initial


def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            mail_admins_contact(
                request,
                '%(subject)s',
                CONTACT_TEMPLATE,
                form.cleaned_data,
                form.cleaned_data['email'],
            )
            return redirect('home')
    else:
        initial = get_initial_contact(request)
        if 'subject' in request.GET:
            initial['subject'] = request.GET['subject']
        form = ContactForm(initial=initial)

    return render(
        request,
        'accounts/contact.html',
        {
            'form': form,
            'title': _('Contact'),
        }
    )


def hosting(request):
    '''
    Form for hosting request.
    '''
    if not appsettings.OFFER_HOSTING:
        return redirect('home')

    if request.method == 'POST':
        form = HostingForm(request.POST)
        if form.is_valid():
            mail_admins_contact(
                request,
                'Hosting request for %(project)s',
                HOSTING_TEMPLATE,
                form.cleaned_data,
                form.cleaned_data['email'],
            )
            return redirect('home')
    else:
        initial = get_initial_contact(request)
        form = HostingForm(initial=initial)

    return render(
        request,
        'accounts/hosting.html',
        {
            'form': form,
            'title': _('Hosting'),
        }
    )


def user_page(request, user):
    '''
    User details page.
    '''
    user = get_object_or_404(User, username=user)
    profile = get_object_or_404(Profile, user=user)

    # Filter all user activity
    all_changes = Change.objects.last_changes(request.user).filter(
        user=user,
    )

    # Last user activity
    last_changes = all_changes[:10]

    # Filter where project is active
    user_projects_ids = set(all_changes.values_list(
        'translation__subproject__project', flat=True
    ))
    user_projects = Project.objects.filter(id__in=user_projects_ids)

    return render(
        request,
        'accounts/user.html',
        {
            'page_profile': profile,
            'page_user': user,
            'last_changes': last_changes,
            'last_changes_url': urlencode(
                {'user': user.username.encode('utf-8')}
            ),
            'user_projects': user_projects,
        }
    )


@cache_page(3600 * 24)
def user_avatar(request, user, size):
    '''
    User avatar page.
    '''
    user = get_object_or_404(User, username=user)

    if user.email == 'noreply@weblate.org':
        return redirect(get_fallback_avatar_url(size))

    return HttpResponse(
        content_type='image/png',
        content=get_avatar_image(user, size)
    )


def weblate_login(request):
    '''
    Login handler, just wrapper around login.
    '''

    # Redirect logged in users to profile
    if request.user.is_authenticated():
        return redirect('profile')

    return auth_views.login(
        request,
        template_name='accounts/login.html',
        authentication_form=LoginForm,
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

    return auth_views.logout(
        request,
        next_page=settings.LOGIN_URL,
    )


def register(request):
    '''
    Registration form.
    '''
    if appsettings.REGISTRATION_CAPTCHA:
        form_class = CaptchaRegistrationForm
    else:
        form_class = RegistrationForm

    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid() and appsettings.REGISTRATION_OPEN:
            return complete(request, 'email')
    else:
        form = form_class()

    backends = set(load_backends(BACKENDS).keys())

    return render(
        request,
        'accounts/register.html',
        {
            'registration_email': 'email' in backends,
            'registration_backends': backends - set(['email']),
            'title': _('User registration'),
            'form': form,
        }
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

    return render(
        request,
        'accounts/email.html',
        {
            'title': _('Register email'),
            'form': form,
        }
    )


@login_required
def password(request):
    '''
    Password change / set form.
    '''
    if appsettings.DEMO_SERVER and request.user.username == 'demo':
        return deny_demo(request)

    do_change = False

    if not request.user.has_usable_password():
        do_change = True
        change_form = None
    elif request.method == 'POST':
        change_form = PasswordChangeForm(request.POST)
        if change_form.is_valid():
            cur_password = change_form.cleaned_data['password']
            do_change = request.user.check_password(cur_password)
            if not do_change:
                messages.error(
                    request,
                    _('You have entered an invalid password.')
                )
    else:
        change_form = PasswordChangeForm()

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

            # Update session hash for Django 1.7
            if update_session_auth_hash:
                update_session_auth_hash(request, request.user)

            messages.success(
                request,
                _('Your password has been changed.')
            )
            return redirect('profile')
    else:
        form = PasswordForm()

    return render(
        request,
        'accounts/password.html',
        {
            'title': _('Change password'),
            'change_form': change_form,
            'form': form,
        }
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
            if not request.session.session_key:
                request.session.create()
            request.session['password_reset'] = True
            return complete(request, 'email')
    else:
        form = ResetForm()

    return render(
        request,
        'accounts/reset.html',
        {
            'title': _('Password reset'),
            'form': form,
        }
    )
