# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

import re
from collections import defaultdict

import social_django.utils
from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail.message import EmailMultiAlternatives
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.middleware.csrf import rotate_token
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.cache import patch_response_headers
from django.utils.crypto import get_random_string
from django.utils.decorators import method_decorator
from django.utils.http import urlencode
from django.utils.translation import get_language
from django.utils.translation import ugettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import ListView, TemplateView
from rest_framework.authtoken.models import Token
from social_core.backends.utils import load_backends
from social_core.exceptions import (
    AuthAlreadyAssociated,
    AuthCanceled,
    AuthFailed,
    AuthForbidden,
    AuthMissingParameter,
    AuthStateForbidden,
    AuthStateMissing,
    InvalidEmail,
)
from social_django.views import auth, complete, disconnect

from weblate.accounts.avatar import get_avatar_image, get_fallback_avatar_url
from weblate.accounts.forms import (
    CaptchaForm,
    ContactForm,
    DashboardSettingsForm,
    EmailForm,
    EmptyConfirmForm,
    HostingForm,
    LoginForm,
    NotificationForm,
    PasswordConfirmForm,
    ProfileForm,
    RegistrationForm,
    ResetForm,
    SetPasswordForm,
    SubscriptionForm,
    UserForm,
    UserSettingsForm,
)
from weblate.accounts.models import AuditLog, Subscription, set_lang
from weblate.accounts.notifications import (
    FREQ_NONE,
    NOTIFICATIONS,
    SCOPE_ADMIN,
    SCOPE_COMPONENT,
    SCOPE_DEFAULT,
    SCOPE_PROJECT,
)
from weblate.accounts.utils import remove_user
from weblate.auth.models import User
from weblate.logger import LOGGER
from weblate.trans.models import Change, Component, Project, Suggestion
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.ratelimit import (
    check_rate_limit,
    reset_rate_limit,
    session_ratelimit_post,
)
from weblate.utils.views import get_component, get_project

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

ANCHOR_RE = re.compile(r'^#[a-z]+$')

NOTIFICATION_PREFIX_TEMPLATE = 'notifications__{}'


class EmailSentView(TemplateView):
    """Class for rendering e-mail sent page."""

    template_name = 'accounts/email-sent.html'

    def get_context_data(self, **kwargs):
        """Create context for rendering page."""
        context = super(EmailSentView, self).get_context_data(**kwargs)
        context['is_reset'] = False
        context['is_remove'] = False
        # This view is not visible for invitation that's
        # why don't handle user_invite here
        if kwargs['password_reset']:
            context['title'] = _('Password reset')
            context['is_reset'] = True
        elif kwargs['account_remove']:
            context['title'] = _('Remove account')
            context['is_remove'] = True
        else:
            context['title'] = _('User registration')

        return context

    def get(self, request, *args, **kwargs):
        if not request.session.get('registration-email-sent'):
            return redirect('home')

        kwargs['password_reset'] = request.session['password_reset']
        kwargs['account_remove'] = request.session['account_remove']
        kwargs['user_invite'] = request.session['user_invite']
        # Remove session for not authenticated user here.
        # It is no longer needed and will just cause problems
        # with multiple registrations from single browser.
        if not request.user.is_authenticated:
            request.session.flush()
        else:
            request.session.pop('registration-email-sent')

        return super(EmailSentView, self).get(request, *args, **kwargs)


def mail_admins_contact(request, subject, message, context, sender, to):
    """Send a message to the admins, as defined by the ADMINS setting."""
    LOGGER.info('contact form from %s', sender)
    if not to and settings.ADMINS:
        to = [a[1] for a in settings.ADMINS]
    elif not settings.ADMINS:
        messages.error(request, _('Message could not be sent to administrator!'))
        LOGGER.error('ADMINS not configured, can not send message!')
        return

    mail = EmailMultiAlternatives(
        '{0}{1}'.format(settings.EMAIL_SUBJECT_PREFIX, subject % context),
        message % context,
        to=to,
        headers={'Reply-To': sender},
    )

    mail.send(fail_silently=False)

    messages.success(request, _('Message has been sent to administrator.'))


