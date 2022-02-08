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

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils.translation import gettext_lazy as _

from weblate.trans.defines import EMAIL_LENGTH
from weblate.utils import forms
from weblate.utils.validators import validate_email


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
    description = _("E-mail")
    default_error_messages = {"unique": _("A user with this e-mail already exists.")}

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
