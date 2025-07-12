# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from collections.abc import Iterable
from typing import Any

from django import forms
from django.utils.translation import gettext_lazy
from django_stubs_ext import StrOrPromise


class BaseFileFormatParam:
    name: str = ""
    file_formats: Iterable[str] = ()
    field_class: type[forms.Field] = forms.CharField
    label: StrOrPromise = ""

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
        return {
            "required": False,
        }


FILE_FORMATS_PARAMS: list[type[BaseFileFormatParam]] = []


def register_file_format_param(
    param_class: type[BaseFileFormatParam],
) -> type[BaseFileFormatParam]:
    """Register a new file format parameter class."""
    if not hasattr(param_class, "name"):
        msg = f"File format parameter class {param_class.__name__} must have a 'name' attribute."
        raise ValueError(msg)
    if param_class.name in [p.get_identifier() for p in FILE_FORMATS_PARAMS]:
        msg = f"File format parameter class {param_class.__name__} with name '{param_class.name}' is already registered."
        raise ValueError(msg)
    FILE_FORMATS_PARAMS.append(param_class)
    return param_class


def load_initial_file_format_params() -> dict[str, Any]:
    """Load initial values for file format parameters."""
    initial_params: dict[str, Any] = {}
    for param_class in FILE_FORMATS_PARAMS:
        param = param_class()
        initial_params[param.get_identifier()] = param.get_field_kwargs().get("initial")
    return initial_params


class JSONOutputCustomizationBaseParam(BaseFileFormatParam):
    file_formats = (
        "json",
        "json-nested",
    )


@register_file_format_param
class JSONOutputSortKeys(JSONOutputCustomizationBaseParam):
    name = "json_sort_keys"
    label = gettext_lazy("Sort JSON keys")
    field_class = forms.BooleanField


@register_file_format_param
class JSONOutputIndentation(JSONOutputCustomizationBaseParam):
    name = "json_indent"
    label = gettext_lazy("JSON indentation")
    field_class = forms.IntegerField

    def get_field_kwargs(self):
        kwargs = super().get_field_kwargs()
        kwargs.update({"min_value": 0, "initial": 4})
        return kwargs


@register_file_format_param
class JSONOutputIndentStyle(JSONOutputCustomizationBaseParam):
    name = "json_ident_style"
    label = gettext_lazy("JSON indentation style")
    field_class = forms.ChoiceField

    def get_field_kwargs(self):
        kwargs = super().get_field_kwargs()
        kwargs.update(
            {
                "choices": [
                    ("spaces", gettext_lazy("Spaces")),
                    ("tabs", gettext_lazy("Tabs")),
                ],
                "initial": "spaces",
            }
        )
        return kwargs


@register_file_format_param
class GettextPoLineWrap(BaseFileFormatParam):
    name = "po_line_wrap"
    file_formats = (
        "po",
        "po-mono",
    )
    label = gettext_lazy("Long lines wrapping")
    field_class = forms.ChoiceField

    def get_field_kwargs(self):
        kwargs = super().get_field_kwargs()
        kwargs.update(
            {
                "choices": [
                    (
                        77,
                        gettext_lazy(
                            "Wrap lines at 77 characters and at newlines (xgettext default)"
                        ),
                    ),
                    (
                        65535,
                        gettext_lazy(
                            "Only wrap lines at newlines (like 'xgettext --no-wrap')"
                        ),
                    ),
                    (-1, gettext_lazy("No line wrapping")),
                ],
                "initial": 77,
                "help_text": gettext_lazy(
                    "By default gettext wraps lines at 77 characters and at newlines. "
                    "With the --no-wrap parameter, wrapping is only done at newlines."
                ),
            }
        )
        return kwargs


