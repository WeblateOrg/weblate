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

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout
from django import forms
from django.http import QueryDict
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

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
        label=_("Path of generated MO file"),
        required=False,
        initial="{{ filename|stripext }}.mo",
        help_text=_("If not specified, the location of the PO file will be used."),
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
    filename = forms.CharField(label=_("Name of generated file"), required=True)
    template = forms.CharField(
        widget=forms.Textarea(), label=_("Content of generated file"), required=True
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
        label=_("Long lines wrapping"),
        choices=[
            (77, _("Wrap lines at 77 characters and at newlines")),
            (65535, _("Only wrap lines at newlines")),
            (-1, _("No line wrapping")),
        ],
        required=True,
        initial=77,
        help_text=_(
            "By default gettext wraps lines at 77 characters and at newlines. "
            "With the --no-wrap parameter, wrapping is only done at newlines."
        ),
    )


class MsgmergeForm(BaseAddonForm):
    previous = forms.BooleanField(
        label=_("Keep previous msgids of translated strings"),
        required=False,
        initial=True,
    )
    no_location = forms.BooleanField(
        label=_("Remove locations of translated strings"),
        required=False,
        initial=False,
    )
    fuzzy = forms.BooleanField(
        label=_("Use fuzzy matching"), required=False, initial=True
    )


