# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.utils.translation import gettext_lazy
from oauth2_provider.admin import ApplicationAdmin
from oauth2_provider.models import Application

if TYPE_CHECKING:
    from django import forms
    from django.db.models import Field
    from django.http import HttpRequest


class WeblateApplicationAdmin(ApplicationAdmin):
    def formfield_for_choice_field(
        self, db_field: Field, request: HttpRequest, **kwargs: object
    ) -> forms.Field:
        choices = {
            "client_type": [
                (Application.CLIENT_CONFIDENTIAL, gettext_lazy("Confidential")),
                (Application.CLIENT_PUBLIC, gettext_lazy("Public")),
            ],
            "authorization_grant_type": [
                (
                    Application.GRANT_AUTHORIZATION_CODE,
                    gettext_lazy("Authorization code"),
                )
            ],
            "algorithm": [
                (Application.RS256_ALGORITHM, gettext_lazy("RSA with SHA-256"))
            ],
        }
        if db_field.name in choices:
            kwargs["choices"] = choices[db_field.name]
        return super().formfield_for_choice_field(db_field, request, **kwargs)


admin.site.unregister(Application)
admin.site.register(Application, WeblateApplicationAdmin)
