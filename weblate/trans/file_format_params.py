# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

from django import forms
from django.utils.functional import classproperty
from django.utils.translation import gettext_lazy
from django_stubs_ext import StrOrPromise
from translate.storage.base import TranslationStore
from translate.storage.lisa import LISAfile

if TYPE_CHECKING:
    from translate.storage.jsonl10n import JsonFile
    from translate.storage.pypo import pofile
    from translate.storage.yaml import YAMLFile


class BaseFileFormatParam:
    name: str = ""
    file_formats: Sequence[str] = []
    field_class: type[forms.Field] = forms.CharField
    label: StrOrPromise = ""
    default: str | int | bool
    field_kwargs: dict = {}
    choices: list[tuple[str | int, StrOrPromise]] | None = None
    help_text: StrOrPromise | None = None

    @classmethod
    def get_identifier(cls) -> str:
        return cls.name

    def get_field(self) -> forms.Field:
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
        if self.help_text:
            kwargs["help_text"] = self.help_text
        return kwargs

    def setup_store(self, store: TranslationStore, **file_format_params) -> None:
        """Configure store with this file format parameters."""


FILE_FORMATS_PARAMS: list[type[BaseFileFormatParam]] = []


def register_file_format_param(
    param_class: type[BaseFileFormatParam],
) -> type[BaseFileFormatParam]:
    """Register a new file format parameter class."""
    FILE_FORMATS_PARAMS.append(param_class)
    return param_class


def get_params_for_file_format(file_format: str) -> list[type[BaseFileFormatParam]]:
    """Get all registered file format parameters for a given file format."""
    return [param for param in FILE_FORMATS_PARAMS if file_format in param.file_formats]


def get_default_params_for_file_format(file_format: str) -> dict[str, str | int | bool]:
    """Get default values for all registered file format parameters."""
    params = get_params_for_file_format(file_format)
    return {param.name: param.default for param in params}


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

    def setup_store(self, store: TranslationStore, **file_format_params) -> None:
        cast("JsonFile", store).dump_args["sort_keys"] = file_format_params.get(
            self.name, self.default
        )


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

    def setup_store(self, store: TranslationStore, **file_format_params) -> None:
        indent = int(
            file_format_params.get(
                JSONOutputIndentation.name, JSONOutputIndentation.default
            )
            or JSONOutputIndentation.default
        )
        dump_args = cast("JsonFile", store).dump_args
        if file_format_params.get(self.name, self.default) == "tabs":
            dump_args["indent"] = "\t" * indent
        else:
            dump_args["indent"] = indent


@register_file_format_param
class JSONOutputCompactSeparators(JSONOutputCustomizationBaseParam):
    name = "json_use_compact_separators"
    label = gettext_lazy("Avoid spaces after separators")
    field_class = forms.BooleanField
    default = False

    def setup_store(self, store: TranslationStore, **file_format_params) -> None:
        dump_args = cast("JsonFile", store).dump_args
        use_compact_separators = file_format_params.get(self.name, self.default)
        dump_args["separators"] = (
            ",",
            ":" if use_compact_separators else ": ",
        )


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
    help_text = gettext_lazy(
        "By default gettext wraps lines at 77 characters and at newlines."
        "With the --no-wrap parameter, wrapping is only done at newlines."
    )

    def setup_store(self, store: TranslationStore, **file_format_params) -> None:
        cast("pofile", store).wrapper.width = int(
            file_format_params.get(self.name, self.default) or self.default
        )


class BaseGettextFormatParam(BaseFileFormatParam):
    file_formats = ("po",)


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

    def setup_store(self, store: TranslationStore, **file_format_params) -> None:
        cast("YAMLFile", store).dump_args["indent"] = int(
            file_format_params.get(self.name, self.default) or self.default
        )


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

    def setup_store(self, store: TranslationStore, **file_format_params) -> None:
        cast("YAMLFile", store).dump_args["width"] = int(
            file_format_params.get(self.name, self.default) or self.default
        )


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

    def setup_store(self, store: TranslationStore, **file_format_params) -> None:
        breaks = {"dos": "\r\n", "mac": "\r", "unix": "\n"}
        line_break = file_format_params.get(self.name, self.default)
        cast("YAMLFile", store).dump_args["line_break"] = breaks[line_break]


@register_file_format_param
class XMLClosingTags(BaseFileFormatParam):
    name = "xml_closing_tags"
    label = gettext_lazy("Include closing tag for blank XML tags")
    field_class = forms.BooleanField
    default = True

    @classproperty
    def file_formats(self) -> Sequence[str]:
        from weblate.formats.models import FILE_FORMATS

        result = []
        for file_format, format_class in FILE_FORMATS.items():
            store_class = format_class.get_class()
            if store_class and issubclass(store_class, LISAfile):
                result.append(file_format)
        return result

    def setup_store(self, store: TranslationStore, **file_format_params) -> None:
        cast("LISAfile", store).XMLSelfClosingTags = not file_format_params.get(
            self.name, self.default
        )
