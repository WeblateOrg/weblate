# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import copy
import json
import re
from datetime import date, datetime, timedelta
from secrets import token_hex

from crispy_forms.bootstrap import InlineCheckboxes, InlineRadios, Tab, TabHolder
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Fieldset, Layout
from django import forms
from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.core.validators import FileExtensionValidator
from django.db.models import Q
from django.forms import model_to_dict
from django.forms.models import ModelChoiceIterator
from django.forms.utils import from_current_timezone
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.utils.translation import gettext, gettext_lazy
from translation_finder import DiscoveryResult, discover

from weblate.auth.models import Group, User
from weblate.checks.flags import Flags
from weblate.checks.models import CHECKS
from weblate.checks.utils import highlight_string
from weblate.formats.models import EXPORTERS, FILE_FORMATS
from weblate.glossary.forms import GlossaryAddMixin
from weblate.lang.data import BASIC_LANGUAGES
from weblate.lang.models import Language
from weblate.machinery.models import MACHINERY
from weblate.trans.backups import ProjectBackup
from weblate.trans.defines import (
    BRANCH_LENGTH,
    COMPONENT_NAME_LENGTH,
    FILENAME_LENGTH,
    REPO_LENGTH,
)
from weblate.trans.filter import FILTERS, get_filter_choice
from weblate.trans.models import Announcement, Change, Component, Label, Project, Unit
from weblate.trans.specialchars import RTL_CHARS_DATA, get_special_chars
from weblate.trans.util import check_upload_method_permissions, is_repo_link
from weblate.trans.validators import validate_check_flags
from weblate.utils.antispam import is_spam
from weblate.utils.forms import (
    ColorWidget,
    ContextDiv,
    EmailField,
    FilterForm,
    QueryField,
    SearchField,
    SortedSelect,
    SortedSelectMultiple,
    UserField,
    UsernameField,
)
from weblate.utils.hash import checksum_to_hash, hash_to_checksum
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_CHOICES,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_READONLY,
    STATE_TRANSLATED,
)
from weblate.utils.validators import validate_file_extension
from weblate.vcs.models import VCS_REGISTRY

BUTTON_TEMPLATE = """
<button class="btn btn-default {0}" title="{1}" {2}>{3}</button>
"""
RADIO_TEMPLATE = """
<label class="btn btn-default {0}" title="{1}">
<input type="radio" name="{2}" value="{3}" {4}/>
{5}
</label>
"""
GROUP_TEMPLATE = """
<div class="btn-group btn-group-xs" {0}>{1}</div>
"""
TOOLBAR_TEMPLATE = """
<div class="btn-toolbar pull-right flip editor-toolbar">{0}</div>
"""


class MarkdownTextarea(forms.Textarea):
    def __init__(self, **kwargs):
        kwargs["attrs"] = {
            "dir": "auto",
            "class": "markdown-editor highlight-editor",
            "data-mode": "markdown",
        }
        super().__init__(**kwargs)


class WeblateDateInput(forms.DateInput):
    input_type = "date"


class WeblateDateField(forms.DateField):
    def __init__(self, **kwargs):
        if "widget" not in kwargs:
            kwargs["widget"] = WeblateDateInput
        super().__init__(**kwargs)

    def to_python(self, value):
        """Produce timezone-aware datetime with 00:00:00 as time."""
        value = super().to_python(value)
        if isinstance(value, date):
            return from_current_timezone(
                datetime(value.year, value.month, value.day, 0, 0, 0)  # noqa: DTZ001
            )
        return value


class ChecksumField(forms.CharField):
    """Field for handling checksum IDs for translation."""

    def __init__(self, *args, **kwargs):
        kwargs["widget"] = forms.HiddenInput
        super().__init__(*args, **kwargs)

    def clean(self, value):
        super().clean(value)
        if not value:
            return None
        try:
            return checksum_to_hash(value)
        except ValueError:
            raise ValidationError(gettext("Invalid checksum specified!"))


class FlagField(forms.CharField):
    default_validators = [validate_check_flags]


class PluralTextarea(forms.Textarea):
    """Text-area extension which possibly handles plurals."""

    def __init__(self, *args, **kwargs):
        self.profile = None
        super().__init__(*args, **kwargs)

    def get_rtl_toolbar(self, fieldname):
        # Special chars
        chars = format_html_join(
            "\n",
            BUTTON_TEMPLATE,
            (
                (
                    "specialchar",
                    name,
                    format_html(
                        'data-value="{}"',
                        mark_safe(  # noqa: S308
                            value.encode("ascii", "xmlcharrefreplace").decode("ascii")
                        ),
                    ),
                    char,
                )
                for name, char, value in RTL_CHARS_DATA
            ),
        )

        groups = format_html_join(
            "\n", GROUP_TEMPLATE, [("", chars)]  # Only one group.
        )

        return format_html(TOOLBAR_TEMPLATE, groups)

    def get_rtl_toggle(self, language, fieldname):
        if language.direction != "rtl":
            return ""

        # RTL/LTR switch
        rtl_name = f"rtl-{fieldname}"
        rtl_switch = format_html_join(
            "\n",
            RADIO_TEMPLATE,
            [
                (
                    "direction-toggle active",
                    gettext("Toggle text direction"),
                    rtl_name,
                    "rtl",
                    format_html('checked="checked"'),
                    "RTL",
                ),
                (
                    "direction-toggle",
                    gettext("Toggle text direction"),
                    rtl_name,
                    "ltr",
                    format_html(""),
                    "LTR",
                ),
            ],
        )
        groups = format_html_join(
            "\n",
            GROUP_TEMPLATE,
            [(format_html('data-toggle="buttons"'), rtl_switch)],  # Only one group.
        )
        return format_html(TOOLBAR_TEMPLATE, groups)

    def get_toolbar(self, language, fieldname, unit, idx, source):
        """Return toolbar HTML code."""
        profile = self.profile

        # Special chars
        chars = format_html_join(
            "\n",
            BUTTON_TEMPLATE,
            (
                (
                    "specialchar",
                    name,
                    format_html(
                        'data-value="{}"',
                        mark_safe(  # noqa: S308
                            value.encode("ascii", "xmlcharrefreplace").decode("ascii")
                        ),
                    ),
                    char,
                )
                for name, char, value in get_special_chars(
                    language, profile.special_chars, unit.source
                )
            ),
        )

        groups = format_html_join(
            "\n", GROUP_TEMPLATE, [("", chars)]  # Only one group.
        )

        result = format_html(TOOLBAR_TEMPLATE, groups)

        if language.direction == "rtl":
            result = format_html("{}{}", self.get_rtl_toolbar(fieldname), result)

        return result

    def render(self, name, value, attrs=None, renderer=None, **kwargs):
        """Render all textareas with correct plural labels."""
        unit = value
        values = unit.get_target_plurals()
        translation = unit.translation
        lang_label = lang = translation.language
        if "zen-mode" in self.attrs:
            lang_label = format_html(
                '<a class="language" href="{}">{}</a>',
                unit.get_absolute_url(),
                lang_label,
            )
        plural = translation.plural
        tabindex = self.attrs["tabindex"]
        plurals = unit.get_source_plurals()
        placeables = set()
        for text in plurals:
            placeables.update(hl[2] for hl in highlight_string(text, unit))
        placeables = list(placeables)
        show_plural_labels = len(values) > 1 and not translation.component.is_multivalue

        # Need to add extra class
        attrs["class"] = "translation-editor form-control highlight-editor"
        attrs["tabindex"] = tabindex
        attrs["lang"] = lang.code
        attrs["dir"] = lang.direction
        attrs["rows"] = 3
        attrs["data-max"] = unit.get_max_length()
        attrs["data-mode"] = unit.edit_mode
        attrs["data-placeables"] = "|".join(re.escape(pl) for pl in placeables if pl)
        if unit.readonly:
            attrs["readonly"] = 1

        # Okay we have more strings
        ret = []
        base_id = f"id_{unit.checksum}"
        for idx, val in enumerate(values):
            # Generate ID
            fieldname = f"{name}_{idx}"
            fieldid = f"{base_id}_{idx}"
            attrs["id"] = fieldid
            attrs["tabindex"] = tabindex + idx
            source = plurals[1] if idx and len(plurals) > 1 else plurals[0]

            # Render textare
            textarea = super().render(fieldname, val, attrs, renderer, **kwargs)
            # Label for plural
            label = lang_label
            if show_plural_labels:
                label = format_html("{}, {}", label, plural.get_plural_label(idx))
            elif translation.component.is_multivalue and idx > 0:
                label = format_html("{}, {}", label, gettext("Alternative translation"))
            ret.append(
                render_to_string(
                    "snippets/editor.html",
                    {
                        "toolbar": self.get_toolbar(lang, fieldid, unit, idx, source),
                        "fieldid": fieldid,
                        "label": label,
                        "textarea": textarea,
                        "max_length": attrs["data-max"],
                        "length": len(val),
                        "source_length": len(source),
                        "rtl_toggle": self.get_rtl_toggle(lang, fieldid),
                    },
                )
            )

        # Show plural formula for more strings
        if show_plural_labels:
            ret.append(
                render_to_string(
                    "snippets/plural-formula.html",
                    {"plural": plural, "user": self.profile.user},
                )
            )

        return format_html_join("", "{}", ((v,) for v in ret))

    def value_from_datadict(self, data, files, name):
        """Return processed plurals as a list."""
        ret = []
        for idx in range(0, 10):
            fieldname = f"{name}_{idx:d}"
            if fieldname not in data:
                break
            ret.append(data.get(fieldname, ""))
        return [r.replace("\r", "") for r in ret]


