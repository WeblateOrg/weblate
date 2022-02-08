#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

import sys
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache
from django.core.checks import run_checks
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from weblate.accounts.views import UserList
from weblate.auth.decorators import management_access
from weblate.auth.forms import AdminInviteUserForm
from weblate.auth.models import User
from weblate.configuration.models import Setting
from weblate.configuration.views import CustomCSSView
from weblate.trans.forms import AnnouncementForm
from weblate.trans.models import Alert, Announcement, Component, Project
from weblate.trans.util import redirect_param
from weblate.utils import messages
from weblate.utils.celery import get_queue_stats
from weblate.utils.checks import measure_cache_latency, measure_database_latency
from weblate.utils.errors import report_error
from weblate.utils.tasks import database_backup, settings_backup
from weblate.utils.version import GIT_LINK, GIT_REVISION
from weblate.utils.views import show_form_errors
from weblate.vcs.ssh import (
    RSA_KEY,
    add_host_key,
    can_generate_key,
    generate_ssh_key,
    get_host_keys,
    get_key_data,
    ssh_file,
)
from weblate.wladmin.forms import (
    ActivateForm,
    AppearanceForm,
    BackupForm,
    SSHAddForm,
    TestMailForm,
    UserSearchForm,
)
from weblate.wladmin.models import BackupService, ConfigurationError, SupportStatus
from weblate.wladmin.tasks import backup_service, support_status_update

MENU = (
    ("index", "manage", gettext_lazy("Weblate status")),
    ("backups", "manage-backups", gettext_lazy("Backups")),
    ("memory", "manage-memory", gettext_lazy("Translation memory")),
    ("performance", "manage-performance", gettext_lazy("Performance report")),
    ("ssh", "manage-ssh", gettext_lazy("SSH keys")),
    ("alerts", "manage-alerts", gettext_lazy("Alerts")),
    ("repos", "manage-repos", gettext_lazy("Repositories")),
    ("users", "manage-users", gettext_lazy("Users")),
    ("appearance", "manage-appearance", gettext_lazy("Appearance")),
    ("tools", "manage-tools", gettext_lazy("Tools")),
)
if "weblate.billing" in settings.INSTALLED_APPS:
    MENU += (("billing", "manage-billing", gettext_lazy("Billing")),)


@management_access
def manage(request):
    support = SupportStatus.objects.get_current()
    initial = None
    activation_code = request.GET.get("activation")
    if activation_code and len(activation_code) < 400:
        initial = {"secret": activation_code}
    return render(
        request,
        "manage/index.html",
        {
            "menu_items": MENU,
            "menu_page": "index",
            "support": support,
            "activate_form": ActivateForm(initial=initial),
            "git_revision_link": GIT_LINK,
            "git_revision": GIT_REVISION,
        },
    )


def send_test_mail(email):
    send_mail(
        subject="Test e-mail from Weblate on %s" % timezone.now(),
        message="It works.",
        recipient_list=[email],
        from_email=None,
    )


@management_access
def tools(request):
    email_form = TestMailForm(initial={"email": request.user.email})
    announce_form = AnnouncementForm()

    if request.method == "POST":
        if "email" in request.POST:
            email_form = TestMailForm(request.POST)
            if email_form.is_valid():
                try:
                    send_test_mail(**email_form.cleaned_data)
                    messages.success(request, _("Test e-mail sent."))
                except Exception as error:
                    report_error()
                    messages.error(request, _("Could not send test e-mail: %s") % error)

        if "sentry" in request.POST:
            try:
                raise Exception("Test exception")
            except Exception:
                report_error()

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
def discovery(request):
    support = SupportStatus.objects.get_current()

    if support.secret:
        support.discoverable = not support.discoverable
        support.save(update_fields=["discoverable"])
        support_status_update.delay()

    return redirect("manage")


@management_access
@require_POST
def activate(request):
    form = ActivateForm(request.POST)
    if form.is_valid():
        support = SupportStatus(**form.cleaned_data)
        try:
            support.refresh()
            support.save()
            messages.success(request, _("Activation completed."))
        except Exception:
            report_error()
            messages.error(
                request,
                _(
                    "Could not activate your installation. "
                    "Please ensure your activation token is correct."
                ),
            )
    else:
        show_form_errors(request, form)
    return redirect("manage")


@management_access
def repos(request):
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
def backups(request):
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
            messages.success(request, _("Backup process triggered"))
            return redirect("manage-backups")

    context = {
        "services": BackupService.objects.all(),
        "menu_items": MENU,
        "menu_page": "backups",
        "form": form,
        "activate_form": ActivateForm(),
    }
    return render(request, "manage/backups.html", context)


