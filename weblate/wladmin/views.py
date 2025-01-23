# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache
from django.core.checks import run_checks
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db.models import Count, QuerySet
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.utils.translation import gettext, gettext_lazy
from django.views.decorators.http import require_POST
from django.views.generic import ListView
from django.views.generic.edit import FormMixin
from requests.exceptions import HTTPError, Timeout

from weblate.accounts.forms import AdminUserSearchForm, ContactForm
from weblate.accounts.views import UserList, get_initial_contact
from weblate.auth.decorators import management_access
from weblate.auth.forms import AdminInviteUserForm, SitewideTeamForm
from weblate.auth.models import (
    AuthenticatedHttpRequest,
    Group,
    GroupQuerySet,
    Invitation,
    User,
)
from weblate.configuration.models import Setting, SettingCategory
from weblate.configuration.views import CustomCSSView
from weblate.trans.forms import AnnouncementForm
from weblate.trans.models import Alert, Announcement, Component, Project
from weblate.trans.util import redirect_param
from weblate.utils import messages
from weblate.utils.cache import measure_cache_latency
from weblate.utils.celery import get_queue_stats
from weblate.utils.db import measure_database_latency
from weblate.utils.errors import report_error
from weblate.utils.stats import prefetch_stats
from weblate.utils.tasks import database_backup, settings_backup
from weblate.utils.version import GIT_LINK, GIT_REVISION
from weblate.utils.views import show_form_errors
from weblate.utils.zammad import ZammadError, submit_zammad_ticket
from weblate.vcs.ssh import (
    KeyType,
    add_host_key,
    can_generate_key,
    generate_ssh_key,
    get_all_key_data,
    get_host_keys,
    get_key_data_raw,
)
from weblate.wladmin.forms import (
    ActivateForm,
    AppearanceForm,
    BackupForm,
    SSHAddForm,
    TestMailForm,
)
from weblate.wladmin.models import BackupService, ConfigurationError, SupportStatus
from weblate.wladmin.tasks import backup_service, support_status_update

if TYPE_CHECKING:
    from django.http.request import QueryDict
    from django_stubs_ext import StrOrPromise

MENU: tuple[tuple[str, str, StrOrPromise], ...] = (
    ("index", "manage", gettext_lazy("Weblate status")),
    ("backups", "manage-backups", gettext_lazy("Backups")),
    ("memory", "manage-memory", gettext_lazy("Translation memory")),
    ("performance", "manage-performance", gettext_lazy("Performance report")),
    ("ssh", "manage-ssh", gettext_lazy("SSH keys")),
    ("alerts", "manage-alerts", gettext_lazy("Alerts")),
    ("repos", "manage-repos", gettext_lazy("Repositories")),
    ("users", "manage-users", gettext_lazy("Users")),
    ("teams", "manage-teams", gettext_lazy("Teams")),
    ("appearance", "manage-appearance", gettext_lazy("Appearance")),
    ("tools", "manage-tools", gettext_lazy("Tools")),
    ("machinery", "manage-machinery", gettext_lazy("Automatic suggestions")),
    ("addons", "manage-addons", gettext_lazy("Add-ons")),
)
if "weblate.billing" in settings.INSTALLED_APPS:
    MENU += (("billing", "manage-billing", gettext_lazy("Billing")),)


@management_access
def manage(request: AuthenticatedHttpRequest) -> HttpResponse:
    support = SupportStatus.objects.get_current()
    initial = None
    activation_code = request.GET.get("activation")
    if activation_code and len(activation_code) < 400:
        initial = {"secret": activation_code}
    support_form = None
    if support.name != "community":
        support_form = ContactForm(
            request=request,
            hide_captcha=request.user.is_authenticated,
            initial=get_initial_contact(request),
        )

    return render(
        request,
        "manage/index.html",
        {
            "menu_items": MENU,
            "menu_page": "index",
            "support": support,
            "activate_form": ActivateForm(initial=initial),
            "support_form": support_form,
            "git_revision_link": GIT_LINK,
            "git_revision": GIT_REVISION,
        },
    )


