# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import re
from base64 import b32encode
from binascii import unhexlify
from collections import defaultdict
from datetime import timedelta
from importlib import import_module
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import qrcode
import qrcode.image.svg
import social_django.utils
from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, RedirectURLMixin
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.mail.message import EmailMessage
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
from django.utils.functional import cached_property
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import (
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp import login as otp_login
from django_otp.models import Device
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.util import random_hex
from django_otp_webauthn.models import WebAuthnCredential
from django_otp_webauthn.views import (
    BeginCredentialAuthenticationView,
    CompleteCredentialAuthenticationView,
)
from rest_framework.authtoken.models import Token
from social_core.actions import do_auth
from social_core.backends.open_id import OpenIdAuth
from social_core.exceptions import (
    AuthAlreadyAssociated,
    AuthCanceled,
    AuthException,
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
    OTPTokenForm,
    PasswordConfirmForm,
    ProfileBaseForm,
    ProfileForm,
    RegistrationForm,
    ResetForm,
    SetPasswordForm,
    SubscriptionForm,
    TOTPDeviceForm,
    TOTPTokenForm,
    UserForm,
    UserSearchForm,
    UserSettingsForm,
    WebAuthnTokenForm,
)
from weblate.accounts.models import AuditLog, Subscription, VerifiedEmail
from weblate.accounts.notifications import (
    NOTIFICATIONS,
    NotificationFrequency,
    NotificationScope,
    get_email_headers,
    send_notification_email,
)
from weblate.accounts.pipeline import EmailAlreadyAssociated, UsernameAlreadyAssociated
from weblate.accounts.utils import (
    SESSION_SECOND_FACTOR_SOCIAL,
    SESSION_SECOND_FACTOR_TOTP,
    SESSION_SECOND_FACTOR_USER,
    SESSION_WEBAUTHN_AUDIT,
    DeviceType,
    get_key_name,
    lock_user,
    remove_user,
)
from weblate.auth.forms import UserEditForm
from weblate.auth.models import (
    AuthenticatedHttpRequest,
    Invitation,
    User,
    get_anonymous,
    get_auth_keys,
)
from weblate.auth.utils import format_address
from weblate.logger import LOGGER
from weblate.trans.models import Change, Component, Project, Suggestion, Translation
from weblate.trans.models.component import translation_prefetch_tasks
from weblate.trans.models.project import prefetch_project_flags
from weblate.trans.util import redirect_next
from weblate.utils import messages
from weblate.utils.errors import add_breadcrumb, report_error
from weblate.utils.ratelimit import check_rate_limit, session_ratelimit_post
from weblate.utils.request import get_ip_address, get_user_agent
from weblate.utils.stats import prefetch_stats
from weblate.utils.token import get_token
from weblate.utils.views import get_paginator, parse_path
from weblate.utils.zammad import ZammadError, submit_zammad_ticket

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest

AUTHID_SALT = "weblate.authid"
AUTHID_MAX_AGE = 600

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

    do_password_reset: bool
    do_account_remove: bool

    def get_context_data(self, **kwargs):
        """Create context for rendering page."""
        context = super().get_context_data(**kwargs)
        context["validity"] = settings.AUTH_TOKEN_VALID // 3600
        context["is_reset"] = False
        context["is_remove"] = False
        if self.do_password_reset:
            context["title"] = gettext("Password reset")
            context["is_reset"] = True
        elif self.do_account_remove:
            context["title"] = gettext("Remove account")
            context["is_remove"] = True
        else:
            context["title"] = gettext("User registration")

        return context

    def get(self, request: AuthenticatedHttpRequest, *args, **kwargs):  # type: ignore[override]
        if not request.session.get("registration-email-sent"):
            return redirect("home")

        self.do_password_reset = request.session["password_reset"]
        self.do_account_remove = request.session["account_remove"]

        # Remove session for not authenticated user here.
        # It is no longer needed and will just cause problems
        # with multiple registrations from single browser.
        if not request.user.is_authenticated:
            request.session.flush()
        else:
            request.session.pop("registration-email-sent")

        return super().get(request, *args, **kwargs)


def mail_admins_contact(
    request: AuthenticatedHttpRequest,
    *,
    subject: str,
    message: str,
    context: dict[str, Any],
    name: str,
    email: str,
    to: list[str],
) -> None:
    """Send a message to the admins, as defined by the ADMINS setting."""
    LOGGER.info("contact form from %s", email)
    subject = f"{settings.EMAIL_SUBJECT_PREFIX}{subject}"
    body = MESSAGE_TEMPLATE.format(
        message=message % context,
        address=get_ip_address(request),
        agent=get_user_agent(request),
        username=request.user.username,
    )

    if not to and settings.ADMINS:
        to = [a[1] for a in settings.ADMINS]
    elif not settings.ADMINS:
        messages.error(request, gettext("Could not send message to administrator."))
        LOGGER.error("ADMINS not configured, cannot send message")
        return

    if settings.ZAMMAD_URL and len(to) == 1 and to[0].endswith("@weblate.org"):
        try:
            submit_zammad_ticket(
                title=subject,
                body=body,
                name=name,
                email=email,
            )
        except ZammadError as error:
            messages.error(request, str(error))
        except OSError:
            report_error("Could not create ticket")
            messages.error(
                request, gettext("Could not open a ticket, please try again later.")
            )
        else:
            messages.success(
                request,
                gettext("Your request has been sent, you will shortly hear from us."),
            )

    else:
        headers = get_email_headers("contact")
        sender = format_address(name, email)

        if settings.CONTACT_FORM == "reply-to":
            headers["Reply-To"] = sender
            from_email = to[0]
        else:
            from_email = sender

        mail = EmailMessage(
            subject=subject, body=body, to=to, from_email=from_email, headers=headers
        )

        mail.send(fail_silently=False)

        messages.success(
            request,
            gettext("Your request has been sent, you will shortly hear from us."),
        )


def redirect_profile(page: str | None = None):
    url = reverse("profile")
    if page and ANCHOR_RE.match(page):
        url = f"{url}{page}"
    return HttpResponseRedirect(url)


def get_notification_forms(request: AuthenticatedHttpRequest):
    user = request.user
    subscriptions: dict[tuple[NotificationScope, int, int], dict[str, int]] = (
        defaultdict(dict)
    )
    initials: dict[tuple[NotificationScope, int, int], dict[str, Any]] = {}
    key: tuple[NotificationScope, int, int]

    # Ensure watched, admin and all scopes are visible
    for needed in (
        NotificationScope.SCOPE_WATCHED,
        NotificationScope.SCOPE_ADMIN,
        NotificationScope.SCOPE_ALL,
    ):
        key = (needed, -1, -1)
        subscriptions[key] = {}
        initials[key] = {"scope": needed, "project": None, "component": None}
    active = (NotificationScope.SCOPE_WATCHED, -1, -1)

    # Include additional scopes from request
    if "notify_project" in request.GET:
        try:
            project = user.allowed_projects.get(pk=request.GET["notify_project"])
            active = key = (NotificationScope.SCOPE_PROJECT, project.pk, -1)
            subscriptions[key] = {}
            initials[key] = {
                "scope": NotificationScope.SCOPE_PROJECT,
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
            active = key = (NotificationScope.SCOPE_COMPONENT, -1, component.pk)
            subscriptions[key] = {}
            initials[key] = {
                "scope": NotificationScope.SCOPE_COMPONENT,
                "component": component,
            }
        except (ObjectDoesNotExist, ValueError):
            pass

    # Populate scopes from the database
    for subscription in user.subscription_set.select_related("project", "component"):
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
            user=user,
            show_default=i > 1,
            removable=i > 2,
            subscriptions=details[1],
            is_active=details[0] == active,
            initial=initials[details[0]],
            prefix=NOTIFICATION_PREFIX_TEMPLATE.format(i),
            data=request.POST if request.method == "POST" else None,
        )
    for i in range(len(subscriptions), 200):
        prefix = NOTIFICATION_PREFIX_TEMPLATE.format(i)
        if prefix + "-scope" in request.POST or i < len(subscriptions):
            yield NotificationForm(
                user=user,
                show_default=i > 1,
                removable=i > 2,
                subscriptions={},
                is_active=i == 0,
                prefix=prefix,
                data=request.POST,
                initial=initials[details[0]],
            )


@never_cache
@login_required
def user_profile(request: AuthenticatedHttpRequest):
    user = request.user
    profile = user.profile
    profile.fixup_profile(request)

    form_classes: list[type[ProfileBaseForm | UserForm]] = [
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
        .distinct()
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
            "user_groups": user.cached_groups.prefetch_related(
                "roles", "projects", "languages", "components"
            ),
            "profile": profile,
            "title": gettext("User profile"),
            "licenses": license_components,
            "associated": social,
            "new_backends": new_backends,
            "has_email_auth": "email" in all_backends,
            "auditlog": user.auditlog_set.order()[:20],
            "totp_keys": user.totpdevice_set.all(),
            "webauthn_keys": user.webauthncredential_set.all(),
            "recovery_keys_count": StaticToken.objects.filter(
                device__user=user
            ).count(),
        },
    )


