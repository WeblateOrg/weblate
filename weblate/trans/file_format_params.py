# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar, Literal, TypedDict, Unpack, cast

from django import forms
from django.utils.functional import classproperty
from django.utils.translation import gettext_lazy
from translate.storage.lisa import LISAfile

from weblate.utils.params import (
    BaseParam,
    FieldKwargsDict,
    get_default_params_for_scope,
    get_param_by_name,
    get_params_for_scope,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django_stubs_ext import StrOrPromise
    from translate.storage.base import TranslationStore
    from translate.storage.csvl10n import csvfile
    from translate.storage.jsonl10n import JsonFile
    from translate.storage.pypo import pofile
    from translate.storage.yaml import YAMLFile


class FileFormatParams(TypedDict, total=False):
    json_sort_keys: Literal["none", "case_sensitive", "case_insensitive"]
    json_indent: int
    json_indent_style: Literal["spaces", "tabs"]
    json_use_compact_separators: bool
    po_line_wrap: int
    po_keep_previous: bool
    po_remove_obsolete: bool
    po_no_location: bool
    po_fuzzy_matching: bool
    po_set_language_team: bool
    po_set_last_translator: bool
    po_set_x_generator: bool
    po_report_msgid_bugs_to: bool
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
    csv_escape_formulas: bool
    csv_simple_encoding: str
    dos_eol: bool
    gwt_encoding: str
    line_max_length: int
    md_extract_code_blocks: bool
    md_extract_frontmatter: bool
    md_frontmatter_translate_values: bool
    md_no_placeholders: bool
    merge_duplicates: bool


FileFormatParamKey = Literal[
    "dos_eol",
    "json_sort_keys",
    "json_indent",
    "json_indent_style",
    "json_use_compact_separators",
    "po_line_wrap",
    "po_keep_previous",
    "po_remove_obsolete",
    "po_no_location",
    "po_fuzzy_matching",
    "po_set_language_team",
    "po_set_last_translator",
    "po_set_x_generator",
    "po_report_msgid_bugs_to",
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
    "csv_escape_formulas",
    "csv_simple_encoding",
    "gwt_encoding",
    "merge_duplicates",
    "line_max_length",
    "md_extract_code_blocks",
    "md_extract_frontmatter",
    "md_frontmatter_translate_values",
    "md_no_placeholders",
]


class BaseFileFormatParam(BaseParam):
    name: FileFormatParamKey  # type: ignore[assignment]
    file_formats: Sequence[str] = []
    widget_css_class: ClassVar[str] = "file-format-param"
    scope_attribute: ClassVar[str] = "fileformats"

    @classmethod
    def get_scopes(cls) -> Sequence[str]:
        return cls.file_formats

    def setup_store(
        self, store: TranslationStore, **file_format_params: Unpack[FileFormatParams]
    ) -> None:
        """Configure store with this file format parameters."""

    @classmethod
    def is_encoding(cls):
        return cls.name.endswith("_encoding")

    @classmethod
    def supports_all_formats(cls) -> bool:
        return cls.supports_all_scopes()

    @classmethod
    def supports_format(cls, file_format: str) -> bool:
        return cls.supports_scope(file_format)


FILE_FORMATS_PARAMS: list[type[BaseFileFormatParam]] = []


def register_file_format_param(
    param_class: type[BaseFileFormatParam],
) -> type[BaseFileFormatParam]:
    """Register a new file format parameter class."""
    FILE_FORMATS_PARAMS.append(param_class)
    return param_class


def get_params_for_file_format(file_format: str) -> list[type[BaseFileFormatParam]]:
    """Get all registered file format parameters for a given file format."""
    return get_params_for_scope(FILE_FORMATS_PARAMS, file_format)


def get_default_params_for_file_format(file_format: str) -> FileFormatParams:
    """Get default values for all registered file format parameters."""
    return cast(
        "FileFormatParams",
        get_default_params_for_scope(FILE_FORMATS_PARAMS, file_format),
    )


def get_effective_params_for_file_format(
    file_format: str, file_format_params: FileFormatParams | None
) -> FileFormatParams:
    """Get normalized effective values for file format parameters."""
    return cast(
        "FileFormatParams",
        {
            param.name: param.get_value(file_format_params)
            for param in get_params_for_file_format(file_format)
        },
    )


def strip_unused_file_format_params(
    file_format: str, file_format_params: FileFormatParams
) -> FileFormatParams:
    """Clean file format parameters, removing those not applicable to the given file format."""
    for param in FILE_FORMATS_PARAMS:
        if not param.supports_format(file_format):
            file_format_params.pop(param.name, None)
    return file_format_params


def get_param_for_name(name: str) -> type[BaseFileFormatParam]:
    """Get parameter class for given name."""
    return get_param_by_name(FILE_FORMATS_PARAMS, name)


def get_encoding_param(
    file_format: str, file_format_params: FileFormatParams | None
) -> str | None:
    """Get encoding parameter from file format parameters."""
    raw_file_format_params = (
        cast("FileFormatParams", {})
        if file_format_params is None
        else file_format_params
    )
    for param in get_params_for_file_format(file_format):
        if param.is_encoding():
            default_encoding = cast("str", param.default)
            if param.name not in raw_file_format_params:
                return default_encoding
            if raw_file_format_params.get(param.name) is None:
                return default_encoding
            return cast("str", param.get_value(raw_file_format_params))
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


class CaseInsensitiveSortingEncoder(json.JSONEncoder):
    def __init__(self, *args, **kwargs) -> None:
        kwargs["sort_keys"] = False
        super().__init__(*args, **kwargs)

    def encode(self, o: object) -> str:
        return super().encode(self._sort_keys_case_insensitive(o))

    def _sort_keys_case_insensitive(self, o: object) -> object:
        if isinstance(o, dict):
            return {
                key: self._sort_keys_case_insensitive(value)
                for key, value in sorted(
                    o.items(),
                    key=lambda item: str(item[0]).casefold(),
                )
            }
        if isinstance(o, (list, tuple)):
            return [self._sort_keys_case_insensitive(item) for item in o]
        return o


@register_file_format_param
class JSONOutputSortKeys(JSONOutputCustomizationBaseParam):
    name = "json_sort_keys"
    label = gettext_lazy("Sort JSON keys")
    field_class = forms.ChoiceField
    choices: ClassVar[list[tuple[str | int, StrOrPromise]] | None] = [
        ("none", gettext_lazy("Do not sort")),
        ("case_sensitive", gettext_lazy("Case-sensitive sort")),
        ("case_insensitive", gettext_lazy("Case-insensitive sort")),
    ]
    default = "none"

    def setup_store(
        self, store: TranslationStore, **file_format_params: Unpack[FileFormatParams]
    ) -> None:
        dump_args = cast("JsonFile", store).dump_args
        sort_mode = self.get_value(file_format_params)
        if sort_mode == "case_sensitive":
            dump_args["sort_keys"] = True
        elif sort_mode == "case_insensitive":
            # turn off JSONFile sorting which uses Python's default key ordering (cae sensitive)
            dump_args["sort_keys"] = False
            dump_args["cls"] = CaseInsensitiveSortingEncoder  # type: ignore[typeddict-item]


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
        wrapper = cast("pofile", store).wrapper
        if wrapper is None:
            msg = "The PO wrapper should not be none"
            raise TypeError(msg)
        wrapper.width = int(self.get_value(file_format_params))


class BaseGettextFormatParam(BaseFileFormatParam):
    file_formats: Sequence[str] = ("po",)


@register_file_format_param
class GettextKeepPreviousMsgids(BaseGettextFormatParam):
    name = "po_keep_previous"
    label = gettext_lazy("Keep previous msgids of translated strings")
    field_class = forms.BooleanField
    default = True
    help_text = gettext_lazy("Controls previous msgid comments for fuzzy strings.")


@register_file_format_param
class GettextRemoveObsolete(BaseGettextFormatParam):
    file_formats: Sequence[str] = ("po", "po-mono")
    name = "po_remove_obsolete"
    label = gettext_lazy("Remove obsolete strings")
    field_class = forms.BooleanField
    default = False
    help_text = gettext_lazy(
        "Remove obsolete entries from PO files when saving translation changes "
        "or updating from a POT file."
    )


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


@register_file_format_param
class GettextSetLanguageTeamHeader(BaseGettextFormatParam):
    file_formats = ("po", "po-mono")
    name = "po_set_language_team"
    label = gettext_lazy("Update language team header")
    field_class = forms.BooleanField
    default = True
    help_text = gettext_lazy('Lets Weblate update the "Language-Team" file header.')


@register_file_format_param
class GettextLastTranslator(BaseGettextFormatParam):
    file_formats = ("po", "po-mono")
    name = "po_set_last_translator"
    label = gettext_lazy("Update last translator header")
    field_class = forms.BooleanField
    default = True
    help_text = gettext_lazy('Lets Weblate update the "Last-Translator" file header.')


@register_file_format_param
class GettextXGenerator(BaseGettextFormatParam):
    file_formats = ("po", "po-mono")
    name = "po_set_x_generator"
    label = gettext_lazy("Update X-Generator header")
    field_class = forms.BooleanField
    default = True
    help_text = gettext_lazy('Lets Weblate update the "X-Generator" file header.')


@register_file_format_param
class GettextReportMsgidBugsTo(BaseGettextFormatParam):
    file_formats = ("po", "po-mono")
    name = "po_report_msgid_bugs_to"
    label = gettext_lazy("Report msgid bugs to")
    field_class = forms.BooleanField
    default = True
    help_text = gettext_lazy(
        'Lets Weblate update the "Report-Msgid-Bugs-To" file header if Source string bug reporting address is set.'
    )


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
        # ruff: ignore[import-outside-top-level]
        from weblate.formats.models import (
            FILE_FORMATS,
        )

        # ruff: ignore[import-outside-top-level]
        from weblate.formats.ttkit import (
            TTKitFormat,
        )

        result = []
        for file_format, format_class in FILE_FORMATS.items():
            if issubclass(format_class, TTKitFormat):
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
class MergeDuplicates(BaseFileFormatParam):
    file_formats = (
        "markdown",
        "mdx",
        "html",
        "txt",
        "dokuwiki",
        "mediawiki",
        "asciidoc",
    )
    name = "merge_duplicates"
    label = gettext_lazy("Deduplicate identical strings")
    field_class = forms.BooleanField
    default = False
    help_text = gettext_lazy(
        "Consolidates identical source strings into a single translation unit. "
        "Prevents translation loss during file restructuring or table reordering "
        "by removing position-dependent context."
    )


@register_file_format_param
class StringsEncoding(BaseFileFormatParam):
    file_formats = ("strings",)
    name = "strings_encoding"
    label = gettext_lazy("File encoding")
    field_class = forms.ChoiceField
    choices: ClassVar[list[tuple[str | int, StrOrPromise]] | None] = [
        ("utf-8", gettext_lazy("UTF-8")),
        ("utf-16", gettext_lazy("UTF-16")),
    ]
    default = "utf-8"
    help_text = gettext_lazy("Encoding used for iOS strings files")


@register_file_format_param
class PropertiesEncoding(BaseFileFormatParam):
    file_formats = ("properties",)
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
class CSVFormulaEscaping(BaseFileFormatParam):
    file_formats = ("csv", "csv-multi", "csv-simple")
    name = "csv_escape_formulas"
    label = gettext_lazy("Escape spreadsheet formulas")
    field_class = forms.BooleanField
    default = False
    help_text = gettext_lazy(
        "Prefix values that look like spreadsheet formulas with an apostrophe "
        "when saving CSV files."
    )

    def setup_store(
        self, store: TranslationStore, **file_format_params: Unpack[FileFormatParams]
    ) -> None:
        cast("csvfile", store).escape_formulas = self.get_value(file_format_params)


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


@register_file_format_param
class DOSLineEndings(BaseFileFormatParam):
    file_formats = ("*",)
    name = "dos_eol"
    label = gettext_lazy("DOS line endings")
    field_class = forms.BooleanField
    default = False
    help_text = gettext_lazy(
        "Use DOS line endings (\\r\\n) instead of UNIX line endings (\\n) in strings."
    )


@register_file_format_param
class LineMaxLength(BaseFileFormatParam):
    name = "line_max_length"
    file_formats = ("markdown", "mdx")
    label = gettext_lazy("Maximum line length")
    field_class = forms.IntegerField
    default = 80
    field_kwargs: ClassVar[FieldKwargsDict] = {"min_value": 20, "max_value": 1000}
    help_text = gettext_lazy(
        "The maximum number of characters for each line in the output file."
    )


@register_file_format_param
class MdExtractCodeBlocks(BaseFileFormatParam):
    name = "md_extract_code_blocks"
    file_formats = ("markdown", "mdx")
    label = gettext_lazy("Extract code blocks")
    field_class = forms.BooleanField
    default = True
    help_text = gettext_lazy(
        "Whether to extract translatable content from code blocks in Markdown and MDX files."
    )


@register_file_format_param
class MdExtractFrontmatter(BaseFileFormatParam):
    name = "md_extract_frontmatter"
    file_formats = ("markdown", "mdx")
    label = gettext_lazy("Extract front matter")
    field_class = forms.BooleanField
    default = True
    help_text = gettext_lazy(
        "Whether to extract and translate YAML front matter blocks in Markdown and MDX files."
    )


@register_file_format_param
class MdFrontmatterTranslateValues(BaseFileFormatParam):
    name = "md_frontmatter_translate_values"
    file_formats = ("markdown", "mdx")
    label = gettext_lazy("Translate front matter values")
    field_class = forms.BooleanField
    default = False
    help_text = gettext_lazy(
        "Parse YAML front matter and translate only scalar string values. "
        "Keys, structure, comments, and formatting are preserved when possible."
    )


@register_file_format_param
class MdNoPlaceholders(BaseFileFormatParam):
    name = "md_no_placeholders"
    file_formats = ("markdown", "mdx")
    label = gettext_lazy("Disable placeholders")
    field_class = forms.BooleanField
    default = False
    help_text = gettext_lazy(
        "Disables detection and processing of placeholders in Markdown and MDX files."
    )
