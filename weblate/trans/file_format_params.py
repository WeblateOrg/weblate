# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal, TypedDict, Unpack, cast

from django import forms
from django.utils.functional import classproperty
from django.utils.translation import gettext_lazy
from translate.storage.lisa import LISAfile

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django_stubs_ext import StrOrPromise
    from translate.storage.base import TranslationStore
    from translate.storage.jsonl10n import JsonFile
    from translate.storage.pypo import pofile
    from translate.storage.yaml import YAMLFile


class FieldKwargsDict(TypedDict, total=False):
    min_value: int
    max_value: int
    min_length: int


class FileFormatParams(TypedDict, total=False):
    json_sort_keys: bool
    json_indent: int
    json_indent_style: Literal["spaces", "tabs"]
    json_use_compact_separators: bool
    po_line_wrap: int
    po_keep_previous: bool
    po_no_location: bool
    po_fuzzy_matching: bool
    yaml_indent: int
    yaml_line_wrap: int
    yaml_line_break: str
    xml_closing_tags: bool
    flatxml_root_name: str
    flatxml_value_name: str
    flatxml_key_name: str
    strings_encoding: str
    properties_encoding: str
    csv_encoding: str
    csv_simple_encoding: str
    gwt_encoding: str
    markdown_merge_duplicates: bool
    html_merge_duplicates: bool
    txt_merge_duplicates: bool


class BaseFileFormatParam:
    name: Literal[
        "json_sort_keys",
        "json_indent",
        "json_indent_style",
        "json_use_compact_separators",
        "po_line_wrap",
        "po_keep_previous",
        "po_no_location",
        "po_fuzzy_matching",
        "yaml_indent",
        "yaml_line_wrap",
        "yaml_line_break",
        "xml_closing_tags",
        "flatxml_root_name",
        "flatxml_value_name",
        "flatxml_key_name",
        "strings_encoding",
        "properties_encoding",
        "csv_encoding",
        "csv_simple_encoding",
        "gwt_encoding",
        "markdown_merge_duplicates",
        "html_merge_duplicates",
        "txt_merge_duplicates",
    ]
    file_formats: Sequence[str] = []
    field_class: type[forms.Field] = forms.CharField
    label: StrOrPromise = ""
    default: str | int | bool
    field_kwargs: ClassVar[FieldKwargsDict] = {}
    choices: ClassVar[list[tuple[str | int, StrOrPromise]] | None] = None
    help_text: StrOrPromise | None = None

    @classmethod
    def get_identifier(cls) -> str:
        return cls.name

    def get_field(self) -> forms.Field:
        widget = self.field_class.widget(attrs=self.get_widget_attrs())
        return self.field_class(widget=widget, **self.get_field_kwargs())

    def get_widget_attrs(self) -> dict:
        field_classes = ["file-format-param-field"]

        if self.field_class == forms.BooleanField:
            field_classes.append("form-check-input")
        else:
            field_classes.append("form-control")

        return {
            "label": self.label,
            "fileformats": " ".join(self.file_formats),
            "class": " ".join(field_classes),
        }

    def get_field_kwargs(self) -> dict:
        kwargs = cast("dict", self.field_kwargs.copy())
        kwargs.update({"required": False, "initial": self.default})
        if self.choices is not None:
            kwargs["choices"] = self.choices
        if self.help_text:
            kwargs["help_text"] = self.help_text
        return kwargs

    def setup_store(
        self, store: TranslationStore, **file_format_params: Unpack[FileFormatParams]
    ) -> None:
        """Configure store with this file format parameters."""

    @classmethod
    def get_value(cls, file_format_params: FileFormatParams):
        value = file_format_params.get(cls.name, cls.default)
        type_cast = type(cls.default)
        try:
            return type_cast(value)
        except (ValueError, TypeError):
            return cls.default

    @classmethod
    def is_encoding(cls):
        return cls.name.endswith("_encoding")


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