@login_required
@session_ratelimit_post("remove")
@never_cache
def user_remove(request: AuthenticatedHttpRequest):
    is_confirmation = "remove_confirm" in request.session
    if is_confirmation:
        if request.method == "POST":
            remove_user(request.user, request)
            rotate_token(request)
            auth_logout(request)
            messages.success(request, gettext("Your account has been removed."))
            return redirect("home")
        confirm_form = EmptyConfirmForm(request)

    elif request.method == "POST":
        confirm_form = PasswordConfirmForm(request, request.POST)
        if confirm_form.is_valid():
            store_userid(request, remove=True)
            request.GET = {"email": request.user.email}  # type: ignore[assignment]
            AuditLog.objects.create(
                request.user, request, "removal-request", **request.GET
            )
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
def confirm(request: AuthenticatedHttpRequest):
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


def get_initial_contact(request: AuthenticatedHttpRequest):
    """Fill in initial contact form fields from request."""
    initial = {}
    if request.user.is_authenticated:
        initial["name"] = request.user.full_name
        initial["email"] = request.user.email
    return initial


@never_cache
def contact(request: AuthenticatedHttpRequest):
    if request.method == "POST":
        form = ContactForm(
            request=request,
            hide_captcha=request.user.is_authenticated,
            data=request.POST,
        )
        if not check_rate_limit("message", request):
            messages.error(
                request, gettext("Too many messages sent, please try again later.")
            )
        elif form.is_valid():
            mail_admins_contact(
                request,
                subject=form.cleaned_data["subject"],
                message=CONTACT_TEMPLATE,
                context=form.cleaned_data,
                name=form.cleaned_data["name"],
                email=form.cleaned_data["email"],
                to=settings.ADMINS_CONTACT,
            )
            return redirect("home")
    else:
        initial = get_initial_contact(request)
        if request.GET.get("t") in CONTACT_SUBJECTS:
            initial["subject"] = CONTACT_SUBJECTS[request.GET["t"]]
        form = ContactForm(
            request=request, hide_captcha=request.user.is_authenticated, initial=initial
        )

    return render(
        request,
        "accounts/contact.html",
        {"form": form, "title": gettext("Contact")},
    )


