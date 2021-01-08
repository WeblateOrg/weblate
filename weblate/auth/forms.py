#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from django import forms
from django.conf import settings
from django.http import HttpRequest
from social_django.views import complete

from weblate.accounts.forms import UniqueEmailMixin
from weblate.accounts.models import AuditLog
from weblate.accounts.strategy import create_session
from weblate.accounts.views import store_userid
from weblate.auth.models import User, get_anonymous
from weblate.trans.models import Change


def send_invitation(request: HttpRequest, project_name: str, user: User):
    """Send invitation to user to join project."""
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
    complete(fake, "email")


class InviteUserForm(forms.ModelForm, UniqueEmailMixin):
    class Meta:
        model = User
        fields = ["email", "username", "full_name"]

    def save(self, request, project=None):
        self.instance.set_unusable_password()
        user = super().save()
        if project:
            project.add_user(user)
        Change.objects.create(
            project=project,
            action=Change.ACTION_INVITE_USER,
            user=request.user,
            details={"username": user.username},
        )
        AuditLog.objects.create(
            user=user,
            request=request,
            activity="invited",
            username=request.user.username,
        )
        send_invitation(request, project.name if project else settings.SITE_TITLE, user)


class AdminInviteUserForm(InviteUserForm):
    class Meta:
        model = User
        fields = ["email", "username", "full_name", "is_superuser"]
