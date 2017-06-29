# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals

from django.db import transaction
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth import logout
from django.conf import settings
from django.utils.translation import ugettext as _
from django.contrib.auth.decorators import login_required
from django.core.mail.message import EmailMultiAlternatives
from django.utils import translation
from django.utils.cache import patch_response_headers
from django.utils.crypto import get_random_string
from django.utils.translation import get_language
from django.contrib.auth.models import User
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView, ListView
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.urlresolvers import reverse
from django.utils.http import urlencode
from django.template.loader import render_to_string

from rest_framework.authtoken.models import Token

from social_core.backends.utils import load_backends
from social_core.exceptions import (
    AuthMissingParameter, InvalidEmail, AuthFailed, AuthCanceled,
    AuthStateMissing, AuthStateForbidden, AuthAlreadyAssociated,
)
from social_django.utils import BACKENDS
from social_django.views import complete, auth

from weblate.accounts.forms import (
    RegistrationForm, PasswordConfirmForm, EmailForm, ResetForm,
    LoginForm, HostingForm, CaptchaForm, SetPasswordForm,
)
from weblate.accounts.ratelimit import check_rate_limit
from weblate.logger import LOGGER
from weblate.accounts.avatar import get_avatar_image, get_fallback_avatar_url
from weblate.accounts.models import set_lang, remove_user, Profile
from weblate.utils import messages
from weblate.trans.models import Change, Project, SubProject, Suggestion
from weblate.trans.views.helper import get_project
from weblate.accounts.forms import (
    ProfileForm, SubscriptionForm, UserForm, ContactForm,
    SubscriptionSettingsForm, UserSettingsForm, DashboardSettingsForm
)
from weblate.accounts.notifications import notify_account_activity

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
Username:   %(username)s

Additional message:

%(message)s
'''

CONTACT_SUBJECTS = {
    'lang': 'New language request',
    'reg': 'Registration problems',
    'hosting': 'Commercial hosting',
    'account': 'Suspicious account activity',
}


class RegistrationTemplateView(TemplateView):
    """Class for rendering registration pages."""
    def get_context_data(self, **kwargs):
        """Create context for rendering page."""
        context = super(RegistrationTemplateView, self).get_context_data(
            **kwargs
        )
        context['title'] = _('User registration')
        return context

    def get(self, request, *args, **kwargs):
        if not request.session.get('registration-email-sent'):
            return redirect('home')

        # Remove session for not authenticated user here.
        # It is no longer needed and will just cause problems
        # with multiple registrations from single browser.
        if not request.user.is_authenticated:
            request.session.flush()
        else:
            request.session.pop('registration-email-sent')

        return super(RegistrationTemplateView, self).get(
            request, *args, **kwargs
        )


def mail_admins_contact(request, subject, message, context, sender):
    """Send a message to the admins, as defined by the ADMINS setting."""
    LOGGER.info(
        'contact form from %s',
        sender,
    )
    if not settings.ADMINS:
        messages.error(
            request,
            _('Message could not be sent to administrator!')
        )
        LOGGER.error(
            'ADMINS not configured, can not send message!'
        )
        return

    mail = EmailMultiAlternatives(
        '{0}{1}'.format(settings.EMAIL_SUBJECT_PREFIX, subject % context),
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
    """Deny editing of demo account on demo server."""
    messages.warning(
        request,
        _('You cannot change demo account on the demo server.')
    )
    return redirect_profile(request.POST.get('activetab'))


def avoid_demo(function):
    """Avoid page being served to demo account."""
    def demo_wrap(request, *args, **kwargs):
        if settings.DEMO_SERVER and request.user.username == 'demo':
            return deny_demo(request)
        return function(request, *args, **kwargs)
    return demo_wrap


def session_ratelimit_post(function):
    """Session based rate limiting for POST requests."""
    def rate_wrap(request, *args, **kwargs):
        attempts = request.session.get('auth_attempts', 0)
        if request.method == 'POST':
            if attempts >= settings.AUTH_MAX_ATTEMPTS:
                logout(request)
                messages.error(
                    request,
                    _('Too many authentication attempts!')
                )
                return redirect('login')
            request.session['auth_attempts'] = attempts + 1
        return function(request, *args, **kwargs)
    return rate_wrap


def session_ratelimit_reset(request):
    request.session['auth_attempts'] = 0


def redirect_profile(page=''):
    url = reverse('profile')
    if page and page.startswith('#'):
        url = url + page
    return HttpResponseRedirect(url)


@login_required
def user_profile(request):

    profile = request.user.profile

    if not profile.language:
        profile.language = get_language()
        profile.save()

    form_classes = [
        ProfileForm,
        SubscriptionForm,
        SubscriptionSettingsForm,
        UserSettingsForm,
        DashboardSettingsForm,
    ]
    all_backends = set(load_backends(BACKENDS).keys())

    if request.method == 'POST':
        # Parse POST params
        forms = [form(request.POST, instance=profile) for form in form_classes]
        forms.append(UserForm(request.POST, instance=request.user))

        if settings.DEMO_SERVER and request.user.username == 'demo':
            return deny_demo(request)

        if all(form.is_valid() for form in forms):
            # Save changes
            for form in forms:
                form.save()

            # Change language
            set_lang(request, request.user.profile)

            # Redirect after saving (and possibly changing language)
            response = redirect_profile(request.POST.get('activetab'))

            # Set language cookie and activate new language (for message below)
            lang_code = profile.language
            response.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang_code)
            translation.activate(lang_code)

            messages.success(request, _('Your profile has been updated.'))

            return response
    else:
        forms = [form(instance=profile) for form in form_classes]
        forms.append(UserForm(instance=request.user))

        if not request.user.has_usable_password() and 'email' in all_backends:
            messages.warning(
                request,
                render_to_string('accounts/password-warning.html')
            )

    social = request.user.social_auth.all()
    social_names = [assoc.provider for assoc in social]
    new_backends = [
        x for x in all_backends
        if x == 'email' or x not in social_names
    ]
    license_projects = SubProject.objects.filter(
        project__in=Project.objects.all_acl(request.user)
    ).exclude(
        license=''
    )

    result = render(
        request,
        'accounts/profile.html',
        {
            'form': forms[0],
            'subscriptionform': forms[1],
            'subscriptionsettingsform': forms[2],
            'usersettingsform': forms[3],
            'dashboardsettingsform': forms[4],
            'userform': forms[5],
            'profile': profile,
            'title': _('User profile'),
            'licenses': license_projects,
            'associated': social,
            'new_backends': new_backends,
            'managed_projects': Project.objects.filter(
                groupacl__groups__name__endswith='@Administration',
                groupacl__groups__user=request.user,
            ).distinct(),
            'auditlog': request.user.auditlog_set.all()[:20],
        }
    )
    result.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        profile.language
    )
    return result


@login_required
@avoid_demo
@session_ratelimit_post
def user_remove(request):
    if request.method == 'POST':
        confirm_form = PasswordConfirmForm(request, request.POST)
        if confirm_form.is_valid():
            session_ratelimit_reset(request)
            remove_user(request.user, request)
            logout(request)
            messages.success(
                request,
                _('Your account has been removed.')
            )
            return redirect('home')
    else:
        confirm_form = PasswordConfirmForm(request)

    return render(
        request,
        'accounts/removal.html',
        {
            'confirm_form': confirm_form,
        }
    )


@login_required
@avoid_demo
@session_ratelimit_post
def confirm(request):
    details = request.session.get('reauthenticate')
    if not details:
        return redirect('home')

    if request.method == 'POST':
        confirm_form = PasswordConfirmForm(request, request.POST)
        if confirm_form.is_valid():
            session_ratelimit_reset(request)
            request.session.pop('reauthenticate')
            request.session['reauthenticate_done'] = True
            return redirect('social:complete', backend=details['backend'])
    else:
        confirm_form = PasswordConfirmForm(request)

    context = {
        'confirm_form': confirm_form,
    }
    context.update(details)

    return render(
        request,
        'accounts/confirm.html',
        context
    )


def get_initial_contact(request):
    """Fill in initial contact form fields from request."""
    initial = {}
    if request.user.is_authenticated:
        initial['name'] = request.user.first_name
        initial['email'] = request.user.email
    return initial


def contact(request):
    captcha = None
    show_captcha = (
        settings.REGISTRATION_CAPTCHA and
        not request.user.is_authenticated
    )

    if request.method == 'POST':
        form = ContactForm(request.POST)
        if show_captcha:
            captcha = CaptchaForm(request, form, request.POST)
        if not check_rate_limit(request):
            messages.error(
                request,
                _('Too many messages sent, please try again later!')
            )
        elif (captcha is None or captcha.is_valid()) and form.is_valid():
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
        if request.GET.get('t') in CONTACT_SUBJECTS:
            initial['subject'] = CONTACT_SUBJECTS[request.GET['t']]
        form = ContactForm(initial=initial)
        if show_captcha:
            captcha = CaptchaForm(request)

    return render(
        request,
        'accounts/contact.html',
        {
            'form': form,
            'captcha_form': captcha,
            'title': _('Contact'),
        }
    )


@login_required
def hosting(request):
    """Form for hosting request."""
    if not settings.OFFER_HOSTING:
        return redirect('home')

    if request.method == 'POST':
        form = HostingForm(request.POST)
        if form.is_valid():
            context = form.cleaned_data
            context['username'] = request.user.username
            mail_admins_contact(
                request,
                'Hosting request for %(project)s',
                HOSTING_TEMPLATE,
                context,
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
    """User details page."""
    user = get_object_or_404(User, username=user)
    profile = Profile.objects.get_or_create(user=user)[0]

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
                {'user': user.username}
            ),
            'user_projects': user_projects,
        }
    )


def user_avatar(request, user, size):
    """User avatar view."""
    user = get_object_or_404(User, username=user)

    if user.email == 'noreply@weblate.org':
        return redirect(get_fallback_avatar_url(size))

    response = HttpResponse(
        content_type='image/png',
        content=get_avatar_image(request, user, size)
    )

    patch_response_headers(response, 3600 * 24 * 7)

    return response


def weblate_login(request):
    """Login handler, just wrapper around standard Django login."""

    # Redirect logged in users to profile
    if request.user.is_authenticated:
        return redirect_profile()

    # Redirect if there is only one backend
    auth_backends = list(load_backends(BACKENDS).keys())
    if len(auth_backends) == 1 and auth_backends[0] != 'email':
        return redirect('social:begin', auth_backends[0])

    return auth_views.login(
        request,
        template_name='accounts/login.html',
        authentication_form=LoginForm,
        extra_context={
            'login_backends': [
                x for x in auth_backends if x != 'email'
            ],
            'can_reset': 'email' in auth_backends,
            'title': _('Login'),
        }
    )


@require_POST
@login_required
def weblate_logout(request):
    """Logout handler, just wrapper around standard Django logout."""
    messages.info(request, _('Thanks for using Weblate!'))

    return auth_views.logout(
        request,
        next_page=reverse('home'),
    )


def register(request):
    """Registration form."""
    captcha = None

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request, form, request.POST)
        if ((captcha is None or captcha.is_valid()) and
                form.is_valid() and settings.REGISTRATION_OPEN):
            if form.cleaned_data['email_user']:
                notify_account_activity(
                    form.cleaned_data['email_user'],
                    request,
                    'connect'
                )
                request.session['registration-email-sent'] = True
                return redirect('email-sent')
            store_userid(request)
            return social_complete(request, 'email')
    else:
        form = RegistrationForm()
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request)

    backends = set(load_backends(BACKENDS).keys())

    # Redirect if there is only one backend
    if len(backends) == 1 and 'email' not in backends:
        return redirect('social:begin', backends.pop())

    return render(
        request,
        'accounts/register.html',
        {
            'registration_email': 'email' in backends,
            'registration_backends': backends - set(['email']),
            'title': _('User registration'),
            'form': form,
            'captcha_form': captcha,
        }
    )


@login_required
@avoid_demo
def email_login(request):
    """Connect email."""
    captcha = None

    if request.method == 'POST':
        form = EmailForm(request.POST)
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request, form, request.POST)
        if (captcha is None or captcha.is_valid()) and form.is_valid():
            if form.cleaned_data['email_user']:
                notify_account_activity(
                    form.cleaned_data['email_user'],
                    request,
                    'connect'
                )
                request.session['registration-email-sent'] = True
                return redirect('email-sent')
            store_userid(request)
            return social_complete(request, 'email')
    else:
        form = EmailForm()
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request)

    return render(
        request,
        'accounts/email.html',
        {
            'title': _('Register email'),
            'form': form,
            'captcha_form': captcha,
        }
    )


@login_required
@avoid_demo
@session_ratelimit_post
def password(request):
    """Password change / set form."""
    do_change = False

    if request.method == 'POST':
        change_form = PasswordConfirmForm(request, request.POST)
        do_change = change_form.is_valid()
    else:
        change_form = PasswordConfirmForm(request)

    if request.method == 'POST':
        form = SetPasswordForm(request.user, request.POST)
        if form.is_valid() and do_change:
            session_ratelimit_reset(request)

            # Clear flag forcing user to set password
            redirect_page = '#auth'
            if 'show_set_password' in request.session:
                del request.session['show_set_password']
                redirect_page = ''

            # Change the password
            form.save(request)

            return redirect_profile(redirect_page)
    else:
        form = SetPasswordForm(request.user)

    return render(
        request,
        'accounts/password.html',
        {
            'title': _('Change password'),
            'change_form': change_form,
            'form': form,
        }
    )


def reset_password_set(request):
    """Perform actual password reset."""
    user = User.objects.get(pk=request.session['perform_reset'])
    if user.has_usable_password():
        request.session.pop('perform_reset')
        request.session.delete()
        request.session.create()
        messages.error(
            request,
            _('Password reset has been already completed!')
        )
        return redirect('login')
    if request.method == 'POST':
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            request.session.pop('perform_reset')
            request.session.delete()
            form.save(request)
            request.session.create()
            return redirect('login')
    else:
        form = SetPasswordForm(user)
    return render(
        request,
        'accounts/reset.html',
        {
            'title': _('Password reset'),
            'form': form,
            'captcha_form': None,
            'second_stage': True,
        }
    )


def reset_password(request):
    """Password reset handling."""
    if request.user.is_authenticated:
        redirect_profile()
    if 'email' not in load_backends(BACKENDS).keys():
        messages.error(
            request,
            _('Can not reset password, email authentication is disabled!')
        )
        return redirect('login')

    captcha = None

    # We're already in the reset phase
    if 'perform_reset' in request.session:
        return reset_password_set(request)
    elif request.method == 'POST':
        form = ResetForm(request.POST)
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request, form, request.POST)
        if (captcha is None or captcha.is_valid()) and form.is_valid():
            if form.cleaned_data['email_user']:
                rate_limited = notify_account_activity(
                    form.cleaned_data['email_user'],
                    request,
                    'reset-request'
                )
                if not rate_limited:
                    request.session['password_reset'] = True
                    store_userid(request)
                    return social_complete(request, 'email')
            request.session['registration-email-sent'] = True
            return redirect('email-sent')
    else:
        form = ResetForm()
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request)

    return render(
        request,
        'accounts/reset.html',
        {
            'title': _('Password reset'),
            'form': form,
            'captcha_form': captcha,
            'second_stage': False,
        }
    )


@require_POST
@login_required
@avoid_demo
@session_ratelimit_post
def reset_api_key(request):
    """Reset user API key"""
    # Need to delete old token as key is primary key
    with transaction.atomic():
        Token.objects.filter(user=request.user).delete()
        Token.objects.create(
            user=request.user,
            key=get_random_string(40)
        )

    return redirect_profile('#api')


@require_POST
@login_required
@avoid_demo
def watch(request, project):
    obj = get_project(request, project)
    request.user.profile.subscriptions.add(obj)
    return redirect(obj)


@require_POST
@login_required
@avoid_demo
def unwatch(request, project):
    obj = get_project(request, project)
    request.user.profile.subscriptions.remove(obj)
    return redirect(obj)


class SuggestionView(ListView):
    paginate_by = 25
    model = Suggestion

    def get_queryset(self):
        return Suggestion.objects.filter(
            user=get_object_or_404(User, username=self.kwargs['user']),
            project__in=Project.objects.all_acl(self.request.user)
        )

    def get_context_data(self):
        result = super(SuggestionView, self).get_context_data()
        user = get_object_or_404(User, username=self.kwargs['user'])
        result['page_user'] = user
        result['page_profile'] = user.profile
        return result


def store_userid(request):
    """Store user ID in the session."""
    request.session['social_auth_user'] = request.user.pk


@require_POST
@avoid_demo
def social_auth(request, backend):
    """Wrapper around social_django.views.auth.

    - requires POST (to avoid CSRF on auth)
    - it stores current user in session (to avoid CSRF on complete)
    """
    store_userid(request)
    return auth(request, backend)


@csrf_exempt
@avoid_demo
def social_complete(request, backend):
    """Wrapper around social_django.views.complete.

    - blocks access for demo user
    - gracefuly handle backend errors
    """
    def fail(message):
        messages.error(request, message)
        return redirect(reverse('login'))

    def redirect_token():
        return fail(_(
            'Failed to verify your registration! '
            'Probably the verification token has expired. '
            'Please try the registration again.'
        ))

    def redirect_state():
        return fail(
            _('Authentication failed due to invalid session state.')
        )

    try:
        return complete(request, backend)
    except InvalidEmail:
        return redirect_token()
    except AuthMissingParameter as error:
        if error.parameter in ('email', 'user', 'expires'):
            return redirect_token()
        elif error.parameter in ('state', 'code'):
            return redirect_state()
        elif error.parameter == 'demo':
            return fail(
                _('Can not change authentication for demo!')
            )
        elif error.parameter == 'disabled':
            return fail(
                _('New registrations are disabled!')
            )
        raise
    except (AuthStateMissing, AuthStateForbidden):
        return redirect_state()
    except AuthFailed:
        return fail(_(
            'Authentication has failed, probably due to expired token '
            'or connection error.'
        ))
    except AuthCanceled:
        return fail(_('Authentication has been cancelled.'))
    except AuthAlreadyAssociated:
        return fail(_(
            'Failed to complete your registration! This authentication, '
            'email or username are already associated with another account!'
        ))
