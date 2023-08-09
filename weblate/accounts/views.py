# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import timedelta
from importlib import import_module

import social_django.utils
from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.mail.message import EmailMultiAlternatives
from django.core.signing import (
    BadSignature,
    SignatureExpired,
    TimestampSigner,
    dumps,
    loads,
)
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.http.response import HttpResponseServerError
from django.middleware.csrf import rotate_token
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_response_headers
from django.utils.decorators import method_decorator
from django.utils.http import urlencode
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import ListView, TemplateView, UpdateView
from rest_framework.authtoken.models import Token
from social_core.actions import do_auth
from social_core.backends.open_id import OpenIdAuth
from social_core.exceptions import (
    AuthAlreadyAssociated,
    AuthCanceled,
    AuthFailed,
    AuthForbidden,
    AuthMissingParameter,
    AuthStateForbidden,
    AuthStateMissing,
    InvalidEmail,
    MissingBackend,
)
from social_django.utils import load_backend, load_strategy
from social_django.views import complete, disconnect

from weblate.accounts.avatar import get_avatar_image, get_fallback_avatar_url
from weblate.accounts.forms import (
    CaptchaForm,
    CommitForm,
    ContactForm,
    DashboardSettingsForm,
    EmailForm,
    EmptyConfirmForm,
    GroupAddForm,
    GroupRemoveForm,
    LanguagesForm,
    LoginForm,
    NotificationForm,
    PasswordConfirmForm,
    ProfileForm,
    RegistrationForm,
    ResetForm,
    SetPasswordForm,
    SubscriptionForm,
    UserForm,
    UserSearchForm,
    UserSettingsForm,
)
from weblate.accounts.models import AuditLog, Subscription, VerifiedEmail
from weblate.accounts.notifications import (
    FREQ_INSTANT,
    FREQ_NONE,
    NOTIFICATIONS,
    SCOPE_ADMIN,
    SCOPE_ALL,
    SCOPE_COMPONENT,
    SCOPE_PROJECT,
    SCOPE_WATCHED,
    send_notification_email,
)
from weblate.accounts.pipeline import EmailAlreadyAssociated, UsernameAlreadyAssociated
from weblate.accounts.utils import remove_user
from weblate.auth.forms import UserEditForm
from weblate.auth.models import Invitation, User, get_auth_keys
from weblate.auth.utils import format_address
from weblate.logger import LOGGER
from weblate.trans.models import Change, Component, Project, Suggestion, Translation
from weblate.trans.models.component import translation_prefetch_tasks
from weblate.trans.models.project import prefetch_project_flags
from weblate.utils import messages
from weblate.utils.errors import add_breadcrumb, report_error
from weblate.utils.ratelimit import check_rate_limit, session_ratelimit_post
from weblate.utils.request import get_ip_address, get_user_agent
from weblate.utils.stats import prefetch_stats
from weblate.utils.token import get_token
from weblate.utils.views import get_paginator, parse_path

CONTACT_TEMPLATE = """
Message from %(name)s <%(email)s>:

%(message)s
"""


MESSAGE_TEMPLATE = """
{message}

--
User: {username}
IP address: {address}
User agent: {agent}
"""

CONTACT_SUBJECTS = {
    "lang": "New language request",
    "reg": "Registration problems",
    "hosting": "Commercial hosting",
    "account": "Suspicious account activity",
    "trial": "Trial extension request",
}

ANCHOR_RE = re.compile(r"^#[a-z]+$")

NOTIFICATION_PREFIX_TEMPLATE = "notifications__{}"


class EmailSentView(TemplateView):
    r"""Class for rendering "E-mail sent" page."""

    template_name = "accounts/email-sent.html"

    def get_context_data(self, **kwargs):
        """Create context for rendering page."""
        context = super().get_context_data(**kwargs)
        context["validity"] = settings.AUTH_TOKEN_VALID // 3600
        context["is_reset"] = False
        context["is_remove"] = False
        if self.request.flags["password_reset"]:
            context["title"] = gettext("Password reset")
            context["is_reset"] = True
        elif self.request.flags["account_remove"]:
            context["title"] = gettext("Remove account")
            context["is_remove"] = True
        else:
            context["title"] = gettext("User registration")

        return context

    def get(self, request, *args, **kwargs):
        if not request.session.get("registration-email-sent"):
            return redirect("home")

        request.flags = {
            "password_reset": request.session["password_reset"],
            "account_remove": request.session["account_remove"],
        }

        # Remove session for not authenticated user here.
        # It is no longer needed and will just cause problems
        # with multiple registrations from single browser.
        if not request.user.is_authenticated:
            request.session.flush()
        else:
            request.session.pop("registration-email-sent")

        return super().get(request, *args, **kwargs)


