# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

import regex
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout
from django import forms
from django.http import QueryDict
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy, pgettext_lazy
from fedora_messaging.exceptions import ConfigurationException
from lxml.cssselect import CSSSelector

from weblate.addons.base import BaseAddon
from weblate.formats.models import FILE_FORMATS
from weblate.trans.actions import ActionEvents
from weblate.trans.discovery import (
    ComponentDiscovery,
    get_component_detected_discovery_presets,
    get_detected_discovery_preset_values_key,
)
from weblate.trans.forms import AutoForm, BulkEditForm
from weblate.trans.models import Translation
from weblate.utils.forms import (
    CachedModelChoiceField,
    ContextDiv,
    SortedSelectMultiple,
    WeblateServiceURLField,
)
from weblate.utils.regex import compile_regex, regex_match, regex_sub
from weblate.utils.render import validate_render, validate_render_translation
from weblate.utils.validators import (
    DomainOrIPValidator,
    validate_asset_url,
    validate_filename,
    validate_re,
    validate_re_nonempty,
    validate_webhook_secret_string,
    validate_webhook_url,
)

if TYPE_CHECKING:
    from weblate.addons.autotranslate import (
        AutoTranslateAddon,
        AutoTranslateAddonStoredConfiguration,
    )
    from weblate.addons.cdn import CDNJSAddon  # noqa: F401
    from weblate.addons.consistency import LanguageConsistencyAddon  # noqa: F401
    from weblate.addons.generate import (
        GenerateFileAddon,  # noqa: F401
        GenerateFileAddonConfiguration,
    )
    from weblate.addons.gettext import MesonAddon
    from weblate.addons.git import (
        GitSquashAddon,  # noqa: F401
        GitSquashAddonStoredConfiguration,
    )
    from weblate.addons.models import Addon
    from weblate.addons.properties import (
        PropertiesSortAddon,  # noqa: F401
        PropertiesSortAddonStoredConfiguration,
    )
    from weblate.auth.models import User
    from weblate.trans.discovery import (
        DetectedDiscoveryPreset,
        DetectedDiscoveryPresetValues,
    )
    from weblate.trans.models import Component, Project


class BaseAddonForm[StoredConfigurationT, AddonT: BaseAddon](forms.Form):
    def __init__(
        self,
        user: User | None,
        addon: AddonT,
        instance: Addon | None = None,
        *args,
        **kwargs,
    ) -> None:
        self._addon: AddonT = addon
        self.user = user
        forms.Form.__init__(self, *args, **kwargs)

    def serialize_form(self) -> StoredConfigurationT:
        return cast("StoredConfigurationT", self.cleaned_data)

    def save(self):
        self._addon.configure(self.serialize_form())
        return self._addon.instance