class PluralField(forms.CharField):
    """
    Renderer for the plural field.

    The only difference from CharField is that it does not
    enforce the value to be a string.
    """

    def __init__(self, **kwargs):
        kwargs["label"] = ""
        super().__init__(widget=PluralTextarea, **kwargs)

    def to_python(self, value):
        """Return list or string as returned by PluralTextarea."""
        return value

    def clean(self, value):
        value = super().clean(value)
        if not value or (self.required and not any(value)):
            raise ValidationError(self.error_messages["required"], code="required")
        return value


class FilterField(forms.ChoiceField):
    def __init__(self, *args, **kwargs):
        kwargs["label"] = gettext_lazy("Search filter")
        if "required" not in kwargs:
            kwargs["required"] = False
        kwargs["choices"] = get_filter_choice()
        kwargs["error_messages"] = {
            "invalid_choice": gettext_lazy("Please choose a valid filter type.")
        }
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value == "untranslated":
            return "todo"
        return super().to_python(value)


class ChecksumForm(forms.Form):
    """Form for handling checksum IDs for translation."""

    checksum = ChecksumField(required=True)

    def __init__(self, unit_set, *args, **kwargs):
        self.unit_set = unit_set
        super().__init__(*args, **kwargs)

    def clean_checksum(self):
        """Validate whether checksum is valid and fetches unit for it."""
        if "checksum" not in self.cleaned_data:
            return

        unit_set = self.unit_set

        try:
            self.cleaned_data["unit"] = unit_set.filter(
                id_hash=self.cleaned_data["checksum"]
            )[0]
        except (Unit.DoesNotExist, IndexError):
            raise ValidationError(
                gettext("The string you wanted to translate is no longer available.")
            )


class UnitForm(forms.Form):
    def __init__(self, unit: Unit, *args, **kwargs):
        self.unit = unit
        super().__init__(*args, **kwargs)


class FuzzyField(forms.BooleanField):
    help_as_icon = True

    def __init__(self, *args, **kwargs):
        kwargs["label"] = gettext_lazy("Needs editing")
        kwargs["help_text"] = gettext_lazy(
            'Strings are usually marked as "Needs editing" after the source '
            "string is updated, or when marked as such manually."
        )
        super().__init__(*args, **kwargs)
        self.widget.attrs["class"] = "fuzzy_checkbox"


class TranslationForm(UnitForm):
    """Form used for translation of single string."""

    contentsum = ChecksumField(required=True)
    translationsum = ChecksumField(required=True)
    target = PluralField(required=False)
    fuzzy = FuzzyField(required=False)
    review = forms.ChoiceField(
        label=gettext_lazy("Review state"),
        choices=[
            (STATE_FUZZY, gettext_lazy("Needs editing")),
            (STATE_TRANSLATED, gettext_lazy("Waiting for review")),
            (STATE_APPROVED, gettext_lazy("Approved")),
        ],
        required=False,
        widget=forms.RadioSelect,
    )
    explanation = forms.CharField(
        widget=MarkdownTextarea,
        label=gettext_lazy("Explanation"),
        help_text=gettext_lazy(
            "Additional explanation to clarify meaning or usage of the string."
        ),
        max_length=1000,
        required=False,
    )

    def __init__(self, user, unit: Unit, *args, **kwargs):
        if unit is not None:
            kwargs["initial"] = {
                "checksum": unit.checksum,
                "contentsum": hash_to_checksum(unit.content_hash),
                "translationsum": hash_to_checksum(unit.get_target_hash()),
                "target": unit,
                "fuzzy": unit.fuzzy,
                "review": unit.state,
                "explanation": unit.explanation,
            }
            kwargs["auto_id"] = f"id_{unit.checksum}_%s"
        tabindex = kwargs.pop("tabindex", 100)
        super().__init__(unit, *args, **kwargs)
        if unit.readonly:
            for field in ["target", "fuzzy", "review"]:
                self.fields[field].widget.attrs["readonly"] = 1
            self.fields["review"].choices = [
                (STATE_READONLY, gettext_lazy("Read only")),
            ]
        self.user = user
        self.fields["target"].widget.attrs["tabindex"] = tabindex
        self.fields["target"].widget.profile = user.profile
        self.fields["review"].widget.attrs["class"] = "review_radio"
        # Avoid failing validation on untranslated string
        if args:
            self.fields["review"].choices.append((STATE_EMPTY, ""))
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Field("target"),
            Field("fuzzy"),
            Field("contentsum"),
            Field("translationsum"),
            InlineRadios("review"),
            Field("explanation"),
        )
        if unit and user.has_perm("unit.review", unit.translation):
            self.fields["fuzzy"].widget = forms.HiddenInput()
        else:
            self.fields["review"].widget = forms.HiddenInput()
        if unit.translation.component.is_glossary:
            if unit.is_source:
                self.fields["explanation"].label = gettext("Source string explanation")
            else:
                self.fields["explanation"].label = gettext("Translation explanation")
        else:
            self.fields["explanation"].widget = forms.HiddenInput()

    def clean(self):
        super().clean()

        # Check required fields
        required = {"target", "contentsum", "translationsum"}
        if not required.issubset(self.cleaned_data):
            return

        unit = self.unit

        if self.cleaned_data["contentsum"] != unit.content_hash:
            raise ValidationError(
                gettext(
                    "The source string has changed meanwhile. "
                    "Please check your changes."
                )
            )

        if self.cleaned_data["translationsum"] != unit.get_target_hash():
            # Allow repeated edits by the same author
            last_author = unit.get_last_content_change()[0]
            if last_author != self.user:
                raise ValidationError(
                    gettext(
                        "The translation of the string has changed meanwhile. "
                        "Please check your changes."
                    )
                )

        # Add extra margin to limit to allow XML tags which might
        # be ignored for the length calculation. On the other side,
        # we do not want to process arbitrarily long strings here.
        max_length = 10 * (unit.get_max_length() + 100)
        for text in self.cleaned_data["target"]:
            if len(text) > max_length:
                raise ValidationError(gettext("Translation text too long!"))
        if self.user.has_perm(
            "unit.review", unit.translation
        ) and self.cleaned_data.get("review"):
            self.cleaned_data["state"] = int(self.cleaned_data["review"])
        elif self.cleaned_data["fuzzy"]:
            self.cleaned_data["state"] = STATE_FUZZY
        else:
            self.cleaned_data["state"] = STATE_TRANSLATED


class ZenTranslationForm(TranslationForm):
    checksum = ChecksumField(required=True)

    def __init__(self, user, unit, *args, **kwargs):
        super().__init__(user, unit, *args, **kwargs)
        self.helper.form_action = reverse(
            "save_zen", kwargs={"path": unit.translation.get_url_path()}
        )
        self.helper.form_tag = True
        self.helper.disable_csrf = False
        self.helper.layout.append(Field("checksum"))
        self.fields["target"].widget.attrs["zen-mode"] = True
        if not user.has_perm("unit.edit", unit):
            for field in ["target", "fuzzy", "review"]:
                self.fields[field].widget.attrs["disabled"] = 1


class DownloadForm(forms.Form):
    q = QueryField()
    format = forms.ChoiceField(
        label=gettext_lazy("File format"),
        choices=[],
        initial="po",
        required=True,
        widget=forms.RadioSelect,
    )

    def __init__(self, translation, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["format"].choices = [
            (x.name, x.verbose) for x in EXPORTERS.values() if x.supports(translation)
        ]
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            SearchField("q"),
            InlineRadios("format"),
        )