@login_required
@session_ratelimit_post("hosting")
@never_cache
def hosting(request: AuthenticatedHttpRequest):
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
def trial(request: AuthenticatedHttpRequest):
    """Form for hosting request."""
    if not settings.OFFER_HOSTING:
        return redirect("home")

    plan = request.POST.get("plan", "640k")

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
    request: AuthenticatedHttpRequest

    def post(self, request: AuthenticatedHttpRequest, *args, **kwargs):  # type: ignore[override]
        if not request.user.has_perm("user.edit"):
            raise PermissionDenied
        user = self.object = self.get_object()
        if "add_group" in request.POST:
            self.group_form = GroupAddForm(request.POST)
            if self.group_form.is_valid():
                user.add_team(request, self.group_form.cleaned_data["add_group"])
                return HttpResponseRedirect(self.get_success_url() + "#groups")
        if "remove_group" in request.POST:
            form = GroupRemoveForm(request.POST)
            if form.is_valid():
                user.remove_team(request, form.cleaned_data["remove_group"])
                return HttpResponseRedirect(self.get_success_url() + "#groups")
        if "remove_user" in request.POST:
            remove_user(user, request, skip_notify=True)
            return HttpResponseRedirect(self.get_success_url() + "#groups")

        if "remove_2fa" in request.POST:
            for device in user.profile.second_factors:
                key_name = get_key_name(device)
                device.delete()
                AuditLog.objects.create(user, None, "twofactor-remove", device=key_name)
            return HttpResponseRedirect(self.get_success_url() + "#edit")

        if "disable_password" in request.POST:
            lock_user(user, "admin-locked")
            return HttpResponseRedirect(self.get_success_url() + "#edit")

        return super().post(request, *args, **kwargs)

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

        # Filter where project is active
        user_translation_ids = set(
            all_changes.content()
            .filter(timestamp__gte=timezone.now() - timedelta(days=90))
            .values_list("translation", flat=True)
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
        # Last user activity
        context["last_changes"] = all_changes.recent()
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


def user_contributions(request: AuthenticatedHttpRequest, user: str):
    page_user = get_object_or_404(User, username=user)
    user_translation_ids = set(
        Change.objects.content()
        .filter(user=page_user)
        .values_list("translation", flat=True)
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
            "page_user": page_user,
            "page_profile": page_user.profile,
            "page_user_translations": translation_prefetch_tasks(
                prefetch_stats(get_paginator(request, user_translations))
            ),
        },
    )