def mail_admins_contact(request, subject, message, context, sender, to):
    """Send a message to the admins, as defined by the ADMINS setting."""
    LOGGER.info("contact form from %s", sender)
    if not to and settings.ADMINS:
        to = [a[1] for a in settings.ADMINS]
    elif not settings.ADMINS:
        messages.error(request, gettext("Could not send message to administrator."))
        LOGGER.error("ADMINS not configured, cannot send message")
        return

    if settings.CONTACT_FORM == "reply-to":
        kwargs = {"headers": {"Reply-To": sender}}
    else:
        kwargs = {"from_email": sender}

    mail = EmailMultiAlternatives(
        subject=f"{settings.EMAIL_SUBJECT_PREFIX}{subject % context}",
        body=MESSAGE_TEMPLATE.format(
            message=message % context,
            address=get_ip_address(request),
            agent=get_user_agent(request),
            username=request.user.username,
        ),
        to=to,
        **kwargs,
    )

    mail.send(fail_silently=False)

    messages.success(
        request, gettext("Your request has been sent, you will shortly hear from us.")
    )


def redirect_profile(page=""):
    url = reverse("profile")
    if page and ANCHOR_RE.match(page):
        url = url + page
    return HttpResponseRedirect(url)


def get_notification_forms(request):
    user = request.user
    if request.method == "POST":
        for i in range(200):
            prefix = NOTIFICATION_PREFIX_TEMPLATE.format(i)
            if prefix + "-scope" in request.POST:
                yield NotificationForm(
                    request.user, i > 1, {}, i == 0, prefix=prefix, data=request.POST
                )
    else:
        subscriptions = defaultdict(dict)
        initials = {}

        # Ensure watched, admin and all scopes are visible
        for needed in (SCOPE_WATCHED, SCOPE_ADMIN, SCOPE_ALL):
            key = (needed, -1, -1)
            subscriptions[key] = {}
            initials[key] = {"scope": needed, "project": None, "component": None}
        active = (SCOPE_WATCHED, -1, -1)

        # Include additional scopes from request
        if "notify_project" in request.GET:
            try:
                project = user.allowed_projects.get(pk=request.GET["notify_project"])
                active = key = (SCOPE_PROJECT, project.pk, -1)
                subscriptions[key] = {}
                initials[key] = {
                    "scope": SCOPE_PROJECT,
                    "project": project,
                    "component": None,
                }
            except (ObjectDoesNotExist, ValueError):
                pass
        if "notify_component" in request.GET:
            try:
                component = Component.objects.filter_access(user).get(
                    pk=request.GET["notify_component"],
                )
                active = key = (SCOPE_COMPONENT, -1, component.pk)
                subscriptions[key] = {}
                initials[key] = {
                    "scope": SCOPE_COMPONENT,
                    "component": component,
                }
            except (ObjectDoesNotExist, ValueError):
                pass

        # Populate scopes from the database
        for subscription in user.subscription_set.select_related(
            "project", "component"
        ):
            key = (
                subscription.scope,
                subscription.project_id or -1,
                subscription.component_id or -1,
            )
            subscriptions[key][subscription.notification] = subscription.frequency
            initials[key] = {
                "scope": subscription.scope,
                "project": subscription.project,
                "component": subscription.component,
            }

        # Generate forms
        for i, details in enumerate(sorted(subscriptions.items())):
            yield NotificationForm(
                user,
                i > 1,
                details[1],
                details[0] == active,
                initial=initials[details[0]],
                prefix=NOTIFICATION_PREFIX_TEMPLATE.format(i),
            )


@never_cache
@login_required
def user_profile(request):
    user = request.user
    profile = user.profile
    profile.fixup_profile(request)

    form_classes = [
        LanguagesForm,
        SubscriptionForm,
        UserSettingsForm,
        DashboardSettingsForm,
        ProfileForm,
        CommitForm,
        UserForm,
    ]
    forms = [form.from_request(request) for form in form_classes]
    forms.extend(get_notification_forms(request))
    all_backends = get_auth_keys()

    if request.method == "POST":
        if all(form.is_valid() for form in forms):
            # Save changes
            for form in forms:
                if hasattr(form, "audit"):
                    form.audit(request)
                form.save()

            messages.success(request, gettext("Your profile has been updated."))

            # Redirect after saving (and possibly changing language)
            return redirect_profile(request.POST.get("activetab"))
    elif not user.has_usable_password() and "email" in all_backends:
        messages.warning(request, render_to_string("accounts/password-warning.html"))

    social = user.social_auth.all()
    social_names = [assoc.provider for assoc in social]
    new_backends = [
        x for x in sorted(all_backends) if x == "email" or x not in social_names
    ]
    user_translation_ids = set(
        Change.objects.filter(
            user=user, timestamp__gte=timezone.now() - timedelta(days=90)
        ).values_list("translation", flat=True)
    )
    license_components = (
        Component.objects.filter_access(user)
        .filter(translation__id__in=user_translation_ids)
        .exclude(license="")
        .prefetch(alerts=False)
        .order_by("license")
    )

    return render(
        request,
        "accounts/profile.html",
        {
            "languagesform": forms[0],
            "subscriptionform": forms[1],
            "usersettingsform": forms[2],
            "dashboardsettingsform": forms[3],
            "profileform": forms[4],
            "commitform": forms[5],
            "userform": forms[6],
            "notification_forms": forms[7:],
            "all_forms": forms,
            "user_groups": user.groups.prefetch_related(
                "roles", "projects", "languages", "components"
            ),
            "profile": profile,
            "title": gettext("User profile"),
            "licenses": license_components,
            "associated": social,
            "new_backends": new_backends,
            "has_email_auth": "email" in all_backends,
            "auditlog": user.auditlog_set.order()[:20],
        },
    )