def get_default_params_for_file_format(file_format: str) -> FileFormatParams:
    """Get default values for all registered file format parameters."""
    params = get_params_for_file_format(file_format)
    return cast("FileFormatParams", {param.name: param.default for param in params})


def strip_unused_file_format_params(
    file_format: str, file_format_params: FileFormatParams
) -> FileFormatParams:
    """Clean file format parameters, removing those not applicable to the given file format."""
    for param in FILE_FORMATS_PARAMS:
        if file_format not in param.file_formats:
            file_format_params.pop(param.name, None)
    return file_format_params


def get_param_for_name(name: str) -> type[BaseFileFormatParam]:
    """Get parameter class for given name."""
    for param in FILE_FORMATS_PARAMS:
        if param.name == name:
            return param
    msg = f"Unknown parameter: {name}"
    raise ValueError(msg)


def get_encoding_param(file_format_params: FileFormatParams | None) -> str | None:
    """Get encoding parameter from file format parameters."""
    if file_format_params is None:
        file_format_params = {}
    for param_name, value in file_format_params.items():
        try:
            if get_param_for_name(param_name).is_encoding():
                return cast("str", value)
        except ValueError:
            continue
    return None


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

    def setup_store(
        self, store: TranslationStore, **file_format_params: Unpack[FileFormatParams]
    ) -> None:
        # TODO: Type annotation will be fixed upstream via https://github.com/translate/translate/pull/5999
        cast("JsonFile", store).dump_args["sort_keys"] = self.get_value(
            file_format_params
        )


@register_file_format_param
class JSONOutputIndentation(JSONOutputCustomizationBaseParam):
    name = "json_indent"
    label = gettext_lazy("JSON indentation")
    field_class = forms.IntegerField
    default = 4
    field_kwargs: ClassVar[FieldKwargsDict] = {"min_value": 0}


@register_file_format_param
class JSONOutputIndentStyle(JSONOutputCustomizationBaseParam):
    name = "json_indent_style"
    label = gettext_lazy("JSON indentation style")
    field_class = forms.ChoiceField
    choices: ClassVar[list[tuple[str | int, StrOrPromise]] | None] = [
        ("spaces", gettext_lazy("Spaces")),
        ("tabs", gettext_lazy("Tabs")),
    ]
    default = "spaces"

    def setup_store(
        self, store: TranslationStore, **file_format_params: Unpack[FileFormatParams]
    ) -> None:
        indent = JSONOutputIndentation.get_value(file_format_params)
        dump_args = cast("JsonFile", store).dump_args
        if self.get_value(file_format_params) == "tabs":
            dump_args["indent"] = "\t" * indent
        else:
            dump_args["indent"] = indent


@register_file_format_param
class JSONOutputCompactSeparators(JSONOutputCustomizationBaseParam):
    name = "json_use_compact_separators"
    label = gettext_lazy("Avoid spaces after separators")
    field_class = forms.BooleanField
    default = False

    def setup_store(
        self, store: TranslationStore, **file_format_params: Unpack[FileFormatParams]
    ) -> None:
        dump_args = cast("JsonFile", store).dump_args
        use_compact_separators = self.get_value(file_format_params)
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
    choices: ClassVar[list[tuple[str | int, StrOrPromise]] | None] = [
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
        "By default, gettext wraps lines at 77 characters and at newlines. "
        "With the --no-wrap parameter, wrapping is only done at newlines."
    )

    def setup_store(
        self, store: TranslationStore, **file_format_params: Unpack[FileFormatParams]
    ) -> None:
        cast("pofile", store).wrapper.width = int(self.get_value(file_format_params))


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
    field_kwargs: ClassVar[FieldKwargsDict] = {"min_value": 1, "max_value": 10}

    def setup_store(
        self, store: TranslationStore, **file_format_params: Unpack[FileFormatParams]
    ) -> None:
        cast("YAMLFile", store).dump_args["indent"] = int(  # type: ignore[assignment]
            self.get_value(file_format_params)
        )


