# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout
from django import forms
from django.http import QueryDict
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy
from lxml.cssselect import CSSSelector

from weblate.formats.models import FILE_FORMATS
from weblate.trans.actions import ActionEvents
from weblate.trans.discovery import ComponentDiscovery
from weblate.trans.forms import AutoForm, BulkEditForm
from weblate.trans.models import Component, Project, Translation
from weblate.utils.forms import (
    CachedModelChoiceField,
    ContextDiv,
    SortedSelectMultiple,
    WeblateServiceURLField,
)
from weblate.utils.render import validate_render, validate_render_translation
from weblate.utils.validators import (
    validate_base64_encoded_string,
    validate_filename,
    validate_re,
)

if TYPE_CHECKING:
    from weblate.auth.models import User


class BaseAddonForm(forms.Form):
    def __init__(
        self, user: User | None, addon, instance=None, *args, **kwargs
    ) -> None:
        self._addon = addon
        self.user = user
        forms.Form.__init__(self, *args, **kwargs)

    def serialize_form(self):
        return self.cleaned_data

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


class GenerateForm(BaseAddonForm):
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


class GettextCustomizeForm(BaseAddonForm):
    width = forms.ChoiceField(
        label=gettext_lazy("Long lines wrapping"),
        choices=[
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
        ],
        required=True,
        initial=77,
        help_text=gettext_lazy(
            "By default gettext wraps lines at 77 characters and at newlines. "
            "With the --no-wrap parameter, wrapping is only done at newlines."
        ),
    )


class MsgmergeForm(BaseAddonForm):
    previous = forms.BooleanField(
        label=gettext_lazy("Keep previous msgids of translated strings"),
        required=False,
        initial=True,
    )
    no_location = forms.BooleanField(
        label=gettext_lazy("Remove locations of translated strings"),
        required=False,
        initial=False,
    )
    fuzzy = forms.BooleanField(
        label=gettext_lazy("Use fuzzy matching"), required=False, initial=True
    )


class GitSquashForm(BaseAddonForm):
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


class JSONCustomizeForm(BaseAddonForm):
    sort_keys = forms.BooleanField(label=gettext_lazy("Sort JSON keys"), required=False)
    indent = forms.IntegerField(
        label=gettext_lazy("JSON indentation"), min_value=0, initial=4, required=True
    )
    style = forms.ChoiceField(
        label=gettext_lazy("JSON indentation style"),
        choices=[
            ("spaces", gettext_lazy("Spaces")),
            ("tabs", gettext_lazy("Tabs")),
        ],
        required=True,
        initial="space",
    )


class XMLCustomizeForm(BaseAddonForm):
    """Class defining user Form to configure XML Formatting AddOn."""

    closing_tags = forms.BooleanField(
        label=gettext_lazy("Include closing tag for blank XML tags"),
        required=False,
        initial=True,
    )


class YAMLCustomizeForm(BaseAddonForm):
    indent = forms.IntegerField(
        label=gettext_lazy("YAML indentation"),
        min_value=1,
        max_value=10,
        initial=2,
        required=True,
    )
    width = forms.ChoiceField(
        label=gettext_lazy("Long lines wrapping"),
        choices=[
            ("80", gettext_lazy("Wrap lines at 80 chars")),
            ("100", gettext_lazy("Wrap lines at 100 chars")),
            ("120", gettext_lazy("Wrap lines at 120 chars")),
            ("180", gettext_lazy("Wrap lines at 180 chars")),
            ("65535", gettext_lazy("No line wrapping")),
        ],
        required=True,
        initial=80,
    )
    line_break = forms.ChoiceField(
        label=gettext_lazy("Line breaks"),
        choices=[
            ("dos", gettext_lazy("DOS (\\r\\n)")),
            ("unix", gettext_lazy("UNIX (\\n)")),
            ("mac", gettext_lazy("MAC (\\r)")),
        ],
        required=True,
        initial="unix",
    )


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