@management_access
@require_POST
def support_form(request: AuthenticatedHttpRequest) -> HttpResponse:
    support = SupportStatus.objects.get_current()
    if support.name == "community":
        raise PermissionDenied
    form = ContactForm(
        request=request,
        hide_captcha=request.user.is_authenticated,
        data=request.POST,
    )
    if not form.is_valid():
        show_form_errors(request, form)
    else:
        try:
            url, number = submit_zammad_ticket(
                title=form.cleaned_data["subject"],
                body=form.cleaned_data["message"],
                name=form.cleaned_data["name"],
                email=form.cleaned_data["email"],
                zammad_url="https://care.weblate.org",
            )
            messages.success(
                request,
                format_html(
                    """{} <a href="{}">{}</a>""",
                    gettext("Customer care ticket created:"),
                    url,
                    number,
                ),
            )
        except ZammadError as error:
            messages.error(request, str(error))
    return redirect("manage")


def send_test_mail(email: str) -> None:
    send_mail(
        subject=f"Test e-mail from Weblate on {timezone.now()}",
        message="It works.",
        recipient_list=[email],
        from_email=None,
    )


@management_access
def tools(request: AuthenticatedHttpRequest) -> HttpResponse:
    email_form = TestMailForm(initial={"email": request.user.email})
    announce_form = AnnouncementForm()

    if request.method == "POST":
        if "email" in request.POST:
            email_form = TestMailForm(request.POST)
            if email_form.is_valid():
                try:
                    send_test_mail(**email_form.cleaned_data)
                    messages.success(request, gettext("Test e-mail sent."))
                except Exception as error:
                    report_error("E-mail sending failed")
                    messages.error(
                        request, gettext("Could not send test e-mail: %s") % error
                    )
                return redirect("manage-tools")

        if "sentry" in request.POST:
            report_error("Test message", message=True, level="info")
            return redirect("manage-tools")

        if "message" in request.POST:
            announce_form = AnnouncementForm(request.POST)
            if announce_form.is_valid():
                Announcement.objects.create(
                    user=request.user, **announce_form.cleaned_data
                )

    return render(
        request,
        "manage/tools.html",
        {
            "menu_items": MENU,
            "menu_page": "tools",
            "email_form": email_form,
            "announce_form": announce_form,
        },
    )


@management_access
@require_POST
def discovery(request: AuthenticatedHttpRequest) -> HttpResponse:
    support = SupportStatus.objects.get_current()

    if not support.discoverable and settings.SITE_TITLE == "Weblate":
        messages.error(
            request,
            gettext(
                "Please change SITE_TITLE in settings to make your Weblate easy to recognize in discover."
            ),
        )
    elif support.secret:
        support.discoverable = not support.discoverable
        support.save(update_fields=["discoverable"])
        support_status_update.delay()

    return redirect("manage")


@management_access
@require_POST
def activate(request: AuthenticatedHttpRequest) -> HttpResponse:
    support = None
    if "refresh" in request.POST:
        support = SupportStatus.objects.get_current()
    else:
        form = ActivateForm(request.POST)
        if form.is_valid():
            support = SupportStatus(**form.cleaned_data)
        else:
            show_form_errors(request, form)

    if support is not None:
        try:
            support.refresh()
        except Timeout:
            report_error("Activation timeout")
            messages.error(
                request,
                gettext(
                    "Could not activate your installation. Please try again later."
                ),
            )
        except HTTPError as error:
            report_error("Activation error")
            if error.response.status_code == 404:
                messages.error(
                    request,
                    gettext(
                        "Could not activate your installation. "
                        "Please ensure your activation token is correct."
                    ),
                )
            else:
                messages.error(
                    request,
                    gettext(
                        "Could not activate your installation. Please try again later."
                    ),
                )
        except Exception as error:
            report_error("Activation error")
            messages.error(
                request,
                gettext("Could not activate your installation: %s") % error,
            )
        else:
            support.save()
            messages.success(request, gettext("Activation completed."))
    return redirect("manage")


@management_access
def repos(request: AuthenticatedHttpRequest) -> HttpResponse:
    """Provide report about Git status of all repos."""
    return render(
        request,
        "manage/repos.html",
        {
            "components": Component.objects.order_project(),
            "menu_items": MENU,
            "menu_page": "repos",
        },
    )


@management_access
def backups(request: AuthenticatedHttpRequest) -> HttpResponse:
    form = BackupForm()
    if request.method == "POST":
        if "repository" in request.POST:
            form = BackupForm(request.POST)
            if form.is_valid():
                form.save()
                return redirect("manage-backups")
        elif "remove" in request.POST:
            service = BackupService.objects.get(pk=request.POST["service"])
            service.delete()
            return redirect("manage-backups")
        elif "toggle" in request.POST:
            service = BackupService.objects.get(pk=request.POST["service"])
            service.enabled = not service.enabled
            service.save()
            return redirect("manage-backups")
        elif "trigger" in request.POST:
            settings_backup.delay()
            database_backup.delay()
            backup_service.delay(pk=request.POST["service"])
            messages.success(request, gettext("Backup process triggered"))
            return redirect("manage-backups")

    context = {
        "services": BackupService.objects.all(),
        "menu_items": MENU,
        "menu_page": "backups",
        "form": form,
        "activate_form": ActivateForm(),
    }
    return render(request, "manage/backups.html", context)