def redirect_profile(page=''):
    url = reverse('profile')
    if page and ANCHOR_RE.match(page):
        url = url + page
    return HttpResponseRedirect(url)


def get_notification_forms(request):
    user = request.user
    if request.method == 'POST':
        for i in range(1000):
            prefix = NOTIFICATION_PREFIX_TEMPLATE.format(i)
            if prefix + '-scope' in request.POST:
                yield NotificationForm(
                    request.user, i > 0, {}, i == 0, prefix=prefix, data=request.POST
                )
    else:
        subscriptions = defaultdict(dict)
        initials = {}

        # Ensure default and admin scopes are visible
        for needed in (SCOPE_DEFAULT, SCOPE_ADMIN):
            key = (needed, None, None)
            subscriptions[key] = {}
            initials[key] = {'scope': needed, 'project': None, 'component': None}
        active = (SCOPE_DEFAULT, None, None)

        # Include additional scopes from request
        if 'notify_project' in request.GET:
            try:
                project = user.allowed_projects.get(pk=request.GET['notify_project'])
                active = key = (SCOPE_PROJECT, project.pk, None)
                subscriptions[key] = {}
                initials[key] = {
                    'scope': SCOPE_PROJECT,
                    'project': project,
                    'component': None,
                }
            except (ObjectDoesNotExist, ValueError):
                pass
        if 'notify_component' in request.GET:
            try:
                component = Component.objects.get(
                    project__in=user.allowed_projects,
                    pk=request.GET['notify_component'],
                )
                active = key = (SCOPE_COMPONENT, None, component.pk)
                subscriptions[key] = {}
                initials[key] = {
                    'scope': SCOPE_COMPONENT,
                    'project': None,
                    'component': component,
                }
            except (ObjectDoesNotExist, ValueError):
                pass

        # Popupate scopes from the database
        for subscription in user.subscription_set.iterator():
            key = (
                subscription.scope,
                subscription.project_id,
                subscription.component_id,
            )
            subscriptions[key][subscription.notification] = subscription.frequency
            initials[key] = {
                'scope': subscription.scope,
                'project': subscription.project,
                'component': subscription.component,
            }

        # Generate forms
        for i, details in enumerate(sorted(subscriptions.items())):
            yield NotificationForm(
                user,
                i > 0,
                details[1],
                details[0] == active,
                initial=initials[details[0]],
                prefix=NOTIFICATION_PREFIX_TEMPLATE.format(i),
            )


@never_cache
@login_required
def user_profile(request):
    profile = request.user.profile

    if not profile.language:
        profile.language = get_language()
        profile.save(update_fields=['language'])

    form_classes = [
        ProfileForm,
        SubscriptionForm,
        UserSettingsForm,
        DashboardSettingsForm,
        UserForm,
    ]
    forms = [form.from_request(request) for form in form_classes]
    forms.extend(get_notification_forms(request))
    all_backends = set(load_backends(social_django.utils.BACKENDS).keys())

    if request.method == 'POST':
        if all(form.is_valid() for form in forms):
            # Save changes
            for form in forms:
                if hasattr(form, 'audit'):
                    form.audit(request)
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
        if not request.user.has_usable_password() and 'email' in all_backends:
            messages.warning(
                request, render_to_string('accounts/password-warning.html')
            )

    social = request.user.social_auth.all()
    social_names = [assoc.provider for assoc in social]
    new_backends = [x for x in all_backends if x == 'email' or x not in social_names]
    license_projects = (
        Component.objects.filter(project__in=request.user.allowed_projects)
        .exclude(license='')
        .order_project()
    )

    result = render(
        request,
        'accounts/profile.html',
        {
            'languagesform': forms[0],
            'subscriptionform': forms[1],
            'usersettingsform': forms[2],
            'dashboardsettingsform': forms[3],
            'userform': forms[4],
            'notification_forms': forms[5:],
            'all_forms': forms,
            'profile': profile,
            'title': _('User profile'),
            'licenses': license_projects,
            'associated': social,
            'new_backends': new_backends,
            'auditlog': request.user.auditlog_set.order()[:20],
        },
    )
    result.set_cookie(settings.LANGUAGE_COOKIE_NAME, profile.language)
    return result


