# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from collections.abc import Iterable
from typing import Any

from appconf import AppConf
from django import forms
from django.utils.translation import gettext_lazy
from django_stubs_ext import StrOrPromise

from weblate.utils.classloader import ClassLoader


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
        field_class = ""

        if self.field_class != forms.BooleanField:
            # for display reason, the default radio/checkbox input looks better than bootstrap one
            field_class += " form-control"

        return {
            "label": self.label,
            "fileformats": " ".join(self.file_formats),
            "class": field_class,
        }

    def get_field_kwargs(self) -> dict:
        return {
            "required": False,
        }


class JSONOutputCustomizationBaseParam(BaseFileFormatParam):
    file_formats = (
        "json",
        "json-nested",
    )


class JSONOutputSortKeys(JSONOutputCustomizationBaseParam):
    name = "json_sort_keys"
    label = gettext_lazy("Sort JSON keys")
    field_class = forms.BooleanField


class JSONOutputIndentation(JSONOutputCustomizationBaseParam):
    name = "json_indent"
    label = gettext_lazy("JSON indentation")
    field_class = forms.IntegerField

    def get_field_kwargs(self):
        kwargs = super().get_field_kwargs()
        kwargs.update({"min_value": 0, "initial": 4})
        return kwargs


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


class FileFormatParamsLoader(ClassLoader):
    def __init__(self) -> None:
        super().__init__(
            "FILE_FORMAT_PARAMS", construct=True, base_class=BaseFileFormatParam
        )


FILE_FORMATS_PARAMS = FileFormatParamsLoader()


class FileFormatParamsConf(AppConf):
    FILE_FORMAT_PARAMS = (
        "weblate.trans.form_params.GettextPoLineWrap",
        "weblate.trans.form_params.JSONOutputSortKeys",
        "weblate.trans.form_params.JSONOutputIndentation",
        "weblate.trans.form_params.JSONOutputIndentStyle",
    )

    class Meta:
        prefix = ""


class FormParamsWidget(forms.MultiWidget):
    template_name = "bootstrap3/labelled_multiwidget.html"

    def __init__(
        self,
        widgets: dict[str, forms.Widget],
        fields_order: list[tuple[str, str]],
        attrs=None,
    ):
        self.fields_order = fields_order
        super().__init__(widgets, attrs)

    def decompress(self, value: dict) -> list[Any]:
        return [getattr(value, param_name, None) for param_name in self.fields_order]

    def render(self, *args, **kwargs):
        return super().render(*args, **kwargs)

    def get_context(self, name, value, attrs):
        return super().get_context(name, value, attrs)


class FormParamsField(forms.MultiValueField):
    def __init__(self, encoder=None, decoder=None, **kwargs):
        # TODO: handle encoder and decoder
        fields = []
        subwidgets = {}

        self.fields_order: list[tuple] = []
        for file_param in FILE_FORMATS_PARAMS.values():
            field = file_param.get_field()
            fields.append(field)
            subwidgets[file_param.get_identifier()] = field.widget
            self.fields_order.append(file_param.get_identifier())

        widget = FormParamsWidget(subwidgets, self.fields_order)
        super().__init__(fields, widget=widget, require_all_fields=False, **kwargs)

    def compress(self, data_list) -> dict:
        # NOTE: returns a flat dict, with the name of the file format param as key
        # it is assumed that only the param for the current format are stored
        compressed_value: dict[str, dict] = {}
        if data_list:
            # TODO: make sure that the default values for other formats aren't passed as well
            update_data = {
                param_name: value
                for param_name, value in zip(self.fields_order, data_list, strict=False)
                if value is not None
            }
            compressed_value.update(update_data)
        return compressed_value