class SimpleUploadForm(forms.Form):
    """Base form for uploading a file."""

    file = forms.FileField(
        label=gettext_lazy("File"), validators=[validate_file_extension]
    )
    method = forms.ChoiceField(
        label=gettext_lazy("File upload mode"),
        choices=(
            ("translate", gettext_lazy("Add as translation")),
            ("approve", gettext_lazy("Add as approved translation")),
            ("suggest", gettext_lazy("Add as suggestion")),
            ("fuzzy", gettext_lazy("Add as translation needing edit")),
            ("replace", gettext_lazy("Replace existing translation file")),
            ("source", gettext_lazy("Update source strings")),
            ("add", gettext_lazy("Add new strings")),
        ),
        widget=forms.RadioSelect,
        required=True,
    )
    fuzzy = forms.ChoiceField(
        label=gettext_lazy('Processing of "Needs editing" strings'),
        choices=(
            ("", gettext_lazy("Do not import")),
            ("process", gettext_lazy('Import as "Needs editing"')),
            ("approve", gettext_lazy("Import as translated")),
        ),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False

    @staticmethod
    def get_field_doc(field):
        return ("user/files", f"upload-{field.name}")

    def remove_translation_choice(self, value):
        """Remove "Add as translation" choice."""
        choices = self.fields["method"].choices
        self.fields["method"].choices = [
            choice for choice in choices if choice[0] != value
        ]


class UploadForm(SimpleUploadForm):
    """Uploading form with the option to overwrite current messages."""

    conflicts = forms.ChoiceField(
        label=gettext_lazy("Conflict handling"),
        help_text=gettext_lazy(
            "Whether to overwrite existing translations if the string is "
            "already translated."
        ),
        choices=(
            ("", gettext_lazy("Change only untranslated strings")),
            ("replace-translated", gettext_lazy("Change translated strings")),
            (
                "replace-approved",
                gettext_lazy("Change translated and approved strings"),
            ),
        ),
        required=False,
        initial="replace-translated",
    )


class ExtraUploadForm(UploadForm):
    """Advanced upload form for users who can override authorship."""

    author_name = forms.CharField(label=gettext_lazy("Author name"))
    author_email = EmailField(label=gettext_lazy("Author e-mail"))


def get_upload_form(user, translation, *args, **kwargs):
    """Return correct upload form based on user permissions."""
    if user.has_perm("upload.authorship", translation):
        form = ExtraUploadForm
        kwargs["initial"] = {"author_name": user.full_name, "author_email": user.email}
    elif user.has_perm("upload.overwrite", translation):
        form = UploadForm
    else:
        form = SimpleUploadForm
    result = form(*args, **kwargs)
    for method in [x[0] for x in result.fields["method"].choices]:
        if not check_upload_method_permissions(user, translation, method):
            result.remove_translation_choice(method)
    # Remove approved choice for non review projects
    if not user.has_perm("unit.review", translation) and form != SimpleUploadForm:
        result.fields["conflicts"].choices = [
            choice
            for choice in result.fields["conflicts"].choices
            if choice[0] != "approved"
        ]
    return result


class SearchForm(forms.Form):
    """Text-searching form."""

    q = QueryField()
    sort_by = forms.CharField(required=False, widget=forms.HiddenInput)
    checksum = ChecksumField(required=False)
    offset = forms.IntegerField(min_value=-1, required=False, widget=forms.HiddenInput)
    offset_kwargs = {}

    def __init__(self, user, language=None, show_builder=True, **kwargs):
        """Generate choices for other components in the same project."""
        self.user = user
        self.language = language
        super().__init__(**kwargs)

        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field("offset", **self.offset_kwargs),
                SearchField("q"),
                Field("sort_by", template="snippets/sort-field.html"),
                css_class="btn-toolbar",
                role="toolbar",
            ),
            ContextDiv(
                template="snippets/query-builder.html",
                context={
                    "user": self.user,
                    "month_ago": timezone.now() - timedelta(days=31),
                    "show_builder": show_builder,
                    "language": self.language,
                },
            ),
            Field("checksum"),
            # Add hidden submit button so that submission via enter works
            # See https://stackoverflow.com/a/477699/225718
            HTML('<input type="submit" hidden />'),
        )

    def get_name(self):
        """Return verbose name for a search."""
        return FILTERS.get_search_name(self.cleaned_data.get("q", ""))

    def get_search_query(self):
        return self.cleaned_data["q"]

    def clean_offset(self):
        if self.cleaned_data.get("offset") is None:
            self.cleaned_data["offset"] = 1
        return self.cleaned_data["offset"]

    def items(self):
        items = []
        # Skip checksum and offset as these change
        ignored = {"offset", "checksum"}
        for param in sorted(self.cleaned_data):
            value = self.cleaned_data[param]
            # We don't care about empty values or ignored ones
            if value is None or param in ignored:
                continue
            if isinstance(value, bool):
                # Only store true values
                if value:
                    items.append((param, "1"))
            elif isinstance(value, int):
                # Avoid storing 0 values
                if value > 0:
                    items.append((param, str(value)))
            elif isinstance(value, datetime):
                # Convert date to string
                items.append((param, value.date().isoformat()))
            elif isinstance(value, list):
                items.extend((param, val) for val in value)
            elif isinstance(value, User):
                items.append((param, value.username))
            elif value:
                # It should be a string here
                items.append((param, value))
        return items

    def urlencode(self):
        return urlencode(self.items())

    def reset_offset(self):
        """
        Resets form offset.

        This is needed to avoid issues when using the form as the default for
        any new search.
        """
        data = copy.copy(self.data)  # pylint: disable=access-member-before-definition
        data["offset"] = "1"
        data["checksum"] = ""
        self.data = data
        return self


class PositionSearchForm(SearchForm):
    offset = forms.IntegerField(min_value=-1, required=False)
    offset_kwargs = {"template": "snippets/position-field.html"}


class MergeForm(UnitForm):
    """Simple form for merging the translation of two units."""

    merge = forms.IntegerField()

    def clean(self):
        super().clean()
        if "merge" not in self.cleaned_data:
            return None
        unit = self.unit
        translation = unit.translation
        project = translation.component.project
        try:
            self.cleaned_data["merge_unit"] = merge_unit = Unit.objects.get(
                pk=self.cleaned_data["merge"],
                translation__component__project=project,
                translation__language=translation.language,
            )
        except Unit.DoesNotExist:
            raise ValidationError(gettext("Could not find the merged string."))
        else:
            # Compare in Python to ensure case sensitiveness on MySQL
            if not translation.is_source and unit.source != merge_unit.source:
                raise ValidationError(gettext("Could not find merged string."))
        return self.cleaned_data


class RevertForm(UnitForm):
    """Form for reverting edits."""

    revert = forms.IntegerField()

    def clean(self):
        super().clean()
        if "revert" not in self.cleaned_data:
            return None
        try:
            self.cleaned_data["revert_change"] = Change.objects.get(
                pk=self.cleaned_data["revert"], unit=self.unit
            )
        except Change.DoesNotExist:
            raise ValidationError(gettext("Could not find the reverted change."))
        return self.cleaned_data


class AutoForm(forms.Form):
    """Automatic translation form."""

    mode = forms.ChoiceField(
        label=gettext_lazy("Automatic translation mode"),
        initial="suggest",
    )
    filter_type = FilterField(
        required=True,
        initial="todo",
        help_text=gettext_lazy(
            "Please note that translating all strings will "
            "discard all existing translations."
        ),
    )
    auto_source = forms.ChoiceField(
        label=gettext_lazy("Source of automated translations"),
        choices=[
            ("others", gettext_lazy("Other translation components")),
            ("mt", gettext_lazy("Machine translation")),
        ],
        initial="others",
    )
    component = forms.ChoiceField(
        label=gettext_lazy("Components"),
        required=False,
        help_text=gettext_lazy(
            "Turn on contribution to shared translation memory for the project to "
            "get access to additional components."
        ),
        initial="",
    )
    engines = forms.MultipleChoiceField(
        label=gettext_lazy("Machine translation engines"), choices=[], required=False
    )
    threshold = forms.IntegerField(
        label=gettext_lazy("Score threshold"), initial=80, min_value=1, max_value=100
    )

    def __init__(self, obj, user=None, *args, **kwargs):
        """Generate choices for other components in the same project."""
        super().__init__(*args, **kwargs)
        self.obj = obj

        # Add components from other projects with enabled shared TM
        self.components = obj.project.component_set.filter(
            source_language=obj.source_language
        ) | Component.objects.filter(
            source_language_id=obj.source_language_id,
            project__contribute_shared_tm=True,
        ).exclude(
            project=obj.project
        )

        # Fetching first few entries is faster than doing a count query on possibly
        # thousands of components
        if len(self.components.values_list("id")[:30]) == 30:
            # Do not show choices when too many
            self.fields["component"] = forms.CharField(
                required=False,
                label=gettext("Component"),
                help_text=gettext(
                    "Enter slug of a component to use as source, "
                    "keep blank to use all components in the current project."
                ),
            )
        else:
            choices = [
                (s.id, str(s))
                for s in self.components.order_project().prefetch_related("project")
            ]

            self.fields["component"].choices = [
                ("", gettext("All components in current project")),
                *choices,
            ]

        machinery_settings = obj.project.get_machinery_settings()

        engines = sorted(
            (
                MACHINERY[engine](setting)
                for engine, setting in machinery_settings.items()
                if engine in MACHINERY
            ),
            key=lambda engine: engine.name,
        )
        engine_ids = {engine.get_identifier() for engine in engines}
        self.fields["engines"].choices = [
            (engine.get_identifier(), engine.name) for engine in engines
        ]
        if "weblate" in engine_ids:
            self.fields["engines"].initial = "weblate"

        use_types = {"all", "nottranslated", "todo", "fuzzy", "check:inconsistent"}

        self.fields["filter_type"].choices = [
            x for x in self.fields["filter_type"].choices if x[0] in use_types
        ]

        choices = [
            ("suggest", gettext("Add as suggestion")),
            ("translate", gettext("Add as translation")),
            ("fuzzy", gettext('Add as "Needing edit"')),
        ]
        if user is not None and user.has_perm("unit.review", obj):
            choices.append(("approved", gettext("Add as approved translation")))
        self.fields["mode"].choices = choices

        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field("mode"),
            Field("filter_type"),
            InlineRadios("auto_source", id="select_auto_source"),
            Div("component", css_id="auto_source_others"),
            Div("engines", "threshold", css_id="auto_source_mt"),
        )

    def clean_component(self):
        component = self.cleaned_data["component"]
        if not component:
            return None
        if component.isdigit():
            try:
                result = self.components.get(pk=component)
            except Component.DoesNotExist:
                raise ValidationError(gettext("Component not found!"))
        else:
            slashes = component.count("/")
            if slashes == 0:
                try:
                    result = self.components.get(
                        slug=component, project=self.obj.project
                    )
                except Component.DoesNotExist:
                    raise ValidationError(gettext("Component not found!"))
            elif slashes == 1:
                project_slug, component_slug = component.split("/")
                try:
                    result = self.components.get(
                        slug=component_slug, project__slug=project_slug
                    )
                except Component.DoesNotExist:
                    raise ValidationError(gettext("Component not found!"))
            else:
                raise ValidationError(gettext("Please provide valid component slug!"))
        return result.pk