@login_required
@session_ratelimit_post("remove")
@never_cache
def user_remove(request):
    is_confirmation = "remove_confirm" in request.session
    if is_confirmation:
        if request.method == "POST":
            remove_user(request.user, request)
            rotate_token(request)
            logout(request)
            messages.success(request, gettext("Your account has been removed."))
            return redirect("home")
        confirm_form = EmptyConfirmForm(request)

    elif request.method == "POST":
        confirm_form = PasswordConfirmForm(request, request.POST)
        if confirm_form.is_valid():
            store_userid(request, remove=True)
            request.GET = {"email": request.user.email}
            return social_complete(request, "email")
    else:
        confirm_form = PasswordConfirmForm(request)

    return render(
        request,
        "accounts/removal.html",
        {"confirm_form": confirm_form, "is_confirmation": is_confirmation},
    )


@session_ratelimit_post("confirm")
@never_cache
def confirm(request):
    details = request.session.get("reauthenticate")
    if not details:
        return redirect("home")

    if request.method == "POST":
        confirm_form = PasswordConfirmForm(
            request, request.POST, user=User.objects.get(pk=details["user_pk"])
        )
        if confirm_form.is_valid():
            request.session.pop("reauthenticate")
            request.session["reauthenticate_done"] = True
            return redirect("social:complete", backend=details["backend"])
    else:
        confirm_form = PasswordConfirmForm(request)

    context = {"confirm_form": confirm_form}
    context.update(details)

    return render(request, "accounts/confirm.html", context)


def get_initial_contact(request):
    """Fill in initial contact form fields from request."""
    initial = {}
    if request.user.is_authenticated:
        initial["name"] = request.user.full_name
        initial["email"] = request.user.email
    return initial


@never_cache
def contact(request):
    captcha = None
    show_captcha = settings.REGISTRATION_CAPTCHA and not request.user.is_authenticated

    if request.method == "POST":
        form = ContactForm(request.POST)
        if show_captcha:
            captcha = CaptchaForm(request, form, request.POST)
        if not check_rate_limit("message", request):
            messages.error(
                request, gettext("Too many messages sent, please try again later.")
            )
        elif (captcha is None or captcha.is_valid()) and form.is_valid():
            mail_admins_contact(
                request,
                "%(subject)s",
                CONTACT_TEMPLATE,
                form.cleaned_data,
                format_address(form.cleaned_data["name"], form.cleaned_data["email"]),
                settings.ADMINS_CONTACT,
            )
            return redirect("home")
    else:
        initial = get_initial_contact(request)
        if request.GET.get("t") in CONTACT_SUBJECTS:
            initial["subject"] = CONTACT_SUBJECTS[request.GET["t"]]
        form = ContactForm(initial=initial)
        if show_captcha:
            captcha = CaptchaForm(request)

    return render(
        request,
        "accounts/contact.html",
        {"form": form, "captcha_form": captcha, "title": gettext("Contact")},
    )


@login_required
@session_ratelimit_post("hosting")
@never_cache
def hosting(request):
    """Form for hosting request."""
    if not settings.OFFER_HOSTING:
        return redirect("home")

    from weblate.billing.models import Billing

    billings = (
        Billing.objects.for_user(request.user)
        .filter(state=Billing.STATE_TRIAL)
        .order_by("-payment", "expiry")
    )

    return render(
        request,
        "accounts/hosting.html",
        {
            "title": gettext("Hosting"),
            "billings": billings,
        },
    )


@login_required
@session_ratelimit_post("trial")
@never_cache
def trial(request):
    """Form for hosting request."""
    if not settings.OFFER_HOSTING:
        return redirect("home")

    plan = request.POST.get("plan", "enterprise")

    # Avoid frequent requests for a trial for same user
    if plan != "libre" and request.user.auditlog_set.filter(activity="trial").exists():
        messages.error(
            request,
            gettext(
                "Seems you've already requested a trial period recently. "
                "Please contact us with your inquiry so we can find the "
                "best solution for you."
            ),
        )
        return redirect(reverse("contact") + "?t=trial")

    if request.method == "POST":
        from weblate.billing.models import Billing, Plan

        AuditLog.objects.create(request.user, request, "trial")
        billing = Billing.objects.create(
            plan=Plan.objects.get(slug=plan),
            state=Billing.STATE_TRIAL,
            expiry=timezone.now() + timedelta(days=14),
        )
        billing.owners.add(request.user)
        messages.info(
            request,
            gettext(
                "Your trial period is now up and running; "
                "create your translation project and start Weblating!"
            ),
        )
        return redirect(reverse("create-project") + f"?billing={billing.pk}")

    return render(request, "accounts/trial.html", {"title": gettext("Gratis trial")})