@login_required
@session_ratelimit_post('remove')
@never_cache
def user_remove(request):
    is_confirmation = 'remove_confirm' in request.session
    if is_confirmation:
        if request.method == 'POST':
            remove_user(request.user, request)
            rotate_token(request)
            logout(request)
            messages.success(request, _('Your account has been removed.'))
            return redirect('home')
        confirm_form = EmptyConfirmForm(request)

    elif request.method == 'POST':
        confirm_form = PasswordConfirmForm(request, request.POST)
        if confirm_form.is_valid():
            reset_rate_limit('remove', request)
            store_userid(request, remove=True)
            request.GET = {'email': request.user.email}
            return social_complete(request, 'email')
    else:
        confirm_form = PasswordConfirmForm(request)

    return render(
        request,
        'accounts/removal.html',
        {'confirm_form': confirm_form, 'is_confirmation': is_confirmation},
    )


@session_ratelimit_post('confirm')
@never_cache
def confirm(request):
    details = request.session.get('reauthenticate')
    if not details:
        return redirect('home')

    # Monkey patch request
    request.user = User.objects.get(pk=details['user_pk'])

    if request.method == 'POST':
        confirm_form = PasswordConfirmForm(request, request.POST)
        if confirm_form.is_valid():
            request.session.pop('reauthenticate')
            request.session['reauthenticate_done'] = True
            return redirect('social:complete', backend=details['backend'])
    else:
        confirm_form = PasswordConfirmForm(request)

    context = {'confirm_form': confirm_form}
    context.update(details)

    return render(request, 'accounts/confirm.html', context)


def get_initial_contact(request):
    """Fill in initial contact form fields from request."""
    initial = {}
    if request.user.is_authenticated:
        initial['name'] = request.user.full_name
        initial['email'] = request.user.email
    return initial


@never_cache
def contact(request):
    captcha = None
    show_captcha = settings.REGISTRATION_CAPTCHA and not request.user.is_authenticated

    if request.method == 'POST':
        form = ContactForm(request.POST)
        if show_captcha:
            captcha = CaptchaForm(request, form, request.POST)
        if not check_rate_limit('message', request):
            messages.error(
                request, _('Too many messages sent, please try again later!')
            )
        elif (captcha is None or captcha.is_valid()) and form.is_valid():
            mail_admins_contact(
                request,
                '%(subject)s',
                CONTACT_TEMPLATE,
                form.cleaned_data,
                form.cleaned_data['email'],
                settings.ADMINS_CONTACT,
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
        {'form': form, 'captcha_form': captcha, 'title': _('Contact')},
    )


@login_required
@session_ratelimit_post('hosting')
@never_cache
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
                settings.ADMINS_HOSTING,
            )
            return redirect('home')
    else:
        initial = get_initial_contact(request)
        form = HostingForm(initial=initial)

    return render(
        request, 'accounts/hosting.html', {'form': form, 'title': _('Hosting')}
    )


def user_page(request, user):
    """User details page."""
    user = get_object_or_404(User, username=user)

    # Filter all user activity
    all_changes = Change.objects.last_changes(request.user).filter(user=user)

    # Last user activity
    last_changes = all_changes[:10]

    # Filter where project is active
    user_projects_ids = set(
        all_changes.values_list('translation__component__project', flat=True)
    )
    user_projects = Project.objects.filter(id__in=user_projects_ids)

    return render(
        request,
        'accounts/user.html',
        {
            'page_profile': user.profile,
            'page_user': user,
            'last_changes': last_changes,
            'last_changes_url': urlencode({'user': user.username}),
            'user_projects': user_projects,
        },
    )


