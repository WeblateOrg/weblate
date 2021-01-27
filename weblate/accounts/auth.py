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

from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.db.models.signals import pre_save
from django.dispatch.dispatcher import receiver

from weblate.auth.models import User


def try_get_user(username, list_all=False):
    """Wrapper to get User object for authentication."""
    if list_all:
        method = User.objects.filter
    else:
        method = User.objects.get
    if "@" in username:
        return method(email=username)
    return method(username=username)


class WeblateUserBackend(ModelBackend):
    """Weblate authentication backend."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        """Prohibit login for anonymous user and allows to login by e-mail."""
        if username == settings.ANONYMOUS_USER_NAME or username is None:
            return None

        try:
            user = try_get_user(username)
            if user.check_password(password):
                return user
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            pass
        return None

    def get_user(self, user_id):
        try:
            user = User.objects.select_related("profile").get(pk=user_id)
        except User.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None


@receiver(pre_save, sender=User)
def disable_anon_user_password_save(sender, instance, **kwargs):
    """Block setting password for anonymous user."""
    if instance.is_anonymous and instance.has_usable_password():
        raise ValueError("Anonymous user can not have usable password!")