class UserPage(UpdateView):
    model = User
    template_name = "accounts/user.html"
    slug_field = "username"
    slug_url_kwarg = "user"
    context_object_name = "page_user"
    form_class = UserEditForm

    group_form = None

    def post(self, request, **kwargs):
        if not request.user.has_perm("user.edit"):
            raise PermissionDenied
        user = self.object = self.get_object()
        if "add_group" in request.POST:
            self.group_form = GroupAddForm(request.POST)
            if self.group_form.is_valid():
                user.groups.add(self.group_form.cleaned_data["add_group"])
                return HttpResponseRedirect(self.get_success_url() + "#groups")
        if "remove_group" in request.POST:
            form = GroupRemoveForm(request.POST)
            if form.is_valid():
                user.groups.remove(form.cleaned_data["remove_group"])
                return HttpResponseRedirect(self.get_success_url() + "#groups")
        if "remove_user" in request.POST:
            remove_user(user, request)
            return HttpResponseRedirect(self.get_success_url() + "#groups")

        return super().post(request, **kwargs)

    def form_valid(self, form):
        """If the form is valid, save the associated model."""
        self.object = form.save(self.request)
        return HttpResponseRedirect(self.get_success_url())

    def get_queryset(self):
        return super().get_queryset().select_related("profile")

    def get_context_data(self, **kwargs):
        """Create context for rendering page."""
        context = super().get_context_data(**kwargs)
        user = self.object
        request = self.request

        allowed_projects = request.user.allowed_projects

        # Filter all user activity
        all_changes = Change.objects.last_changes(request.user).filter(user=user)

        # Last user activity
        last_changes = all_changes[:10]

        # Filter where project is active
        user_translation_ids = set(
            all_changes.filter(
                timestamp__gte=timezone.now() - timedelta(days=90)
            ).values_list("translation", flat=True)
        )
        user_translations = (
            Translation.objects.prefetch()
            .filter(
                id__in=list(user_translation_ids)[:10],
                component__project__in=allowed_projects,
            )
            .order()
        )

        context["page_profile"] = user.profile
        context["last_changes"] = last_changes.preload()
        context["last_changes_url"] = urlencode({"user": user.username})
        context["page_user_translations"] = translation_prefetch_tasks(
            prefetch_stats(user_translations)
        )
        owned = (user.owned_projects & allowed_projects.distinct()).order()[:11]
        context["page_owned_projects_more"] = len(owned) == 11
        context["page_owned_projects"] = prefetch_project_flags(
            prefetch_stats(owned[:10])
        )
        watched = (user.watched_projects & allowed_projects).order()[:11]
        context["page_watched_projects_more"] = len(watched) == 11
        context["page_watched_projects"] = prefetch_project_flags(
            prefetch_stats(watched[:10])
        )
        context["user_languages"] = user.profile.all_languages[:7]
        context["group_form"] = self.group_form or GroupAddForm()
        context["page_user_groups"] = (
            user.groups.annotate(Count("user"))
            .prefetch_related("defining_project")
            .order()
        )
        return context


def user_contributions(request, user: str):
    user = get_object_or_404(User, username=user)
    user_translation_ids = set(
        Change.objects.filter(user=user).values_list("translation", flat=True)
    )
    user_translations = (
        Translation.objects.filter_access(request.user)
        .prefetch()
        .filter(
            id__in=user_translation_ids,
        )
        .order()
    )
    return render(
        request,
        "accounts/user_contributions.html",
        {
            "page_user": user,
            "page_profile": user.profile,
            "page_user_translations": translation_prefetch_tasks(
                prefetch_stats(get_paginator(request, user_translations))
            ),
        },
    )


def user_avatar(request, user: str, size: int):
    """User avatar view."""
    allowed_sizes = (
        # Used in top navigation
        24,
        # In text avatars
        32,
        # 80 pixels used when linked with weblate.org
        80,
        # Public profile
        128,
    )
    if size not in allowed_sizes:
        raise Http404(f"Not supported size: {size}")

    user = get_object_or_404(User, username=user)

    if user.email == "noreply@weblate.org":
        return redirect(get_fallback_avatar_url(size))
    if user.email == f"noreply+{user.pk}@weblate.org":
        return redirect(os.path.join(settings.STATIC_URL, "state/ghost.svg"))

    response = HttpResponse(
        content_type="image/png", content=get_avatar_image(user, size)
    )

    patch_response_headers(response, 3600 * 24 * 7)

    return response