def user_avatar(request, user, size):
    """User avatar view."""
    user = get_object_or_404(User, username=user)

    if user.email == 'noreply@weblate.org':
        return redirect(get_fallback_avatar_url(size))

    response = HttpResponse(
        content_type='image/png', content=get_avatar_image(request, user, size)
    )

    patch_response_headers(response, 3600 * 24 * 7)

    return response


def redirect_single(request, backend):
    """Redirect user to single authentication backend."""
    return render(request, 'accounts/redirect.html', {'backend': backend})


class WeblateLoginView(LoginView):
    """Login handler, just a wrapper around standard Django login."""

    form_class = LoginForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super(WeblateLoginView, self).get_context_data(**kwargs)
        auth_backends = list(load_backends(social_django.utils.BACKENDS).keys())
        context['login_backends'] = [x for x in auth_backends if x != 'email']
        context['can_reset'] = 'email' in auth_backends
        context['title'] = _('Login')
        return context

    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        # Redirect logged in users to profile
        if request.user.is_authenticated:
            return redirect_profile()

        # Redirect if there is only one backend
        auth_backends = list(load_backends(social_django.utils.BACKENDS).keys())
        if len(auth_backends) == 1 and auth_backends[0] != 'email':
            return redirect_single(request, auth_backends[0])

        if 'next' in request.GET:
            messages.info(request, _('Log in to use Weblate.'))

        return super(WeblateLoginView, self).dispatch(request, *args, **kwargs)


class WeblateLogoutView(LogoutView):
    """Logout handler, just a wrapper around standard Django logout."""

    @method_decorator(require_POST)
    @method_decorator(login_required)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        return super(WeblateLogoutView, self).dispatch(request, *args, **kwargs)

    def get_next_page(self):
        messages.info(self.request, _('Thank you for using Weblate.'))
        return reverse('home')


def fake_email_sent(request, reset=False):
    """Fake redirect to e-mail sent page."""
    request.session['registration-email-sent'] = True
    request.session['password_reset'] = reset
    request.session['account_remove'] = False
    request.session['user_invite'] = False
    return redirect('email-sent')


@never_cache
def register(request):
    """Registration form."""
    captcha = None

    if request.method == 'POST':
        form = RegistrationForm(request, request.POST)
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request, form, request.POST)
        if (
            (captcha is None or captcha.is_valid())
            and form.is_valid()
            and settings.REGISTRATION_OPEN
        ):
            if form.cleaned_data['email_user']:
                AuditLog.objects.create(
                    form.cleaned_data['email_user'], request, 'connect'
                )
                return fake_email_sent(request)
            store_userid(request)
            return social_complete(request, 'email')
    else:
        form = RegistrationForm(request)
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request)

    backends = set(load_backends(social_django.utils.BACKENDS).keys())

    # Redirect if there is only one backend
    if len(backends) == 1 and 'email' not in backends:
        return redirect_single(request, backends.pop())

    return render(
        request,
        'accounts/register.html',
        {
            'registration_email': 'email' in backends,
            'registration_backends': backends - {'email'},
            'title': _('User registration'),
            'form': form,
            'captcha_form': captcha,
        },
    )


@login_required
@never_cache
def email_login(request):
    """Connect e-mail."""
    captcha = None

    if request.method == 'POST':
        form = EmailForm(request.POST)
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request, form, request.POST)
        if (captcha is None or captcha.is_valid()) and form.is_valid():
            email_user = form.cleaned_data['email_user']
            if email_user and email_user != request.user:
                AuditLog.objects.create(
                    form.cleaned_data['email_user'], request, 'connect'
                )
                return fake_email_sent(request)
            store_userid(request)
            return social_complete(request, 'email')
    else:
        form = EmailForm()
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request)

    return render(
        request,
        'accounts/email.html',
        {'title': _('Register e-mail'), 'form': form, 'captcha_form': captcha},
    )


@login_required
@session_ratelimit_post('password')
@never_cache
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
            # Clear flag forcing user to set password
            redirect_page = '#account'
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
        {'title': _('Change password'), 'change_form': change_form, 'form': form},
    )