@register_file_format_param
class YAMLLineWrap(BaseYAMLFormatParam):
    name = "yaml_line_wrap"
    label = gettext_lazy("Long lines wrapping")
    field_class = forms.ChoiceField
    default = 80
    choices: ClassVar[list[tuple[str | int, StrOrPromise]] | None] = [
        (80, gettext_lazy("Wrap lines at 80 chars")),
        (100, gettext_lazy("Wrap lines at 100 chars")),
        (120, gettext_lazy("Wrap lines at 120 chars")),
        (180, gettext_lazy("Wrap lines at 180 chars")),
        (65535, gettext_lazy("No line wrapping")),
    ]

    def setup_store(
        self, store: TranslationStore, **file_format_params: Unpack[FileFormatParams]
    ) -> None:
        cast("YAMLFile", store).dump_args["width"] = int(  # type: ignore[assignment]
            self.get_value(file_format_params)
        )


@register_file_format_param
class YAMLLineBreak(BaseYAMLFormatParam):
    name = "yaml_line_break"
    label = gettext_lazy("Line breaks")
    field_class = forms.ChoiceField
    choices: ClassVar[list[tuple[str | int, StrOrPromise]] | None] = [
        ("dos", gettext_lazy("DOS (\\r\\n)")),
        ("unix", gettext_lazy("UNIX (\\n)")),
        ("mac", gettext_lazy("MAC (\\r)")),
    ]
    default = "unix"

    def setup_store(
        self, store: TranslationStore, **file_format_params: Unpack[FileFormatParams]
    ) -> None:
        breaks = {"dos": "\r\n", "mac": "\r", "unix": "\n"}
        line_break = self.get_value(file_format_params)
        cast("YAMLFile", store).dump_args["line_break"] = breaks[line_break]  # type: ignore[assignment]


@register_file_format_param
class XMLClosingTags(BaseFileFormatParam):
    name = "xml_closing_tags"
    label = gettext_lazy("Include closing tag for blank XML tags")
    field_class = forms.BooleanField
    default = False

    @classproperty
    def file_formats(self) -> Sequence[str]:
        from weblate.formats.models import FILE_FORMATS

        result = []
        for file_format, format_class in FILE_FORMATS.items():
            store_class = format_class.get_class()
            if store_class and issubclass(store_class, LISAfile):
                result.append(file_format)
        return result

    def setup_store(
        self, store: TranslationStore, **file_format_params: Unpack[FileFormatParams]
    ) -> None:
        cast("LISAfile", store).XMLSelfClosingTags = not self.get_value(
            file_format_params
        )


class BaseFlatXMLFormatParam(BaseFileFormatParam):
    file_formats = ("flatxml",)


@register_file_format_param
class FlatXMLRootName(BaseFlatXMLFormatParam):
    name = "flatxml_root_name"
    label = gettext_lazy("FlatXML Root name")
    field_class = forms.CharField
    default = "root"
    field_kwargs: ClassVar[FieldKwargsDict] = {"min_length": 1}


@register_file_format_param
class FlatXMLValueName(BaseFlatXMLFormatParam):
    name = "flatxml_value_name"
    label = gettext_lazy("FlatXML value name")
    field_class = forms.CharField
    default = "str"
    field_kwargs: ClassVar[FieldKwargsDict] = {"min_length": 1}


@register_file_format_param
class FlatXMLKeyName(BaseFlatXMLFormatParam):
    name = "flatxml_key_name"
    label = gettext_lazy("FlatXML key name")
    field_class = forms.CharField
    default = "key"
    field_kwargs: ClassVar[FieldKwargsDict] = {"min_length": 1}


@register_file_format_param
class MarkdownMergeDuplicates(BaseFileFormatParam):
    file_formats = ("markdown",)
    name = "markdown_merge_duplicates"
    label = gettext_lazy("Deduplicate identical strings")
    field_class = forms.BooleanField
    default = False
    help_text = gettext_lazy(
        "Consolidates identical source strings into a single translation unit. "
        "Prevents translation loss during file restructuring or table reordering "
        "by removing position-dependent context."
    )