def redirect_single(request, backend):
    """Redirect user to single authentication backend."""
    return render(
        request,
        "accounts/redirect.html",
        {"backend": backend, "next": request.GET.get("next")},
    )


class WeblateLoginView(LoginView):
    """Login handler, just a wrapper around standard Django login."""

    form_class = LoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        auth_backends = get_auth_keys()
        context["login_backends"] = [x for x in sorted(auth_backends) if x != "email"]
        context["can_reset"] = "email" in auth_backends
        context["title"] = gettext("Sign in")
        return context

    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        # Redirect signed in users to profile
        if request.user.is_authenticated:
            return redirect_profile()

        # Redirect if there is only one backend
        auth_backends = get_auth_keys()
        if len(auth_backends) == 1 and "email" not in auth_backends:
            return redirect_single(request, auth_backends.pop())

        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        rotate_token(self.request)
        return super().form_invalid(form)


class WeblateLogoutView(LogoutView):
    """Logout handler, just a wrapper around standard Django logout."""

    next_page = "home"

    @method_decorator(require_POST)
    @method_decorator(login_required)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        messages.info(self.request, gettext("Thank you for using Weblate."))
        return super().dispatch(request, *args, **kwargs)


def fake_email_sent(request, reset=False):
    """Fake redirect to e-mail sent page."""
    request.session["registration-email-sent"] = True
    request.session["password_reset"] = reset
    request.session["account_remove"] = False
    return redirect("email-sent")


@never_cache
def register(request):
    """Registration form."""
    captcha = None

    # Fetch invitation
    invitation = None
    initial = {}
    if invitation_pk := request.session.get("invitation_link"):
        try:
            invitation = Invitation.objects.get(pk=invitation_pk)
        except Invitation.DoesNotExist:
            del request.session["invitation_link"]
        else:
            initial["email"] = invitation.email

    # Allow registration at all?
    registration_open = settings.REGISTRATION_OPEN or bool(invitation)

    # Get list of allowed backends
    backends = get_auth_keys()
    if settings.REGISTRATION_ALLOW_BACKENDS and not invitation:
        backends = backends & set(settings.REGISTRATION_ALLOW_BACKENDS)
    elif not registration_open:
        backends = set()

    if request.method == "POST" and "email" in backends:
        form = RegistrationForm(request, request.POST)
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request, form, request.POST)
        if (captcha is None or captcha.is_valid()) and form.is_valid():
            if captcha:
                captcha.cleanup_session(request)
            if form.cleaned_data["email_user"]:
                AuditLog.objects.create(
                    form.cleaned_data["email_user"], request, "connect"
                )
                return fake_email_sent(request)
            store_userid(request)
            return social_complete(request, "email")
    else:
        form = RegistrationForm(request, initial=initial)
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request)

    # Redirect if there is only one backend
    if len(backends) == 1 and "email" not in backends and not invitation:
        return redirect_single(request, backends.pop())

    return render(
        request,
        "accounts/register.html",
        {
            "registration_email": "email" in backends,
            "registration_backends": backends - {"email"},
            "title": gettext("User registration"),
            "form": form,
            "captcha_form": captcha,
            "invitation": invitation,
        },
    )


@login_required
@never_cache
def email_login(request):
    """Connect e-mail."""
    captcha = None

    if request.method == "POST":
        form = EmailForm(request.POST)
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request, form, request.POST)
        if (captcha is None or captcha.is_valid()) and form.is_valid():
            if captcha:
                captcha.cleanup_session(request)
            email_user = form.cleaned_data["email_user"]
            if email_user and email_user != request.user:
                AuditLog.objects.create(
                    form.cleaned_data["email_user"], request, "connect"
                )
                return fake_email_sent(request)
            store_userid(request)
            return social_complete(request, "email")
    else:
        form = EmailForm()
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request)

    return render(
        request,
        "accounts/email.html",
        {"title": gettext("Register e-mail"), "form": form, "captcha_form": captcha},
    )


@login_required
@session_ratelimit_post("password")
@never_cache
def password(request):
    """Password change / set form."""
    do_change = True
    change_form = None
    usable = request.user.has_usable_password()

    if "email" not in get_auth_keys() and not usable:
        messages.error(
            request,
            gettext("Cannot reset password, e-mail authentication is turned off."),
        )
        return redirect("profile")

    if usable:
        if request.method == "POST":
            change_form = PasswordConfirmForm(request, request.POST)
            do_change = change_form.is_valid()
        else:
            change_form = PasswordConfirmForm(request)
            do_change = False

    if request.method == "POST":
        form = SetPasswordForm(request.user, request.POST)
        if form.is_valid() and do_change:
            # Clear flag forcing user to set password
            redirect_page = "#account"
            if "show_set_password" in request.session:
                del request.session["show_set_password"]
                redirect_page = ""

            # Change the password
            form.save(request)

            return redirect_profile(redirect_page)
    else:
        form = SetPasswordForm(request.user)

    return render(
        request,
        "accounts/password.html",
        {"title": gettext("Change password"), "change_form": change_form, "form": form},
    )