def reset_password_set(request):
    """Perform actual password reset."""
    user = User.objects.get(pk=request.session['perform_reset'])
    if user.has_usable_password():
        request.session.flush()
        request.session.set_expiry(None)
        messages.error(request, _('Password reset has been already completed!'))
        return redirect('login')
    if request.method == 'POST':
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            request.session.set_expiry(None)
            form.save(request, delete_session=True)
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
        },
    )


@never_cache
def reset_password(request):
    """Password reset handling."""
    if request.user.is_authenticated:
        redirect_profile()
    if 'email' not in load_backends(social_django.utils.BACKENDS).keys():
        messages.error(
            request, _('Cannot reset password, e-mail authentication is turned off.')
        )
        return redirect('login')

    captcha = None

    # We're already in the reset phase
    if 'perform_reset' in request.session:
        return reset_password_set(request)
    if request.method == 'POST':
        form = ResetForm(request.POST)
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request, form, request.POST)
        if (captcha is None or captcha.is_valid()) and form.is_valid():
            if form.cleaned_data['email_user']:
                audit = AuditLog.objects.create(
                    form.cleaned_data['email_user'], request, 'reset-request'
                )
                if not audit.check_rate_limit(request):
                    store_userid(request, True)
                    return social_complete(request, 'email')
            return fake_email_sent(request, True)
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
        },
    )


@require_POST
@login_required
@session_ratelimit_post('reset_api')
def reset_api_key(request):
    """Reset user API key"""
    # Need to delete old token as key is primary key
    with transaction.atomic():
        Token.objects.filter(user=request.user).delete()
        Token.objects.create(user=request.user, key=get_random_string(40))

    return redirect_profile('#api')


@require_POST
@login_required
@session_ratelimit_post('userdata')
def userdata(request):
    response = JsonResponse(request.user.profile.dump_data())
    response['Content-Disposition'] = 'attachment; filename="weblate.json"'
    return response


@require_POST
@login_required
def watch(request, project):
    obj = get_project(request, project)
    request.user.profile.watched.add(obj)
    return redirect(obj)


@require_POST
@login_required
def unwatch(request, project):
    obj = get_project(request, project)
    request.user.profile.watched.remove(obj)
    request.user.subscription_set.filter(
        Q(project=obj) | Q(component__project=obj)
    ).delete()
    return redirect(obj)


def mute_real(user, **kwargs):
    for notification_cls in NOTIFICATIONS:
        if notification_cls.ignore_watched:
            continue
        subscription = user.subscription_set.get_or_create(
            notification=notification_cls.get_name(),
            defaults={'frequency': FREQ_NONE},
            **kwargs
        )[0]
        if subscription.frequency != FREQ_NONE:
            subscription.frequency = FREQ_NONE
            subscription.save(update_fields=['frequency'])


@require_POST
@login_required
def mute_component(request, project, component):
    obj = get_component(request, project, component)
    mute_real(request.user, scope=SCOPE_COMPONENT, component=obj, project=None)
    return redirect(
        '{}?notify_component={}#notifications'.format(reverse('profile'), obj.pk)
    )


@require_POST
@login_required
def mute_project(request, project):
    obj = get_project(request, project)
    mute_real(request.user, scope=SCOPE_PROJECT, component=None, project=obj)
    return redirect(
        '{}?notify_project={}#notifications'.format(reverse('profile'), obj.pk)
    )


class SuggestionView(ListView):
    paginate_by = 25
    model = Suggestion

    def get_queryset(self):
        if self.kwargs['user'] == '-':
            user = None
        else:
            user = get_object_or_404(User, username=self.kwargs['user'])
        return Suggestion.objects.filter(
            user=user, project__in=self.request.user.allowed_projects
        ).order()

    def get_context_data(self):
        result = super(SuggestionView, self).get_context_data()
        if self.kwargs['user'] == '-':
            user = User.objects.get(username=settings.ANONYMOUS_USER_NAME)
        else:
            user = get_object_or_404(User, username=self.kwargs['user'])
        result['page_user'] = user
        result['page_profile'] = user.profile
        return result