class CommentForm(forms.Form):
    """Simple commenting form."""

    scope = forms.ChoiceField(
        label=gettext_lazy("Scope"),
        help_text=gettext_lazy(
            "Is your comment specific to this "
            "translation, or generic for all of them?"
        ),
        choices=(
            (
                "report",
                gettext_lazy("Report issue with the source string"),
            ),
            (
                "global",
                gettext_lazy(
                    "Source string comment, suggestions for changes to this string"
                ),
            ),
            (
                "translation",
                gettext_lazy("Translation comment, discussions with other translators"),
            ),
        ),
    )
    comment = forms.CharField(
        widget=MarkdownTextarea,
        label=gettext_lazy("New comment"),
        help_text=gettext_lazy("You can use Markdown and mention users by @username."),
        max_length=1000,
    )

    def __init__(self, project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove bug-report in case source review is not enabled
        if not project.source_review:
            self.fields["scope"].choices = self.fields["scope"].choices[1:]


class EngageForm(forms.Form):
    """Form to choose language for engagement widgets."""

    lang = forms.ModelChoiceField(
        Language.objects.none(),
        empty_label=gettext_lazy("All languages"),
        required=False,
        to_field_name="code",
    )
    component = forms.ModelChoiceField(
        Component.objects.none(),
        required=False,
        empty_label=gettext_lazy("All components"),
        to_field_name="slug",
    )

    def __init__(self, user, project, *args, **kwargs):
        """Dynamically generate choices for used languages in the project."""
        super().__init__(*args, **kwargs)

        self.fields["lang"].queryset = project.languages
        self.fields["component"].queryset = project.component_set.filter_access(
            user
        ).order()


class NewLanguageOwnerForm(forms.Form):
    """Form for requesting a new language."""

    lang = forms.MultipleChoiceField(
        label=gettext_lazy("Languages"), choices=[], widget=forms.SelectMultiple
    )

    def get_lang_objects(self):
        return Language.objects.exclude(
            Q(translation__component=self.component) | Q(component=self.component)
        )

    def __init__(self, component, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.component = component
        languages = self.get_lang_objects()
        self.fields["lang"].choices = languages.as_choices()


class NewLanguageForm(NewLanguageOwnerForm):
    """Form for requesting a new language."""

    lang = forms.ChoiceField(
        label=gettext_lazy("Language"), choices=[], widget=forms.Select
    )

    def get_lang_objects(self):
        codes = BASIC_LANGUAGES
        if settings.BASIC_LANGUAGES is not None:
            codes = settings.BASIC_LANGUAGES
        return super().get_lang_objects().filter(code__in=codes)

    def __init__(self, component, *args, **kwargs):
        super().__init__(component, *args, **kwargs)
        self.fields["lang"].choices = [
            ("", gettext("Please choose")),
            *self.fields["lang"].choices,
        ]

    def clean_lang(self):
        # Compatibility with NewLanguageOwnerForm
        return [self.cleaned_data["lang"]]


def get_new_language_form(request, component):
    """Return new language form for user."""
    if not request.user.has_perm("translation.add", component):
        raise PermissionDenied
    if request.user.has_perm("translation.add_more", component):
        return NewLanguageOwnerForm
    return NewLanguageForm


class ContextForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ("explanation", "labels", "extra_flags")
        widgets = {
            "labels": forms.CheckboxSelectMultiple(),
            "explanation": MarkdownTextarea,
        }

    doc_links = {
        "explanation": ("admin/translating", "additional-explanation"),
        "labels": ("devel/translations", "labels"),
        "extra_flags": ("admin/translating", "additional-flags"),
    }

    def get_field_doc(self, field):
        return self.doc_links[field.name]

    def __init__(self, data=None, instance=None, user=None, **kwargs):
        kwargs["initial"] = {
            "labels": Label.objects.filter(
                Q(unit=instance) | Q(unit__source_unit=instance)
            )
        }
        super().__init__(data=data, instance=instance, **kwargs)
        project = instance.translation.component.project
        self.fields["labels"].queryset = project.label_set.all()
        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("explanation"),
            Field("labels"),
            ContextDiv(
                template="snippets/labels_description.html",
                context={"project": project, "user": user},
            ),
            Field("extra_flags"),
        )
        self.user = user

    def save(self, commit=True):
        self.instance.update_explanation(
            self.cleaned_data["explanation"], self.user, save=False
        )
        if commit:
            self.instance.save(same_content=True)
            self._save_m2m()
            return self.instance
        return super().save(commit)


class UserManageForm(forms.Form):
    user = UserField(
        label=gettext_lazy("User to add"),
        required=True,
        help_text=gettext_lazy(
            "Please type in an existing Weblate account name or e-mail address."
        ),
    )


class UserAddTeamForm(UserManageForm):
    make_admin = forms.BooleanField(
        required=False,
        initial=False,
        label=gettext_lazy("Team administrator"),
        help_text=gettext_lazy("Allow user to add or remove users from a team."),
    )


class UserBlockForm(forms.Form):
    user = UserField(
        label=gettext_lazy("User to block"),
        help_text=gettext_lazy(
            "Please type in an existing Weblate account name or e-mail address."
        ),
    )
    expiry = forms.ChoiceField(
        label=gettext_lazy("Block duration"),
        choices=(
            ("", gettext_lazy("Block the user until I unblock")),
            ("1", gettext_lazy("Block the user for one day")),
            ("7", gettext_lazy("Block the user for one week")),
            ("30", gettext_lazy("Block the user for one month")),
        ),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        if "auto_id" not in kwargs:
            kwargs["auto_id"] = "id_block_%s"
        super().__init__(*args, **kwargs)


class ReportsForm(forms.Form):
    style = forms.ChoiceField(
        label=gettext_lazy("Report format"),
        help_text=gettext_lazy("Choose a file format for the report"),
        choices=(
            ("rst", gettext_lazy("reStructuredText")),
            ("json", gettext_lazy("JSON")),
            ("html", gettext_lazy("HTML")),
        ),
    )
    period = forms.ChoiceField(
        label=gettext_lazy("Report period"),
        choices=(
            ("30days", gettext_lazy("Last 30 days")),
            ("this-month", gettext_lazy("This month")),
            ("month", gettext_lazy("Last month")),
            ("this-year", gettext_lazy("This year")),
            ("year", gettext_lazy("Last year")),
            ("", gettext_lazy("As specified below")),
        ),
        required=False,
    )
    start_date = WeblateDateField(label=gettext_lazy("Starting date"), required=False)
    end_date = WeblateDateField(label=gettext_lazy("Ending date"), required=False)
    language = forms.ChoiceField(
        label=gettext_lazy("Language"),
        choices=[("", gettext_lazy("All languages"))],
        required=False,
    )

    def __init__(self, scope, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("style"),
            Field("period"),
            Field("language"),
            Field("start_date"),
            Field("end_date"),
        )
        if not scope:
            languages = Language.objects.have_translation()
        elif "project" in scope:
            languages = Language.objects.filter(
                translation__component__project=scope["project"]
            ).distinct()
        elif "component" in scope:
            languages = Language.objects.filter(
                translation__component=scope["component"]
            ).exclude(pk=scope["component"].source_language_id)
        self.fields["language"].choices += languages.as_choices()

    def clean(self):
        super().clean()
        # Invalid value, skip rest of the validation
        if "period" not in self.cleaned_data:
            return

        # Handle predefined periods
        if self.cleaned_data["period"] == "30days":
            end = timezone.now()
            start = end - timedelta(days=30)
        elif self.cleaned_data["period"] == "month":
            end = timezone.now().replace(day=1) - timedelta(days=1)
            start = end.replace(day=1)
        elif self.cleaned_data["period"] == "this-month":
            end = timezone.now().replace(day=1) + timedelta(days=31)
            end = end.replace(day=1) - timedelta(days=1)
            start = end.replace(day=1)
        elif self.cleaned_data["period"] == "year":
            year = timezone.now().year - 1
            end = timezone.make_aware(datetime(year, 12, 31))  # noqa: DTZ001
            start = timezone.make_aware(datetime(year, 1, 1))  # noqa: DTZ001
        elif self.cleaned_data["period"] == "this-year":
            year = timezone.now().year
            end = timezone.make_aware(datetime(year, 12, 31))  # noqa: DTZ001
            start = timezone.make_aware(datetime(year, 1, 1))  # noqa: DTZ001
        else:
            # Validate custom period
            if not self.cleaned_data.get("start_date"):
                raise ValidationError({"start_date": gettext("Missing date!")})
            if not self.cleaned_data.get("end_date"):
                raise ValidationError({"end_date": gettext("Missing date!")})
            start = self.cleaned_data["start_date"]
            end = self.cleaned_data["end_date"]
        # Sanitize timestamps
        self.cleaned_data["start_date"] = start.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        self.cleaned_data["end_date"] = end.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
        # Final validation
        if self.cleaned_data["start_date"] > self.cleaned_data["end_date"]:
            msg = gettext("The starting date has to be before the ending date.")
            raise ValidationError({"start_date": msg, "end_date": msg})


class CleanRepoMixin:
    def clean_repo(self):
        repo = self.cleaned_data.get("repo")
        if not repo or not is_repo_link(repo) or "/" not in repo[10:]:
            return repo
        project, component = repo[10:].split("/", 1)
        try:
            obj = Component.objects.get(
                slug__iexact=component, project__slug__iexact=project
            )
        except Component.DoesNotExist:
            return repo
        if not self.request.user.has_perm("component.edit", obj):
            raise ValidationError(
                gettext("You do not have permission to access this component.")
            )
        return repo


class SettingsBaseForm(CleanRepoMixin, forms.ModelForm):
    """Component base form."""

    class Meta:
        model = Component
        fields = []

    def __init__(self, request, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.helper = FormHelper()
        self.helper.form_tag = False


class SelectChecksWidget(SortedSelectMultiple):
    def __init__(self, attrs=None, choices=()):
        choices = CHECKS.get_choices()
        super().__init__(attrs=attrs, choices=choices)

    def value_from_datadict(self, data, files, name):
        value = super().value_from_datadict(data, files, name)
        if isinstance(value, str):
            return json.loads(value)
        return value

    def format_value(self, value):
        value = super().format_value(value)
        if isinstance(value, str):
            return value
        return json.dumps(value)


class SelectChecksField(forms.JSONField):
    def to_python(self, value):
        if value in self.empty_values:
            return []
        return super().to_python(value)

    def bound_data(self, data, initial):
        if data is None:
            return []
        if isinstance(data, list):
            data = json.dumps(data)
        return super().bound_data(data, initial)


class ComponentDocsMixin:
    @staticmethod
    def get_field_doc(field):
        return ("admin/projects", f"component-{field.name}")


class ProjectDocsMixin:
    @staticmethod
    def get_field_doc(field):
        return ("admin/projects", f"project-{field.name}")


class SpamCheckMixin:
    def spam_check(self, value):
        if is_spam(value, self.request):
            raise ValidationError(gettext("This field has been identified as spam!"))


class ComponentAntispamMixin(SpamCheckMixin):
    def clean_agreement(self):
        value = self.cleaned_data["agreement"]
        self.spam_check(value)
        return value


class ProjectAntispamMixin(SpamCheckMixin):
    def clean_web(self):
        value = self.cleaned_data["web"]
        self.spam_check(value)
        return value

    def clean_instructions(self):
        value = self.cleaned_data["instructions"]
        self.spam_check(value)
        return value


class ComponentSettingsForm(
    SettingsBaseForm, ComponentDocsMixin, ComponentAntispamMixin
):
    """Component settings form."""

    class Meta:
        model = Component
        fields = (
            "name",
            "report_source_bugs",
            "license",
            "agreement",
            "allow_translation_propagation",
            "enable_suggestions",
            "suggestion_voting",
            "suggestion_autoaccept",
            "priority",
            "check_flags",
            "enforced_checks",
            "commit_message",
            "add_message",
            "delete_message",
            "merge_message",
            "addon_message",
            "pull_message",
            "vcs",
            "repo",
            "branch",
            "push",
            "push_branch",
            "repoweb",
            "push_on_commit",
            "commit_pending_age",
            "merge_style",
            "file_format",
            "edit_template",
            "new_lang",
            "language_code_style",
            "source_language",
            "new_base",
            "filemask",
            "screenshot_filemask",
            "template",
            "intermediate",
            "language_regex",
            "variant_regex",
            "restricted",
            "auto_lock_error",
            "links",
            "manage_units",
            "is_glossary",
            "glossary_color",
        )
        widgets = {
            "enforced_checks": SelectChecksWidget,
            "source_language": SortedSelect,
            "language_code_style": SortedSelect,
        }
        field_classes = {"enforced_checks": SelectChecksField}

    def __init__(self, request, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        if self.hide_restricted:
            self.fields["restricted"].widget = forms.HiddenInput()
        self.fields["links"].queryset = request.user.managed_projects.exclude(
            pk=self.instance.project.pk
        )
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    gettext("Basic"),
                    Fieldset(gettext("Name"), "name"),
                    Fieldset(gettext("License"), "license", "agreement"),
                    Fieldset(gettext("Upstream links"), "report_source_bugs"),
                    Fieldset(
                        gettext("Listing and access"),
                        "priority",
                        "restricted",
                        "links",
                    ),
                    Fieldset(
                        gettext("Glossary"),
                        "is_glossary",
                        "glossary_color",
                    ),
                    css_id="basic",
                ),
                Tab(
                    gettext("Translation"),
                    Fieldset(
                        gettext("Suggestions"),
                        "enable_suggestions",
                        "suggestion_voting",
                        "suggestion_autoaccept",
                    ),
                    Fieldset(
                        gettext("Translation settings"),
                        "allow_translation_propagation",
                        "manage_units",
                        "check_flags",
                        "variant_regex",
                        "enforced_checks",
                    ),
                    css_id="translation",
                ),
                Tab(
                    gettext("Version control"),
                    Fieldset(
                        gettext("Locations"),
                        Div(template="trans/repo_help.html"),
                        "vcs",
                        "repo",
                        "branch",
                        "push",
                        "push_branch",
                        "repoweb",
                    ),
                    Fieldset(
                        gettext("Version control settings"),
                        "push_on_commit",
                        "commit_pending_age",
                        "merge_style",
                        "auto_lock_error",
                    ),
                    css_id="vcs",
                ),
                Tab(
                    gettext("Commit messages"),
                    Fieldset(
                        gettext("Commit messages"),
                        ContextDiv(
                            template="trans/messages_help.html",
                            context={"user": request.user},
                        ),
                        "commit_message",
                        "add_message",
                        "delete_message",
                        "merge_message",
                        "addon_message",
                        "pull_message",
                    ),
                    css_id="messages",
                ),
                Tab(
                    gettext("Files"),
                    Fieldset(
                        gettext("Translation files"),
                        "file_format",
                        "filemask",
                        "language_regex",
                        "source_language",
                    ),
                    Fieldset(
                        gettext("Monolingual translations"),
                        "template",
                        "edit_template",
                        "intermediate",
                    ),
                    Fieldset(
                        gettext("Adding new languages"),
                        "new_base",
                        "new_lang",
                        "language_code_style",
                    ),
                    Fieldset(
                        gettext("Screenshots"),
                        "screenshot_filemask",
                    ),
                    css_id="files",
                ),
                template="layout/pills.html",
            )
        )
        vcses = (
            "git",
            "gerrit",
            "gitea",
            "github",
            "gitlab",
            "pagure",
            "local",
            "git-force-push",
        )
        if self.instance.vcs not in vcses:
            vcses = (self.instance.vcs,)
        self.fields["vcs"].choices = [
            c for c in self.fields["vcs"].choices if c[0] in vcses
        ]

    @property
    def hide_restricted(self):
        user = self.request.user
        if user.is_superuser:
            return False
        if settings.OFFER_HOSTING:
            return True
        return not any(
            "component.edit" in permissions
            for permissions, _langs in user.component_permissions[self.instance.pk]
        )

    def clean(self):
        data = self.cleaned_data
        if self.hide_restricted:
            data["restricted"] = self.instance.restricted


class ComponentCreateForm(SettingsBaseForm, ComponentDocsMixin, ComponentAntispamMixin):
    """Component creation form."""

    class Meta:
        model = Component
        fields = [
            "project",
            "name",
            "slug",
            "vcs",
            "repo",
            "branch",
            "push",
            "push_branch",
            "repoweb",
            "file_format",
            "filemask",
            "screenshot_filemask",
            "template",
            "edit_template",
            "intermediate",
            "new_lang",
            "new_base",
            "license",
            "language_code_style",
            "language_regex",
            "source_language",
            "is_glossary",
        ]
        widgets = {
            "source_language": SortedSelect,
            "language_code_style": SortedSelect,
        }


class ComponentNameForm(forms.Form, ComponentDocsMixin, ComponentAntispamMixin):
    name = forms.CharField(
        label=Component.name.field.verbose_name,
        max_length=COMPONENT_NAME_LENGTH,
        help_text=Component.name.field.help_text,
    )
    slug = forms.SlugField(
        label=Component.slug.field.verbose_name,
        max_length=COMPONENT_NAME_LENGTH,
        help_text=Component.slug.field.help_text,
    )
    is_glossary = forms.BooleanField(
        label=Component.is_glossary.field.verbose_name,
        help_text=Component.is_glossary.field.help_text,
        required=False,
    )

    def __init__(self, request, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.request = request


class ComponentSelectForm(ComponentNameForm):
    component = forms.ModelChoiceField(
        queryset=Component.objects.none(),
        label=gettext_lazy("Component"),
        help_text=gettext_lazy("Select an existing component configuration to copy."),
    )

    def __init__(self, request, *args, **kwargs):
        if "instance" in kwargs:
            kwargs.pop("instance")
        if "auto_id" not in kwargs:
            kwargs["auto_id"] = "id_existing_%s"
        super().__init__(request, *args, **kwargs)


class ComponentBranchForm(ComponentSelectForm):
    branch = forms.ChoiceField(label=gettext_lazy("Repository branch"))

    branch_data: dict[int, list[str]] = {}
    instance = None

    def __init__(self, *args, **kwargs):
        kwargs["auto_id"] = "id_branch_%s"
        super().__init__(*args, **kwargs)

    def clean_component(self):
        component = self.cleaned_data["component"]
        self.fields["branch"].choices = [(x, x) for x in self.branch_data[component.pk]]
        return component

    def clean(self):
        form_fields = ("branch", "slug", "name")
        data = self.cleaned_data
        component = data.get("component")
        if not component or any(field not in data for field in form_fields):
            return
        kwargs = model_to_dict(component, exclude=["id", "links"])
        # We need a object, not integer here
        kwargs["source_language"] = component.source_language
        kwargs["project"] = component.project
        for field in form_fields:
            kwargs[field] = data[field]
        self.instance = Component(**kwargs)
        try:
            self.instance.full_clean()
        except ValidationError as error:
            # Can not raise directly, as this will contain errors
            # from fields not present here
            result = {NON_FIELD_ERRORS: []}
            for key, value in error.message_dict.items():
                if key in self.fields:
                    result[key] = value
                else:
                    result[NON_FIELD_ERRORS].extend(value)
            raise ValidationError(error.messages)


class ComponentProjectForm(ComponentNameForm):
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(), label=gettext_lazy("Project")
    )
    source_language = forms.ModelChoiceField(
        widget=SortedSelect,
        label=Component.source_language.field.verbose_name,
        help_text=Component.source_language.field.help_text,
        queryset=Language.objects.all(),
    )

    def __init__(self, request, *args, **kwargs):
        if "instance" in kwargs:
            kwargs.pop("instance")
        super().__init__(request, *args, **kwargs)
        # It might be overridden based on preset project
        self.fields["source_language"].initial = Language.objects.default_language
        self.request = request
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.instance = None

    def clean(self):
        if "project" not in self.cleaned_data:
            return
        project = self.cleaned_data["project"]
        name = self.cleaned_data.get("name")
        if name and project.component_set.filter(name__iexact=name).exists():
            raise ValidationError(
                {"name": gettext("A component with the same name already exists.")}
            )
        slug = self.cleaned_data.get("slug")
        if slug and project.component_set.filter(slug__iexact=slug).exists():
            raise ValidationError(
                {"slug": gettext("A component with the same name already exists.")}
            )


class ComponentScratchCreateForm(ComponentProjectForm):
    file_format = forms.ChoiceField(
        label=gettext_lazy("File format"),
        initial="po-mono",
        choices=FILE_FORMATS.get_choices(
            cond=lambda x: bool(x.new_translation) or hasattr(x, "update_bilingual")
        ),
    )

    def __init__(self, *args, **kwargs):
        kwargs["auto_id"] = "id_scratchcreate_%s"
        super().__init__(*args, **kwargs)


class ComponentZipCreateForm(ComponentProjectForm):
    zipfile = forms.FileField(
        label=gettext_lazy("ZIP file containing translations"),
        validators=[FileExtensionValidator(allowed_extensions=["zip"])],
        widget=forms.FileInput(attrs={"accept": ".zip,application/zip"}),
    )

    field_order = ["zipfile", "project", "name", "slug"]

    def __init__(self, *args, **kwargs):
        kwargs["auto_id"] = "id_zipcreate_%s"
        super().__init__(*args, **kwargs)


class ComponentDocCreateForm(ComponentProjectForm):
    docfile = forms.FileField(
        label=gettext_lazy("Document to translate"),
        validators=[validate_file_extension],
    )

    field_order = ["docfile", "project", "name", "slug"]

    def __init__(self, *args, **kwargs):
        kwargs["auto_id"] = "id_doccreate_%s"
        super().__init__(*args, **kwargs)


class ComponentInitCreateForm(CleanRepoMixin, ComponentProjectForm):
    """
    Component creation form.

    This is mostly copied from the Component model. Probably should be extracted to a
    standalone Repository model…
    """

    project = forms.ModelChoiceField(
        queryset=Project.objects.none(), label=gettext_lazy("Project")
    )
    vcs = forms.ChoiceField(
        label=Component.vcs.field.verbose_name,
        help_text=Component.vcs.field.help_text,
        choices=VCS_REGISTRY.get_choices(exclude={"local"}),
        initial=settings.DEFAULT_VCS,
    )
    repo = forms.CharField(
        label=Component.repo.field.verbose_name,
        max_length=REPO_LENGTH,
        help_text=Component.repo.field.help_text,
    )
    branch = forms.CharField(
        label=Component.branch.field.verbose_name,
        max_length=BRANCH_LENGTH,
        help_text=Component.branch.field.help_text,
        required=False,
    )

    def clean_instance(self, data):
        params = copy.copy(data)
        if "discovery" in params:
            params.pop("discovery")

        instance = Component(**params)
        instance.clean_fields(
            exclude=(
                "filemask",
                "screenshot_filemask",
                "template",
                "file_format",
                "license",
            )
        )
        instance.validate_unique()
        instance.clean_repo()
        self.instance = instance

        # Create linked repos automatically
        repo = instance.suggest_repo_link()
        if repo:
            data["repo"] = repo
            data["branch"] = ""
            self.clean_instance(data)

    def clean(self):
        self.clean_instance(self.cleaned_data)


class ComponentDiscoverForm(ComponentInitCreateForm):
    discovery = forms.ChoiceField(
        label=gettext_lazy("Choose translation files to import"),
        choices=[("manual", gettext_lazy("Specify configuration manually"))],
        required=True,
        widget=forms.RadioSelect,
    )
    filemask = forms.CharField(
        label=Component.filemask.field.verbose_name,
        max_length=FILENAME_LENGTH,
        required=False,
        widget=forms.HiddenInput,
    )
    template = forms.CharField(
        label=Component.template.field.verbose_name,
        max_length=FILENAME_LENGTH,
        required=False,
        widget=forms.HiddenInput,
    )

    def render_choice(self, value):
        context = copy.copy(value)
        try:
            format_cls = FILE_FORMATS[value["file_format"]]
            context["file_format_name"] = format_cls.name
            context["valid"] = True
        except KeyError:
            context["file_format_name"] = value["file_format"]
            context["valid"] = False
        context["origin"] = value.meta["origin"]
        return render_to_string("trans/discover-choice.html", context)

    def __init__(self, request, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        # Hide all fields with exception of discovery
        for field, value in self.fields.items():
            if field == "discovery":
                continue
            value.widget = forms.HiddenInput()
        # Allow all VCS now (to handle zip file upload case)
        self.fields["vcs"].choices = VCS_REGISTRY.get_choices()
        self.discovered = self.perform_discovery(request, kwargs)
        self.fields["discovery"].choices.extend(
            (i, self.render_choice(value)) for i, value in enumerate(self.discovered)
        )

    def perform_discovery(self, request, kwargs):
        if "data" in kwargs and "create_discovery" in request.session:
            discovered = []
            for i, data in enumerate(request.session["create_discovery"]):
                item = DiscoveryResult(data)
                item.meta = request.session["create_discovery_meta"][i]
                discovered.append(item)
            return discovered
        try:
            self.clean_instance(kwargs["initial"])
            discovered = self.discover()
            if not discovered:
                discovered = self.discover(eager=True)
        except ValidationError:
            discovered = []
        request.session["create_discovery"] = discovered
        request.session["create_discovery_meta"] = [x.meta for x in discovered]
        return discovered

    def discover(self, eager: bool = False):
        return discover(
            self.instance.full_path,
            source_language=self.instance.source_language.code,
            eager=eager,
            hint=self.instance.filemask,
        )

    def clean(self):
        super().clean()
        discovery = self.cleaned_data.get("discovery")
        if discovery and discovery != "manual":
            self.cleaned_data.update(self.discovered[int(discovery)])


class ComponentRenameForm(SettingsBaseForm, ComponentDocsMixin):
    """Component rename form."""

    class Meta:
        model = Component
        fields = ["slug"]


class ComponentMoveForm(SettingsBaseForm, ComponentDocsMixin):
    """Component renaming form."""

    class Meta:
        model = Component
        fields = ["project"]

    def __init__(self, request, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields["project"].queryset = request.user.managed_projects


class ProjectSettingsForm(SettingsBaseForm, ProjectDocsMixin, ProjectAntispamMixin):
    """Project settings form."""

    class Meta:
        model = Project
        fields = (
            "name",
            "web",
            "instructions",
            "set_language_team",
            "use_shared_tm",
            "contribute_shared_tm",
            "enable_hooks",
            "language_aliases",
            "access_control",
            "translation_review",
            "source_review",
        )
        widgets = {
            "access_control": forms.RadioSelect,
            "instructions": MarkdownTextarea,
            "language_aliases": forms.TextInput,
        }

    def clean(self):
        data = self.cleaned_data
        if settings.OFFER_HOSTING:
            data["contribute_shared_tm"] = data["use_shared_tm"]

        # ACCESS_PUBLIC = 0, so the condition can not be simplified to not data["access_control"]
        if (
            "access_control" not in data
            or data["access_control"] is None
            or data["access_control"] == ""  # noqa: PLC1901
        ):
            data["access_control"] = self.instance.access_control
        access = data["access_control"]

        self.changed_access = access != self.instance.access_control

        if self.changed_access and not self.user_can_change_access:
            raise ValidationError(
                {
                    "access_control": gettext(
                        "You do not have permission to change project access control."
                    )
                }
            )
        if self.changed_access and access in (
            Project.ACCESS_PUBLIC,
            Project.ACCESS_PROTECTED,
        ):
            unlicensed = self.instance.component_set.filter(license="")
            if unlicensed:
                raise ValidationError(
                    {
                        "access_control": gettext(
                            "You must specify a license for these components "
                            "to make them publicly accessible: %s"
                        )
                        % ", ".join(unlicensed.values_list("name", flat=True))
                    }
                )

    def save(self, commit: bool = True):
        super().save(commit=commit)
        if self.changed_access:
            Change.objects.create(
                project=self.instance,
                action=Change.ACTION_ACCESS_EDIT,
                user=self.user,
                details={"access_control": self.instance.access_control},
            )

    def __init__(self, request, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.user = request.user
        self.user_can_change_access = request.user.has_perm(
            "billing:project.permissions", self.instance
        )
        self.changed_access = False
        self.helper.form_tag = False
        if not self.user_can_change_access:
            disabled = {"disabled": True}
            self.fields["access_control"].required = False
            self.fields["access_control"].help_text = gettext(
                "You do not have permission to change project access control."
            )
        else:
            disabled = {}
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    gettext("Basic"),
                    "name",
                    "web",
                    "instructions",
                    css_id="basic",
                ),
                Tab(
                    gettext("Access"),
                    InlineRadios(
                        "access_control",
                        template="%s/layout/radioselect_access.html",
                        **disabled,
                    ),
                    css_id="access",
                ),
                Tab(
                    gettext("Workflow"),
                    "set_language_team",
                    "use_shared_tm",
                    "contribute_shared_tm",
                    "enable_hooks",
                    "language_aliases",
                    "translation_review",
                    "source_review",
                    css_id="workflow",
                ),
                Tab(
                    gettext("Components"),
                    ContextDiv(
                        template="snippets/project-component-settings.html",
                        context={"object": self.instance, "user": request.user},
                    ),
                    css_id="components",
                ),
                template="layout/pills.html",
            )
        )

        if settings.OFFER_HOSTING:
            self.fields["contribute_shared_tm"].widget = forms.HiddenInput()
            self.fields["use_shared_tm"].help_text = gettext(
                "Uses and contributes to the pool of shared translations "
                "between projects."
            )
            self.fields["access_control"].choices = [
                choice
                for choice in self.fields["access_control"].choices
                if choice[0] != Project.ACCESS_CUSTOM
            ]


class ProjectRenameForm(SettingsBaseForm, ProjectDocsMixin):
    """Project renaming form."""

    class Meta:
        model = Project
        fields = ["slug"]


class BillingMixin(forms.Form):
    # This is fake field with is either hidden or configured
    # in the view
    billing = forms.ModelChoiceField(
        label=gettext_lazy("Billing"),
        queryset=User.objects.none(),
        required=True,
        empty_label=None,
    )


class ProjectCreateForm(
    BillingMixin, SettingsBaseForm, ProjectDocsMixin, ProjectAntispamMixin
):
    """Project creation form."""

    class Meta:
        model = Project
        fields = ("name", "slug", "web", "instructions")


class ProjectImportCreateForm(ProjectCreateForm):
    class Meta:
        model = Project
        fields = ("name", "slug")

    def __init__(self, request, projectbackup, *args, **kwargs):
        kwargs["initial"] = {
            "name": projectbackup.data["project"]["name"],
            "slug": projectbackup.data["project"]["slug"],
        }
        super().__init__(request, *args, **kwargs)
        self.projectbackup = projectbackup
        self.helper.layout = Layout(
            ContextDiv(
                template="trans/project_import_info.html",
                context={"projectbackup": projectbackup},
            ),
            Field("name"),
            Field("slug"),
            Field("billing"),
        )


class ProjectImportForm(BillingMixin, forms.Form):
    """Component base form."""

    zipfile = forms.FileField(
        label=gettext_lazy("ZIP file containing project backup"),
        validators=[FileExtensionValidator(allowed_extensions=["zip"])],
        widget=forms.FileInput(attrs={"accept": ".zip,application/zip"}),
    )

    def __init__(self, request, projectbackup=None, *args, **kwargs):
        kwargs.pop("instance", None)
        super().__init__(*args, **kwargs)
        self.request = request
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("zipfile"),
            Field("billing"),
        )

    def clean_zipfile(self):
        zipfile = self.cleaned_data["zipfile"]
        backup = ProjectBackup(zipfile)
        try:
            backup.validate()
        except Exception as error:
            raise ValidationError(gettext("Could not load project backup: %s") % error)
        self.cleaned_data["projectbackup"] = backup
        return zipfile