def handle_dismiss(request: AuthenticatedHttpRequest) -> HttpResponse:
    try:
        error = ConfigurationError.objects.get(pk=int(request.POST["pk"]))
        if "ignore" in request.POST:
            error.ignored = True
            error.save(update_fields=["ignored"])
        else:
            error.delete()
    except (ValueError, KeyError, ConfigurationError.DoesNotExist):
        messages.error(request, gettext("Could not dismiss the configuration error!"))
    return redirect("manage-performance")


@management_access
def performance(request: AuthenticatedHttpRequest) -> HttpResponse:
    """Show performance tuning tips."""
    if request.method == "POST":
        return handle_dismiss(request)
    checks = run_checks(include_deployment_checks=True)

    context = {
        "checks": [check for check in checks if not check.is_silenced()],
        "errors": ConfigurationError.objects.filter(ignored=False),
        "queues": get_queue_stats().items(),
        "menu_items": MENU,
        "menu_page": "performance",
        "web_encoding": [sys.getfilesystemencoding(), sys.getdefaultencoding()],
        "celery_encoding": cache.get("celery_encoding"),
        "celery_latency": cache.get("celery_latency"),
        "database_latency": measure_database_latency(),
        "cache_latency": measure_cache_latency(),
    }

    return render(request, "manage/performance.html", context)


@management_access
def ssh_key(request: AuthenticatedHttpRequest) -> HttpResponse:
    key_type = cast("KeyType", request.GET.get("type", "rsa"))
    filename, data = get_key_data_raw(key_type=key_type, kind="private")
    if data is None:
        raise Http404

    response = HttpResponse(data, content_type="text/plain")
    response["Content-Disposition"] = f"attachment; filename={filename}"
    response["Content-Length"] = len(data)
    return response


@management_access
def ssh(request: AuthenticatedHttpRequest) -> HttpResponse:
    """Show information and manipulate with SSH key."""
    # Check whether we can generate SSH key
    can_generate = can_generate_key()

    # Grab action type
    action = request.POST.get("action")

    # Generate key if it does not exist yet
    if can_generate and action == "generate":
        key_type = cast("KeyType", request.POST.get("type", "rsa"))
        generate_ssh_key(request, key_type=key_type)
        return redirect("manage-ssh")

    # Read key data if it exists
    keys = get_all_key_data()

    # Add host key
    form = SSHAddForm()
    if action == "add-host":
        form = SSHAddForm(request.POST)
        if form.is_valid():
            add_host_key(request, **form.cleaned_data)

    context = {
        "public_ssh_keys": keys,
        "can_generate": can_generate,
        "missing_ssh_keys": [
            keydata for keydata in keys.values() if keydata["key"] is None
        ],
        "host_keys": get_host_keys(),
        "menu_items": MENU,
        "menu_page": "ssh",
        "add_form": form,
    }

    return render(request, "manage/ssh.html", context)


@management_access
def alerts(request: AuthenticatedHttpRequest) -> HttpResponse:
    """Show component alerts."""
    context = {
        "alerts": Alert.objects.order_by(
            "name", "component__project__name", "component__name"
        ).select_related("component", "component__project"),
        "no_components": Project.objects.annotate(Count("component")).filter(
            component__count=0
        ),
        "menu_items": MENU,
        "menu_page": "alerts",
    }

    return render(request, "manage/alerts.html", context)


@method_decorator(management_access, name="dispatch")
class AdminUserList(UserList):
    template_name = "manage/users.html"
    form_class = AdminUserSearchForm
    initial_query = "is:active"

    def get_base_queryset(self) -> QuerySet[User]:
        return User.objects.all()

    def post(self, request: AuthenticatedHttpRequest, **kwargs) -> HttpResponse:
        if "email" in request.POST:
            invite_form = AdminInviteUserForm(request.POST)
            if invite_form.is_valid():
                invite_form.save(request)
                return redirect("manage-users")
        return super().get(request, **kwargs)

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        result = super().get_context_data(**kwargs)

        if self.request.method == "POST":
            invite_form = AdminInviteUserForm(self.request.POST)
            invite_form.is_valid()
        else:
            invite_form = AdminInviteUserForm()

        result["menu_items"] = MENU
        result["menu_page"] = "users"
        result["invite_form"] = invite_form
        result["search_form"] = self.form
        result["invitations"] = Invitation.objects.all().select_related("user")
        return result