@register_file_format_param
class HTMLMergeDuplicates(BaseFileFormatParam):
    file_formats = ("html",)
    name = "html_merge_duplicates"
    label = gettext_lazy("Deduplicate identical strings")
    field_class = forms.BooleanField
    default = False
    help_text = gettext_lazy(
        "Consolidates identical source strings into a single translation unit. "
        "Prevents translation loss during file restructuring "
        "by removing position-dependent context."
    )


@register_file_format_param
class TxtMergeDuplicates(BaseFileFormatParam):
    file_formats = ("txt", "dokuwiki", "mediawiki")
    name = "txt_merge_duplicates"
    label = gettext_lazy("Deduplicate identical strings")
    field_class = forms.BooleanField
    default = False
    help_text = gettext_lazy(
        "Consolidates identical source strings into a single translation unit. "
        "Prevents translation loss during file restructuring "
        "by removing position-dependent context."
    )


@register_file_format_param
class StringsEncoding(BaseFileFormatParam):
    file_formats = ("strings",)
    name = "strings_encoding"
    label = gettext_lazy("File encoding")
    field_class = forms.ChoiceField
    choices: ClassVar[list[tuple[str | int, StrOrPromise]] | None] = [
        ("utf-16", gettext_lazy("UTF-16")),
        ("utf-8", gettext_lazy("UTF-8")),
    ]
    default = "utf-16"
    help_text = gettext_lazy("Encoding used for iOS strings files")


@register_file_format_param
class PropertiesEncoding(BaseFileFormatParam):
    file_formats = (
        "properties",
        "xwiki-page-properties",
    )
    name = "properties_encoding"
    label = gettext_lazy("File encoding")
    field_class = forms.ChoiceField
    choices: ClassVar[list[tuple[str | int, StrOrPromise]] | None] = [
        ("iso-8859-1", gettext_lazy("ISO-8859-1")),
        ("utf-8", gettext_lazy("UTF-8")),
        ("utf-16", gettext_lazy("UTF-16")),
    ]
    default = "iso-8859-1"
    help_text = gettext_lazy("Encoding used for Java Properties files")


@register_file_format_param
class CSVEncoding(BaseFileFormatParam):
    file_formats = ("csv", "csv-multi")
    name = "csv_encoding"
    label = gettext_lazy("File encoding")
    field_class = forms.ChoiceField
    choices: ClassVar[list[tuple[str | int, StrOrPromise]] | None] = [
        ("auto", gettext_lazy("Auto-detect")),
        ("utf-8", gettext_lazy("UTF-8")),
    ]
    default = "auto"
    help_text = gettext_lazy("Encoding used for CSV files")


@register_file_format_param
class CSVSimpleEncoding(BaseFileFormatParam):
    file_formats = ("csv-simple",)
    name = "csv_simple_encoding"
    label = gettext_lazy("File encoding")
    field_class = forms.ChoiceField
    choices: ClassVar[list[tuple[str | int, StrOrPromise]] | None] = [
        ("auto", gettext_lazy("Auto-detect")),
        ("utf-8", gettext_lazy("UTF-8")),
        ("iso-8859-1", gettext_lazy("ISO-8859-1")),
    ]
    default = "auto"
    help_text = gettext_lazy("Encoding used for simple CSV files")


@register_file_format_param
class GWTEncoding(BaseFileFormatParam):
    name = "gwt_encoding"
    file_formats = ("gwt",)
    label = gettext_lazy("File encoding")
    field_class = forms.ChoiceField
    choices: ClassVar[list[tuple[str | int, StrOrPromise]] | None] = [
        ("utf-8", gettext_lazy("UTF-8")),
        ("iso-8859-1", gettext_lazy("ISO-8859-1")),
    ]
    default = "utf-8"
    help_text = gettext_lazy("Encoding used for GWT Properties files")