def reset_password_set(request):
    """Perform actual password reset."""
    user = User.objects.get(pk=request.session["perform_reset"])
    if user.has_usable_password():
        request.session.flush()
        request.session.set_expiry(None)
        messages.error(request, gettext("Password reset has been already completed."))
        return redirect("login")
    if request.method == "POST":
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            request.session.set_expiry(None)
            form.save(request, delete_session=True)
            return redirect("login")
    else:
        form = SetPasswordForm(user)
    return render(
        request,
        "accounts/reset.html",
        {
            "title": gettext("Password reset"),
            "form": form,
            "captcha_form": None,
            "second_stage": True,
        },
    )


def get_registration_hint(email: str) -> str | None:
    domain = email.rsplit("@", 1)[-1]
    return settings.REGISTRATION_HINTS.get(domain)


@never_cache
def reset_password(request):
    """Password reset handling."""
    if request.user.is_authenticated:
        return redirect_profile()
    if "email" not in get_auth_keys():
        messages.error(
            request,
            gettext("Cannot reset password, e-mail authentication is turned off."),
        )
        return redirect("login")

    captcha = None

    # We're already in the reset phase
    if "perform_reset" in request.session:
        return reset_password_set(request)
    if request.method == "POST":
        form = ResetForm(request.POST)
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request, form, request.POST)
        if (captcha is None or captcha.is_valid()) and form.is_valid():
            if captcha:
                captcha.cleanup_session(request)
            if form.cleaned_data["email_user"]:
                audit = AuditLog.objects.create(
                    form.cleaned_data["email_user"], request, "reset-request"
                )
                if not audit.check_rate_limit(request):
                    store_userid(request, reset=True)
                    return social_complete(request, "email")
            else:
                email = form.cleaned_data["email"]
                send_notification_email(
                    None,
                    [email],
                    "reset-nonexisting",
                    context={
                        "address": get_ip_address(request),
                        "user_agent:": get_user_agent(request),
                        "registration_hint": get_registration_hint(email),
                    },
                )
            return fake_email_sent(request, True)
    else:
        form = ResetForm()
        if settings.REGISTRATION_CAPTCHA:
            captcha = CaptchaForm(request)

    return render(
        request,
        "accounts/reset.html",
        {
            "title": gettext("Password reset"),
            "form": form,
            "captcha_form": captcha,
            "second_stage": False,
        },
    )


@require_POST
@login_required
@session_ratelimit_post("reset_api")
def reset_api_key(request):
    """Reset user API key."""
    # Need to delete old token as key is primary key
    with transaction.atomic():
        Token.objects.filter(user=request.user).delete()
        Token.objects.create(user=request.user, key=get_token("wlu"))

    return redirect_profile("#api")


@require_POST
@login_required
@session_ratelimit_post("userdata")
def userdata(request):
    response = JsonResponse(request.user.profile.dump_data())
    response["Content-Disposition"] = 'attachment; filename="weblate.json"'
    return response


@require_POST
@login_required
def watch(request, path):
    user = request.user
    redirect_obj = obj = parse_path(request, path, (Component, Project))
    if isinstance(obj, Component):
        project = obj.project

        # Mute project level subscriptions
        mute_real(user, scope=SCOPE_PROJECT, component=None, project=project)
        # Manually enable component level subscriptions
        for default_subscription in user.subscription_set.filter(scope=SCOPE_WATCHED):
            subscription, created = user.subscription_set.get_or_create(
                notification=default_subscription.notification,
                scope=SCOPE_COMPONENT,
                component=obj,
                project=None,
                defaults={"frequency": default_subscription.frequency},
            )
            if not created and subscription.frequency != default_subscription.frequency:
                subscription.frequency = default_subscription.frequency
                subscription.save(update_fields=["frequency"])

        # Watch project
        obj = project
    user.profile.watched.add(obj)
    return redirect(redirect_obj)


@require_POST
@login_required
def unwatch(request, path):
    obj = parse_path(request, path, (Project,))
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
            defaults={"frequency": FREQ_NONE},
            **kwargs,
        )[0]
        if subscription.frequency != FREQ_NONE:
            subscription.frequency = FREQ_NONE
            subscription.save(update_fields=["frequency"])


@require_POST
@login_required
def mute(request, path):
    obj = parse_path(request, path, (Component, Project))
    if isinstance(obj, Component):
        mute_real(request.user, scope=SCOPE_COMPONENT, component=obj, project=None)
        return redirect(
            "{}?notify_component={}#notifications".format(reverse("profile"), obj.pk)
        )
    mute_real(request.user, scope=SCOPE_PROJECT, component=None, project=obj)
    return redirect(
        "{}?notify_project={}#notifications".format(reverse("profile"), obj.pk)
    )