class ReplaceForm(forms.Form):
    q = QueryField(
        required=False,
        help_text=gettext_lazy("Optional additional filter applied to the strings"),
    )
    search = forms.CharField(
        label=gettext_lazy("Search string"),
        min_length=1,
        required=True,
        strip=False,
        help_text=gettext_lazy("Case-sensitive string to search for and replace."),
    )
    replacement = forms.CharField(
        label=gettext_lazy("Replacement string"),
        min_length=1,
        required=True,
        strip=False,
    )

    def __init__(self, *args, **kwargs):
        kwargs["auto_id"] = "id_replace_%s"
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            SearchField("q"),
            Field("search"),
            Field("replacement"),
            Div(template="snippets/replace-help.html"),
        )


class ReplaceConfirmForm(forms.Form):
    units = forms.ModelMultipleChoiceField(queryset=Unit.objects.none(), required=False)
    confirm = forms.BooleanField(required=True, initial=True, widget=forms.HiddenInput)

    def __init__(self, units, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["units"].queryset = units


class MatrixLanguageForm(forms.Form):
    """Form for requesting a new language."""

    lang = forms.MultipleChoiceField(
        label=gettext_lazy("Languages"), choices=[], widget=forms.SelectMultiple
    )

    def __init__(self, component, *args, **kwargs):
        super().__init__(*args, **kwargs)
        languages = Language.objects.filter(translation__component=component).exclude(
            pk=component.source_language_id
        )
        self.fields["lang"].choices = languages.as_choices()


class NewUnitBaseForm(forms.Form):
    variant = forms.ModelChoiceField(
        Unit.objects.none(),
        widget=forms.HiddenInput,
        required=False,
    )

    def __init__(self, translation, user, tabindex: int | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tabindex = tabindex or 200
        self.translation = translation
        self.fields["variant"].queryset = translation.unit_set.all()
        self.user = user

    def clean(self):
        try:
            data = self.as_kwargs()
        except KeyError:
            # Probably the validation of some fields has failed
            return
        self.translation.validate_new_unit_data(**data)

    def get_glossary_flags(self):
        return ""

    def as_kwargs(self):
        flags = Flags()
        flags.merge(self.get_glossary_flags())
        variant = self.cleaned_data.get("variant")
        if variant:
            flags.set_value("variant", variant.source)
        return {
            "context": self.cleaned_data.get("context", ""),
            "source": self.cleaned_data["source"],
            "target": self.cleaned_data.get("target"),
            "extra_flags": flags.format(),
            "explanation": self.cleaned_data.get("explanation", ""),
            "auto_context": self.cleaned_data.get("auto_context", False),
        }


class NewMonolingualUnitForm(NewUnitBaseForm):
    context = forms.CharField(
        label=gettext_lazy("Translation key"),
        help_text=gettext_lazy(
            "Key used to identify the string in the translation file. "
            "File-format specific rules might apply."
        ),
        required=True,
    )
    source = PluralField(
        label=gettext_lazy("Source language text"),
        help_text=gettext_lazy(
            "You can edit this later, as with any other string in "
            "the source language."
        ),
        required=True,
    )

    def __init__(self, translation, user, tabindex: int | None = None, *args, **kwargs):
        super().__init__(translation, user, tabindex, *args, **kwargs)
        self.fields["context"].widget.attrs["tabindex"] = self.tabindex
        self.fields["source"].widget.attrs["tabindex"] = self.tabindex + 1
        self.fields["source"].widget.profile = user.profile
        self.fields["source"].initial = Unit(translation=translation, id_hash=0)


class NewBilingualSourceUnitForm(NewUnitBaseForm):
    context = forms.CharField(
        label=gettext_lazy("Context"),
        help_text=gettext_lazy("Optional context to clarify the source strings."),
        required=False,
    )
    auto_context = forms.BooleanField(
        required=False,
        initial=True,
        label=gettext_lazy(
            "Auto-adjust context when an identical string already exists."
        ),
    )
    source = PluralField(
        label=gettext_lazy("Source string"),
        required=True,
    )

    def __init__(self, translation, user, tabindex: int | None = None, *args, **kwargs):
        super().__init__(translation, user, tabindex, *args, **kwargs)
        self.fields["context"].widget.attrs["tabindex"] = self.tabindex
        self.fields["context"].label = translation.component.context_label
        self.fields["source"].widget.attrs["tabindex"] = self.tabindex + 1
        self.fields["source"].widget.profile = user.profile
        self.fields["source"].initial = Unit(
            translation=translation.component.source_translation, id_hash=0
        )


class NewBilingualUnitForm(NewBilingualSourceUnitForm):
    target = PluralField(
        label=gettext_lazy("Translated string"),
        help_text=gettext_lazy(
            "You can edit this later, as with any other string in the translation."
        ),
        required=True,
    )

    def __init__(self, translation, user, tabindex: int | None = None, *args, **kwargs):
        super().__init__(translation, user, tabindex, *args, **kwargs)
        self.fields["target"].widget.attrs["tabindex"] = self.tabindex + 2
        self.fields["target"].widget.profile = user.profile
        self.fields["target"].initial = Unit(translation=translation, id_hash=0)


class NewBilingualGlossarySourceUnitForm(GlossaryAddMixin, NewBilingualSourceUnitForm):
    def __init__(self, translation, user, tabindex: int | None = None, *args, **kwargs):
        if kwargs["initial"] is None:
            kwargs["initial"] = {}
        kwargs["initial"]["terminology"] = True
        super().__init__(translation, user, tabindex, *args, **kwargs)


class NewBilingualGlossaryUnitForm(GlossaryAddMixin, NewBilingualUnitForm):
    pass


def get_new_unit_form(translation, user, data=None, initial=None):
    if translation.component.has_template():
        return NewMonolingualUnitForm(translation, user, data=data, initial=initial)
    if translation.component.is_glossary:
        if translation.is_source:
            return NewBilingualGlossarySourceUnitForm(
                translation, user, data=data, initial=initial
            )
        return NewBilingualGlossaryUnitForm(
            translation, user, data=data, initial=initial
        )
    if translation.is_source:
        return NewBilingualSourceUnitForm(translation, user, data=data, initial=initial)
    return NewBilingualUnitForm(translation, user, data=data, initial=initial)


class CachedQueryIterator(ModelChoiceIterator):
    """
    Choice iterator for cached querysets.

    It assumes the queryset is reused and avoids using an iterator or counting queries.
    """

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)
        for obj in self.queryset:
            yield self.choice(obj)

    def __len__(self):
        return len(self.queryset) + (1 if self.field.empty_label is not None else 0)

    def __bool__(self):
        return self.field.empty_label is not None or bool(self.queryset)


class CachedModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    iterator = CachedQueryIterator

    def _get_queryset(self):
        return self._queryset

    def _set_queryset(self, queryset):
        self._queryset = queryset
        self.widget.choices = self.choices

    queryset = property(_get_queryset, _set_queryset)


class BulkEditForm(forms.Form):
    q = QueryField(required=True)
    state = forms.ChoiceField(
        label=gettext_lazy("State to set"),
        choices=[(-1, gettext_lazy("Do not change"))],
    )
    add_flags = FlagField(
        label=gettext_lazy("Translation flags to add"), required=False
    )
    remove_flags = FlagField(
        label=gettext_lazy("Translation flags to remove"), required=False
    )
    add_labels = CachedModelMultipleChoiceField(
        queryset=Label.objects.none(),
        label=gettext_lazy("Labels to add"),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
    )
    remove_labels = CachedModelMultipleChoiceField(
        queryset=Label.objects.none(),
        label=gettext_lazy("Labels to remove"),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
    )

    def __init__(self, user, obj, *args, **kwargs):
        project = kwargs.pop("project")
        kwargs["auto_id"] = "id_bulk_%s"
        super().__init__(*args, **kwargs)
        labels = project.label_set.all()
        if labels:
            self.fields["remove_labels"].queryset = labels
            self.fields["add_labels"].queryset = labels

        excluded = {STATE_EMPTY, STATE_READONLY}
        show_review = True
        if user is not None and not user.has_perm("unit.review", obj):
            show_review = False
            excluded.add(STATE_APPROVED)

        # Filter offered states
        choices = self.fields["state"].choices
        for value, label in STATE_CHOICES:
            if value in excluded:
                continue
            if value == STATE_TRANSLATED and show_review:
                label = gettext("Waiting for review")

            choices.append((value, label))
        self.fields["state"].choices = choices

        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(template="snippets/bulk-help.html"),
            SearchField("q"),
            Field("state"),
            Field("add_flags"),
            Field("remove_flags"),
        )
        if labels:
            self.helper.layout.append(InlineCheckboxes("add_labels"))
            self.helper.layout.append(InlineCheckboxes("remove_labels"))


