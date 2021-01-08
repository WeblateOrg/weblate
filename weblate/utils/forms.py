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

from crispy_forms.layout import Div, Field
from crispy_forms.utils import TEMPLATE_PACK
from django import forms
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from weblate.trans.defines import USERNAME_LENGTH
from weblate.trans.filter import FILTERS
from weblate.trans.util import sort_unicode
from weblate.utils.validators import validate_username


class UsernameField(forms.CharField):
    default_validators = [validate_username]

    def __init__(self, *args, **kwargs):
        params = {
            "max_length": USERNAME_LENGTH,
            "help_text": _(
                "Username may only contain letters, "
                "numbers or the following characters: @ . + - _"
            ),
            "label": _("Username"),
            "required": True,
        }
        params.update(kwargs)
        self.valid = None

        super().__init__(*args, **params)


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

    def render(self, form, form_style, context, template_pack=TEMPLATE_PACK, **kwargs):
        template = self.get_template_name(template_pack)
        return render_to_string(template, self.context)


class SearchField(Field):
    def __init__(self, *args, **kwargs):
        kwargs["template"] = "snippets/query-field.html"
        super().__init__(*args, **kwargs)

    def render(self, form, form_style, context, template_pack=TEMPLATE_PACK, **kwargs):
        extra_context = {"custom_filter_list": self.get_search_query_choices()}
        return super().render(
            form, form_style, context, template_pack, extra_context, **kwargs
        )

    def get_search_query_choices(self):
        """Return all filtering choices for query field."""
        filter_keys = [
            "nottranslated",
            "todo",
            "translated",
            "fuzzy",
            "suggestions",
            "variants",
            "labels",
            "context",
            "nosuggestions",
            "comments",
            "allchecks",
            "approved",
            "unapproved",
        ]
        result = [
            (key, FILTERS.get_filter_name(key), FILTERS.get_filter_query(key))
            for key in filter_keys
        ]
        return result


class FilterForm(forms.Form):
    project = forms.SlugField(required=False)
    component = forms.SlugField(required=False)
    lang = forms.SlugField(required=False)
    user = UsernameField(required=False)