class SuggestionView(ListView):
    paginate_by = 25
    model = Suggestion

    def get_queryset(self):
        if self.kwargs["user"] == "-":
            user = None
        else:
            user = get_object_or_404(User, username=self.kwargs["user"])
        return (
            Suggestion.objects.filter_access(self.request.user)
            .filter(user=user)
            .order()
        )

    def get_context_data(self, *, object_list=None, **kwargs):
        result = super().get_context_data(object_list=object_list, **kwargs)
        if self.kwargs["user"] == "-":
            user = User.objects.get(username=settings.ANONYMOUS_USER_NAME)
        else:
            user = get_object_or_404(User, username=self.kwargs["user"])
        result["page_user"] = user
        result["page_profile"] = user.profile
        return result


def store_userid(request, *, reset: bool = False, remove: bool = False):
    """Store user ID in the session."""
    request.session["social_auth_user"] = request.user.pk
    request.session["password_reset"] = reset
    request.session["account_remove"] = remove


@require_POST
@login_required
def social_disconnect(request, backend, association_id=None):
    """
    Wrapper around social_django.views.disconnect.

    - Requires POST (to avoid CSRF on auth)
    - Blocks disconnecting last entry
    """
    # Block removal of last social auth
    if request.user.social_auth.count() <= 1:
        messages.error(request, gettext("Could not remove user identity"))
        return redirect_profile("#account")

    # Block removal of last verified email
    verified = VerifiedEmail.objects.filter(social__user=request.user).exclude(
        social__provider=backend, social_id=association_id
    )
    if not verified.exists():
        messages.error(
            request,
            gettext("Add another identity by confirming your e-mail address first."),
        )
        return redirect_profile("#account")

    return disconnect(request, backend, association_id)


@never_cache
@require_POST
def social_auth(request, backend):
    """
    Wrapper around social_django.views.auth.

    - Incorporates modified social_djang.utils.psa
    - Requires POST (to avoid CSRF on auth)
    - Stores current user in session (to avoid CSRF upon completion)
    - Stores session ID in the request URL if needed
    """
    # Fill in idp in case it is not provided
    if backend == "saml" and "idp" not in request.GET:
        request.GET = request.GET.copy()
        request.GET["idp"] = "weblate"
    store_userid(request)
    uri = reverse("social:complete", args=(backend,))
    request.social_strategy = load_strategy(request)
    try:
        request.backend = load_backend(request.social_strategy, backend, uri)
    except MissingBackend:
        raise Http404("Backend not found")
    # Store session ID for OpenID based auth. The session cookies will not be sent
    # on returning POST request due to SameSite cookie policy
    if isinstance(request.backend, OpenIdAuth):
        request.backend.redirect_uri += "?authid={}".format(
            dumps(
                (request.session.session_key, get_ip_address(request)),
                salt="weblate.authid",
            )
        )
    return do_auth(request.backend, redirect_name=REDIRECT_FIELD_NAME)


def auth_fail(request, message):
    messages.error(request, message)
    return redirect(reverse("login"))


def registration_fail(request, message):
    messages.error(request, gettext("Could not complete registration.") + " " + message)
    messages.info(
        request,
        gettext("Please check if you have already registered an account.")
        + " "
        + gettext(
            "You can also request a new password, if you have lost your credentials."
        ),
    )

    return redirect(reverse("login"))


def auth_redirect_token(request):
    return auth_fail(
        request,
        gettext(
            "Try registering again to verify your identity, "
            "the confirmation link probably expired."
        ),
    )


def auth_redirect_state(request):
    return auth_fail(
        request, gettext("Could not authenticate due to invalid session state.")
    )


def handle_missing_parameter(request, backend, error):
    if backend != "email" and error.parameter == "email":
        return auth_fail(
            request,
            gettext("Got no e-mail address from third party authentication service.")
            + " "
            + gettext("Please register using e-mail instead."),
        )
    if error.parameter in ("email", "user", "expires"):
        return auth_redirect_token(request)
    if error.parameter in ("state", "code"):
        return auth_redirect_state(request)
    if error.parameter == "disabled":
        return auth_fail(request, gettext("New registrations are turned off."))
    return None


