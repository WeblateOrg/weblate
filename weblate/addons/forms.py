# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout
from django import forms
from django.http import QueryDict
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy
from lxml.cssselect import CSSSelector

from weblate.formats.models import FILE_FORMATS
from weblate.trans.discovery import ComponentDiscovery
from weblate.trans.forms import AutoForm, BulkEditForm
from weblate.utils.forms import ContextDiv
from weblate.utils.render import validate_render, validate_render_component
from weblate.utils.validators import validate_filename, validate_re


class AddonFormMixin:
    def serialize_form(self):
        return self.cleaned_data

    def save(self):
        self._addon.configure(self.serialize_form())
        return self._addon.instance


class BaseAddonForm(forms.Form, AddonFormMixin):
    def __init__(self, user, addon, instance=None, *args, **kwargs):
        self._addon = addon
        self.user = user
        super().__init__(*args, **kwargs)


class GenerateMoForm(BaseAddonForm):
    path = forms.CharField(
        label=gettext_lazy("Path of generated MO file"),
        required=False,
        initial="{{ filename|stripext }}.mo",
        help_text=gettext_lazy(
            "If not specified, the location of the PO file will be used."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field("path"),
            ContextDiv(
                template="addons/generatemo_help.html", context={"user": self.user}
            ),
        )

    def test_render(self, value):
        validate_render_component(value, translation=True)

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field("filename"),
            Field("template"),
            ContextDiv(
                template="addons/generate_help.html", context={"user": self.user}
            ),
        )

    def test_render(self, value):
        validate_render_component(value, translation=True)

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

    def __init__(self, *args, **kwargs):
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

    def __init__(self, *args, **kwargs):
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
            if self.cleaned_data["preview"]:
                self.fields["confirm"].widget = forms.CheckboxInput()
                self.helper.layout.insert(0, Field("confirm"))
                created, matched, deleted = self.discovery.perform(
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

    def clean(self):
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
            matches = {key: "test" for key in self.cleaned_match_re.groupindex}
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


class AutoAddonForm(AutoForm, AddonFormMixin):
    def __init__(self, user, addon, instance=None, **kwargs):
        self.user = user
        self._addon = addon
        super().__init__(obj=addon.instance.component, **kwargs)


class BulkEditAddonForm(BulkEditForm, AddonFormMixin):
    def __init__(self, user, addon, instance=None, **kwargs):
        self.user = user
        self._addon = addon
        component = addon.instance.component
        super().__init__(obj=component, project=component.project, user=None, **kwargs)

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
    files = forms.CharField(
        widget=forms.Textarea(),
        label=gettext_lazy("Extract strings from HTML files"),
        required=False,
        help_text=gettext_lazy(
            "List of filenames in current repository or remote URLs to parse "
            "for translatable strings."
        ),
    )

    def __init__(self, *args, **kwargs):
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
            )
        return self.cleaned_data["css_selector"]


class PseudolocaleAddonForm(BaseAddonForm):
    source = forms.ChoiceField(label=gettext_lazy("Source strings"), required=True)
    target = forms.ChoiceField(
        label=gettext_lazy("Target translation"),
        required=True,
        help_text=gettext_lazy("All strings in this translation will be overwritten"),
    )
    prefix = forms.CharField(
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [
            (translation.pk, str(translation.language))
            for translation in self._addon.instance.component.translation_set.all()
        ]
        self.fields["source"].choices = choices
        self.fields["target"].choices = choices
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

    def clean(self):
        if self.cleaned_data["source"] == self.cleaned_data["target"]:
            raise forms.ValidationError(
                gettext("The source and target have to be different languages.")
            )