def user_avatar(request: AuthenticatedHttpRequest, user: str, size: int):
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
        msg = f"Not supported size: {size}"
        raise Http404(msg)

    avatar_user = get_object_or_404(User, username=user)

    if avatar_user.email == "noreply@weblate.org":
        return redirect(get_fallback_avatar_url(int(size)))
    if avatar_user.email == f"noreply+{avatar_user.pk}@weblate.org":
        return redirect(os.path.join(settings.STATIC_URL, "state/ghost.svg"))

    response = HttpResponse(
        content_type="image/png", content=get_avatar_image(avatar_user, size)
    )

    patch_response_headers(response, 3600 * 24 * 7)

    return response


def redirect_single(request: AuthenticatedHttpRequest, backend: str):
    """Redirect user to single authentication backend."""
    return render(
        request,
        "accounts/redirect.html",
        {"backend": backend, "next": request.GET.get("next")},
    )


class BaseLoginView(LoginView):
    def form_invalid(self, form):
        rotate_token(self.request)
        return super().form_invalid(form)

    def form_valid(self, form):
        """Security check complete. Log the user in."""
        user = form.get_user()
        if user.profile.has_2fa:
            # Store session indication for second factor
            self.request.session[SESSION_SECOND_FACTOR_USER] = (user.id, user.backend)
            # Redirect to second factor login
            redirect_to = self.request.POST.get(
                self.redirect_field_name, self.request.GET.get(self.redirect_field_name)
            )
            login_params: dict[str, str] = {}
            if redirect_to:
                login_params[self.redirect_field_name] = redirect_to
            login_url = reverse(
                "2fa-login", kwargs={"backend": user.profile.get_second_factor_type()}
            )
            return HttpResponseRedirect(f"{login_url}?{urlencode(login_params)}")
        auth_login(self.request, user)
        return HttpResponseRedirect(self.get_success_url())


class WeblateLoginView(BaseLoginView):
    """Login handler, just a wrapper around standard Django login."""

    form_class = LoginForm  # type: ignore[assignment]
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
    def dispatch(self, request: AuthenticatedHttpRequest, *args, **kwargs):  # type: ignore[override]
        # Redirect signed in users to profile
        if request.user.is_authenticated:
            return redirect_profile()

        # Redirect if there is only one backend
        auth_backends = get_auth_keys()
        if len(auth_backends) == 1 and "email" not in auth_backends:
            return redirect_single(request, auth_backends.pop())

        return super().dispatch(request, *args, **kwargs)


class WeblateLogoutView(TemplateView):
    """
    Logout handler, just a reimplementation of standard Django logout.

    - no redirect support
    - login_required decorator
    """

    http_method_names = ["post", "options"]
    template_name = "registration/logged_out.html"
    request: AuthenticatedHttpRequest

    @method_decorator(require_POST)
    @method_decorator(login_required)
    @method_decorator(never_cache)
    def post(self, request: AuthenticatedHttpRequest, *args, **kwargs):  # type: ignore[override]
        """Logout may be done via POST."""
        auth_logout(request)
        request.user = get_anonymous()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = gettext("Signed out")
        return context


def fake_email_sent(request: AuthenticatedHttpRequest, reset: bool = False):
    """Fake redirect to e-mail sent page."""
    request.session["registration-email-sent"] = True
    request.session["password_reset"] = reset
    request.session["account_remove"] = False
    return redirect("email-sent")


@never_cache
def register(request: AuthenticatedHttpRequest):
    """Registration form."""
    # Fetch invitation
    invitation: Invitation | None = None
    initial = {}
    if invitation_pk := request.session.get("invitation_link"):
        try:
            invitation = Invitation.objects.get(pk=invitation_pk)
        except Invitation.DoesNotExist:
            del request.session["invitation_link"]
        else:
            initial["email"] = invitation.email
            initial["username"] = invitation.username
            initial["fullname"] = invitation.full_name

    # Allow registration at all?
    registration_open = settings.REGISTRATION_OPEN or bool(invitation)

    # Hide captcha for invitations
    hide_captcha = invitation is not None

    # Get list of allowed backends
    backends = get_auth_keys()
    if settings.REGISTRATION_ALLOW_BACKENDS and not invitation:
        backends &= set(settings.REGISTRATION_ALLOW_BACKENDS)
    elif not registration_open:
        backends = set()

    if request.method == "POST" and "email" in backends:
        form = RegistrationForm(
            request=request, data=request.POST, hide_captcha=hide_captcha
        )
        if form.is_valid():
            if form.cleaned_data["email_user"]:
                AuditLog.objects.create(
                    form.cleaned_data["email_user"], request, "connect"
                )
                return fake_email_sent(request)
            store_userid(request)
            return social_complete(request, "email")
    else:
        form = RegistrationForm(
            request=request, initial=initial, hide_captcha=hide_captcha
        )

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
            "invitation": invitation,
        },
    )