class GitSquashForm(BaseAddonForm):
    squash = forms.ChoiceField(
        label=_("Commit squashing"),
        widget=forms.RadioSelect,
        choices=(
            ("all", _("All commits into one")),
            ("language", _("Per language")),
            ("file", _("Per file")),
            ("author", _("Per author")),
        ),
        initial="all",
        required=True,
    )
    append_trailers = forms.BooleanField(
        label=_("Append trailers to squashed commit message"),
        required=False,
        initial=True,
        help_text=_(
            "Trailer lines are lines that look similar to RFC 822 e-mail "
            "headers, at the end of the otherwise free-form part of a commit "
            "message, such as 'Co-authored-by: …'."
        ),
    )
    commit_message = forms.CharField(
        widget=forms.Textarea(),
        required=False,
        help_text=_(
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
    sort_keys = forms.BooleanField(label=_("Sort JSON keys"), required=False)
    indent = forms.IntegerField(
        label=_("JSON indentation"), min_value=0, initial=4, required=True
    )


class YAMLCustomizeForm(BaseAddonForm):
    indent = forms.IntegerField(
        label=_("YAML indentation"), min_value=1, max_value=10, initial=2, required=True
    )
    width = forms.ChoiceField(
        label=_("Long lines wrapping"),
        choices=[
            ("80", _("Wrap lines at 80 chars")),
            ("100", _("Wrap lines at 100 chars")),
            ("120", _("Wrap lines at 120 chars")),
            ("180", _("Wrap lines at 180 chars")),
            ("65535", _("No line wrapping")),
        ],
        required=True,
        initial=80,
    )
    line_break = forms.ChoiceField(
        label=_("Line breaks"),
        choices=[
            ("dos", _("DOS (\\r\\n)")),
            ("unix", _("UNIX (\\n)")),
            ("mac", _("MAC (\\r)")),
        ],
        required=True,
        initial="unix",
    )


class RemoveForm(BaseAddonForm):
    age = forms.IntegerField(
        label=_("Days to keep"), min_value=0, initial=30, required=True
    )


class RemoveSuggestionForm(RemoveForm):
    votes = forms.IntegerField(
        label=_("Voting threshold"),
        initial=0,
        required=True,
        help_text=_(
            "Threshold for removal. This field has no effect with " "voting turned off."
        ),
    )


class DiscoveryForm(BaseAddonForm):
    match = forms.CharField(
        label=_("Regular expression to match translation files against"), required=True
    )
    file_format = forms.ChoiceField(
        label=_("File format"),
        choices=FILE_FORMATS.get_choices(empty=True),
        initial="",
        required=True,
    )
    name_template = forms.CharField(
        label=_("Customize the component name"),
        initial="{{ component }}",
        required=True,
    )
    base_file_template = forms.CharField(
        label=_("Define the monolingual base filename"),
        initial="",
        required=False,
        help_text=_("Leave empty for bilingual translation files."),
    )
    new_base_template = forms.CharField(
        label=_("Define the base file for new translations"),
        initial="",
        required=False,
        help_text=_(
            "Filename of file used for creating new translations. "
            "For gettext choose .pot file."
        ),
    )
    language_regex = forms.CharField(
        label=_("Language filter"),
        max_length=200,
        initial="^[^.]+$",
        validators=[validate_re],
        help_text=_(
            "Regular expression to filter "
            "translation files against when scanning for filemask."
        ),
    )
    copy_addons = forms.BooleanField(
        label=_("Clone addons from the main component to the newly created ones"),
        required=False,
        initial=True,
    )
    remove = forms.BooleanField(
        label=_("Remove components for inexistant files"), required=False
    )
    confirm = forms.BooleanField(
        label=_("I confirm the above matches look correct"),
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
            Field("language_regex"),
            Field("copy_addons"),
            Field("remove"),
            ContextDiv(
                template="addons/discovery_help.html", context={"user": self.user}
            ),
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
            **ComponentDiscovery.extract_kwargs(self.cleaned_data)
        )

    def clean(self):
        self.cleaned_data["preview"] = False

        # There are some other errors or the form was loaded from db
        if self.errors or not isinstance(self.data, QueryDict):
            return

        self.cleaned_data["preview"] = True
        if not self.cleaned_data["confirm"]:
            raise forms.ValidationError(
                _("Please review and confirm the matched components.")
            )

    def clean_match(self):
        match = self.cleaned_data["match"]
        validate_re(match, ("component", "language"))
        return match

    @staticmethod
    def test_render(value):
        return validate_render(value, component="test")

    def template_clean(self, name):
        result = self.test_render(self.cleaned_data[name])
        if result and result == self.cleaned_data[name]:
            raise forms.ValidationError(
                _("Please include component markup in the template.")
            )
        return self.cleaned_data[name]

    def clean_name_template(self):
        return self.template_clean("name_template")

    def clean_base_file_template(self):
        return self.template_clean("base_file_template")

    def clean_new_base_template(self):
        return self.template_clean("new_base_template")


class AutoAddonForm(AutoForm, AddonFormMixin):
    def __init__(self, user, addon, instance=None, *args, **kwargs):
        self.user = user
        self._addon = addon
        super().__init__(obj=addon.instance.component, *args, **kwargs)


class BulkEditAddonForm(BulkEditForm, AddonFormMixin):
    def __init__(self, user, addon, instance=None, *args, **kwargs):
        self.user = user
        self._addon = addon
        component = addon.instance.component
        super().__init__(
            obj=component, project=component.project, user=None, *args, **kwargs
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
        label=_("Translation threshold"),
        initial=0,
        max_value=100,
        min_value=0,
        required=True,
        help_text=_("Threshold for inclusion of translations."),
    )
    css_selector = forms.CharField(
        label=_("CSS selector"),
        required=True,
        initial=".l10n",
        help_text=_("CSS selector to detect localizable elements."),
    )
    cookie_name = forms.CharField(
        label=_("Language cookie name"),
        required=False,
        initial="",
        help_text=_("Name of cookie which stores language preference."),
    )
    files = forms.CharField(
        widget=forms.Textarea(),
        label=_("Extract strings from HTML files"),
        required=False,
        help_text=_(
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


class PseudolocaleAddonForm(BaseAddonForm):
    source = forms.ChoiceField(label=_("Source strings"), required=True)
    target = forms.ChoiceField(label=_("Target translation"), required=True)
    prefix = forms.CharField(
        label=_("String prefix"),
        required=False,
        initial="",
    )
    suffix = forms.CharField(
        label=_("String suffix"),
        required=False,
        initial="",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [
            (translation.pk, str(translation.language))
            for translation in self._addon.instance.component.translation_set.all()
        ]
        self.fields["source"].choices = choices
        self.fields["target"].choices = choices

    def clean(self):
        if self.cleaned_data["source"] == self.cleaned_data["target"]:
            raise forms.ValidationError(
                _("The source and target have to be different languages.")
            )