def store_userid(request, reset=False, remove=False, invite=False):
    """Store user ID in the session."""
    request.session['social_auth_user'] = request.user.pk
    request.session['password_reset'] = reset
    request.session['account_remove'] = remove
    request.session['user_invite'] = invite


@require_POST
@login_required
def social_disconnect(request, backend, association_id=None):
    """Wrapper around social_django.views.disconnect.

    - Requires POST (to avoid CSRF on auth)
    - Blocks disconnecting last entry
    """
    if request.user.social_auth.count() <= 1:
        messages.error(request, _('Could not remove user identity'))
        return redirect_profile('#account')
    return disconnect(request, backend, association_id)


@require_POST
def social_auth(request, backend):
    """Wrapper around social_django.views.auth.

    - Requires POST (to avoid CSRF on auth)
    - Stores current user in session (to avoid CSRF upon completion)
    """
    store_userid(request)
    return auth(request, backend)


def auth_fail(request, message):
    messages.error(request, message)
    return redirect(reverse('login'))


def auth_redirect_token(request):
    return auth_fail(
        request,
        _(
            'Could not verify your registration! '
            'The verification token has probably expired. '
            'Please try to register again.'
        ),
    )


def auth_redirect_state(request):
    return auth_fail(request, _('Could not authenticate due to invalid session state.'))


def handle_missing_parameter(request, backend, error):
    report_error(error, request)
    if backend != 'email' and error.parameter == 'email':
        return auth_fail(
            request,
            _('Got no e-mail address from third party authentication service.')
            + ' '
            + _('Please register using e-mail instead.'),
        )
    if error.parameter in ('email', 'user', 'expires'):
        return auth_redirect_token(request)
    if error.parameter in ('state', 'code'):
        return auth_redirect_state(request)
    if error.parameter == 'disabled':
        return auth_fail(request, _('New registrations are turned off.'))
    return None


@csrf_exempt
@never_cache
def social_complete(request, backend):
    """Wrapper around social_django.views.complete.

    - Handles backend errors gracefully
    - Intermediate page (autosubmitted by javascript) to avoid
      confirmations by bots
    """
    if (
        'partial_token' in request.GET
        and 'verification_code' in request.GET
        and 'confirm' not in request.GET
    ):
        return render(
            request,
            'accounts/token.html',
            {
                'partial_token': request.GET['partial_token'],
                'verification_code': request.GET['verification_code'],
                'backend': backend,
            },
        )
    try:
        return complete(request, backend)
    except InvalidEmail:
        return auth_redirect_token(request)
    except AuthMissingParameter as error:
        result = handle_missing_parameter(request, backend, error)
        if result:
            return result
        raise
    except (AuthStateMissing, AuthStateForbidden) as error:
        report_error(error, request)
        return auth_redirect_state(request)
    except AuthFailed as error:
        report_error(error, request)
        return auth_fail(
            request,
            _(
                'Could not authenticate, probably due to an expired token '
                'or connection error.'
            ),
        )
    except AuthCanceled:
        return auth_fail(request, _('Authentication cancelled.'))
    except AuthForbidden as error:
        report_error(error, request)
        return auth_fail(request, _('The server does not allow authentication.'))
    except AuthAlreadyAssociated:
        return auth_fail(
            request,
            _(
                'Could not complete registration. The supplied authentication, '
                'e-mail or username is already in use for another account.'
            ),
        )


def unsubscribe(request):
    if 'i' in request.GET:
        signer = TimestampSigner()
        try:
            subscription = Subscription.objects.get(
                pk=int(signer.unsign(request.GET['i'], max_age=24 * 3600))
            )
            subscription.frequency = FREQ_NONE
            subscription.save(update_fields=['frequency'])
            messages.success(request, _('Notification settings adjusted.'))
        except (BadSignature, SignatureExpired, Subscription.DoesNotExist):
            messages.error(
                request,
                _(
                    'The notification change link is no longer valid, '
                    'please log in to configure notifications.'
                ),
            )

    return redirect_profile('#notifications')
