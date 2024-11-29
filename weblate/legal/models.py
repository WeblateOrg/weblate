# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, cast

from appconf import AppConf
from django.conf import settings
from django.db import models

from weblate.accounts.models import AuditLog
from weblate.utils.request import get_ip_address, get_user_agent

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest

if "wllegal" in settings.INSTALLED_APPS:
    import wllegal.models

    DEFAULT_TOS_DATE = wllegal.models.LEGAL_TOS_DATE
else:
    DEFAULT_TOS_DATE = date(2017, 7, 2)


class WeblateLegalConf(AppConf):
    # Current TOS date
    LEGAL_TOS_DATE = DEFAULT_TOS_DATE

    class Meta:
        prefix = ""


class Agreement(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, unique=True, on_delete=models.deletion.CASCADE
    )
    tos = models.DateField(default=date(1970, 1, 1))
    address = models.GenericIPAddressField(null=True)
    user_agent = models.CharField(max_length=200, default="")
    timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "TOS agreement"
        verbose_name_plural = "TOS agreements"

    def __str__(self) -> str:
        return f"{self.user.username}:{self.tos}"

    @staticmethod
    def current_tos_date() -> date:
        return cast(
            "date",
            settings.LEGAL_TOS_DATE,  # type: ignore[misc]
        )

    def is_current(self):
        return self.tos == self.current_tos_date()

    def make_current(self, request: AuthenticatedHttpRequest) -> None:
        if not self.is_current():
            AuditLog.objects.create(
                self.user, request, "tos", date=self.current_tos_date().isoformat()
            )
            self.tos = self.current_tos_date()
            self.address = get_ip_address(request)
            self.user_agent = get_user_agent(request)
            self.save()
