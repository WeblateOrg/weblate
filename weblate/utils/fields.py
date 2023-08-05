# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils.translation import gettext_lazy

from weblate.trans.defines import EMAIL_LENGTH
from weblate.utils import forms
from weblate.utils.validators import validate_email


# TODO: Drop this in Weblate 5.1
def migrate_json_field(model, db_alias: str, field: str):
    """Migration from custom JSONField to Django native one."""
    updates = []
    new_field = f"{field}_new"

    for obj in model.objects.using(db_alias).iterator():
        value = getattr(obj, field)
        # Skip anything blank, it is the default value of the field
        if not value:
            continue

        setattr(obj, new_field, value)
        updates.append(obj)
        if len(updates) > 1000:
            model.objects.using(db_alias).bulk_update(updates, [new_field])
            updates = []

    if updates:
        model.objects.using(db_alias).bulk_update(updates, [new_field])
        updates = []


# TODO: Drop this in Weblate 5.1
class JSONField(models.TextField):
    """JSON serializaed TextField."""

    def __init__(self, **kwargs):
        if "default" not in kwargs:
            kwargs["default"] = {}
        super().__init__(**kwargs)

    def to_python(self, value):
        """Convert a string from the database to a Python value."""
        if not value:
            return None
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value

    def get_prep_value(self, value):
        """Convert the value to a string that can be stored in the database."""
        if not value:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value, cls=DjangoJSONEncoder)
        return super().get_prep_value(value)

    def from_db_value(self, value, *args, **kwargs):
        return self.to_python(value)

    def get_db_prep_save(self, value, *args, **kwargs):
        if value is None:
            value = {}
        return json.dumps(value, cls=DjangoJSONEncoder)

    def value_from_object(self, obj):
        value = super().value_from_object(obj)
        return json.dumps(value, cls=DjangoJSONEncoder)


class CaseInsensitiveFieldMixin:
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


class UsernameField(CaseInsensitiveFieldMixin, models.CharField):
    pass


class EmailField(CaseInsensitiveFieldMixin, models.CharField):
    default_validators = [validate_email]
    description = gettext_lazy("E-mail")
    default_error_messages = {
        "unique": gettext_lazy("A user with this e-mail already exists.")
    }

    def __init__(self, *args, **kwargs):
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