class GenerateMoForm(BaseAddonForm):
    path = forms.CharField(
        label=gettext_lazy("Path of generated MO file"),
        required=False,
        initial="{{ filename|stripext }}.mo",
        help_text=gettext_lazy(
            "If not specified, the location of the PO file will be used."
        ),
    )
    fuzzy = forms.BooleanField(
        label=gettext_lazy("Include strings needing editing"),
        required=False,
        help_text=gettext_lazy(
            "Strings needing editing (fuzzy) are typically not ready for use as translations."
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field("fuzzy"),
            Field("path"),
            ContextDiv(
                template="addons/generatemo_help.html", context={"user": self.user}
            ),
        )

    def test_render(self, value) -> None:
        validate_render_translation(value)

    def clean_path(self):
        self.test_render(self.cleaned_data["path"])
        validate_filename(self.cleaned_data["path"])
        return self.cleaned_data["path"]


class BaseExtractPotForm(BaseAddonForm):
    interval = forms.ChoiceField(
        label=gettext_lazy("Update frequency"),
        choices=(
            ("daily", gettext_lazy("Daily")),
            ("weekly", gettext_lazy("Weekly")),
            ("monthly", gettext_lazy("Monthly")),
        ),
        initial="weekly",
        required=True,
        help_text=gettext_lazy(
            "How often the add-on should update the POT file when the component is refreshed."
        ),
    )
    normalize_header = forms.BooleanField(
        label=gettext_lazy("Normalize POT header"),
        required=False,
        initial=False,
        help_text=gettext_lazy(
            "Updates gettext headers and replaces placeholder POT comments."
        ),
    )
    update_po_files = forms.BooleanField(
        label=gettext_lazy("Update PO files using msgmerge"),
        required=False,
        initial=True,
        widget=forms.HiddenInput(),
        help_text=gettext_lazy(
            "Ensures the msgmerge add-on is installed and triggers it after the POT file is updated."
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        if self._addon.instance.pk is None and not self._addon.documentation_build:
            self.fields["update_po_files"].widget = forms.CheckboxInput()
        self.helper.layout = Layout(
            Field("interval"),
            Field("normalize_header"),
            Field("update_po_files"),
        )

    def serialize_form(self):
        data = dict(super().serialize_form())
        update_po_files = data.pop("update_po_files", False)
        if self._addon.instance.pk is None and update_po_files:
            data["_install_msgmerge"] = True
        return data


class BaseXgettextExtractPotForm(BaseExtractPotForm):
    COMMENT_MODE_CHOICES = (
        ("off", gettext_lazy("Do not extract comments")),
        ("all", gettext_lazy("Extract all comments")),
        ("tagged", gettext_lazy("Extract comments with tag")),
    )
    CHECK_CHOICES = (
        ("ellipsis-unicode", "ellipsis-unicode"),
        ("space-ellipsis", "space-ellipsis"),
        ("quote-unicode", "quote-unicode"),
        ("bullet-unicode", "bullet-unicode"),
    )
    comment_mode = forms.ChoiceField(
        label=gettext_lazy("Code comments"),
        choices=COMMENT_MODE_CHOICES,
        required=True,
        initial="off",
        help_text=gettext_lazy(
            "Choose whether xgettext should extract no comments, all comments, "
            "or only comments marked with a specific tag."
        ),
    )
    comment_tag = forms.CharField(
        label=gettext_lazy("Comment tag"),
        required=False,
        help_text=gettext_lazy(
            "Tag passed to xgettext for comment extraction when using tagged "
            "comment mode."
        ),
    )
    checks = forms.MultipleChoiceField(
        label=gettext_lazy("xgettext checks"),
        choices=CHECK_CHOICES,
        required=False,
        widget=forms.SelectMultiple(),
        help_text=gettext_lazy(
            "Additional xgettext validation checks to enable for extracted messages."
        ),
    )
    keyword = forms.CharField(
        label=gettext_lazy("Additional keyword"),
        required=False,
        help_text=gettext_lazy(
            "Optional extra keyword passed to xgettext using --keyword."
        ),
    )

    @staticmethod
    def ensure_default_bound_value(data, key: str, value: str):
        if data is None or key in data:
            return data
        if hasattr(data, "copy"):
            data = data.copy()
            if hasattr(data, "setlist"):
                data.setlist(key, [value])
            else:
                data[key] = value
        return data

    def __init__(self, *args, **kwargs) -> None:
        data = self.ensure_default_bound_value(
            kwargs.get("data"), "comment_mode", "off"
        )
        if data is not None:
            kwargs["data"] = data
        super().__init__(*args, **kwargs)

    def clean_xgettext_options(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        comment_mode = cleaned_data.get("comment_mode", "off")
        comment_tag = cleaned_data.get("comment_tag", "").strip()
        if comment_mode == "tagged":
            if not comment_tag:
                self.add_error("comment_tag", gettext("This field is required."))
        else:
            comment_tag = ""
        cleaned_data["comment_tag"] = comment_tag
        cleaned_data["keyword"] = cleaned_data.get("keyword", "").strip()
        return cleaned_data


class XgettextExtractPotForm(BaseXgettextExtractPotForm):
    input_mode = forms.ChoiceField(
        label=gettext_lazy("Input source"),
        choices=(
            ("patterns", gettext_lazy("Source file patterns")),
            ("potfiles", gettext_lazy("POTFILES manifest")),
        ),
        required=True,
        initial="patterns",
        help_text=gettext_lazy(
            "Choose whether xgettext should read source files from glob patterns "
            "or from a POTFILES/POTFILES.in manifest."
        ),
    )
    language = forms.CharField(
        label=gettext_lazy("xgettext language"),
        required=True,
        initial="Python",
        help_text=gettext_lazy(
            "Programming language passed to xgettext, for example Python or C."
        ),
    )
    source_patterns = forms.CharField(
        label=gettext_lazy("Source file patterns"),
        required=False,
        widget=forms.Textarea(),
        help_text=gettext_lazy(
            "Newline-separated repository-relative glob patterns for files to "
            "extract with xgettext."
        ),
    )
    potfiles_path = forms.CharField(
        label=gettext_lazy("POTFILES path"),
        required=False,
        initial="",
        help_text=gettext_lazy(
            "Repository-relative path to POTFILES or POTFILES.in. Entries are "
            "resolved relative to the repository root. If present next to the "
            "manifest, POTFILES.skip excludes listed files from extraction."
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        data = self.ensure_default_bound_value(
            kwargs.get("data"), "input_mode", "patterns"
        )
        if data is not None:
            source_patterns = data.get("source_patterns")
            if isinstance(source_patterns, list):
                data = data.copy()
                data["source_patterns"] = "\n".join(source_patterns)
            kwargs["data"] = data
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout(*self.get_xgettext_layout_fields())

    @classmethod
    def get_xgettext_layout_fields(cls) -> list[Field]:
        return [
            Field("interval"),
            Field("normalize_header"),
            Field("update_po_files"),
            Field("input_mode"),
            Field("language"),
            Field("source_patterns"),
            Field("potfiles_path"),
            Field("comment_mode"),
            Field("comment_tag"),
            Field("checks"),
            Field("keyword"),
        ]

    @staticmethod
    def parse_patterns(value: str) -> list[str]:
        return [line.strip() for line in value.splitlines() if line.strip()]

    def clean(self) -> dict[str, Any]:
        super().clean()
        cleaned_data = self.cleaned_data
        input_mode = cleaned_data.get("input_mode", "patterns")
        patterns = self.parse_patterns(cleaned_data.get("source_patterns", ""))
        potfiles_path = cleaned_data.get("potfiles_path", "").strip()
        if input_mode == "patterns":
            if not patterns:
                self.add_error("source_patterns", gettext("This field is required."))
            for pattern in patterns:
                validate_filename(pattern)
            cleaned_data["source_patterns"] = patterns
            cleaned_data["potfiles_path"] = ""
        else:
            if not potfiles_path:
                self.add_error("potfiles_path", gettext("This field is required."))
            else:
                validate_filename(potfiles_path)
                component = self._addon.instance.component
                if component is not None:
                    manifest = Path(component.full_path) / potfiles_path
                    try:
                        component.check_file_is_valid(str(manifest))
                    except forms.ValidationError as error:
                        self.add_error("potfiles_path", error)
                    else:
                        if manifest.exists() and manifest.is_dir():
                            self.add_error(
                                "potfiles_path",
                                gettext("POTFILES path has to point to a file."),
                            )
            cleaned_data["source_patterns"] = []
            cleaned_data["potfiles_path"] = potfiles_path
        return self.clean_xgettext_options(cleaned_data)


class MesonExtractPotForm(BaseXgettextExtractPotForm):
    preset = forms.ChoiceField(
        label=gettext_lazy("Meson preset"),
        choices=(("glib", gettext_lazy("GLib")),),
        required=True,
        initial="glib",
        help_text=gettext_lazy(
            "Built-in xgettext argument preset matching Meson gettext integration. "
            "The GLib preset adds the keyword and format-flag options used by "
            "Meson's gettext helper."
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout(
            Field("interval"),
            Field("normalize_header"),
            Field("update_po_files"),
            Field("preset"),
            Field("comment_mode"),
            Field("comment_tag"),
            Field("checks"),
            Field("keyword"),
        )

    def clean(self) -> dict[str, Any]:
        super().clean()
        cleaned_data = self.clean_xgettext_options(self.cleaned_data)
        component = self._addon.instance.component
        if component is None:
            return cleaned_data
        addon = cast("MesonAddon", self._addon)
        if not addon.is_meson_layout(component):
            self.add_error(
                None,
                gettext(
                    "The Meson add-on expects a Meson gettext directory with "
                    "meson.build and POTFILES or POTFILES.in."
                ),
            )
        return cleaned_data


class DjangoExtractPotForm(BaseExtractPotForm):
    def clean(self) -> dict[str, Any]:
        super().clean()
        cleaned_data = self.cleaned_data
        component = self._addon.instance.component
        if component is None:
            return cleaned_data
        if not component.new_base.endswith(".pot"):
            self.add_error(
                None,
                gettext("The component has to define a POT file for new translations."),
            )
            return cleaned_data
        if Path(component.new_base).stem not in {"django", "djangojs"}:
            self.add_error(
                None,
                gettext(
                    "The Django add-on expects the template for new translations to "
                    'be named "django.pot" or "djangojs.pot".'
                ),
            )
        return cleaned_data


class SphinxExtractPotForm(BaseExtractPotForm):
    filter_mode = forms.ChoiceField(
        label=gettext_lazy("Filtering"),
        choices=(
            ("none", pgettext_lazy("None filtering", "None")),
            ("weblate_docs", gettext_lazy("Weblate documentation")),
        ),
        initial="none",
        required=False,
        help_text=gettext_lazy(
            "Optionally remove strings that are not useful to translate after Sphinx extraction."
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout(
            Field("interval"),
            Field("normalize_header"),
            Field("update_po_files"),
            Field("filter_mode"),
        )

    def clean(self) -> dict[str, Any]:
        super().clean()
        cleaned_data = self.cleaned_data
        component = self._addon.instance.component
        if component is None:
            return cleaned_data
        if not component.new_base.endswith(".pot"):
            self.add_error(
                None,
                gettext(
                    "The Sphinx add-on expects the template for new translations "
                    "to be a .pot file."
                ),
            )
            return cleaned_data
        template = Path(component.new_base)
        parts = template.parts
        if "locales" not in parts:
            self.add_error(
                None,
                gettext(
                    "The Sphinx add-on expects the template for new translations "
                    'to live in a "locales" directory.'
                ),
            )
            return cleaned_data
        locales_index = parts.index("locales")
        source_parts = parts[:locales_index]
        if source_parts:
            component_root = Path(component.full_path)
            source_dir = component_root.joinpath(*source_parts)
            try:
                component.check_file_is_valid(str(source_dir))
            except forms.ValidationError:
                self.add_error(
                    None,
                    gettext("Could not determine Sphinx source directory."),
                )
            else:
                if not source_dir.is_dir():
                    self.add_error(
                        None,
                        gettext("Could not determine Sphinx source directory."),
                    )
        return cleaned_data


class GenerateForm(
    BaseAddonForm["GenerateFileAddonConfiguration", "GenerateFileAddon"]
):
    filename = forms.CharField(
        label=gettext_lazy("Name of generated file"), required=True
    )
    template = forms.CharField(
        widget=forms.Textarea(),
        label=gettext_lazy("Content of generated file"),
        required=True,
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field("filename"),
            Field("template"),
            ContextDiv(
                template="addons/generate_help.html", context={"user": self.user}
            ),
        )

    def test_render(self, value) -> None:
        validate_render_translation(value)

    def clean_filename(self):
        self.test_render(self.cleaned_data["filename"])
        validate_filename(self.cleaned_data["filename"])
        return self.cleaned_data["filename"]

    def clean_template(self):
        self.test_render(self.cleaned_data["template"])
        return self.cleaned_data["template"]

    def serialize_form(self) -> GenerateFileAddonConfiguration:
        return {
            "filename": self.cleaned_data["filename"],
            "template": self.cleaned_data["template"],
        }


class GitSquashForm(
    BaseAddonForm["GitSquashAddonStoredConfiguration", "GitSquashAddon"]
):
    squash = forms.ChoiceField(
        label=gettext_lazy("Commit squashing"),
        widget=forms.RadioSelect,
        choices=(
            ("all", gettext_lazy("All commits into one")),
            ("language", gettext_lazy("Per language")),
            ("file", gettext_lazy("Per file")),
            ("author", gettext_lazy("Per author")),
        ),
        initial="all",
        required=True,
    )
    append_trailers = forms.BooleanField(
        label=gettext_lazy("Append trailers to squashed commit message"),
        required=False,
        initial=True,
        help_text=gettext_lazy(
            "Trailer lines are lines that look similar to RFC 822 e-mail "
            "headers, at the end of the otherwise free-form part of a commit "
            "message, such as 'Co-authored-by: …'."
        ),
    )
    commit_message = forms.CharField(
        label=gettext_lazy("Commit message"),
        widget=forms.Textarea(),
        required=False,
        help_text=gettext_lazy(
            "This commit message will be used instead of the combined commit "
            "messages from the squashed commits."
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field("squash"),
            Field("append_trailers"),
            Field("commit_message"),
            ContextDiv(template="addons/squash_help.html", context={"user": self.user}),
        )

    def serialize_form(self) -> GitSquashAddonStoredConfiguration:
        return {
            "squash": self.cleaned_data["squash"],
            "append_trailers": self.cleaned_data["append_trailers"],
            "commit_message": self.cleaned_data["commit_message"],
        }


class RemoveForm(BaseAddonForm):
    age = forms.IntegerField(
        label=gettext_lazy("Days to keep"), min_value=0, initial=30, required=True
    )


class RemoveSuggestionForm(RemoveForm):
    votes = forms.IntegerField(
        label=gettext_lazy("Voting threshold"),
        initial=0,
        required=True,
        help_text=gettext_lazy(
            "Threshold for removal. This field has no effect with voting turned off."
        ),
    )


class LanguageConsistencyPreviewForm(
    BaseAddonForm[dict[str, object], "LanguageConsistencyAddon"]
):
    confirm = forms.BooleanField(
        label=gettext_lazy("I confirm the above actions look correct"),
        required=False,
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            ContextDiv(
                template="addons/language_consistency_preview.html",
                context={
                    "preview": self._addon.get_installation_preview(),
                    "warning": self._addon.get_preview_warning(),
                    "user": self.user,
                },
            ),
            Field("confirm"),
        )

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean() or {}
        if not cleaned_data.get("confirm"):
            raise forms.ValidationError(
                gettext("Please review and confirm the missing language changes.")
            )
        return cleaned_data

    def serialize_form(self):
        return {}


class DiscoveryForm(BaseAddonForm):
    COMPONENT_TEMPLATE_SENTINELS: ClassVar[tuple[str, ...]] = (
        "alpha",
        "bravo12",
        "charlie_xyz",
        "Q",
    )
    DETECTED_PRESET_ID_PREFIX: ClassVar[str] = "detected-"
    PRESET_VALUE_FIELDS: ClassVar[tuple[str, ...]] = (
        "match",
        "file_format",
        "name_template",
        "base_file_template",
        "new_base_template",
        "intermediate_template",
        "language_regex",
    )
    PRESET_FILENAME_LANGUAGE = "filename-language"
    PRESET_FOLDER_PER_LANGUAGE = "folder-per-language"
    PRESET_GETTEXT_LOCALES = "gettext-locales"
    PRESET_COMPLEX_FILENAMES = "complex-filenames"
    PRESET_REPEATED_LANGUAGE = "repeated-language"
    PRESET_SPLIT_ANDROID = "split-android-strings"
    PRESET_MULTIPLE_PATHS = "multiple-paths"
    PRESETS: ClassVar[dict[str, DetectedDiscoveryPresetValues]] = {
        PRESET_FOLDER_PER_LANGUAGE: {
            "match": r"(?P<language>[^/.]*)/(?P<component>[^/]*)\.po",
            "file_format": "po",
            "name_template": "{{ component }}",
            "base_file_template": "",
            "new_base_template": "",
            "intermediate_template": "",
            "language_regex": "^[^.]+$",
        },
        PRESET_GETTEXT_LOCALES: {
            "match": r"locale/(?P<language>[^/.]*)/LC_MESSAGES/(?P<component>[^/]*)\.po",
            "file_format": "po",
            "name_template": "{{ component }}",
            "base_file_template": "",
            "new_base_template": "",
            "intermediate_template": "",
            "language_regex": "^[^.]+$",
        },
        PRESET_COMPLEX_FILENAMES: {
            "match": r"src/locale/(?P<component>[^/]*)\.(?P<language>[^/.]*)\.po",
            "file_format": "po",
            "name_template": "{{ component }}",
            "base_file_template": "",
            "new_base_template": "",
            "intermediate_template": "",
            "language_regex": "^[^.]+$",
        },
        PRESET_FILENAME_LANGUAGE: {
            "match": r"(?:(?P<path>.*/))?(?P<component>.+?)_(?P<language>[A-Za-z]{2,3}(?:[_-][A-Za-z0-9]+)*)\.(?P<extension>[^/.]+)",
            "file_format": "",
            "name_template": "{{ component }}",
            "base_file_template": "",
            "new_base_template": "",
            "intermediate_template": "",
            "language_regex": "^[^.]+$",
        },
        PRESET_REPEATED_LANGUAGE: {
            "match": r"locale/(?P<language>[^/.]*)/(?P<component>[^/]*)/(?P=language)\.po",
            "file_format": "po",
            "name_template": "{{ component }}",
            "base_file_template": "",
            "new_base_template": "",
            "intermediate_template": "",
            "language_regex": "^[^.]+$",
        },
        PRESET_SPLIT_ANDROID: {
            "match": r"res/values-(?P<language>[^/.]*)/strings-(?P<component>[^/]*)\.xml",
            "file_format": "aresource",
            "name_template": "{{ component }}",
            "base_file_template": "",
            "new_base_template": "",
            "intermediate_template": "",
            "language_regex": "^[^.]+$",
        },
        PRESET_MULTIPLE_PATHS: {
            "match": r"(?P<originalHierarchy>.+/)(?P<component>[^/]*)/src/main/resources/ApplicationResources_(?P<language>[^/.]*)\.properties",
            "file_format": "properties",
            "name_template": "{{ originalHierarchy }}: {{ component }}",
            "base_file_template": "",
            "new_base_template": "",
            "intermediate_template": "",
            "language_regex": "^[^.]+$",
        },
    }

    match = forms.CharField(
        label=gettext_lazy("Regular expression to match translation files against"),
        required=True,
        help_text=gettext_lazy(
            "The regular expression must define named groups for component and language."
        ),
    )
    file_format = forms.ChoiceField(
        label=gettext_lazy("File format"),
        choices=FILE_FORMATS.get_choices(empty=True),
        initial="",
        required=True,
    )
    name_template = forms.CharField(
        label=gettext_lazy("Customize the component name"),
        initial="{{ component }}",
        required=True,
        help_text=gettext_lazy(
            "Use Django template syntax. This template must include {{ component }}."
        ),
    )
    base_file_template = forms.CharField(
        label=gettext_lazy("Define the monolingual base filename"),
        initial="",
        required=False,
        help_text=gettext_lazy(
            "Leave empty for bilingual translation files. When set, this template must include {{ component }}."
        ),
    )
    new_base_template = forms.CharField(
        label=gettext_lazy("Define the base file for new translations"),
        initial="",
        required=False,
        help_text=gettext_lazy(
            "Filename of file used for creating new translations. "
            "For gettext choose .pot file. This template must include {{ component }}."
        ),
    )
    intermediate_template = forms.CharField(
        label=gettext_lazy("Intermediate language file"),
        initial="",
        required=False,
        help_text=gettext_lazy(
            "Filename of intermediate translation file. In most cases "
            "this is a translation file provided by developers and is "
            "used when creating actual source strings. This template must include {{ component }}."
        ),
    )

    language_regex = forms.CharField(
        label=gettext_lazy("Language filter"),
        max_length=200,
        initial="^[^.]+$",
        validators=[validate_re_nonempty],
        help_text=gettext_lazy(
            "Regular expression to filter "
            "translation files against when scanning for file mask."
        ),
    )
    copy_addons = forms.BooleanField(
        label=gettext_lazy(
            "Clone add-ons from the main component to the newly created ones"
        ),
        required=False,
        initial=True,
    )
    remove = forms.BooleanField(
        label=gettext_lazy("Remove components for inexistent files"), required=False
    )
    confirm = forms.BooleanField(
        label=gettext_lazy("I confirm the above matches look correct"),
        required=False,
        widget=forms.HiddenInput,
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field("match"),
            Field("file_format"),
            Field("name_template"),
            Field("base_file_template"),
            Field("new_base_template"),
            Field("intermediate_template"),
            Field("language_regex"),
            Field("copy_addons"),
            Field("remove"),
        )
        if self.guided_preset_sections:
            self.helper.layout.insert(
                0,
                ContextDiv(
                    template="addons/discovery_presets.html",
                    context={
                        "guided_presets": self.guided_presets,
                        "guided_preset_sections": self.guided_preset_sections,
                    },
                ),
            )
        if self.is_bound:
            # Perform form validation
            self.full_clean()
            # Show preview if form was submitted
            if self.cleaned_data.get("preview"):
                self.fields["confirm"].widget = forms.CheckboxInput()
                self.helper.layout.insert(0, Field("confirm"))
                created, matched, deleted, skipped = self.discovery.perform(
                    preview=True, remove=self.cleaned_data["remove"]
                )
                self.helper.layout.insert(
                    0,
                    ContextDiv(
                        template="addons/discovery_preview.html",
                        context={
                            "matches_created": created,
                            "matches_matched": matched,
                            "matches_deleted": deleted,
                            "matches_errors": self.discovery.errors,
                            "matches_skipped": skipped,
                            "user": self.user,
                        },
                    ),
                )

    def serialize_form(self):
        result = dict(self.cleaned_data)
        result.pop("confirm", None)
        result.pop("preview", None)
        return result

    @classmethod
    def render_builtin_ui_preset(
        cls,
        preset_id: str,
        label: str,
        description: str,
    ) -> dict[str, object]:
        values = cls.PRESETS[preset_id]
        file_format_label = cls.render_preset_file_format_label(values)
        base_file_label = cls.render_preset_base_file_label(values)
        details = cls.render_preset_label_details(values)
        return {
            "id": preset_id,
            "kind": "generic",
            "title": label,
            "details": details,
            "file_format_label": file_format_label,
            "base_file_label": base_file_label,
            "examples": (),
            "label": gettext("Generic preset: %(name)s [%(details)s]")
            % {
                "name": label,
                "details": details,
            },
            "description": description,
            "values": values,
        }

    @staticmethod
    def render_preset_file_format_label(values: DetectedDiscoveryPresetValues) -> str:
        file_format = values.get("file_format", "")
        if not file_format:
            return gettext("format not preset")
        if file_format in FILE_FORMATS:
            return str(FILE_FORMATS[file_format].name)
        return file_format

    @staticmethod
    def render_preset_base_file_label(values: DetectedDiscoveryPresetValues) -> str:
        if base_file_template := values.get("base_file_template", ""):
            return gettext("monolingual base: %(base)s") % {
                "base": DiscoveryForm.render_preset_template_label(base_file_template)
            }
        return gettext("no monolingual base")

    @staticmethod
    def render_preset_template_label(value: str) -> str:
        return regex_sub(r"{{\s*component\s*}}", "*", value)

    @classmethod
    def render_preset_label_details(cls, values: DetectedDiscoveryPresetValues) -> str:
        return gettext("%(format)s; %(base)s") % {
            "format": cls.render_preset_file_format_label(values),
            "base": cls.render_preset_base_file_label(values),
        }

    @classmethod
    def get_builtin_ui_presets(cls) -> list[dict[str, object]]:
        return [
            cls.render_builtin_ui_preset(
                cls.PRESET_FOLDER_PER_LANGUAGE,
                gettext("One folder per language"),
                gettext("Matches files like cs/application.po."),
            ),
            cls.render_builtin_ui_preset(
                cls.PRESET_GETTEXT_LOCALES,
                gettext("Gettext locales layout"),
                gettext("Matches files like locale/cs/LC_MESSAGES/application.po."),
            ),
            cls.render_builtin_ui_preset(
                cls.PRESET_COMPLEX_FILENAMES,
                gettext("Complex filenames"),
                gettext("Matches files like src/locale/application.cs.po."),
            ),
            cls.render_builtin_ui_preset(
                cls.PRESET_FILENAME_LANGUAGE,
                gettext("Filename-based language variants"),
                gettext("Matches files like news_en.md."),
            ),
            cls.render_builtin_ui_preset(
                cls.PRESET_REPEATED_LANGUAGE,
                gettext("Repeated language code"),
                gettext("Matches files like locale/cs/application/cs.po."),
            ),
            cls.render_builtin_ui_preset(
                cls.PRESET_SPLIT_ANDROID,
                gettext("Split Android strings"),
                gettext("Matches files like res/values-cs/strings-about.xml."),
            ),
            cls.render_builtin_ui_preset(
                cls.PRESET_MULTIPLE_PATHS,
                gettext("Matching multiple paths"),
                gettext(
                    "Matches nested Java properties layouts and also fills the component name template."
                ),
            ),
        ]

    @classmethod
    def get_preset_values_key(
        cls, values: DetectedDiscoveryPresetValues
    ) -> tuple[str, ...]:
        return get_detected_discovery_preset_values_key(values)

    def render_detected_ui_preset(
        self, preset: DetectedDiscoveryPreset, index: int
    ) -> dict[str, object]:
        examples = self.render_detected_ui_examples(preset)
        sample = examples[0]
        values = preset["values"]
        file_format_label = self.render_preset_file_format_label(values)
        base_file_label = self.render_preset_base_file_label(values)
        details = self.render_preset_label_details(values)
        return {
            "id": f"{self.DETECTED_PRESET_ID_PREFIX}{index}",
            "kind": "detected",
            "title": sample,
            "details": details,
            "file_format_label": file_format_label,
            "base_file_label": base_file_label,
            "examples": (),
            "label": gettext("Detected: %(pattern)s [%(details)s]")
            % {
                "pattern": sample,
                "details": details,
            },
            "description": "",
            "values": values,
        }

    @staticmethod
    def render_detected_ui_example(example: str, match: str) -> str:
        detected = regex_match(f"^{match}$", example)
        if detected is None or "component" not in detected.re.groupindex:
            return example

        start, end = detected.span("component")
        if start < 0 or end < 0:
            return example
        return f"{example[:start]}*{example[end:]}"

    @classmethod
    def render_detected_ui_examples(
        cls, preset: DetectedDiscoveryPreset
    ) -> tuple[str, ...]:
        match = preset["values"]["match"]
        rendered: list[str] = []
        seen: set[str] = set()
        for example in preset["examples"]:
            rendered_example = cls.render_detected_ui_example(example, match)
            if rendered_example in seen:
                continue
            seen.add(rendered_example)
            rendered.append(rendered_example)
        return tuple(rendered) or preset["examples"]

    @cached_property
    def detected_ui_presets(self) -> list[dict[str, object]]:
        component = self._addon.instance.component
        if component is None or self._addon.instance.pk is not None:
            return []

        builtins = {
            self.get_preset_values_key(values) for values in self.PRESETS.values()
        }
        detected: list[dict[str, object]] = []
        seen: set[tuple[str, ...]] = set()
        for preset in get_component_detected_discovery_presets(component):
            key = self.get_preset_values_key(preset["values"])
            if key in builtins or key in seen:
                continue
            seen.add(key)
            detected.append(self.render_detected_ui_preset(preset, len(detected) + 1))
        return detected

    @cached_property
    def generic_ui_presets(self) -> list[dict[str, object]]:
        return self.get_builtin_ui_presets()

    @cached_property
    def guided_presets(self) -> list[dict[str, object]]:
        return [*self.detected_ui_presets, *self.generic_ui_presets]

    @cached_property
    def guided_preset_sections(self) -> list[dict[str, object]]:
        sections: list[dict[str, object]] = []
        has_detected = bool(self.detected_ui_presets)
        if has_detected:
            sections.append(
                {
                    "id": "detected",
                    "title": gettext("Detected from repository"),
                    "kind": "detected",
                    "expanded": True,
                    "presets": self.detected_ui_presets,
                }
            )
        if self.generic_ui_presets:
            sections.append(
                {
                    "id": "generic",
                    "title": gettext("Generic presets"),
                    "kind": "generic",
                    "expanded": not has_detected,
                    "presets": self.generic_ui_presets,
                }
            )
        return sections

    def get_ui_presets(self) -> list[dict[str, object]]:
        return self.guided_presets

    @cached_property
    def discovery(self):
        component = self._addon.instance.component
        if component is None:
            msg = "Discovery add-on requires a component"
            raise ValueError(msg)
        return ComponentDiscovery(
            component,
            **ComponentDiscovery.extract_kwargs(self.cleaned_data),
        )

    def clean(self) -> None:
        if file_format := self.cleaned_data.get("file_format"):
            is_monolingual = FILE_FORMATS[file_format].monolingual
            if is_monolingual and not self.cleaned_data.get("base_file_template"):
                raise forms.ValidationError(
                    {
                        "base_file_template": gettext(
                            "You can not use a monolingual translation without a base file."
                        )
                    }
                )
            if is_monolingual is False and self.cleaned_data["base_file_template"]:
                raise forms.ValidationError(
                    {
                        "base_file_template": gettext(
                            "You can not use a base file for bilingual translation."
                        )
                    }
                )

        self.cleaned_data["preview"] = False

        # There are some other errors or the form was loaded from db
        if self.errors or not isinstance(self.data, QueryDict):
            return

        self.cleaned_data["preview"] = True
        if not self.cleaned_data["confirm"]:
            raise forms.ValidationError(
                gettext("Please review and confirm the matched components.")
            )

    def clean_match(self):
        match = self.cleaned_data["match"]
        validate_re(match, ("component", "language"))
        return match

    @cached_property
    def cleaned_match_re(self):
        if "match" not in self.cleaned_data:
            return None
        try:
            return compile_regex(self.cleaned_data["match"])
        except regex.error:
            return None

    def test_render(self, value):
        if self.cleaned_match_re is None:
            matches = {"component": "test"}
        else:
            matches = dict.fromkeys(self.cleaned_match_re.groupindex, "test")
        return validate_render(value, **matches)

    def template_clean(self, name):
        value = self.cleaned_data[name]
        if not value:
            return value

        self.test_render(value)
        if not self.template_depends_on_component(value):
            raise forms.ValidationError(self.get_component_template_error())
        return value

    def template_depends_on_component(self, value: str) -> bool:
        if self.cleaned_match_re is None:
            matches = {"component": "", "language": "test"}
        else:
            matches = dict.fromkeys(self.cleaned_match_re.groupindex, "test")
        rendered = set()
        for component in self.COMPONENT_TEMPLATE_SENTINELS:
            matches["component"] = component
            rendered.add(validate_render(value, **matches))
            if len(rendered) > 1:
                return True
        return False

    def get_component_template_error(self) -> str:
        if (
            self.cleaned_match_re is not None
            and "component" in self.cleaned_match_re.groupindex
        ):
            return gettext("This template must include {{ component }}.")
        return gettext("This template must include component markup.")

    def clean_name_template(self):
        return self.template_clean("name_template")

    def clean_base_file_template(self):
        return self.template_clean("base_file_template")

    def clean_new_base_template(self):
        return self.template_clean("new_base_template")

    def clean_intermediate_template(self):
        return self.template_clean("intermediate_template")


class AutoAddonForm(
    BaseAddonForm["AutoTranslateAddonStoredConfiguration", "AutoTranslateAddon"],
    AutoForm,
):
    def __init__(
        self,
        user: User | None,
        addon: AutoTranslateAddon,
        instance=None,
        **kwargs,
    ) -> None:
        BaseAddonForm.__init__(self, user, addon)
        AutoForm.__init__(
            self, obj=addon.instance.component or addon.instance.project, **kwargs
        )

    def serialize_form(self) -> AutoTranslateAddonStoredConfiguration:
        return {
            "mode": self.cleaned_data["mode"],
            "q": self.cleaned_data["q"],
            "auto_source": self.cleaned_data["auto_source"],
            "component": self.cleaned_data["component"],
            "engines": self.cleaned_data["engines"],
            "threshold": self.cleaned_data["threshold"],
        }


class BulkEditAddonForm(BaseAddonForm, BulkEditForm):
    def __init__(self, user: User | None, addon, instance=None, **kwargs) -> None:
        BaseAddonForm.__init__(self, user, addon)
        obj: Project | Component | None = None
        project: Project | None = None
        if addon.instance.component:
            obj = addon.instance.component
            project = addon.instance.component.project
        elif addon.instance.project:
            obj = project = addon.instance.project
        BulkEditForm.__init__(
            self,
            obj=obj,
            project=project,
            user=None,
            **kwargs,
        )

    def serialize_form(self):
        result = dict(self.cleaned_data)
        # Need to convert to JSON serializable objects
        result["add_labels"] = list(result["add_labels"].values_list("name", flat=True))
        result["remove_labels"] = list(
            result["remove_labels"].values_list("name", flat=True)
        )
        return result


class CDNJSForm(BaseAddonForm[dict[str, object], "CDNJSAddon"]):
    threshold = forms.IntegerField(
        label=gettext_lazy("Translation threshold"),
        initial=0,
        max_value=100,
        min_value=0,
        required=True,
        help_text=gettext_lazy(
            "The percentage of translated strings that must be present for translation to be included."
        ),
    )
    css_selector = forms.CharField(
        label=gettext_lazy("CSS selector"),
        required=True,
        initial=".l10n",
        help_text=gettext_lazy("CSS selector to detect localizable elements."),
    )
    cookie_name = forms.CharField(
        label=gettext_lazy("Language cookie name"),
        required=False,
        initial="",
        help_text=gettext_lazy("Name of cookie which stores language preference."),
    )
    # This shadows files from the Form class
    files = forms.CharField(  # type: ignore[assignment]
        widget=forms.Textarea(),
        label=gettext_lazy("Extract strings from HTML files"),
        required=False,
        help_text=gettext_lazy(
            "List of filenames in current repository or remote URLs to parse "
            "for translatable strings."
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field("threshold"),
            Field("css_selector"),
            Field("cookie_name"),
            Field("files"),
        )
        if self.is_bound and self._addon.instance.pk:
            self.helper.layout.insert(
                0,
                ContextDiv(
                    template="addons/cdnjs.html",
                    context={"url": self._addon.cdn_js_url, "user": self.user},
                ),
            )

    def clean_css_selector(self):
        try:
            CSSSelector(self.cleaned_data["css_selector"], translator="html")
        except Exception as error:
            raise forms.ValidationError(
                gettext("Could not parse CSS selector: %s") % error
            ) from error
        return self.cleaned_data["css_selector"]

    def clean_files(self):
        files = self.cleaned_data["files"]
        errors: list[str] = []

        for filename in files.splitlines():
            filename = filename.strip()
            if not filename:
                continue
            try:
                if filename.startswith(("http://", "https://")):
                    validate_asset_url(filename)
                else:
                    validate_filename(filename)
            except forms.ValidationError as error:
                errors.extend(error.messages)

        if errors:
            raise forms.ValidationError(errors)

        return files


class TranslationLanguageChoiceField(CachedModelChoiceField):
    def label_from_instance(self, obj):
        return str(obj.language)


class PseudolocaleAddonForm(BaseAddonForm):
    source = TranslationLanguageChoiceField(
        label=gettext_lazy("Source strings"),
        required=True,
        queryset=Translation.objects.none(),
    )
    target = TranslationLanguageChoiceField(
        label=gettext_lazy("Target translation"),
        required=True,
        help_text=gettext_lazy("All strings in this translation will be overwritten"),
        queryset=Translation.objects.none(),
    )
    # This shadows prefix from the Form class
    prefix = forms.CharField(  # type: ignore[assignment]
        label=gettext_lazy("Prepended static text"),
        required=False,
        initial="",
    )
    var_prefix = forms.CharField(
        label=gettext_lazy("Prepended variable text"),
        required=False,
        initial="",
    )
    suffix = forms.CharField(
        label=gettext_lazy("Appended static text"),
        required=False,
        initial="",
    )
    var_suffix = forms.CharField(
        label=gettext_lazy("Appended variable text"),
        required=False,
        initial="",
    )
    var_multiplier = forms.FloatField(
        label=gettext_lazy("Variable text multiplier"),
        required=False,
        initial=0.1,
        help_text=gettext_lazy(
            "How many times to repeat the variable text depending on "
            "the length of the source string."
        ),
    )
    include_readonly = forms.BooleanField(
        label=gettext_lazy("Include read-only strings"),
        required=False,
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self._addon.instance.component:
            queryset = self._addon.instance.component.translation_set.all()
            self.fields["source"].queryset = queryset  # type: ignore[attr-defined]
            self.fields["target"].queryset = queryset  # type: ignore[attr-defined]
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field("source"),
            Field("include_readonly"),
            Field("target"),
            Field("prefix"),
            Field("var_prefix"),
            Field("suffix"),
            Field("var_suffix"),
            Field("var_multiplier"),
            ContextDiv(
                template="addons/pseudolocale.html",
            ),
        )

    def clean(self) -> None:
        if "source" not in self.cleaned_data or "target" not in self.cleaned_data:
            return
        if self.cleaned_data["source"] == self.cleaned_data["target"]:
            raise forms.ValidationError(
                gettext("The source and target have to be different languages.")
            )

    def serialize_form(self):
        result = dict(self.cleaned_data)
        # Need to convert to JSON serializable objects
        result["source"] = result["source"].pk
        result["target"] = result["target"].pk
        return result


class PropertiesSortAddonForm(
    BaseAddonForm[
        "PropertiesSortAddonStoredConfiguration",
        "PropertiesSortAddon",
    ]
):
    case_sensitive = forms.BooleanField(
        label=gettext_lazy("Enable case-sensitive key sorting"),
        required=False,
        initial=False,
    )

    def serialize_form(self) -> PropertiesSortAddonStoredConfiguration:
        return {"case_sensitive": self.cleaned_data["case_sensitive"]}


class ChangeBaseAddonForm(BaseAddonForm):
    """Base form for Change-based addons."""

    events = forms.MultipleChoiceField(
        label=gettext_lazy("Change events"),
        required=False,
        widget=SortedSelectMultiple(),
        choices=ActionEvents.choices,
    )


class BaseWebhooksAddonForm(ChangeBaseAddonForm):
    """Form for webhook add-on configuration."""

    webhook_url = WeblateServiceURLField(
        label=gettext_lazy("Webhook URL"),
        required=True,
    )

    field_order = [  # noqa: RUF012
        "webhook_url",
        "events",
    ]

    def clean_webhook_url(self) -> str:
        value = self.cleaned_data["webhook_url"]
        validate_webhook_url(value)
        return value


class WebhooksAddonForm(BaseWebhooksAddonForm):
    """Form for webhook add-on configuration."""

    secret = forms.CharField(
        label=gettext_lazy("Webhook secret"),
        validators=[
            validate_webhook_secret_string,
        ],
        required=False,
        help_text=gettext_lazy(
            "The Standard Webhooks secret is a base64 encoded string."
        ),
    )

    field_order = [  # noqa: RUF012
        "webhook_url",
        "secret",
        "events",
    ]


class FedoraMessagingAddonForm(ChangeBaseAddonForm):
    amqp_host = forms.CharField(
        label=gettext_lazy("AMQP broker host"),
        help_text=gettext_lazy("The AMQP broker to connect to."),
        validators=[DomainOrIPValidator()],
    )
    amqp_ssl = forms.BooleanField(
        label=gettext_lazy("Use SSL for AMQP connection"),
        required=False,
    )
    ca_cert = forms.CharField(
        widget=forms.Textarea(),
        label=gettext_lazy("CA certificates"),
        help_text=gettext_lazy(
            "Bundle of PEM encoded CA certificates used to validate the certificate presented by the server."
        ),
        required=False,
    )
    client_key = forms.CharField(
        widget=forms.Textarea(),
        label=gettext_lazy("Client SSL key"),
        help_text=gettext_lazy("PEM encoded client private SSL key."),
        required=False,
    )

    client_cert = forms.CharField(
        widget=forms.Textarea(),
        label=gettext_lazy("Client SSL certificates"),
        help_text=gettext_lazy("PEM encoded client SSL certificate."),
        required=False,
    )

    def clean(self) -> None:
        from .fedora_messaging import FedoraMessagingAddon  # noqa: PLC0415

        amqp_ssl = self.cleaned_data.get("amqp_ssl")
        if amqp_ssl is not None:
            if amqp_ssl:
                if (
                    not self.cleaned_data.get("ca_cert")
                    or not self.cleaned_data.get("client_key")
                    or not self.cleaned_data.get("client_cert")
                ):
                    raise forms.ValidationError(
                        {
                            "amqp_ssl": gettext(
                                "The SSL certificates have to be provided for SSL connection."
                            )
                        }
                    )

            elif (
                self.cleaned_data.get("ca_cert")
                or self.cleaned_data.get("client_key")
                or self.cleaned_data.get("client_cert")
            ):
                raise forms.ValidationError(
                    {
                        "amqp_ssl": gettext(
                            "The SSL certificates are not used without a SSL connection."
                        )
                    }
                )

        if amqp_host := self.cleaned_data.get("amqp_host"):
            try:
                FedoraMessagingAddon.configure_fedora_messaging(
                    amqp_host=amqp_host,
                    amqp_ssl=self.cleaned_data.get("amqp_ssl", False),
                    ca_cert=self.cleaned_data.get("ca_cert"),
                    client_key=self.cleaned_data.get("client_key"),
                    client_cert=self.cleaned_data.get("client_cert"),
                    force_update=True,
                )
            except ConfigurationException as error:
                raise forms.ValidationError(error.message) from error
