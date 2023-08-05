# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from crispy_forms.layout import Div, Field
from crispy_forms.utils import TEMPLATE_PACK
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils.translation import gettext, gettext_lazy

from weblate.trans.defines import EMAIL_LENGTH, USERNAME_LENGTH
from weblate.trans.filter import FILTERS
from weblate.trans.util import sort_unicode
from weblate.utils.search import parse_query
from weblate.utils.validators import validate_email, validate_username


class QueryField(forms.CharField):
    def __init__(self, parser: str = "unit", **kwargs):
        if "label" not in kwargs:
            kwargs["label"] = gettext("Query")
        if "required" not in kwargs:
            kwargs["required"] = False
        self.parser = parser
        super().__init__(**kwargs)

    def clean(self, value):
        if not value:
            if self.required:
                raise ValidationError(gettext("Missing query string."))
            return ""
        try:
            parse_query(value, parser=self.parser)
        except Exception as error:
            raise ValidationError(
                gettext("Could not parse query string: {}").format(error)
            ) from error
        return value


class UsernameField(forms.CharField):
    default_validators = [validate_username]

    def __init__(self, *args, **kwargs):
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

        super().__init__(*args, **params)


class UserField(forms.CharField):
    def __init__(
        self,
        queryset=None,
        empty_label="---------",
        to_field_name=None,
        limit_choices_to=None,
        blank=None,
        **kwargs,
    ):
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
        try:
            return User.objects.get(Q(username=value) | Q(email=value))
        except User.DoesNotExist:
            raise ValidationError(gettext("Could not find any such user."))
        except User.MultipleObjectsReturned:
            raise ValidationError(gettext("More possible users were found."))


class EmailField(forms.EmailField):
    """
    Slightly restricted EmailField.

    We blacklist some additional local parts and customize error messages.
    """

    default_validators = [validate_email]

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", EMAIL_LENGTH)
        super().__init__(*args, **kwargs)


class SortedSelectMixin:
    """Mixin for Select widgets to sort choices alphabetically."""

    def optgroups(self, name, value, attrs=None):
        groups = super().optgroups(name, value, attrs)
        return sort_unicode(groups, lambda val: str(val[1][0]["label"]))


class ColorWidget(forms.RadioSelect):
    def __init__(self, attrs=None, choices=()):
        attrs = {**(attrs or {}), "class": "color_edit"}
        super().__init__(attrs, choices)


class SortedSelectMultiple(SortedSelectMixin, forms.SelectMultiple):
    """Wrapper class to sort choices alphabetically."""


class SortedSelect(SortedSelectMixin, forms.Select):
    """Wrapper class to sort choices alphabetically."""


class ContextDiv(Div):
    def __init__(self, *fields, **kwargs):
        self.context = kwargs.pop("context", {})
        super().__init__(*fields, **kwargs)

    def render(self, form, context, template_pack=TEMPLATE_PACK, **kwargs):
        template = self.get_template_name(template_pack)
        return render_to_string(template, self.context)


class SearchField(Field):
    def __init__(self, *args, **kwargs):
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


class FilterForm(forms.Form):
    project = forms.SlugField(required=False)
    component = forms.SlugField(required=False)
    lang = forms.SlugField(required=False)
    user = UsernameField(required=False)
