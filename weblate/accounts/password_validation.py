# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from weblate.accounts.models import AuditLog


class CharsPasswordValidator:
    """Validate whether the password is not only whitespace or single char."""

    def validate(self, password, user=None):
        if not password:
            return

        if not password.strip():
            raise ValidationError(
                _("This password consists of only whitespace."),
                code="password_whitespace",
            )
        if not password.strip(password[0]):
            raise ValidationError(
                _("This password is only a single character."),
                code="password_same_chars",
            )

    def get_help_text(self):
        return _(
            "Your password can't consist of a single character or only whitespace."
        )


class PastPasswordsValidator:
    """Validate whether the password was not used before."""

    def validate(self, password, user=None):
        if user is not None:
            passwords = []
            if user.has_usable_password():
                passwords.append(user.password)

            for log in AuditLog.objects.get_past_passwords(user=user):
                if "password" in log.params:
                    passwords.append(log.params["password"])

            for old in passwords:
                if check_password(password, old):
                    raise ValidationError(
                        _("Can not reuse previously used password."),
                        code="password-past",
                    )

    def get_help_text(self):
        return _("Your password can't match a password you have used in the past.")