@management_access
def users_check(request: AuthenticatedHttpRequest) -> HttpResponse:
    data: QueryDict = request.GET
    # Legacy links for care.weblate.org integration
    if "email" in data and "q" not in data:
        data = data.copy()
        data.setlist("q", data.getlist("email"))
    form = AdminUserSearchForm(data)

    user_list = None
    if form.is_valid():
        query = form.cleaned_data.get("q", "")
        parser = getattr(form.fields["q"], "parser", "unit")
        user_list = User.objects.search(query, parser=parser)[:2]
        if user_list.count() != 1:
            return redirect_param(
                "manage-users", "?q={}".format(quote(form.cleaned_data["q"]))
            )
        return redirect(user_list[0])
    return redirect("manage-users")


@management_access
def appearance(request: AuthenticatedHttpRequest) -> HttpResponse:
    current = Setting.objects.get_settings_dict(SettingCategory.UI)
    form = AppearanceForm(initial=current)

    if request.method == "POST":
        if "reset" in request.POST:
            Setting.objects.filter(category=SettingCategory.UI).delete()
            CustomCSSView.drop_cache()
            return redirect("manage-appearance")
        form = AppearanceForm(request.POST)
        if form.is_valid():
            for name, value in form.cleaned_data.items():
                if name not in current:
                    # New setting previously not set
                    Setting.objects.create(
                        category=SettingCategory.UI, name=name, value=value
                    )
                else:
                    if value != current[name]:
                        # Update setting
                        Setting.objects.filter(
                            category=SettingCategory.UI, name=name
                        ).update(value=value)
                    current.pop(name)
            # Drop stale settings
            if current:
                Setting.objects.filter(
                    category=SettingCategory.UI, name__in=current.keys()
                ).delete()

            # Flush cache
            CustomCSSView.drop_cache()
            return redirect("manage-appearance")

    return render(
        request,
        "manage/appearance.html",
        {
            "menu_items": MENU,
            "menu_page": "appearance",
            "form": form,
        },
    )


@management_access
def billing(request: AuthenticatedHttpRequest) -> HttpResponse:
    from weblate.billing.models import Billing

    trial = []
    pending = []
    removal = []
    free = []
    paid = []
    terminated = []

    # We will list all billings anyway, so fetch  them at once
    billings = Billing.objects.prefetch().order_by("expiry", "removal", "id")
    projects = []

    for current in billings:
        if current.removal:
            removal.append(current)
        if current.state == Billing.STATE_TRIAL:
            if (
                current.plan
                and current.plan.price == 0
                and current.payment.get("libre_request")
            ):
                pending.append(current)
            trial.append(current)
        elif current.state == Billing.STATE_TERMINATED:
            terminated.append(current)
        elif current.plan.price:
            paid.append(current)
        else:
            free.append(current)
        projects.extend(current.ordered_projects)
    prefetch_stats(projects)

    return render(
        request,
        "manage/billing.html",
        {
            "menu_items": MENU,
            "menu_page": "billing",
            "trial": trial,
            "removal": removal,
            "free": free,
            "paid": paid,
            "terminated": terminated,
            "pending": pending,
        },
    )


@method_decorator(management_access, name="dispatch")
class TeamListView(FormMixin, ListView):
    template_name = "manage/teams.html"
    paginate_by = 50
    model = Group
    form_class = SitewideTeamForm

    def get_queryset(self) -> QuerySet[Group]:
        return (
            cast("GroupQuerySet", super().get_queryset())
            .prefetch_related("languages", "projects", "components")
            .filter(defining_project=None)
            .annotate(Count("user"), Count("autogroup"))
            .order()
        )

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        result = super().get_context_data(**kwargs)
        result["menu_items"] = MENU
        result["menu_page"] = "teams"
        return result

    def get_success_url(self) -> str:
        return reverse("manage-teams")

    def post(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> HttpResponse:
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        return self.form_invalid(form)

    def form_valid(self, form: SitewideTeamForm) -> HttpResponse:
        form.save()
        return super().form_valid(form)