@register_file_format_param
class XMLClosingTags(BaseFileFormatParam):
    name = "xml_closing_tags"
    file_formats = ("xml",)
    label = gettext_lazy("Include closing tag for blank XML tags")
    field_class = forms.BooleanField

    def get_field_kwargs(self):
        kwargs = super().get_field_kwargs()
        kwargs.update({"initial": True})
        return kwargs


class BaseYAMLFormatParam(BaseFileFormatParam):
    file_formats = (
        "yaml",
        "ryml",
        "yml",
    )

    def get_widget_attrs(self) -> dict:
        attrs = super().get_widget_attrs()
        attrs["data-file-formats"] = " ".join(self.file_formats)
        return attrs


@register_file_format_param
class YAMLOutputIndentation(BaseYAMLFormatParam):
    name = "yaml_indent"
    label = gettext_lazy("YAML indentation")
    field_class = forms.IntegerField

    def get_field_kwargs(self):
        kwargs = super().get_field_kwargs()
        kwargs.update({"min_value": 0, "max_value": 10, "initial": 2})
        return kwargs


@register_file_format_param
class YAMLLineWrap(BaseYAMLFormatParam):
    name = "yaml_line_wrap"
    label = gettext_lazy("Long lines wrapping")
    field_class = forms.ChoiceField

    def get_field_kwargs(self):
        kwargs = super().get_field_kwargs()
        kwargs.update(
            {
                "choices": [
                    ("80", gettext_lazy("Wrap lines at 80 chars")),
                    ("100", gettext_lazy("Wrap lines at 100 chars")),
                    ("120", gettext_lazy("Wrap lines at 120 chars")),
                    ("180", gettext_lazy("Wrap lines at 180 chars")),
                    ("65535", gettext_lazy("No line wrapping")),
                ],
                "initial": 80,
            }
        )
        return kwargs


@register_file_format_param
class YAMLLineBreak(BaseYAMLFormatParam):
    name = "yaml_line_break"
    label = gettext_lazy("Line breaks")
    field_class = forms.ChoiceField

    def get_field_kwargs(self):
        kwargs = super().get_field_kwargs()
        kwargs.update(
            {
                "choices": [
                    ("dos", gettext_lazy("DOS (\\r\\n)")),
                    ("unix", gettext_lazy("UNIX (\\n)")),
                    ("mac", gettext_lazy("MAC (\\r)")),
                ],
                "initial": "unix",
            }
        )
        return kwargs


class FormParamsWidget(forms.MultiWidget):
    template_name = "bootstrap3/labelled_multiwidget.html"
    subwidget_class = "file-format-param"

    def __init__(
        self,
        widgets: dict[str, forms.Widget],
        fields_order: list[tuple[str, str]],
        attrs=None,
    ):
        self.fields_order = fields_order
        super().__init__(widgets, attrs)

    def decompress(self, value: dict) -> list[Any]:
        value = {**load_initial_file_format_params(), **(value or {})}
        return [value.get(param_name) for param_name in self.fields_order]

    def get_context(self, *args, **kwargs) -> dict[str, Any]:
        context = super().get_context(*args, **kwargs)
        context["subwidget_class"] = self.subwidget_class
        return context


class FormParamsField(forms.MultiValueField):
    def __init__(self, encoder=None, decoder=None, **kwargs):
        fields = []
        subwidgets = {}

        self.fields_order: list[tuple] = []
        for file_param in FILE_FORMATS_PARAMS:
            field = file_param().get_field()
            fields.append(field)
            subwidgets[file_param.get_identifier()] = field.widget
            self.fields_order.append(file_param.get_identifier())

        widget = FormParamsWidget(subwidgets, self.fields_order)
        super().__init__(fields, widget=widget, require_all_fields=False, **kwargs)

    def compress(self, data_list) -> dict:
        compressed_value: dict[str, Any] = {}
        if data_list:
            update_data = {
                param_name: value
                for param_name, value in zip(self.fields_order, data_list, strict=False)
                if value is not None
            }
            compressed_value.update(update_data)
        return compressed_value
