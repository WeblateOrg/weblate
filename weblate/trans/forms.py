#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

import copy
import json
import re
from datetime import date, datetime, timedelta
from typing import Dict, List

from crispy_forms.bootstrap import InlineCheckboxes, InlineRadios, Tab, TabHolder
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, Fieldset, Layout
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
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from translation_finder import DiscoveryResult, discover

from weblate.auth.models import Group, User
from weblate.checks.flags import Flags
from weblate.checks.models import CHECKS
from weblate.checks.utils import highlight_string
from weblate.formats.models import EXPORTERS, FILE_FORMATS
from weblate.glossary.forms import GlossaryAddMixin
from weblate.lang.data import BASIC_LANGUAGES
from weblate.lang.models import Language
from weblate.machinery import MACHINE_TRANSLATION_SERVICES
from weblate.trans.defines import COMPONENT_NAME_LENGTH, REPO_LENGTH
from weblate.trans.filter import FILTERS, get_filter_choice
from weblate.trans.models import (
    Announcement,
    Change,
    Component,
    Label,
    Project,
    ProjectToken,
    Unit,
)
from weblate.trans.specialchars import RTL_CHARS_DATA, get_special_chars
from weblate.trans.util import check_upload_method_permissions, is_repo_link
from weblate.trans.validators import validate_check_flags
from weblate.utils.antispam import is_spam
from weblate.utils.errors import report_error
from weblate.utils.forms import (
    ColorWidget,
    ContextDiv,
    EmailField,
    SearchField,
    SortedSelect,
    SortedSelectMultiple,
    UsernameField,
)
from weblate.utils.hash import checksum_to_hash, hash_to_checksum
from weblate.utils.search import parse_query
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
    def __init__(self, datepicker=True, **kwargs):
        attrs = {"type": "date"}
        if datepicker:
            attrs["data-provide"] = "datepicker"
            attrs["data-date-format"] = "yyyy-mm-dd"
        super().__init__(attrs=attrs, format="%Y-%m-%d", **kwargs)


