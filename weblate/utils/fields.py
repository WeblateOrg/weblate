# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from django.db import models
from django.utils.translation import gettext_lazy

from weblate.trans.defines import EMAIL_LENGTH
from weblate.utils import forms
from weblate.utils.validators import validate_email


class CaseInsensitiveField(models.CharField):
    """Field mixin that uses case-insensitive lookup alternatives if they exist."""

    LOOKUP_CONVERSIONS = {
        "exact": "iexact",
        "contains": "icontains",
        "startswith": "istartswith",
        "endswith": "iendswith",
        "regex": "iregex",
    }

    def get_lookup(self, lookup_name):
        converted = self.LOOKUP_CONVERSIONS.get(lookup_name, lookup_name)
        return super().get_lookup(converted)


class UsernameField(CaseInsensitiveField):
    pass


class EmailField(CaseInsensitiveField):
    default_validators = [validate_email]
    description = gettext_lazy("E-mail")
    default_error_messages = {
        "unique": gettext_lazy("A user with this e-mail already exists.")
    }

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("max_length", EMAIL_LENGTH)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        # We do not exclude max_length if it matches default as we want to change
        # the default in future.
        return name, path, args, kwargs

    def formfield(self, **kwargs):
        # As with CharField, this will cause email validation to be performed
        # twice.
        return super().formfield(
            **{
                "form_class": forms.EmailField,
                **kwargs,
            }
        )