@login_required
@never_cache
def email_login(request: AuthenticatedHttpRequest):
    """Connect e-mail."""
    if request.method == "POST":
        form = EmailForm(request=request, data=request.POST)
        if form.is_valid():
            email_user = form.cleaned_data["email_user"]
            if email_user and email_user != request.user:
                AuditLog.objects.create(
                    form.cleaned_data["email_user"], request, "connect"
                )
                return fake_email_sent(request)
            store_userid(request)
            return social_complete(request, "email")
    else:
        form = EmailForm(request=request)

    return render(
        request,
        "accounts/email.html",
        {"title": gettext("Register e-mail"), "form": form},
    )


@login_required
@session_ratelimit_post("password")
@never_cache
def password(request: AuthenticatedHttpRequest):
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


def reset_password_set(request: AuthenticatedHttpRequest):
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
            "second_stage": True,
        },
    )


def get_registration_hint(email: str) -> str | None:
    domain = email.rsplit("@", 1)[-1]
    return settings.REGISTRATION_HINTS.get(domain)


@never_cache
def reset_password(request: AuthenticatedHttpRequest):
    """Password reset handling."""
    if request.user.is_authenticated:
        return redirect_profile()
    if "email" not in get_auth_keys():
        messages.error(
            request,
            gettext("Cannot reset password, e-mail authentication is turned off."),
        )
        return redirect("login")

    # We're already in the reset phase
    if "perform_reset" in request.session:
        return reset_password_set(request)
    if request.method == "POST":
        form = ResetForm(request=request, data=request.POST)
        if form.is_valid():
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
                        "user_agent": get_user_agent(request),
                        "registration_hint": get_registration_hint(email),
                    },
                )
            return fake_email_sent(request, True)
    else:
        form = ResetForm(request=request)

    return render(
        request,
        "accounts/reset.html",
        {
            "title": gettext("Password reset"),
            "form": form,
            "second_stage": False,
        },
    )


@require_POST
@login_required
@session_ratelimit_post("reset_api")
def reset_api_key(request: AuthenticatedHttpRequest):
    """Reset user API key."""
    # Need to delete old token as key is primary key
    with transaction.atomic():
        Token.objects.filter(user=request.user).delete()
        Token.objects.create(user=request.user, key=get_token("wlu"))

    return redirect_profile("#api")


@require_POST
@login_required
@session_ratelimit_post("userdata")
def userdata(request: AuthenticatedHttpRequest):
    response = JsonResponse(request.user.profile.dump_data())
    response["Content-Disposition"] = 'attachment; filename="weblate.json"'
    return response


