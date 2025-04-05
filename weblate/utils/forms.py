# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Literal

from crispy_forms.layout import Div, Field
from crispy_forms.utils import TEMPLATE_PACK
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms.models import ModelChoiceIterator
from django.template.loader import render_to_string
from django.utils.translation import gettext, gettext_lazy
from pyparsing import ParseException

from weblate.formats.helpers import CONTROLCHARS
from weblate.trans.defines import EMAIL_LENGTH, USERNAME_LENGTH
from weblate.trans.filter import FILTERS
from weblate.trans.util import sort_unicode
from weblate.utils.errors import report_error

from .validators import WeblateServiceURLValidator, validate_email, validate_username


class QueryField(forms.CharField):
    def __init__(
        self, parser: Literal["unit", "user", "superuser"] = "unit", **kwargs
    ) -> None:
        if "label" not in kwargs:
            kwargs["label"] = gettext_lazy("Query")
        if "required" not in kwargs:
            kwargs["required"] = False
        if "widget" not in kwargs:
            kwargs["widget"] = forms.Textarea(attrs={"cols": None, "rows": 1})
        self.parser = parser
        super().__init__(**kwargs)

    def clean(self, value):
        from weblate.utils.search import parse_query

        if not value:
            if self.required:
                raise ValidationError(gettext("Missing query string."))
            return ""
        try:
            parse_query(value, parser=self.parser)
        except (ValueError, ParseException) as error:
            raise ValidationError(
                gettext("Could not parse query string: {}").format(error)
            ) from error
        except Exception as error:
            report_error("Error parsing search query")
            raise ValidationError(
                gettext("Could not parse query string: {}").format(error)
            ) from error
        return value


class UsernameField(forms.CharField):
    default_validators = [validate_username]

    def __init__(
        self,
        *,
        max_length: int | None = None,
        min_length: int | None = None,
        strip: bool = True,
        empty_value: str = "",
        **kwargs,
    ) -> None:
        params = {
            "max_length": USERNAME_LENGTH,
            "help_text": gettext_lazy(
                "Username may only contain letters, "
                "numbers or the following characters: @ . + - _"
            ),
            "label": gettext_lazy("Username"),
            "required": True,
        }
        params.update(kwargs)
        self.valid = None

        super().__init__(
            max_length=max_length,
            min_length=min_length,
            strip=strip,
            empty_value=empty_value,
            **kwargs,
        )


class UserField(forms.CharField):
    def __init__(
        self,
        queryset=None,
        empty_label="---------",
        to_field_name=None,
        limit_choices_to=None,
        blank=None,
        **kwargs,
    ) -> None:
        # This swallows some parameters to mimic ModelChoiceField API
        super().__init__(**kwargs)

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        attrs["dir"] = "ltr"
        attrs["class"] = "user-autocomplete"
        attrs["spellcheck"] = "false"
        attrs["autocorrect"] = "off"
        attrs["autocomplete"] = "off"
        attrs["autocapitalize"] = "off"
        return attrs

    def clean(self, value):
        from weblate.auth.models import User

        if not value:
            if self.required:
                raise ValidationError(gettext("Missing username or e-mail."))
            return None
        if any(char in value for char in CONTROLCHARS):
            raise ValidationError(
                gettext("String contains control character: %s") % repr(value)
            )
        try:
            return User.objects.get(Q(username=value) | Q(email=value))
        except User.DoesNotExist as error:
            raise ValidationError(gettext("Could not find any such user.")) from error
        except User.MultipleObjectsReturned as error:
            raise ValidationError(gettext("More possible users were found.")) from error


class EmailField(forms.EmailField):
    """
    Slightly restricted EmailField.

    We block some additional local parts and customize error messages.
    """

    default_validators = [validate_email]

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("max_length", EMAIL_LENGTH)
        super().__init__(*args, **kwargs)


class SortedChoiceWidget(forms.widgets.ChoiceWidget):
    """Wrapper class to sort choices alphabetically."""

    def optgroups(self, name, value, attrs=None):
        groups = super().optgroups(name, value, attrs)
        return sort_unicode(groups, lambda val: str(val[1][0]["label"]))


class SortedSelect(SortedChoiceWidget, forms.Select):
    """Wrapper class to sort choices alphabetically."""


class ColorWidget(forms.RadioSelect):
    def __init__(self, attrs=None, choices=()) -> None:
        attrs = {**(attrs or {}), "class": "color_edit"}
        super().__init__(attrs, choices)


class SortedSelectMultiple(SortedSelect, forms.SelectMultiple):
    """Wrapper class to sort choices alphabetically."""


class ContextDiv(Div):
    def __init__(self, *fields, **kwargs) -> None:
        self.context = kwargs.pop("context", {})
        super().__init__(*fields, **kwargs)

    def render(self, form, context, template_pack=TEMPLATE_PACK, **kwargs):
        template = self.get_template_name(template_pack)
        return render_to_string(template, self.context)


class SearchField(Field):
    def __init__(self, *args, **kwargs) -> None:
        kwargs["template"] = "snippets/query-field.html"
        super().__init__(*args, **kwargs)

    def render(self, form, context, template_pack=TEMPLATE_PACK, **kwargs):
        extra_context = {"custom_filter_list": self.get_search_query_choices()}
        return super().render(form, context, template_pack, extra_context, **kwargs)

    def get_search_query_choices(self):
        """Return all filtering choices for query field."""
        filter_keys = [
            "nottranslated",
            "todo",
            "translated",
            "fuzzy",
            "suggestions",
            "variants",
            "screenshots",
            "labels",
            "context",
            "nosuggestions",
            "comments",
            "allchecks",
            "approved",
            "unapproved",
        ]
        return [
            (key, FILTERS.get_filter_name(key), FILTERS.get_filter_query(key))
            for key in filter_keys
        ]


class CachedQueryIterator(ModelChoiceIterator):
    """
    Choice iterator for cached querysets.

    It assumes the queryset is reused and avoids using an iterator or counting queries.
    """

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)
        for obj in self.queryset:
            yield self.choice(obj)

    def __len__(self) -> int:
        return len(self.queryset) + (1 if self.field.empty_label is not None else 0)

    def __bool__(self) -> bool:
        return self.field.empty_label is not None or bool(self.queryset)


class CachedModelChoiceField(forms.ModelChoiceField):
    iterator = CachedQueryIterator

    def _get_queryset(self):
        return self._queryset

    def _set_queryset(self, queryset) -> None:
        self._queryset = queryset
        self.widget.choices = self.choices

    queryset = property(_get_queryset, _set_queryset)


class CachedModelMultipleChoiceField(
    CachedModelChoiceField, forms.ModelMultipleChoiceField
):
    pass


class WeblateServiceURLField(forms.URLField):
    default_validators = [WeblateServiceURLValidator()]