class ContributorAgreementForm(forms.Form):
    confirm = forms.BooleanField(
        label=gettext_lazy("I accept the contributor agreement"), required=True
    )
    next = forms.CharField(required=False, widget=forms.HiddenInput)


class BaseDeleteForm(forms.Form):
    confirm = forms.CharField(required=True)
    warning_template = ""

    def __init__(self, obj, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.obj = obj
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            ContextDiv(
                template=self.warning_template,
                css_class="form-group",
                context=self.get_template_context(obj),
            ),
            Field("confirm"),
        )
        self.helper.form_tag = False

    def get_template_context(self, obj):
        return {"object": obj}

    def clean(self):
        if self.cleaned_data.get("confirm") != self.obj.full_slug:
            raise ValidationError(
                gettext("The slug does not match the one marked for deletion!")
            )


class TranslationDeleteForm(BaseDeleteForm):
    confirm = forms.CharField(
        label=gettext_lazy("Removal confirmation"),
        help_text=gettext_lazy(
            "Please type in the full slug of the translation to confirm."
        ),
        required=True,
    )
    warning_template = "trans/delete-translation.html"

    def get_template_context(self, obj):
        context = super().get_template_context(obj)
        context["languages_addon"] = any(
            addon.name == "weblate.consistency.languages"
            for addon in obj.component.addons_cache["__all__"]
        )
        return context