@require_POST
@login_required
def watch(request: AuthenticatedHttpRequest, path):
    user = request.user
    redirect_obj = obj = parse_path(request, path, (Component, Project))
    if isinstance(obj, Component):
        project = obj.project

        # Mute project level subscriptions
        mute_real(
            user, scope=NotificationScope.SCOPE_PROJECT, component=None, project=project
        )
        # Manually enable component level subscriptions
        for default_subscription in user.subscription_set.filter(
            scope=NotificationScope.SCOPE_WATCHED
        ):
            subscription, created = user.subscription_set.get_or_create(
                notification=default_subscription.notification,
                scope=NotificationScope.SCOPE_COMPONENT,
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
    return redirect_next(request.GET.get("next"), redirect_obj)


@require_POST
@login_required
def unwatch(request: AuthenticatedHttpRequest, path):
    obj = parse_path(request, path, (Project,))
    request.user.profile.watched.remove(obj)
    request.user.subscription_set.filter(
        Q(project=obj) | Q(component__project=obj)
    ).delete()
    return redirect_next(request.GET.get("next"), obj)


def mute_real(user: User, **kwargs) -> None:
    for notification_cls in NOTIFICATIONS:
        if notification_cls.ignore_watched:
            continue
        try:
            subscription = user.subscription_set.get_or_create(
                notification=notification_cls.get_name(),
                defaults={"frequency": NotificationFrequency.FREQ_NONE},
                **kwargs,
            )[0]
        except Subscription.MultipleObjectsReturned:
            subscriptions = user.subscription_set.filter(
                notification=notification_cls.get_name(), **kwargs
            )
            # Remove extra subscriptions
            for subscription in subscriptions[1:]:
                subscription.delete()
            subscription = subscriptions[0]
        if subscription.frequency != NotificationFrequency.FREQ_NONE:
            subscription.frequency = NotificationFrequency.FREQ_NONE
            subscription.save(update_fields=["frequency"])


@require_POST
@login_required
def mute(request: AuthenticatedHttpRequest, path):
    obj = parse_path(request, path, (Component, Project))
    if isinstance(obj, Component):
        mute_real(
            request.user,
            scope=NotificationScope.SCOPE_COMPONENT,
            component=obj,
            project=None,
        )
        return redirect(
            "{}?notify_component={}#notifications".format(reverse("profile"), obj.pk)
        )
    mute_real(
        request.user, scope=NotificationScope.SCOPE_PROJECT, component=None, project=obj
    )
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


def store_userid(
    request: AuthenticatedHttpRequest, *, reset: bool = False, remove: bool = False
) -> None:
    """Store user ID in the session."""
    request.session["social_auth_user"] = request.user.pk
    request.session["password_reset"] = reset
    request.session["account_remove"] = remove


@require_POST
@login_required
def social_disconnect(
    request: AuthenticatedHttpRequest, backend: str, association_id: str | None = None
):
    """
    Disconnect social authentication.

    Wrapper around social_django.views.disconnect:

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
def social_auth(request: AuthenticatedHttpRequest, backend: str):
    """
    Social authentication endpoint.

    Wrapper around social_django.views.auth:

    - Incorporates modified social_djang.utils.psa
    - Requires POST (to avoid CSRF on auth)
    - Stores current user in session (to avoid CSRF upon completion)
    - Stores session ID in the request URL if needed
    """
    # Fill in idp in case it is not provided
    if backend == "saml" and "idp" not in request.GET:
        request.GET = request.GET.copy()  # type: ignore[assignment]
        request.GET["idp"] = "weblate"  # type: ignore[misc]
    store_userid(request)
    uri = reverse("social:complete", args=(backend,))
    request.social_strategy = load_strategy(request)
    try:
        request.backend = load_backend(request.social_strategy, backend, uri)
    except MissingBackend:
        msg = "Backend not found"
        raise Http404(msg) from None

    # Store session ID for OpenID or SAML based auth. The session cookies will
    # not be sent on returning POST request due to SameSite cookie policy
    if isinstance(request.backend, OpenIdAuth) or backend == "saml":
        request.backend.redirect_uri += "?authid={}".format(
            dumps(
                (request.session.session_key, get_ip_address(request)),
                salt=AUTHID_SALT,
            )
        )

    try:
        return do_auth(request.backend, redirect_name=REDIRECT_FIELD_NAME)
    except AuthException as error:
        report_error("Could not authenticate")
        messages.error(request, gettext("Could not authenticate: %s") % error)
        return redirect("login")


def auth_fail(request: AuthenticatedHttpRequest, message: str):
    messages.error(request, message)
    return redirect(reverse("login"))


def registration_fail(request: AuthenticatedHttpRequest, message: str):
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


def auth_redirect_token(request: AuthenticatedHttpRequest):
    return auth_fail(
        request,
        gettext(
            "Try registering again to verify your identity, "
            "the confirmation link probably expired."
        ),
    )


def auth_redirect_state(request: AuthenticatedHttpRequest):
    return auth_fail(
        request, gettext("Could not authenticate due to invalid session state.")
    )


def handle_missing_parameter(
    request: AuthenticatedHttpRequest, backend: str, error: AuthMissingParameter
):
    if backend != "email" and error.parameter == "email":
        messages = [
            gettext("Got no e-mail address from third party authentication service.")
        ]
        if "email" in get_auth_keys():
            # Show only if e-mail authentication is turned on
            messages.append(gettext("Please register using e-mail instead."))
        return auth_fail(request, " ".join(messages))
    if error.parameter in {"email", "user", "expires"}:
        return auth_redirect_token(request)
    if error.parameter in {"state", "code", "RelayState"}:
        return auth_redirect_state(request)
    if error.parameter == "disabled":
        return auth_fail(request, gettext("New registrations are turned off."))
    return None


@csrf_exempt
@never_cache
def social_complete(request: AuthenticatedHttpRequest, backend: str):  # noqa: C901
    """
    Social authentication completion endpoint.

    Wrapper around social_django.views.complete:

    - Handles backend errors gracefully
    - Intermediate page (autosubmitted by JavaScript) to avoid
      confirmations by bots
    - Restores session from authid for some backends (see social_auth)
    """
    if "authid" in request.GET:
        try:
            session_key, ip_address = loads(
                request.GET["authid"],
                max_age=AUTHID_MAX_AGE,
                salt=AUTHID_SALT,
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
        response = complete(request, backend)
    except InvalidEmail:
        report_error("Could not register")
        return auth_redirect_token(request)
    except AuthMissingParameter as error:
        report_error("Could not register")
        result = handle_missing_parameter(request, backend, error)
        if result:
            return result
        raise
    except (AuthStateMissing, AuthStateForbidden):
        report_error("Could not register")
        return auth_redirect_state(request)
    except AuthFailed:
        report_error("Could not register")
        return auth_fail(
            request,
            gettext(
                "Could not authenticate, probably due to an expired token "
                "or connection error."
            ),
        )
    except AuthCanceled:
        report_error("Could not register")
        return auth_fail(request, gettext("Authentication cancelled."))
    except AuthForbidden:
        report_error("Could not register")
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
        report_error("Could not register")
        return registration_fail(request, str(error))

    # Finish second factor authentication
    if persistent_id := request.session.pop(DEVICE_ID_SESSION_KEY, None):
        device = Device.from_persistent_id(persistent_id)
        otp_login(request, device)

    return response


@login_required
@require_POST
def subscribe(request: AuthenticatedHttpRequest):
    if "onetime" in request.POST:
        component = Component.objects.get(pk=request.POST["component"])
        request.user.check_access_component(component)
        subscription = Subscription(
            user=request.user,
            notification=request.POST["onetime"],
            scope=NotificationScope.SCOPE_COMPONENT,
            frequency=NotificationFrequency.FREQ_INSTANT,
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


def unsubscribe(request: AuthenticatedHttpRequest):
    if "i" in request.GET:
        signer = TimestampSigner()
        try:
            subscription = Subscription.objects.get(
                pk=int(signer.unsign(request.GET["i"], max_age=24 * 3600))
            )
            subscription.frequency = NotificationFrequency.FREQ_NONE
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
def saml_metadata(request: AuthenticatedHttpRequest):
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
        report_error("SAML metadata", level="error")
        return HttpResponseServerError(content=", ".join(errors))

    return HttpResponse(content=metadata, content_type="text/xml")


@method_decorator(login_required, name="dispatch")
class UserList(ListView):
    paginate_by = 50
    model = User
    form_class = UserSearchForm
    initial_query = ""

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

    def setup(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:  # type: ignore[override]
        super().setup(request, *args, **kwargs)
        if "q" in request.GET:
            form = self.form_class(request.GET)
        else:
            form = self.form_class({"q": self.initial_query})
        self.form = form
        self.sort_query = ""
        if form.is_valid():
            self.sort_query = form.cleaned_data.get("sort_by", "")
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


@method_decorator(login_required, name="dispatch")
class RecoveryCodesView(TemplateView):
    template_name = "accounts/recovery-codes.html"

    def post(self, request, *args, **kwargs):
        user = request.user
        # Delete all existing tokens
        StaticToken.objects.filter(device__user=user).delete()

        # Get device
        device = StaticDevice.objects.filter(user=user).first()
        if device is None:
            device = StaticDevice.objects.create(user=user, name="Backup Code")

        # Generate tokens
        for _i in range(16):
            token = StaticToken.random_token()
            device.token_set.create(token=token)

        AuditLog.objects.create(user, request, "recovery-generate")

        return redirect("recovery-codes")

    def get(self, request, *args, **kwargs):
        user = request.user
        AuditLog.objects.create(user, request, "recovery-show")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        user = self.request.user
        recovery_codes = StaticToken.objects.filter(device__user=user).values_list(
            "token", flat=True
        )
        result["recovery_codes"] = recovery_codes
        result["recovery_codes_str"] = "\n".join(recovery_codes)
        return result


@method_decorator(login_required, name="dispatch")
class WebAuthnCredentialView(DetailView):
    model = WebAuthnCredential

    message_remove = gettext_lazy("The security key was removed.")
    message_add = gettext_lazy("The security key %s was registered.")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def get(self, request, *args, **kwargs):
        return redirect_profile("#account")

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        if "delete" in request.POST:
            key_name = get_key_name(obj)
            obj.delete()
            AuditLog.objects.create(
                request.user, request, "twofactor-remove", device=key_name
            )
            messages.success(request, self.message_remove)
        elif "name" in request.POST:
            obj.name = request.POST["name"]
            obj.save(update_fields=["name"])
            key_name = get_key_name(obj)
            audit_pk = request.session.pop(SESSION_WEBAUTHN_AUDIT, None)
            if isinstance(obj, WebAuthnCredential) and audit_pk is not None:
                audit = AuditLog.objects.get(pk=audit_pk)
                audit.params = {"device": key_name}
                audit.save(update_fields=["params"])
            messages.success(
                request,
                self.message_add % key_name,
            )
        return redirect_profile("#account")


@method_decorator(login_required, name="dispatch")
class TOTPDetailView(WebAuthnCredentialView):
    model = TOTPDevice

    message_remove = gettext_lazy("The authentication app was removed.")
    message_add = gettext_lazy("The authentication app %s was registered.")


@method_decorator(login_required, name="dispatch")
class TOTPView(FormView):
    template_name = "accounts/totp.html"
    form_class = TOTPDeviceForm
    session_key = SESSION_SECOND_FACTOR_TOTP

    @cached_property
    def totp_key(self) -> str:
        key = self.request.session.get(self.session_key, None)
        if key is None:
            key = random_hex(20)
            self.request.session[self.session_key] = key
        return key

    @cached_property
    def totp_key_b32(self) -> str:
        key = self.totp_key
        rawkey = unhexlify(key.encode("ascii"))
        return b32encode(rawkey).decode("utf-8")

    @cached_property
    def totp_url(self) -> str:
        # For a complete run-through of all the parameters, have a look at the
        # specs at:
        # https://github.com/google/google-authenticator/wiki/Key-Uri-Format

        accountname = self.request.user.username
        issuer = settings.SITE_TITLE
        label = f"{issuer}: {accountname}"

        # Ensure that the secret parameter is the FIRST parameter of the URI, this
        # allows Microsoft Authenticator to work.
        query = (
            ("secret", self.totp_key_b32),
            ("digits", "6"),
            ("issuer", issuer),
        )

        return f"otpauth://totp/{quote(label)}?{urlencode(query)}"

    @property
    def totp_svg(self):
        image = qrcode.make(self.totp_url, image_factory=qrcode.image.svg.SvgPathImage)
        return mark_safe(image.to_string(encoding="unicode"))  # noqa: S308

    def get_context_data(self, **kwargs):
        """Create context for rendering page."""
        context = super().get_context_data(**kwargs)
        context["totp_key_b32"] = self.totp_key_b32
        context["totp_url"] = self.totp_url
        context["totp_svg"] = self.totp_svg
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["key"] = self.totp_key
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form: TOTPDeviceForm):
        device = form.save()
        AuditLog.objects.create(
            self.request.user,
            self.request,
            "twofactor-add",
            device=get_key_name(device),
        )
        return redirect_profile("#account")


class SecondFactorMixin(View):
    def second_factor_completed(self, device: Device) -> None:
        # Store audit log entry aboute used device and update last used device type
        user = self.get_user()
        user.profile.log_2fa(self.request, device)
        del self.request.session[SESSION_SECOND_FACTOR_USER]

        if not self.request.session.get(SESSION_SECOND_FACTOR_SOCIAL):
            # Keep login on social pipeline if we got here from it
            auth_login(self.request, user)
            # Perform OTP login
            otp_login(self.request, device)
        else:
            self.request.session[DEVICE_ID_SESSION_KEY] = device.persistent_id
            # This is completed in social_complete after completing social login

    def get_user(self) -> User:
        try:
            user_id, backend = self.request.session[SESSION_SECOND_FACTOR_USER]
        except KeyError as error:
            raise Http404 from error
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist as error:
            raise Http404 from error
        user.backend = backend
        return user


class SecondFactorLoginView(SecondFactorMixin, RedirectURLMixin, FormView):
    template_name = "accounts/2fa.html"
    next_page = settings.LOGIN_REDIRECT_URL
    forms = {
        "totp": TOTPTokenForm,
        "webauthn": WebAuthnTokenForm,
        "recovery": OTPTokenForm,
    }

    def get_backend(self) -> DeviceType:
        backend = self.kwargs["backend"]
        if backend not in self.forms:
            raise Http404
        return backend

    def get_form_class(self):
        return self.forms[self.get_backend()]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.user
        kwargs["request"] = self.request
        return kwargs

    def get_context_data(self, **kwargs):
        """Create context for rendering page."""
        context = super().get_context_data(**kwargs)
        context["second_factor_types"] = self.user.profile.second_factor_types - {
            self.get_backend()
        }
        context["next"] = self.request.GET.get("next", "")
        context["title"] = gettext("Second factor sign in")
        return context

    def dispatch(self, request: AuthenticatedHttpRequest, *args, **kwargs):  # type: ignore[override]
        self.user = self.get_user()
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        self.second_factor_completed(form.user.otp_device)

        return HttpResponseRedirect(self.get_success_url())


class WeblateBeginCredentialAuthenticationView(
    SecondFactorMixin, BeginCredentialAuthenticationView
):
    pass


class WeblateCompleteCredentialAuthenticationView(
    SecondFactorMixin, CompleteCredentialAuthenticationView
):
    def complete_auth(self, device: WebAuthnCredential) -> User:
        return self.second_factor_completed(device)