def handle_dismiss(request):
    try:
        error = ConfigurationError.objects.get(pk=int(request.POST["pk"]))
        if "ignore" in request.POST:
            error.ignored = True
            error.save(update_fields=["ignored"])
        else:
            error.delete()
    except (ValueError, KeyError, ConfigurationError.DoesNotExist):
        messages.error(request, _("Could not dismiss the configuration error!"))
    return redirect("manage-performance")


@management_access
def performance(request):
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
        "database_latency": measure_database_latency(),
        "cache_latency": measure_cache_latency(),
    }

    return render(request, "manage/performance.html", context)


@management_access
def ssh_key(request):
    with open(ssh_file(RSA_KEY)) as handle:
        data = handle.read()
    response = HttpResponse(data, content_type="text/plain")
    response["Content-Disposition"] = f"attachment; filename={RSA_KEY}"
    response["Content-Length"] = len(data)
    return response


@management_access
def ssh(request):
    """Show information and manipulate with SSH key."""
    # Check whether we can generate SSH key
    can_generate = can_generate_key()

    # Grab action type
    action = request.POST.get("action")

    # Generate key if it does not exist yet
    if can_generate and action == "generate":
        generate_ssh_key(request)

    # Read key data if it exists
    key = get_key_data()

    # Add host key
    form = SSHAddForm()
    if action == "add-host":
        form = SSHAddForm(request.POST)
        if form.is_valid():
            add_host_key(request, **form.cleaned_data)

    context = {
        "public_key": key,
        "can_generate": can_generate,
        "host_keys": get_host_keys(),
        "menu_items": MENU,
        "menu_page": "ssh",
        "add_form": form,
    }

    return render(request, "manage/ssh.html", context)


@management_access
def alerts(request):
    """Shows component alerts."""
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

    def post(self, request, **kwargs):
        if "email" in request.POST:
            invite_form = AdminInviteUserForm(request.POST)
            if invite_form.is_valid():
                user = invite_form.save(request)
                messages.success(
                    request,
                    mark_safe(
                        escape(_("Created user account %s."))
                        % '<a href="{}">{}</a>'.format(
                            escape(user.get_absolute_url()),
                            escape(user.username),
                        )
                    ),
                )
                return redirect("manage-users")
        return super().get(request, **kwargs)

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)

        if self.request.method == "POST":
            invite_form = AdminInviteUserForm(self.request.POST)
            invite_form.is_valid()
        else:
            invite_form = AdminInviteUserForm()

        result["menu_items"] = MENU
        result["menu_page"] = "users"
        result["invite_form"] = invite_form
        result["search_form"] = UserSearchForm()
        return result


@management_access
def users_check(request):
    form = UserSearchForm(request.GET if request.GET else None)

    user_list = None
    if form.is_valid():
        email = form.cleaned_data["email"]
        user_list = User.objects.filter(
            Q(email=email)
            | Q(social_auth__verifiedemail__email__iexact=email)
            | Q(username=email)
        ).distinct()
        if user_list.count() != 1:
            return redirect_param(
                "manage-users", "?q={}".format(quote(form.cleaned_data["email"]))
            )
        return redirect(user_list[0])
    return redirect("manage-users")


@management_access
def appearance(request):

    current = Setting.objects.get_settings_dict(Setting.CATEGORY_UI)
    form = AppearanceForm(initial=current)

    if request.method == "POST":
        if "reset" in request.POST:
            Setting.objects.filter(category=Setting.CATEGORY_UI).delete()
            CustomCSSView.drop_cache()
            return redirect("manage-appearance")
        form = AppearanceForm(request.POST)
        if form.is_valid():
            for name, value in form.cleaned_data.items():
                if name not in current:
                    # New setting previously not set
                    Setting.objects.create(
                        category=Setting.CATEGORY_UI, name=name, value=value
                    )
                else:
                    if value != current[name]:
                        # Update setting
                        Setting.objects.filter(
                            category=Setting.CATEGORY_UI, name=name
                        ).update(value=value)
                    current.pop(name)
            # Drop stale settings
            if current:
                Setting.objects.filter(
                    category=Setting.CATEGORY_UI, name__in=current.keys()
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
def billing(request):
    from weblate.billing.models import Billing

    trial = []
    pending = []
    removal = []
    free = []
    paid = []
    terminated = []

    # We will list all billings anyway, so fetch  them at once
    billings = Billing.objects.prefetch().order_by("expiry", "removal", "id")

    for currrent in billings:
        if currrent.removal:
            removal.append(currrent)
        elif currrent.state == Billing.STATE_TRIAL:
            if (
                currrent.plan
                and currrent.plan.price == 0
                and currrent.payment.get("libre_request")
            ):
                pending.append(currrent)
            trial.append(currrent)
        elif currrent.state == Billing.STATE_TERMINATED:
            terminated.append(currrent)
        elif currrent.plan.price:
            paid.append(currrent)
        else:
            free.append(currrent)

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
