# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.db.models.signals import pre_save
from django.dispatch.dispatcher import receiver

from weblate.auth.models import AuthenticatedHttpRequest, User


def try_get_user(username, list_all=False):
    """Get User object for authentication."""
    method = User.objects.filter if list_all else User.objects.get
    if "@" in username:
        return method(email=username)
    return method(username=username)


class WeblateUserBackend(ModelBackend):
    """Weblate authentication backend."""

    def authenticate(
        self, request: AuthenticatedHttpRequest, username=None, password=None, **kwargs
    ):
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
def disable_anon_user_password_save(sender, instance, **kwargs) -> None:
    """Block setting password for anonymous user."""
    if instance.is_anonymous and instance.has_usable_password():
        msg = "Anonymous user can not have usable password!"
        raise ValueError(msg)