class DiscoveryForm(BaseAddonForm):
    match = forms.CharField(
        label=gettext_lazy("Regular expression to match translation files against"),
        required=True,
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
    )
    base_file_template = forms.CharField(
        label=gettext_lazy("Define the monolingual base filename"),
        initial="",
        required=False,
        help_text=gettext_lazy("Leave empty for bilingual translation files."),
    )
    new_base_template = forms.CharField(
        label=gettext_lazy("Define the base file for new translations"),
        initial="",
        required=False,
        help_text=gettext_lazy(
            "Filename of file used for creating new translations. "
            "For gettext choose .pot file."
        ),
    )
    intermediate_template = forms.CharField(
        label=gettext_lazy("Intermediate language file"),
        initial="",
        required=False,
        help_text=gettext_lazy(
            "Filename of intermediate translation file. In most cases "
            "this is a translation file provided by developers and is "
            "used when creating actual source strings."
        ),
    )

    language_regex = forms.CharField(
        label=gettext_lazy("Language filter"),
        max_length=200,
        initial="^[^.]+$",
        validators=[validate_re],
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
                            "matches_skipped": skipped,
                            "user": self.user,
                        },
                    ),
                )

    @cached_property
    def discovery(self):
        return ComponentDiscovery(
            self._addon.instance.component,
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
            return re.compile(self.cleaned_data["match"])
        except re.error:
            return None

    def test_render(self, value):
        if self.cleaned_match_re is None:
            matches = {"component": "test"}
        else:
            matches = dict.fromkeys(self.cleaned_match_re.groupindex, "test")
        return validate_render(value, **matches)

    def template_clean(self, name):
        result = self.test_render(self.cleaned_data[name])
        if result and result == self.cleaned_data[name]:
            raise forms.ValidationError(
                gettext("Please include component markup in the template.")
            )
        return self.cleaned_data[name]

    def clean_name_template(self):
        return self.template_clean("name_template")

    def clean_base_file_template(self):
        return self.template_clean("base_file_template")

    def clean_new_base_template(self):
        return self.template_clean("new_base_template")

    def clean_intermediate_template(self):
        return self.template_clean("intermediate_template")


class AutoAddonForm(BaseAddonForm, AutoForm):
    def __init__(self, user: User, addon, instance=None, **kwargs) -> None:
        BaseAddonForm.__init__(self, user, addon)
        AutoForm.__init__(
            self, obj=addon.instance.component or addon.instance.project, **kwargs
        )


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


class CDNJSForm(BaseAddonForm):
    threshold = forms.IntegerField(
        label=gettext_lazy("Translation threshold"),
        initial=0,
        max_value=100,
        min_value=0,
        required=True,
        help_text=gettext_lazy("Threshold for inclusion of translations."),
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
        label=gettext_lazy("Fixed string prefix"),
        required=False,
        initial="",
    )
    var_prefix = forms.CharField(
        label=gettext_lazy("Variable string prefix"),
        required=False,
        initial="",
    )
    suffix = forms.CharField(
        label=gettext_lazy("Fixed string suffix"),
        required=False,
        initial="",
    )
    var_suffix = forms.CharField(
        label=gettext_lazy("Variable string suffix"),
        required=False,
        initial="",
    )
    var_multiplier = forms.FloatField(
        label=gettext_lazy("Variable part multiplier"),
        required=False,
        initial=0.1,
        help_text=gettext_lazy(
            "How many times to repeat the variable part depending on "
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
            self.fields["source"].queryset = queryset
            self.fields["target"].queryset = queryset
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


class PropertiesSortAddonForm(BaseAddonForm):
    case_sensitive = forms.BooleanField(
        label=gettext_lazy("Enable case-sensitive key sorting"),
        required=False,
        initial=False,
    )


class ChangeBaseAddonForm(BaseAddonForm):
    """Base form for Change-based addons."""

    events = forms.MultipleChoiceField(
        label=gettext_lazy("Change events"),
        required=False,
        widget=SortedSelectMultiple(),
        choices=ActionEvents.choices,
    )


class WebhooksAddonForm(ChangeBaseAddonForm):
    """Form for webhook add-on configuration."""

    webhook_url = WeblateServiceURLField(
        label=gettext_lazy("Webhook URL"),
        required=True,
    )
    secret = forms.CharField(
        label=gettext_lazy("Secret"),
        validators=[
            validate_base64_encoded_string,
        ],
        required=False,
    )

    field_order = ["webhook_url", "secret", "events"]