class ComponentDeleteForm(BaseDeleteForm):
    confirm = forms.CharField(
        label=gettext_lazy("Removal confirmation"),
        help_text=gettext_lazy(
            "Please type in the full slug of the component to confirm."
        ),
        required=True,
    )
    warning_template = "trans/delete-component.html"


class ProjectDeleteForm(BaseDeleteForm):
    confirm = forms.CharField(
        label=gettext_lazy("Removal confirmation"),
        help_text=gettext_lazy("Please type in the slug of the project to confirm."),
        required=True,
    )
    warning_template = "trans/delete-project.html"


class ProjectLanguageDeleteForm(BaseDeleteForm):
    confirm = forms.CharField(
        label=gettext_lazy("Removal confirmation"),
        help_text=gettext_lazy(
            "Please type in the slug of the project and language to confirm."
        ),
        required=True,
    )
    warning_template = "trans/delete-project-language.html"


class AnnouncementForm(forms.ModelForm):
    """Announcement posting form."""

    class Meta:
        model = Announcement
        fields = ["message", "category", "expiry", "notify"]
        widgets = {
            "expiry": WeblateDateInput(),
            "message": MarkdownTextarea,
        }


class ChangesFilterForm(FilterForm):
    string = forms.ModelChoiceField(
        Unit.objects.none(),
        widget=forms.HiddenInput,
        required=False,
    )

    def __init__(self, request, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["string"].queryset = Unit.objects.filter(
            translation__component__project__in=request.user.allowed_projects
        )


class ChangesForm(forms.Form):
    project = forms.ChoiceField(
        label=gettext_lazy("Project"), choices=[("", "")], required=False
    )
    lang = forms.ChoiceField(
        label=gettext_lazy("Language"), choices=[("", "")], required=False
    )
    action = forms.MultipleChoiceField(
        label=gettext_lazy("Action"),
        required=False,
        widget=SortedSelectMultiple,
        choices=Change.ACTION_CHOICES,
    )
    user = UsernameField(
        label=gettext_lazy("Author username"), required=False, help_text=None
    )
    start_date = WeblateDateField(label=gettext_lazy("Starting date"), required=False)
    end_date = WeblateDateField(label=gettext_lazy("Ending date"), required=False)

    def __init__(self, request, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lang"].choices += Language.objects.have_translation().as_choices()
        self.fields["project"].choices += [
            (project.slug, project.name) for project in request.user.allowed_projects
        ]


class LabelForm(forms.ModelForm):
    class Meta:
        model = Label
        fields = ("name", "color")
        widgets = {"color": ColorWidget()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False


class ProjectTokenCreateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["full_name", "date_expires"]
        widgets = {
            "date_expires": WeblateDateInput(),
        }

    def __init__(self, project, *args, **kwargs):
        self.project = project
        super().__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        self.instance.is_bot = True
        base_name = name = f"bot-{self.project.slug}-{slugify(self.instance.full_name)}"
        while User.objects.filter(
            Q(username=name) | Q(email=f"{name}@bots.noreply.weblate.org")
        ).exists():
            name = f"{base_name}-{token_hex(2)}"
        self.instance.username = name
        self.instance.email = f"{name}@bots.noreply.weblate.org"
        result = super().save(*args, **kwargs)
        self.project.add_user(self.instance, "Administration")
        return result

    def clean_expires(self):
        expires = self.cleaned_data["expires"]
        expires = expires.replace(hour=23, minute=59, second=59, microsecond=999999)
        if expires < timezone.now():
            raise forms.ValidationError(gettext("Expiry cannot be in the past."))
        return expires


class ProjectGroupDeleteForm(forms.Form):
    group = forms.ModelChoiceField(
        Group.objects.none(),
        widget=forms.HiddenInput,
        required=True,
    )

    def __init__(self, project, *args, **kwargs):
        self.project = project
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = project.defined_groups.all()


class ProjectUserGroupForm(UserManageForm):
    groups = forms.ModelMultipleChoiceField(
        Group.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label=gettext_lazy("Teams"),
        required=False,
    )

    def __init__(self, project, *args, **kwargs):
        self.project = project
        super().__init__(*args, **kwargs)
        self.fields["user"].widget = forms.HiddenInput()
        self.fields["groups"].queryset = project.defined_groups.all()


class ProjectFilterForm(forms.Form):
    owned = UserField(required=False)
    watched = UserField(required=False)