@csrf_exempt
@never_cache
def social_complete(request, backend):  # noqa: C901
    """
    Wrapper around social_django.views.complete.

    - Handles backend errors gracefully
    - Intermediate page (autosubmitted by JavaScript) to avoid
      confirmations by bots
    - Restores session from authid for some backends (see social_auth)
    """
    if "authid" in request.GET:
        try:
            session_key, ip_address = loads(
                request.GET["authid"], max_age=600, salt="weblate.authid"
            )
        except (BadSignature, SignatureExpired):
            return auth_redirect_token(request)
        if ip_address != get_ip_address(request):
            return auth_redirect_token(request)
        engine = import_module(settings.SESSION_ENGINE)
        request.session = engine.SessionStore(session_key)

    if (
        "partial_token" in request.GET
        and "verification_code" in request.GET
        and "confirm" not in request.GET
    ):
        return render(
            request,
            "accounts/token.html",
            {
                "partial_token": request.GET["partial_token"],
                "verification_code": request.GET["verification_code"],
                "backend": backend,
            },
        )
    try:
        return complete(request, backend)
    except InvalidEmail:
        report_error()
        return auth_redirect_token(request)
    except AuthMissingParameter as error:
        report_error()
        result = handle_missing_parameter(request, backend, error)
        if result:
            return result
        raise
    except (AuthStateMissing, AuthStateForbidden):
        report_error()
        return auth_redirect_state(request)
    except AuthFailed:
        report_error()
        return auth_fail(
            request,
            gettext(
                "Could not authenticate, probably due to an expired token "
                "or connection error."
            ),
        )
    except AuthCanceled:
        report_error()
        return auth_fail(request, gettext("Authentication cancelled."))
    except AuthForbidden:
        report_error()
        return auth_fail(request, gettext("The server does not allow authentication."))
    except EmailAlreadyAssociated:
        return registration_fail(
            request,
            gettext(
                "The supplied e-mail address is already in use for another account."
            ),
        )
    except UsernameAlreadyAssociated:
        return registration_fail(
            request,
            gettext("The supplied username is already in use for another account."),
        )
    except AuthAlreadyAssociated:
        return registration_fail(
            request,
            gettext(
                "The supplied user identity is already in use for another account."
            ),
        )
    except ValidationError as error:
        report_error()
        return registration_fail(request, str(error))


@login_required
@require_POST
def subscribe(request):
    if "onetime" in request.POST:
        component = Component.objects.get(pk=request.POST["component"])
        request.user.check_access_component(component)
        subscription = Subscription(
            user=request.user,
            notification=request.POST["onetime"],
            scope=SCOPE_COMPONENT,
            frequency=FREQ_INSTANT,
            project=component.project,
            component=component,
            onetime=True,
        )
        try:
            subscription.full_clean()
            subscription.save()
        except ValidationError:
            pass
        messages.success(request, gettext("Notification settings adjusted."))
    return redirect_profile("#notifications")


def unsubscribe(request):
    if "i" in request.GET:
        signer = TimestampSigner()
        try:
            subscription = Subscription.objects.get(
                pk=int(signer.unsign(request.GET["i"], max_age=24 * 3600))
            )
            subscription.frequency = FREQ_NONE
            subscription.save(update_fields=["frequency"])
            messages.success(request, gettext("Notification settings adjusted."))
        except (BadSignature, SignatureExpired, Subscription.DoesNotExist):
            messages.error(
                request,
                gettext(
                    "The notification change link is no longer valid, "
                    "please sign in to configure notifications."
                ),
            )

    return redirect_profile("#notifications")


@csrf_exempt
@never_cache
def saml_metadata(request):
    if "social_core.backends.saml.SAMLAuth" not in settings.AUTHENTICATION_BACKENDS:
        raise Http404

    # Generate metadata
    complete_url = reverse("social:complete", args=("saml",))
    saml_backend = social_django.utils.load_backend(
        load_strategy(request), "saml", complete_url
    )
    metadata, errors = saml_backend.generate_metadata_xml()

    # Handle errors
    if errors:
        add_breadcrumb(category="auth", message="SAML errors", errors=errors)
        report_error(level="error", cause="SAML metadata")
        return HttpResponseServerError(content=", ".join(errors))

    return HttpResponse(content=metadata, content_type="text/xml")


class UserList(ListView):
    paginate_by = 50
    model = User
    form_class = UserSearchForm

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_base_queryset(self):
        return User.objects.filter(is_active=True, is_bot=False)

    def get_queryset(self):
        users = self.get_base_queryset()
        form = self.form
        if form.is_valid():
            search = form.cleaned_data.get("q", "")
            if search:
                users = users.search(search, parser=form.fields["q"].parser)
        else:
            users = users.order()

        return users.order_by(self.sort_query)

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.form = form = self.form_class(request.GET)
        self.sort_query = None
        if form.is_valid():
            self.sort_query = form.cleaned_data.get("sort_by")
        if not self.sort_query:
            self.sort_query = "-date_joined"

    def get_context_data(self, **kwargs):
        """Create context for rendering page."""
        context = super().get_context_data(**kwargs)
        context["form"] = self.form
        context["sort_query"] = self.sort_query
        context["sort_name"] = self.form.sort_choices[self.sort_query.strip("-")]
        context["sort_choices"] = self.form.sort_choices
        context["search_items"] = (
            ("q", self.form.cleaned_data.get("q", "").strip()),
            ("sort_by", self.sort_query),
        )
        context["query_string"] = urlencode(context["search_items"])
        return context