class WeblateDateField(forms.DateField):
    def __init__(self, datepicker=True, **kwargs):
        if "widget" not in kwargs:
            kwargs["widget"] = WeblateDateInput(datepicker=datepicker)
        super().__init__(**kwargs)

    def to_python(self, value):
        """Produce timezone aware datetime with 00:00:00 as time."""
        value = super().to_python(value)
        if isinstance(value, date):
            return from_current_timezone(
                datetime(value.year, value.month, value.day, 0, 0, 0)
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
            raise ValidationError(_("Invalid checksum specified!"))


class UserField(forms.CharField):
    def clean(self, value):
        if not value:
            return None
        try:
            return User.objects.get(Q(username=value) | Q(email=value))
        except User.DoesNotExist:
            raise ValidationError(_("Could not find any such user."))
        except User.MultipleObjectsReturned:
            raise ValidationError(_("More possible users were found."))


class QueryField(forms.CharField):
    def __init__(self, **kwargs):
        if "label" not in kwargs:
            kwargs["label"] = _("Query")
        if "required" not in kwargs:
            kwargs["required"] = False
        super().__init__(**kwargs)

    def clean(self, value):
        if not value:
            if self.required:
                raise ValidationError(_("Missing query string."))
            return ""
        try:
            parse_query(value)
            return value
        except Exception as error:
            report_error()
            raise ValidationError(_("Could not parse query string: {}").format(error))


class FlagField(forms.CharField):
    default_validators = [validate_check_flags]


class PluralTextarea(forms.Textarea):
    """Text-area extension which possibly handles plurals."""

    def __init__(self, *args, **kwargs):
        self.profile = None
        super().__init__(*args, **kwargs)

    def get_rtl_toolbar(self, fieldname):
        groups = []

        # Special chars
        chars = []
        for name, char, value in RTL_CHARS_DATA:
            chars.append(
                BUTTON_TEMPLATE.format(
                    "specialchar",
                    name,
                    'data-value="{}"'.format(
                        value.encode("ascii", "xmlcharrefreplace").decode("ascii")
                    ),
                    char,
                )
            )

        groups.append(GROUP_TEMPLATE.format("", "\n".join(chars)))
        return TOOLBAR_TEMPLATE.format("\n".join(groups))

    def get_rtl_toggle(self, language, fieldname):
        if language.direction != "rtl":
            return ""

        # RTL/LTR switch
        rtl_name = f"rtl-{fieldname}"
        rtl_switch = [
            RADIO_TEMPLATE.format(
                "direction-toggle active",
                gettext("Toggle text direction"),
                rtl_name,
                "rtl",
                'checked="checked"',
                "RTL",
            ),
            RADIO_TEMPLATE.format(
                "direction-toggle",
                gettext("Toggle text direction"),
                rtl_name,
                "ltr",
                "",
                "LTR",
            ),
        ]
        groups = [GROUP_TEMPLATE.format('data-toggle="buttons"', "\n".join(rtl_switch))]
        return mark_safe(TOOLBAR_TEMPLATE.format("\n".join(groups)))

    def get_toolbar(self, language, fieldname, unit, idx, source):
        """Return toolbar HTML code."""
        profile = self.profile
        groups = []

        # Special chars
        chars = [
            BUTTON_TEMPLATE.format(
                "specialchar",
                name,
                'data-value="{}"'.format(
                    value.encode("ascii", "xmlcharrefreplace").decode("ascii")
                ),
                char,
            )
            for name, char, value in get_special_chars(
                language, profile.special_chars, unit.source
            )
        ]

        groups.append(GROUP_TEMPLATE.format("", "\n".join(chars)))

        result = TOOLBAR_TEMPLATE.format("\n".join(groups))

        if language.direction == "rtl":
            result = self.get_rtl_toolbar(fieldname) + result

        return mark_safe(result)

    def render(self, name, value, attrs=None, renderer=None, **kwargs):
        """Render all textareas with correct plural labels."""
        unit = value
        values = unit.get_target_plurals()
        lang = unit.translation.language
        plural = unit.translation.plural
        tabindex = self.attrs["tabindex"]
        placeables = [hl[2] for hl in highlight_string(unit.source_string, unit)]

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
        plurals = unit.get_source_plurals()
        base_id = f"id_{unit.checksum}"
        for idx, val in enumerate(values):
            # Generate ID
            fieldname = f"{name}_{idx}"
            fieldid = f"{base_id}_{idx}"
            attrs["id"] = fieldid
            attrs["tabindex"] = tabindex + idx
            if idx and len(plurals) > 1:
                source = plurals[1]
            else:
                source = plurals[0]

            # Render textare
            textarea = super().render(fieldname, val, attrs, renderer, **kwargs)
            # Label for plural
            label = str(unit.translation.language)
            if len(values) != 1:
                label = f"{label}, {plural.get_plural_label(idx)}"
            ret.append(
                render_to_string(
                    "snippets/editor.html",
                    {
                        "toolbar": self.get_toolbar(lang, fieldid, unit, idx, source),
                        "fieldid": fieldid,
                        "label": mark_safe(label),
                        "textarea": textarea,
                        "max_length": attrs["data-max"],
                        "length": len(val),
                        "source_length": len(source),
                        "rtl_toggle": self.get_rtl_toggle(lang, fieldid),
                    },
                )
            )

        # Show plural formula for more strings
        if len(values) > 1:
            ret.append(
                render_to_string(
                    "snippets/plural-formula.html",
                    {"plural": plural, "user": self.profile.user},
                )
            )

        # Join output
        return mark_safe("".join(ret))

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
    """Renderer for the plural field.

    The only difference from CharField is that it does not force value to be string.
    """

    def __init__(self, max_length=None, min_length=None, **kwargs):
        kwargs["label"] = ""
        super().__init__(widget=PluralTextarea, **kwargs)

    def to_python(self, value):
        """Return list or string as returned by PluralTextarea."""
        return value

    def clean(self, value):
        value = super().clean(value)
        if not value or (self.required and not any(value)):
            raise ValidationError(_("Missing translated string!"))
        return value


class FilterField(forms.ChoiceField):
    def __init__(self, *args, **kwargs):
        kwargs["label"] = _("Search filter")
        if "required" not in kwargs:
            kwargs["required"] = False
        kwargs["choices"] = get_filter_choice()
        kwargs["error_messages"] = {
            "invalid_choice": _("Please choose a valid filter type.")
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
                _("The string you wanted to translate is no longer available.")
            )


class UnitForm(forms.Form):
    def __init__(self, unit: Unit, *args, **kwargs):
        self.unit = unit
        super().__init__(*args, **kwargs)


class FuzzyField(forms.BooleanField):
    help_as_icon = True

    def __init__(self, *args, **kwargs):
        kwargs["label"] = _("Needs editing")
        kwargs["help_text"] = _(
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
        label=_("Review state"),
        choices=[
            (STATE_FUZZY, _("Needs editing")),
            (STATE_TRANSLATED, _("Waiting for review")),
            (STATE_APPROVED, _("Approved")),
        ],
        required=False,
        widget=forms.RadioSelect,
    )
    explanation = forms.CharField(
        widget=MarkdownTextarea,
        label=_("Explanation"),
        help_text=_(
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
                (STATE_READONLY, _("Read only")),
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
        if not unit.translation.component.is_glossary:
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
                _(
                    "Source string has been changed meanwhile. "
                    "Please check your changes."
                )
            )

        if self.cleaned_data["translationsum"] != unit.get_target_hash():
            raise ValidationError(
                _(
                    "Translation of the string has been changed meanwhile. "
                    "Please check your changes."
                )
            )

        max_length = unit.get_max_length()
        for text in self.cleaned_data["target"]:
            if len(text) > max_length:
                raise ValidationError(_("Translation text too long!"))
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
            "save_zen", kwargs=unit.translation.get_reverse_url_kwargs()
        )
        self.helper.form_tag = True
        self.helper.disable_csrf = False
        self.helper.layout.append(Field("checksum"))


class DownloadForm(forms.Form):
    q = QueryField()
    format = forms.ChoiceField(
        label=_("File format"),
        choices=[(x.name, x.verbose) for x in EXPORTERS.values()],
        initial="po",
        required=True,
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            SearchField("q"),
            InlineRadios("format"),
        )


class SimpleUploadForm(forms.Form):
    """Base form for uploading a file."""

    file = forms.FileField(label=_("File"), validators=[validate_file_extension])
    method = forms.ChoiceField(
        label=_("File upload mode"),
        choices=(
            ("translate", _("Add as translation")),
            ("approve", _("Add as approved translation")),
            ("suggest", _("Add as suggestion")),
            ("fuzzy", _("Add as translation needing edit")),
            ("replace", _("Replace existing translation file")),
            ("source", _("Update source strings")),
            ("add", _("Add new strings")),
        ),
        widget=forms.RadioSelect,
        required=True,
    )
    fuzzy = forms.ChoiceField(
        label=_("Processing of strings needing edit"),
        choices=(
            ("", _("Do not import")),
            ("process", _("Import as string needing edit")),
            ("approve", _("Import as translated")),
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
        """Remove add as translation choice."""
        choices = self.fields["method"].choices
        self.fields["method"].choices = [
            choice for choice in choices if choice[0] != value
        ]


class UploadForm(SimpleUploadForm):
    """Upload form with the option to overwrite current messages."""

    conflicts = forms.ChoiceField(
        label=_("Conflict handling"),
        help_text=_(
            "Whether to overwrite existing translations if the string is "
            "already translated."
        ),
        choices=(
            ("", _("Update only untranslated strings")),
            ("replace-translated", _("Update translated strings")),
            ("replace-approved", _("Update translated and approved strings")),
        ),
        required=False,
        initial="replace-translated",
    )


class ExtraUploadForm(UploadForm):
    """Advanced upload form for users who can override authorship."""

    author_name = forms.CharField(label=_("Author name"))
    author_email = EmailField(label=_("Author e-mail"))


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
    if not user.has_perm("unit.review", translation) and not form == SimpleUploadForm:
        result.fields["conflicts"].choices = [
            choice
            for choice in result.fields["conflicts"].choices
            if choice[0] != "approved"
        ]
    return result


class SearchForm(forms.Form):
    """Text searching form."""

    # pylint: disable=invalid-name
    q = QueryField()
    sort_by = forms.CharField(required=False, widget=forms.HiddenInput)
    checksum = ChecksumField(required=False)
    offset = forms.IntegerField(min_value=-1, required=False, widget=forms.HiddenInput)
    offset_kwargs = {}

    def __init__(self, user, language=None, show_builder=True, **kwargs):
        """Generate choices for other component in same project."""
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
            # We don't care about empty values or ignored
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
                for val in value:
                    items.append((param, val))
            elif isinstance(value, User):
                items.append((param, value.username))
            else:
                # It should be string here
                if value:
                    items.append((param, value))
        return items

    def urlencode(self):
        return urlencode(self.items())

    def reset_offset(self):
        """Reset offset to avoid using form as default for new search."""
        data = copy.copy(self.data)
        data["offset"] = "1"
        data["checksum"] = ""
        self.data = data
        return self


class PositionSearchForm(SearchForm):
    offset = forms.IntegerField(min_value=-1, required=False)
    offset_kwargs = {"template": "snippets/position-field.html"}


class MergeForm(UnitForm):
    """Simple form for merging translation of two units."""

    merge = forms.IntegerField()

    def clean(self):
        super().clean()
        if "merge" not in self.cleaned_data:
            return None
        try:
            unit = self.unit
            translation = unit.translation
            project = translation.component.project
            self.cleaned_data["merge_unit"] = merge_unit = Unit.objects.get(
                pk=self.cleaned_data["merge"],
                translation__component__project=project,
                translation__language=translation.language,
            )
            # Compare in Python to ensure case sensitiveness on MySQL
            if not translation.is_source and unit.source != merge_unit.source:
                raise ValidationError(_("Could not find merged string."))
        except Unit.DoesNotExist:
            raise ValidationError(_("Could not find merged string."))
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
            raise ValidationError(_("Could not find reverted change."))
        return self.cleaned_data


class AutoForm(forms.Form):
    """Automatic translation form."""

    mode = forms.ChoiceField(
        label=_("Automatic translation mode"),
        choices=[
            ("suggest", _("Add as suggestion")),
            ("translate", _("Add as translation")),
            ("fuzzy", _("Add as needing edit")),
        ],
        initial="suggest",
    )
    filter_type = FilterField(
        required=True,
        initial="todo",
        help_text=_(
            "Please note that translating all strings will "
            "discard all existing translations."
        ),
    )
    auto_source = forms.ChoiceField(
        label=_("Automatic translation source"),
        choices=[
            ("others", _("Other translation components")),
            ("mt", _("Machine translation")),
        ],
        initial="others",
    )
    component = forms.ChoiceField(
        label=_("Components"),
        required=False,
        help_text=_(
            "Turn on contribution to shared translation memory for the project to "
            "get access to additional components."
        ),
        initial="",
    )
    engines = forms.MultipleChoiceField(
        label=_("Machine translation engines"), choices=[], required=False
    )
    threshold = forms.IntegerField(
        label=_("Score threshold"), initial=80, min_value=1, max_value=100
    )

    def __init__(self, obj, *args, **kwargs):
        """Generate choices for other component in same project."""
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

        # Fetching is faster than doing count on possibly thousands of components
        if len(self.components.values_list("id")[:30]) == 30:
            # Do not show choices when too many
            self.fields["component"] = forms.CharField(
                required=False,
                label=_("Components"),
                help_text=_(
                    "Enter component to use as source, "
                    "keep blank to use all components in current project."
                ),
            )
        else:
            choices = [
                (s.id, str(s))
                for s in self.components.order_project().prefetch_related("project")
            ]

            self.fields["component"].choices = [
                ("", _("All components in current project"))
            ] + choices

        self.fields["engines"].choices = [
            (key, mt.name) for key, mt in MACHINE_TRANSLATION_SERVICES.items()
        ]
        if "weblate" in MACHINE_TRANSLATION_SERVICES.keys():
            self.fields["engines"].initial = "weblate"

        use_types = {"all", "nottranslated", "todo", "fuzzy", "check:inconsistent"}

        self.fields["filter_type"].choices = [
            x for x in self.fields["filter_type"].choices if x[0] in use_types
        ]

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
                raise ValidationError(_("Component not found!"))
        else:
            slashes = component.count("/")
            if slashes == 0:
                try:
                    result = self.components.get(
                        slug=component, project=self.obj.project
                    )
                except Component.DoesNotExist:
                    raise ValidationError(_("Component not found!"))
            elif slashes == 1:
                project_slug, component_slug = component.split("/")
                try:
                    result = self.components.get(
                        slug=component_slug, project__slug=project_slug
                    )
                except Component.DoesNotExist:
                    raise ValidationError(_("Component not found!"))
            else:
                raise ValidationError(_("Please provide valid component slug!"))
        return result.pk


class CommentForm(forms.Form):
    """Simple commenting form."""

    scope = forms.ChoiceField(
        label=_("Scope"),
        help_text=_(
            "Is your comment specific to this "
            "translation or generic for all of them?"
        ),
        choices=(
            (
                "report",
                _("Report issue with the source string"),
            ),
            (
                "global",
                _("Source string comment, suggestions for changes to this string"),
            ),
            (
                "translation",
                _("Translation comment, discussions with other translators"),
            ),
        ),
    )
    comment = forms.CharField(
        widget=MarkdownTextarea,
        label=_("New comment"),
        help_text=_("You can use Markdown and mention users by @username."),
        max_length=1000,
    )

    def __init__(self, project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove bug report in case source review is not enabled
        if not project.source_review:
            self.fields["scope"].choices = self.fields["scope"].choices[1:]


class EngageForm(forms.Form):
    """Form to choose language for engagement widgets."""

    lang = forms.ChoiceField(required=False, choices=[("", _("All languages"))])
    component = forms.ChoiceField(required=False, choices=[("", _("All components"))])

    def __init__(self, user, project, *args, **kwargs):
        """Dynamically generate choices for used languages in project."""
        super().__init__(*args, **kwargs)

        self.fields["lang"].choices += project.languages.as_choices()
        self.fields["component"].choices += (
            project.component_set.filter_access(user)
            .order()
            .values_list("slug", "name")
        )


class NewLanguageOwnerForm(forms.Form):
    """Form for requesting new language."""

    lang = forms.MultipleChoiceField(
        label=_("Languages"), choices=[], widget=forms.SelectMultiple
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
    """Form for requesting new language."""

    lang = forms.ChoiceField(label=_("Language"), choices=[], widget=forms.Select)

    def get_lang_objects(self):
        codes = BASIC_LANGUAGES
        if settings.BASIC_LANGUAGES is not None:
            codes = settings.BASIC_LANGUAGES
        return super().get_lang_objects().filter(code__in=codes)

    def __init__(self, component, *args, **kwargs):
        super().__init__(component, *args, **kwargs)
        self.fields["lang"].choices = [("", _("Please choose"))] + self.fields[
            "lang"
        ].choices

    def clean_lang(self):
        # Compatibility with NewLanguageOwnerForm
        return [self.cleaned_data["lang"]]


def get_new_language_form(request, component):
    """Return new language form for user."""
    if not request.user.has_perm("translation.add", component):
        raise PermissionDenied()
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

    def save(self, commit=True):
        if commit:
            self.instance.save(same_content=True)
            self._save_m2m()
            return self.instance
        return super().save(commit)


class UserManageForm(forms.Form):
    user = UserField(
        label=_("User to add"),
        help_text=_(
            "Please type in an existing Weblate account name or e-mail address."
        ),
    )


class UserBlockForm(forms.Form):
    user = UserField(
        label=_("User to block"),
        help_text=_(
            "Please type in an existing Weblate account name or e-mail address."
        ),
    )
    expiry = forms.ChoiceField(
        label=_("Block duration"),
        choices=(
            ("", _("Block user until I unblock them")),
            ("1", _("Block user for one day")),
            ("7", _("Block user for one week")),
            ("30", _("Block user for one month")),
        ),
        required=False,
    )


class ReportsForm(forms.Form):
    style = forms.ChoiceField(
        label=_("Report format"),
        help_text=_("Choose file format for the report"),
        choices=(
            ("rst", _("reStructuredText")),
            ("json", _("JSON")),
            ("html", _("HTML")),
        ),
    )
    period = forms.ChoiceField(
        label=_("Report period"),
        choices=(
            ("30days", _("Last 30 days")),
            ("this-month", _("This month")),
            ("month", _("Last month")),
            ("this-year", _("This year")),
            ("year", _("Last year")),
            ("", _("As specified")),
        ),
        required=False,
    )
    start_date = WeblateDateField(
        label=_("Starting date"), required=False, datepicker=False
    )
    end_date = WeblateDateField(
        label=_("Ending date"), required=False, datepicker=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("style"),
            Field("period"),
            Div(
                "start_date",
                "end_date",
                css_class="input-group input-daterange",
                data_provide="datepicker",
                data_date_format="yyyy-mm-dd",
            ),
        )

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
            end = timezone.make_aware(datetime(year, 12, 31))
            start = timezone.make_aware(datetime(year, 1, 1))
        elif self.cleaned_data["period"] == "this-year":
            year = timezone.now().year
            end = timezone.make_aware(datetime(year, 12, 31))
            start = timezone.make_aware(datetime(year, 1, 1))
        else:
            # Validate custom period
            if not self.cleaned_data.get("start_date"):
                raise ValidationError({"start_date": _("Missing date!")})
            if not self.cleaned_data.get("end_date"):
                raise ValidationError({"end_date": _("Missing date!")})
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
            msg = _("Starting date has to be before ending date!")
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
                _("You do not have permission to access this component!")
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


class SelectChecksField(forms.CharField):
    def to_python(self, value):
        return value


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
            raise ValidationError(_("This field has been identified as spam!"))


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
        }
        field_classes = {"enforced_checks": SelectChecksField}

    def __init__(self, request, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        if self.hide_restricted:
            self.fields["restricted"].widget = forms.HiddenInput()
        self.fields["links"].queryset = request.user.managed_projects.exclude(
            pk=self.instance.pk
        )
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    _("Basic"),
                    Fieldset(_("Name"), "name"),
                    Fieldset(_("License"), "license", "agreement"),
                    Fieldset(_("Upstream links"), "report_source_bugs"),
                    Fieldset(
                        _("Listing and access"),
                        "priority",
                        "restricted",
                        "links",
                    ),
                    Fieldset(
                        _("Glossary"),
                        "is_glossary",
                        "glossary_color",
                    ),
                    css_id="basic",
                ),
                Tab(
                    _("Translation"),
                    Fieldset(
                        _("Suggestions"),
                        "enable_suggestions",
                        "suggestion_voting",
                        "suggestion_autoaccept",
                    ),
                    Fieldset(
                        _("Translation settings"),
                        "allow_translation_propagation",
                        "manage_units",
                        "check_flags",
                        "variant_regex",
                        "enforced_checks",
                    ),
                    css_id="translation",
                ),
                Tab(
                    _("Version control"),
                    Fieldset(
                        _("Locations"),
                        Div(template="trans/repo_help.html"),
                        "vcs",
                        "repo",
                        "branch",
                        "push",
                        "push_branch",
                        "repoweb",
                    ),
                    Fieldset(
                        _("Version control settings"),
                        "push_on_commit",
                        "commit_pending_age",
                        "merge_style",
                        "auto_lock_error",
                    ),
                    css_id="vcs",
                ),
                Tab(
                    _("Commit messages"),
                    Fieldset(
                        _("Commit messages"),
                        ContextDiv(
                            template="trans/messages_help.html",
                            context={"user": request.user},
                        ),
                        "commit_message",
                        "add_message",
                        "delete_message",
                        "merge_message",
                        "addon_message",
                    ),
                    css_id="messages",
                ),
                Tab(
                    _("Files"),
                    Fieldset(
                        _("Translation files"),
                        "file_format",
                        "filemask",
                        "language_regex",
                        "source_language",
                    ),
                    Fieldset(
                        _("Monolingual translations"),
                        "template",
                        "edit_template",
                        "intermediate",
                    ),
                    Fieldset(
                        _("Adding new languages"),
                        "new_base",
                        "new_lang",
                        "language_code_style",
                    ),
                    css_id="files",
                ),
                template="layout/pills.html",
            )
        )
        vcses = (
            "git",
            "gerrit",
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
            "template",
            "edit_template",
            "intermediate",
            "new_base",
            "license",
            "new_lang",
            "language_code_style",
            "language_regex",
            "source_language",
            "is_glossary",
        ]
        widgets = {"source_language": SortedSelect}


class ComponentNameForm(forms.Form, ComponentDocsMixin, ComponentAntispamMixin):
    name = forms.CharField(
        label=_("Component name"),
        max_length=COMPONENT_NAME_LENGTH,
        help_text=_("Display name"),
    )
    slug = forms.SlugField(
        label=_("URL slug"),
        max_length=COMPONENT_NAME_LENGTH,
        help_text=_("Name used in URLs and filenames."),
    )
    is_glossary = forms.BooleanField(
        label=_("Use as a glossary"),
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
        label=_("Component"),
        help_text=_("Select existing component to copy configuration from."),
    )

    def __init__(self, request, *args, **kwargs):
        if "instance" in kwargs:
            kwargs.pop("instance")
        if "auto_id" not in kwargs:
            kwargs["auto_id"] = "id_existing_%s"
        super().__init__(request, *args, **kwargs)


class ComponentBranchForm(ComponentSelectForm):
    branch = forms.ChoiceField(label=_("Repository branch"))

    branch_data: Dict[int, List[str]] = {}
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
            # Can not raise directly as this will contain errors
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
        queryset=Project.objects.none(), label=_("Project")
    )
    source_language = forms.ModelChoiceField(
        widget=SortedSelect,
        label=_("Source language"),
        help_text=_("Language used for source strings in all components"),
        queryset=Language.objects.all(),
    )

    def __init__(self, request, *args, **kwargs):
        if "instance" in kwargs:
            kwargs.pop("instance")
        super().__init__(request, *args, **kwargs)
        # It might be overriden based on preset project
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
                {"name": _("Component with the same name already exists.")}
            )
        slug = self.cleaned_data.get("slug")
        if slug and project.component_set.filter(slug__iexact=slug).exists():
            raise ValidationError(
                {"slug": _("Component with the same name already exists.")}
            )


