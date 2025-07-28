# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from collections.abc import Iterable

from django import forms
from django.utils.translation import gettext_lazy
from django_stubs_ext import StrOrPromise


class BaseFileFormatParam:
    name: str = ""
    file_formats: Iterable[str] = ()
    field_class: type[forms.Field] = forms.CharField
    label: StrOrPromise = ""
    default: str | int | bool
    field_kwargs: dict = {}
    choices: list[tuple[str | int, StrOrPromise]] | None = None

    @classmethod
    def get_identifier(cls) -> str:
        return cls.name

    def get_field(self) -> forms.Field:
        # TODO: one improvement could be to define the field in full, initialize it, and just replace the widget attribute after
        widget = self.field_class.widget(attrs=self.get_widget_attrs())
        return self.field_class(widget=widget, **self.get_field_kwargs())

    def get_widget_attrs(self) -> dict:
        field_classes = ["file-format-param-field"]

        if self.field_class != forms.BooleanField:
            # the default radio/checkbox input looks better than bootstrap one
            field_classes.append("form-control")

        return {
            "label": self.label,
            "fileformats": " ".join(self.file_formats),
            "class": " ".join(field_classes),
        }

    def get_field_kwargs(self) -> dict:
        kwargs = self.field_kwargs.copy()
        kwargs.update({"required": False, "initial": self.default})
        if self.choices is not None:
            kwargs["choices"] = self.choices
        return kwargs


FILE_FORMATS_PARAMS: list[type[BaseFileFormatParam]] = []


def register_file_format_param(
    param_class: type[BaseFileFormatParam],
) -> type[BaseFileFormatParam]:
    """Register a new file format parameter class."""
    FILE_FORMATS_PARAMS.append(param_class)
    return param_class


def get_params_for_file_format(file_format: str) -> list[str]:
    """Get all registered file format parameters for a given file format."""
    return [
        param.get_identifier()
        for param in FILE_FORMATS_PARAMS
        if file_format in param.file_formats
    ]


class JSONOutputCustomizationBaseParam(BaseFileFormatParam):
    file_formats = (
        "json",
        "json-nested",
        "webextension",
        "i18next",
        "i18nextv4",
        "arb",
        "go-i18n-json",
        "go-i18n-json-v2",
        "formatjs",
        "gotext",
    )


@register_file_format_param
class JSONOutputSortKeys(JSONOutputCustomizationBaseParam):
    name = "json_sort_keys"
    label = gettext_lazy("Sort JSON keys")
    field_class = forms.BooleanField
    default = False


@register_file_format_param
class JSONOutputIndentation(JSONOutputCustomizationBaseParam):
    name = "json_indent"
    label = gettext_lazy("JSON indentation")
    field_class = forms.IntegerField
    default = 4
    field_kwargs = {"min_value": 0}


@register_file_format_param
class JSONOutputIndentStyle(JSONOutputCustomizationBaseParam):
    name = "json_indent_style"
    label = gettext_lazy("JSON indentation style")
    field_class = forms.ChoiceField
    choices = [
        ("spaces", gettext_lazy("Spaces")),
        ("tabs", gettext_lazy("Tabs")),
    ]
    default = "spaces"


@register_file_format_param
class JSONOutputCompactSeparators(JSONOutputCustomizationBaseParam):
    name = "json_use_compact_separators"
    label = gettext_lazy("Avoid spaces after separators")
    field_class = forms.BooleanField
    default = False


@register_file_format_param
class GettextPoLineWrap(BaseFileFormatParam):
    file_formats = (
        "po",
        "po-mono",
    )
    name = "po_line_wrap"
    label = gettext_lazy("Long lines wrapping")
    field_class = forms.ChoiceField
    choices = [
        (
            77,
            gettext_lazy(
                "Wrap lines at 77 characters and at newlines (xgettext default)"
            ),
        ),
        (
            65535,
            gettext_lazy("Only wrap lines at newlines (like 'xgettext --no-wrap')"),
        ),
        (-1, gettext_lazy("No line wrapping")),
    ]
    default = 77

    def get_field_kwargs(self):
        kwargs = super().get_field_kwargs()
        kwargs["help_text"] = gettext_lazy(
            "By default gettext wraps lines at 77 characters and at newlines. "
            "With the --no-wrap parameter, wrapping is only done at newlines."
        )
        return kwargs


class BaseGettextFormatParam(BaseFileFormatParam):
    file_formats = (
        "po",
        "po-mono",
    )


@register_file_format_param
class GettextKeepPreviousMsgids(BaseGettextFormatParam):
    name = "po_keep_previous"
    label = gettext_lazy("Keep previous msgids of translated strings")
    field_class = forms.BooleanField
    default = True


@register_file_format_param
class GettextNoLocation(BaseGettextFormatParam):
    name = "po_no_location"
    label = gettext_lazy("Do not include location information in the file")
    field_class = forms.BooleanField
    default = False


@register_file_format_param
class GettextFuzzyMatching(BaseGettextFormatParam):
    name = "po_fuzzy_matching"
    label = gettext_lazy("Use fuzzy matching")
    field_class = forms.BooleanField
    default = True


class BaseYAMLFormatParam(BaseFileFormatParam):
    file_formats = (
        "yaml",
        "ruby-yaml",
    )


@register_file_format_param
class YAMLOutputIndentation(BaseYAMLFormatParam):
    name = "yaml_indent"
    label = gettext_lazy("YAML indentation")
    field_class = forms.IntegerField
    default = 2
    field_kwargs = {"min_value": 0, "max_value": 10}


@register_file_format_param
class YAMLLineWrap(BaseYAMLFormatParam):
    name = "yaml_line_wrap"
    label = gettext_lazy("Long lines wrapping")
    field_class = forms.ChoiceField
    default = 80
    choices = [
        (80, gettext_lazy("Wrap lines at 80 chars")),
        (100, gettext_lazy("Wrap lines at 100 chars")),
        (120, gettext_lazy("Wrap lines at 120 chars")),
        (180, gettext_lazy("Wrap lines at 180 chars")),
        (65535, gettext_lazy("No line wrapping")),
    ]


@register_file_format_param
class YAMLLineBreak(BaseYAMLFormatParam):
    name = "yaml_line_break"
    label = gettext_lazy("Line breaks")
    field_class = forms.ChoiceField
    choices = [
        ("dos", gettext_lazy("DOS (\\r\\n)")),
        ("unix", gettext_lazy("UNIX (\\n)")),
        ("mac", gettext_lazy("MAC (\\r)")),
    ]
    default = "unix"
