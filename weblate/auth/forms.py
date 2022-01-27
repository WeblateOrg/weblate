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

import social_core.backends.utils
from django import forms
from django.conf import settings
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from social_core.backends.email import EmailAuth
from social_django.views import complete

from weblate.accounts.forms import UniqueEmailMixin
from weblate.accounts.models import AuditLog
from weblate.accounts.strategy import create_session
from weblate.auth.data import SELECTION_MANUAL
from weblate.auth.models import Group, User, get_anonymous
from weblate.trans.models import Change
from weblate.utils import messages
from weblate.utils.errors import report_error


def send_invitation(request: HttpRequest, project_name: str, user: User):
    """Send invitation to user to join project."""
    from weblate.accounts.views import store_userid

    fake = HttpRequest()
    fake.user = get_anonymous()
    fake.method = "POST"
    fake.session = create_session()
    fake.session["invitation_context"] = {
        "from_user": request.user.full_name,
        "project_name": project_name,
    }
    fake.POST["email"] = user.email
    fake.META = request.META
    store_userid(fake, invite=True)

    # Make sure the email backend is there for the invitation
    email_auth = "social_core.backends.email.EmailAuth"
    has_email = email_auth in settings.AUTHENTICATION_BACKENDS
    backup_backends = settings.AUTHENTICATION_BACKENDS
    backup_cache = social_core.backends.utils.BACKENDSCACHE
    if not has_email:
        social_core.backends.utils.BACKENDSCACHE["email"] = EmailAuth
        settings.AUTHENTICATION_BACKENDS += (email_auth,)

    # Send invitation
    complete(fake, "email")

    # Revert temporary settings override
    if not has_email:
        social_core.backends.utils.BACKENDSCACHE = backup_cache
        settings.AUTHENTICATION_BACKENDS = backup_backends


class InviteUserForm(forms.ModelForm, UniqueEmailMixin):
    create = True

    class Meta:
        model = User
        fields = ["email", "username", "full_name"]

    def save(self, request, project=None):
        self.instance.set_unusable_password()
        user = super().save()
        if project:
            project.add_user(user)
        send_email = self.cleaned_data.get("send_email", True)
        if self.create:
            Change.objects.create(
                project=project,
                action=Change.ACTION_INVITE_USER,
                user=request.user,
                details={"username": user.username},
            )
        if self.create or send_email:
            AuditLog.objects.create(
                user=user,
                request=request,
                activity="invited",
                username=request.user.username,
            )
        if send_email:
            try:
                send_invitation(
                    request, project.name if project else settings.SITE_TITLE, user
                )
                messages.success(request, _("User invitation e-mail was sent."))
            except Exception:
                report_error(cause="Failed to send an invitation")
                raise
        return user


class AdminInviteUserForm(InviteUserForm):
    send_email = forms.BooleanField(
        label=_("Send e-mail invitation to the user"),
        initial=True,
        required=False,
    )

    class Meta:
        model = User
        fields = ["email", "username", "full_name", "is_superuser"]


class UserEditForm(AdminInviteUserForm):
    create = False

    send_email = forms.BooleanField(
        label=_("Resend e-mail invitation to the user"),
        initial=False,
        required=False,
    )

    class Meta:
        model = User
        fields = ["username", "full_name", "email", "is_superuser", "is_active"]


class SimpleGroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ["name", "roles", "language_selection", "languages"]

    def save(self, commit=True, project=None):
        if not commit:
            return super().save(commit=commit)
        if project:
            self.instance.defining_project = project
            self.instance.project_selection = SELECTION_MANUAL

        self.instance.save()

        # Save languages only for manual selection, otherwise
        # it would override logic from Group.save()
        if self.instance.language_selection == SELECTION_MANUAL:
            self._save_m2m()
        if project:
            self.instance.projects.add(project)
        return self.instance