class ComponentScratchCreateForm(ComponentProjectForm):
    file_format = forms.ChoiceField(
        label=_("File format"),
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
        label=_("ZIP file containing translations"),
        validators=[FileExtensionValidator(allowed_extensions=["zip"])],
        widget=forms.FileInput(attrs={"accept": ".zip,application/zip"}),
    )

    field_order = ["zipfile", "project", "name", "slug"]

    def __init__(self, *args, **kwargs):
        kwargs["auto_id"] = "id_zipcreate_%s"
        super().__init__(*args, **kwargs)


class ComponentDocCreateForm(ComponentProjectForm):
    docfile = forms.FileField(
        label=_("Document to translate"),
        validators=[validate_file_extension],
    )

    field_order = ["docfile", "project", "name", "slug"]

    def __init__(self, *args, **kwargs):
        kwargs["auto_id"] = "id_doccreate_%s"
        super().__init__(*args, **kwargs)


class ComponentInitCreateForm(CleanRepoMixin, ComponentProjectForm):
    """Component creation form.

    This is mostly copy from Component model. Probably should be extracted to standalone
    Repository model...
    """

    project = forms.ModelChoiceField(
        queryset=Project.objects.none(), label=_("Project")
    )
    vcs = forms.ChoiceField(
        label=_("Version control system"),
        help_text=_(
            "Version control system to use to access your "
            "repository with translations."
        ),
        choices=VCS_REGISTRY.get_choices(exclude={"local"}),
        initial=settings.DEFAULT_VCS,
    )
    repo = forms.CharField(
        label=_("Source code repository"),
        max_length=REPO_LENGTH,
        help_text=_(
            "URL of a repository, use weblate://project/component "
            "for sharing with other component."
        ),
    )
    branch = forms.CharField(
        label=_("Repository branch"),
        max_length=REPO_LENGTH,
        help_text=_("Repository branch to translate"),
        required=False,
    )

    def clean_instance(self, data):
        params = copy.copy(data)
        if "discovery" in params:
            params.pop("discovery")

        instance = Component(**params)
        instance.clean_fields(exclude=("filemask", "file_format", "license"))
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
        label=_("Choose translation files to import"),
        choices=[("manual", _("Specify configuration manually"))],
        required=True,
        widget=forms.RadioSelect,
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
        for field, value in self.fields.items():
            if field == "discovery":
                continue
            value.widget = forms.HiddenInput()
        # Allow all VCS now (to handle zip file upload case)
        self.fields["vcs"].choices = VCS_REGISTRY.get_choices()
        self.discovered = self.perform_discovery(request, kwargs)
        for i, value in enumerate(self.discovered):
            self.fields["discovery"].choices.append((i, self.render_choice(value)))

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
    """Component rename form."""

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
        if (
            "access_control" not in data
            or data["access_control"] is None
            or data["access_control"] == ""
        ):
            data["access_control"] = self.instance.access_control
        access = data["access_control"]

        self.changed_access = access != self.instance.access_control

        if self.changed_access and not self.user_can_change_access:
            raise ValidationError(
                {
                    "access_control": _(
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
                        "access_control": _(
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
            self.fields["access_control"].help_text = _(
                "You do not have permission to change project access control."
            )
        else:
            disabled = {}
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    _("Basic"),
                    "name",
                    "web",
                    "instructions",
                    css_id="basic",
                ),
                Tab(
                    _("Access"),
                    InlineRadios(
                        "access_control",
                        template="%s/layout/radioselect_access.html",
                        **disabled,
                    ),
                    css_id="access",
                ),
                Tab(
                    _("Workflow"),
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
                    _("Components"),
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
            self.fields["use_shared_tm"].help_text = _(
                "Uses and contributes to the pool of shared translations "
                "between projects."
            )
            self.fields["access_control"].choices = [
                choice
                for choice in self.fields["access_control"].choices
                if choice[0] != Project.ACCESS_CUSTOM
            ]


class ProjectRenameForm(SettingsBaseForm, ProjectDocsMixin):
    """Project rename form."""

    class Meta:
        model = Project
        fields = ["slug"]


class ProjectCreateForm(SettingsBaseForm, ProjectDocsMixin, ProjectAntispamMixin):
    """Project creation form."""

    # This is fake field with is either hidden or configured
    # in the view
    billing = forms.ModelChoiceField(
        label=_("Billing"),
        queryset=User.objects.none(),
        required=True,
        empty_label=None,
    )

    class Meta:
        model = Project
        fields = ("name", "slug", "web", "instructions")


class ReplaceForm(forms.Form):
    q = QueryField(
        required=False, help_text=_("Optional additional filter on the strings")
    )
    search = forms.CharField(
        label=_("Search string"),
        min_length=1,
        required=True,
        strip=False,
        help_text=_("Case sensitive string to search for and replace."),
    )
    replacement = forms.CharField(
        label=_("Replacement string"), min_length=1, required=True, strip=False
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
    """Form for requesting new language."""

    lang = forms.MultipleChoiceField(
        label=_("Languages"), choices=[], widget=forms.SelectMultiple
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

    def __init__(self, translation, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.translation = translation
        self.fields["variant"].queryset = translation.unit_set.all()
        self.user = user

    def clean(self):
        try:
            data = self.as_kwargs()
        except KeyError:
            # Probably some fields validation has failed
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
        label=_("Translation key"),
        help_text=_(
            "Key used to identify string in translation file. "
            "File format specific rules might apply."
        ),
        required=True,
    )
    source = PluralField(
        label=_("Source language text"),
        help_text=_(
            "You can edit this later, as with any other string in "
            "the source language."
        ),
        required=True,
    )

    def __init__(self, translation, user, *args, **kwargs):
        super().__init__(translation, user, *args, **kwargs)
        self.fields["context"].widget.attrs["tabindex"] = 99
        self.fields["source"].widget.attrs["tabindex"] = 100
        self.fields["source"].widget.profile = user.profile
        self.fields["source"].initial = Unit(translation=translation, id_hash=0)


class NewBilingualSourceUnitForm(NewUnitBaseForm):
    context = forms.CharField(
        label=_("Context"),
        help_text=_("Optional context to clarify the source strings."),
        required=False,
    )
    auto_context = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Automatically adjust context when same string already exists."),
    )
    source = PluralField(
        label=_("Source string"),
        required=True,
    )

    def __init__(self, translation, user, *args, **kwargs):
        super().__init__(translation, user, *args, **kwargs)
        self.fields["context"].widget.attrs["tabindex"] = 99
        self.fields["context"].label = translation.component.context_label
        self.fields["source"].widget.attrs["tabindex"] = 100
        self.fields["source"].widget.profile = user.profile
        self.fields["source"].initial = Unit(
            translation=translation.component.source_translation, id_hash=0
        )


class NewBilingualUnitForm(NewBilingualSourceUnitForm):
    target = PluralField(
        label=_("Translated string"),
        help_text=_(
            "You can edit this later, as with any other string in the translation."
        ),
        required=True,
    )

    def __init__(self, translation, user, *args, **kwargs):
        super().__init__(translation, user, *args, **kwargs)
        self.fields["target"].widget.attrs["tabindex"] = 101
        self.fields["target"].widget.profile = user.profile
        self.fields["target"].initial = Unit(translation=translation, id_hash=0)


class NewBilingualGlossarySourceUnitForm(GlossaryAddMixin, NewBilingualSourceUnitForm):
    def __init__(self, translation, user, *args, **kwargs):
        if kwargs["initial"] is None:
            kwargs["initial"] = {}
        kwargs["initial"]["terminology"] = True
        super().__init__(translation, user, *args, **kwargs)


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

    It assumes the queryset is reused and avoids using iterator or count queries.
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
        label=_("State to set"), choices=((-1, _("Do not change")),) + STATE_CHOICES
    )
    add_flags = FlagField(label=_("Translation flags to add"), required=False)
    remove_flags = FlagField(label=_("Translation flags to remove"), required=False)
    add_labels = CachedModelMultipleChoiceField(
        queryset=Label.objects.none(),
        label=_("Labels to add"),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
    )
    remove_labels = CachedModelMultipleChoiceField(
        queryset=Label.objects.none(),
        label=_("Labels to remove"),
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
        if user is not None and not user.has_perm("unit.review", obj):
            excluded.add(STATE_APPROVED)

        # Filter offered states
        self.fields["state"].choices = [
            x for x in self.fields["state"].choices if x[0] not in excluded
        ]

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
        label=_("I accept the contributor agreement"), required=True
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
                context={"object": obj},
            ),
            Field("confirm"),
        )
        self.helper.form_tag = False

    def clean(self):
        if self.cleaned_data.get("confirm") != self.obj.full_slug:
            raise ValidationError(
                _("The slug does not match the one marked for deletion!")
            )


class TranslationDeleteForm(BaseDeleteForm):
    confirm = forms.CharField(
        label=_("Removal confirmation"),
        help_text=_("Please type in the full slug of the translation to confirm."),
        required=True,
    )
    warning_template = "trans/delete-translation.html"


class ComponentDeleteForm(BaseDeleteForm):
    confirm = forms.CharField(
        label=_("Removal confirmation"),
        help_text=_("Please type in the full slug of the component to confirm."),
        required=True,
    )
    warning_template = "trans/delete-component.html"


class ProjectDeleteForm(BaseDeleteForm):
    confirm = forms.CharField(
        label=_("Removal confirmation"),
        help_text=_("Please type in the slug of the project to confirm."),
        required=True,
    )
    warning_template = "trans/delete-project.html"


class ProjectLanguageDeleteForm(BaseDeleteForm):
    confirm = forms.CharField(
        label=_("Removal confirmation"),
        help_text=_("Please type in the slug of the project and language to confirm."),
        required=True,
    )
    warning_template = "trans/delete-project-language.html"


class AnnouncementForm(forms.ModelForm):
    """Component base form."""

    class Meta:
        model = Announcement
        fields = ["message", "category", "expiry", "notify"]
        widgets = {
            "expiry": WeblateDateInput(),
            "message": MarkdownTextarea,
        }


class ChangesForm(forms.Form):
    project = forms.ChoiceField(label=_("Project"), choices=[("", "")], required=False)
    lang = forms.ChoiceField(label=_("Language"), choices=[("", "")], required=False)
    action = forms.MultipleChoiceField(
        label=_("Action"),
        required=False,
        widget=SortedSelectMultiple,
        choices=Change.ACTION_CHOICES,
    )
    user = UsernameField(label=_("Author username"), required=False, help_text=None)
    start_date = WeblateDateField(
        label=_("Starting date"), required=False, datepicker=False
    )
    end_date = WeblateDateField(
        label=_("Ending date"), required=False, datepicker=False
    )

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


class ProjectTokenDeleteForm(forms.Form):
    token = forms.ModelChoiceField(
        ProjectToken.objects.none(),
        widget=forms.HiddenInput,
        required=True,
    )

    def __init__(self, project, *args, **kwargs):
        self.project = project
        super().__init__(*args, **kwargs)
        self.fields["token"].queryset = project.projecttoken_set.all()


class ProjectTokenCreateForm(forms.ModelForm):
    class Meta:
        model = ProjectToken
        fields = ["name", "expires", "project"]
        widgets = {
            "expires": WeblateDateInput(),
            "project": forms.HiddenInput,
        }

    def __init__(self, project, *args, **kwargs):
        self.project = project
        kwargs["initial"] = {"project": project}
        super().__init__(*args, **kwargs)

    def clean_project(self):
        if self.project != self.cleaned_data["project"]:
            raise ValidationError("Invalid project!")
        return self.cleaned_data["project"]

    def clean_expires(self):
        expires = self.cleaned_data["expires"]
        expires = expires.replace(hour=23, minute=59, second=59, microsecond=999999)
        if expires < timezone.now():
            raise forms.ValidationError(gettext("Expiry cannot be in the past!"))
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
        label=_("Teams"),
        required=False,
    )

    def __init__(self, project, *args, **kwargs):
        self.project = project
        super().__init__(*args, **kwargs)
        self.fields["user"].widget = forms.HiddenInput()
        self.fields["groups"].queryset = project.defined_groups.all()
