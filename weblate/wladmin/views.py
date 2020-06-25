#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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


from django.core.checks import run_checks
from django.core.mail import send_mail
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from weblate.auth.decorators import management_access
from weblate.auth.forms import InviteUserForm
from weblate.trans.forms import AnnouncementForm
from weblate.trans.models import Alert, Announcement, Component, Project
from weblate.utils import messages
from weblate.utils.celery import get_queue_stats
from weblate.utils.errors import report_error
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
from weblate.wladmin.forms import ActivateForm, BackupForm, SSHAddForm, TestMailForm
from weblate.wladmin.models import BackupService, ConfigurationError, SupportStatus
from weblate.wladmin.tasks import backup_service, configuration_health_check

MENU = (
    ("index", "manage", gettext_lazy("Weblate status")),
    ("backups", "manage-backups", gettext_lazy("Backups")),
    ("memory", "manage-memory", gettext_lazy("Translation memory")),
    ("performance", "manage-performance", gettext_lazy("Performance report")),
    ("ssh", "manage-ssh", gettext_lazy("SSH keys")),
    ("alerts", "manage-alerts", gettext_lazy("Alerts")),
    ("repos", "manage-repos", gettext_lazy("Repositories")),
    ("users", "manage-users", gettext_lazy("Users")),
    ("tools", "manage-tools", gettext_lazy("Tools")),
)


@management_access
def manage(request):
    support = SupportStatus.objects.get_current()
    return render(
        request,
        "manage/index.html",
        {
            "menu_items": MENU,
            "menu_page": "index",
            "support": support,
            "activate_form": ActivateForm(),
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
    context = {
        "components": Component.objects.order_project(),
        "menu_items": MENU,
        "menu_page": "repos",
    }
    return render(request, "manage/repos.html", context)


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
    configuration_health_check(checks)

    context = {
        "checks": [check for check in checks if not check.is_silenced()],
        "errors": ConfigurationError.objects.filter(ignored=False),
        "queues": get_queue_stats().items(),
        "menu_items": MENU,
        "menu_page": "performance",
    }

    return render(request, "manage/performance.html", context)


@management_access
def ssh_key(request):
    with open(ssh_file(RSA_KEY), "r") as handle:
        data = handle.read()
    response = HttpResponse(data, content_type="text/plain")
    response["Content-Disposition"] = "attachment; filename={0}".format(RSA_KEY)
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
        "alerts": Alert.objects.order_by("name").prefetch_related(
            "component", "component__project"
        ),
        "no_components": Project.objects.annotate(Count("component")).filter(
            component__count=0
        ),
        "menu_items": MENU,
        "menu_page": "alerts",
    }

    return render(request, "manage/alerts.html", context)


@management_access
def users(request):
    invite_form = InviteUserForm()

    if request.method == "POST":
        if "email" in request.POST:
            invite_form = InviteUserForm(request.POST)
            if invite_form.is_valid():
                invite_form.save(request)
                messages.success(request, _("User has been invited to this project."))
                return redirect("manage-users")

    return render(
        request,
        "manage/users.html",
        {"menu_items": MENU, "menu_page": "users", "invite_form": invite_form},
    )
