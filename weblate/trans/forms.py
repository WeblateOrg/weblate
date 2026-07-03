# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import copy
import json
import re
from collections import defaultdict
from datetime import datetime
from itertools import chain
from secrets import token_hex
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, cast

import jsonschema
from crispy_forms.bootstrap import InlineCheckboxes, InlineRadios, Tab, TabHolder
from crispy_forms.helper import FormHelper
from crispy_forms.layout import (
    HTML,
    Div,
    Field,
    Fieldset,
    Layout,
)
from django import forms
from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.core.validators import FileExtensionValidator
from django.db.models import Count, Q
from django.forms import model_to_dict
from django.forms.utils import from_current_timezone
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.text import normalize_newlines, slugify
from django.utils.translation import get_language, gettext, gettext_lazy
from translation_finder import DiscoveryResult, discover

from weblate.accounts.models import AuditLog
from weblate.auth.models import Group, User
from weblate.auth.utils import validate_team_assignable_user
from weblate.checks.flags import Flags
from weblate.checks.models import CHECKS
from weblate.checks.utils import highlight_string
from weblate.configuration.models import Setting, SettingCategory
from weblate.formats.base import BilingualUpdateMixin
from weblate.formats.models import EXPORTERS, FILE_FORMATS
from weblate.lang.forms import (
    LanguageCodeChoiceField,
    LimitLanguagesField,
    get_language_code_choices,
)
from weblate.lang.models import Language
from weblate.machinery.base import MACHINERY_DEFAULT_THRESHOLD
from weblate.machinery.models import MACHINERY
from weblate.trans.actions import ActionEvents
from weblate.trans.backups import ProjectBackup
from weblate.trans.defines import (
    BRANCH_LENGTH,
    COMPONENT_NAME_LENGTH,
    FILENAME_LENGTH,
    REPO_LENGTH,
)
from weblate.trans.file_format_params import (
    FILE_FORMATS_PARAMS,
    get_params_for_file_format,
    strip_unused_file_format_params,
)
from weblate.trans.filter import FILTERS
from weblate.trans.inherited_settings import (
    COMPONENT_MESSAGE_SETTINGS,
    INHERITABLE_COMPONENT_FLAGS,
    INHERITABLE_COMPONENT_SETTINGS,
    get_inherit_field_name,
)
from weblate.trans.models import (
    Announcement,
    Category,
    Change,
    CommitPolicyChoices,
    Component,
    Label,
    Project,
    Unit,
    WorkflowSetting,
)
from weblate.trans.specialchars import RTL_CHARS_DATA, get_special_chars
from weblate.trans.util import check_upload_method_permissions, is_repo_link
from weblate.trans.validators import validate_check_flags
from weblate.trans.workspace_move import (
    PROJECT_MOVE_WORKSPACE_SELECT_LIMIT,
    get_project_move_target_workspaces,
    get_project_workspace_move_error,
)
from weblate.utils.antispam import is_spam
from weblate.utils.files import FileUploadMethod
from weblate.utils.forms import (
    CachedModelMultipleChoiceField,
    ColorWidget,
    ContextDiv,
    EmailField,
    InheritedSetting,
    NormalizedNewlineCharField,
    QueryField,
    SearchableSelect,
    SearchField,
    SortedSelect,
    SortedSelectMultiple,
    UserField,
    WeblateDateInput,
)
from weblate.utils.hash import checksum_to_hash, hash_to_checksum
from weblate.utils.html import format_html_join_comma
from weblate.utils.state import (
    FUZZY_STATES,
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_NEEDS_CHECKING,
    STATE_NEEDS_REWRITING,
    STATE_READONLY,
    STATE_TRANSLATED,
    StringState,
    get_state_label,
)
from weblate.utils.validators import (
    validate_component_zip_upload_size,
    validate_file_extension,
    validate_project_backup_upload_size,
    validate_translation_upload_size,
)
from weblate.utils.views import get_sort_name
from weblate.vcs.git import GitMergeRequestBase
from weblate.vcs.models import VCS_REGISTRY
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from django.db.models import Model, QuerySet
    from django.http import QueryDict

    from weblate.accounts.models import Profile
    from weblate.auth.models import AuthenticatedHttpRequest
    from weblate.auth.results import PermissionResult
    from weblate.trans.file_format_params import FileFormatParams
    from weblate.trans.mixins import URLMixin
    from weblate.trans.models import (
        Translation,
    )
    from weblate.trans.models.translation import NewUnitParams
    from weblate.utils.stats import CategoryLanguage, ProjectLanguage


def clean_integration_component_data(
    form: forms.BaseForm, data: dict[str, Any], *, vcs: str | None = None
) -> bool:
    """Normalize settings owned by integration-backed VCS backends."""
    vcs_backend = VCS_REGISTRY.get(vcs or data.get("vcs", ""))
    if vcs_backend is None:
        return True

    for field in vcs_backend.component_clear_fields:
        if field in data:
            data[field] = ""

    if (
        vcs_backend.component_requires_branch
        and not data.get("branch")
        and not is_repo_link(data.get("repo") or "")
    ):
        form.add_error(
            "branch",
            gettext("Repository branch is required for this integration."),
        )
        return False
    return True


class SiteDefaultField(Protocol):
    site_default: bool
    widget: forms.Widget


BUTTON_TEMPLATE = """
<button type="button" class="btn btn-outline-primary {0}" title="{1}" {2}>{3}</button>
"""
RADIO_TEMPLATE = """
<label class="btn btn-outline-primary {0}" title="{1}">
<input type="radio" name="{2}" value="{3}" {4}/>
{5}
</label>
"""
GROUP_TEMPLATE = """
<div class="btn-group btn-group-sm" {0}>{1}</div>
"""
TOOLBAR_TEMPLATE = """
<div class="btn-toolbar float-end editor-toolbar">{0}</div>
"""
MIN_COST_ESTIMATE_TM_THRESHOLD = 75


class FieldDocsMixin(forms.Form):
    def get_field_doc(self, field: forms.Field) -> tuple[str, str] | None:
        raise NotImplementedError


class MarkdownTextarea(forms.Textarea):
    def __init__(self, **kwargs) -> None:
        kwargs["attrs"] = {
            "dir": "auto",
            "class": "markdown-editor highlight-editor",
            "data-mode": "markdown",
        }
        super().__init__(**kwargs)


class DateRangeField(forms.CharField):
    """Field for a date range input."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def to_python(self, value):
        """Convert the string input into data range values."""
        value = super().to_python(value)
        if value in self.empty_values:
            return None
        try:
            start, end = value.split(" - ")
            # ruff: ignore[call-datetime-strptime-without-zone]
            start_date = datetime.strptime(start, "%m/%d/%Y").replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            # ruff: ignore[call-datetime-strptime-without-zone]
            end_date = datetime.strptime(end, "%m/%d/%Y").replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
            return {
                "start_date": from_current_timezone(start_date),
                "end_date": from_current_timezone(end_date),
            }
        except ValueError as error:
            raise ValidationError(gettext("Invalid date!")) from error

    def validate(self, value) -> None:
        """Validate the date range values."""
        if self.required:
            super().validate(value)

        if value not in self.empty_values and value["start_date"] > value["end_date"]:
            raise ValidationError(
                gettext("The starting date has to be before the ending date.")
            )

    def clean(self, value):
        """Produce a clean and validated date range values."""
        value = self.to_python(value)
        self.validate(value)
        return value


class ChecksumField(forms.CharField):
    """Field for handling checksum IDs for translation."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs["widget"] = forms.HiddenInput
        super().__init__(*args, **kwargs)

    def clean(self, value):
        super().clean(value)
        if not value:
            return None
        try:
            return checksum_to_hash(value)
        except ValueError as error:
            raise ValidationError(gettext("Invalid checksum specified!")) from error


class FlagEditorWidget(forms.TextInput):
    """Text input for interactive flag editor."""

    def __init__(self, attrs=None) -> None:
        attrs = {**(attrs or {})}
        existing = attrs.get("class", "").split()
        if "flag-editor" not in existing:
            existing.append("flag-editor")
        attrs["class"] = " ".join(existing)
        attrs.setdefault("autocomplete", "off")
        attrs.setdefault("autocapitalize", "off")
        attrs.setdefault("spellcheck", "false")
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        # Embed active language in the URL so the browser cache key varies on it
        language = get_language() or ""
        url = reverse("js-flag-choices")
        if language:
            url = f"{url}?{urlencode({'lang': language})}"
        context["widget"]["attrs"].setdefault("data-flag-choices-url", url)
        return context


class FlagField(forms.CharField):
    # ruff: ignore[mutable-class-default]
    default_validators = [validate_check_flags]
    widget = FlagEditorWidget

    def __init__(self, *args, **kwargs) -> None:
        # Force the tag-based editor widget
        kwargs["widget"] = FlagEditorWidget()
        super().__init__(*args, **kwargs)


class PluralTextarea(forms.Textarea):
    """Text-area extension which possibly handles plurals."""

    profile: Profile

    def __init__(self, *args, **kwargs) -> None:
        self.is_source_plural: Literal[True] | None = None
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
                        # ruff: ignore[suspicious-mark-safe-usage]
                        mark_safe(
                            value.encode("ascii", "xmlcharrefreplace").decode("ascii")
                        ),
                    ),
                    char,
                )
                for name, char, value in RTL_CHARS_DATA
            ),
        )

        groups = format_html_join(
            "\n",
            GROUP_TEMPLATE,
            [("", chars)],  # Only one group.
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
                    mark_safe('checked="checked"'),
                    "RTL",
                ),
                (
                    "direction-toggle",
                    gettext("Toggle text direction"),
                    rtl_name,
                    "ltr",
                    "",
                    "LTR",
                ),
            ],
        )
        groups = format_html_join(
            "\n",
            GROUP_TEMPLATE,
            [
                (
                    mark_safe('data-bs-toggle="buttons"'),
                    rtl_switch,
                )
            ],  # Only one group.
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
                        'data-value="{}" tabindex="-1"',
                        # ruff: ignore[suspicious-mark-safe-usage]
                        mark_safe(
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
            "\n",
            GROUP_TEMPLATE,
            [("", chars)],  # Only one group.
        )

        result = format_html(TOOLBAR_TEMPLATE, groups)

        if language.direction == "rtl":
            result = format_html("{}{}", self.get_rtl_toolbar(fieldname), result)

        return result

    def render(self, name, value, attrs=None, renderer=None, **kwargs):
        """Render all textareas with correct plural labels."""
        unit = value
        translation = unit.translation
        lang_label = lang = translation.language
        if self.is_source_plural:
            plurals = translation.get_source_plurals()
            values = plurals
        else:
            plurals = unit.get_source_plurals()
            values = unit.get_target_plurals()
        if "zen-mode" in self.attrs:
            lang_label = format_html(
                '<a class="language" href="{}" tabindex="-1">{}</a>',
                unit.get_absolute_url(),
                lang_label,
            )
        plural = translation.plural
        placeables_set: set[str] = set()
        for text in plurals:
            placeables_set.update(
                highlight.text for highlight in highlight_string(text, unit)
            )
        placeables = list(placeables_set)
        show_plural_labels = len(values) > 1 and not translation.component.is_multivalue

        # Need to add extra class
        attrs["class"] = "translation-editor form-control highlight-editor"
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
        for idx in range(10):
            fieldname = f"{name}_{idx:d}"
            if fieldname not in data:
                break
            ret.append(data.get(fieldname, ""))
        return [normalize_newlines(r) for r in ret]


class PluralField(forms.CharField):
    """
    Renderer for the plural field.

    The only difference from CharField is that it does not
    enforce the value to be a string.
    """

    def __init__(self, **kwargs) -> None:
        kwargs["label"] = ""
        super().__init__(widget=PluralTextarea, **kwargs)

    def to_python(self, value):
        """Return list of strings as returned by PluralTextarea."""
        return value

    def clean(self, value):
        value = super().clean(value)
        if not value or (self.required and not any(value)):
            raise ValidationError(self.error_messages["required"], code="required")
        return value


class ChecksumForm(forms.Form):
    """Form for handling checksum IDs for translation."""

    checksum = ChecksumField(required=True)

    def __init__(self, unit_set, *args, **kwargs) -> None:
        self.unit_set = unit_set
        super().__init__(*args, **kwargs)

    def clean_checksum(self) -> str | None:
        """Validate whether checksum is valid and fetches unit for it."""
        if "checksum" not in self.cleaned_data:
            return None

        unit_set = self.unit_set

        checksum = self.cleaned_data["checksum"]
        try:
            self.cleaned_data["unit"] = unit_set.filter(id_hash=checksum)[0]
        except (Unit.DoesNotExist, IndexError) as error:
            raise ValidationError(
                gettext("The string you wanted to translate is no longer available.")
            ) from error
        return checksum


class UnitForm(forms.Form):
    def __init__(self, unit: Unit, *args, **kwargs) -> None:
        self.unit = unit
        super().__init__(*args, **kwargs)


class FuzzyField(forms.BooleanField):
    help_as_icon = True

    def __init__(self, *args, **kwargs) -> None:
        kwargs["label"] = gettext_lazy("Needs editing")
        kwargs["help_text"] = gettext_lazy(
            'Strings are usually marked as "Needs editing" after the source '
            "string is updated, or when marked as such manually."
        )
        super().__init__(*args, **kwargs)
        self.widget.attrs["class"] = "fuzzy_checkbox"


class TranslationForm(UnitForm):
    """Form used for translation of single string."""

    checksum = ChecksumField(required=True)
    contentsum = ChecksumField(required=True)
    translationsum = ChecksumField(required=True)
    target = PluralField(required=False)
    fuzzy = FuzzyField(required=False)
    review = forms.ChoiceField(
        label=gettext_lazy("Review state"),
        choices=[
            (state, get_state_label(state, label, True))
            for state, label in StringState.choices
            if state not in {STATE_READONLY, STATE_EMPTY}
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

    def __init__(self, user: User, unit: Unit, *args, **kwargs) -> None:
        translation = unit.translation
        component = translation.component
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
        super().__init__(unit, *args, **kwargs)
        user_can_edit = user.has_perm("unit.edit", unit)
        user_can_review = user.has_perm("unit.review", translation)
        if unit.readonly:
            self.fields["target"].widget.attrs["readonly"] = 1
            # checkbox cannot be read-only, so hide it instead
            self.fields["fuzzy"].widget = forms.HiddenInput()
            self.fields["review"].choices = [
                (state, label)
                for state, label in StringState.choices
                if state == STATE_READONLY
            ]
        else:
            # Filter fuzzy state choices based on current unit state
            # STATE_NEEDS_CHECKING and STATE_NEEDS_REWRITING are only shown
            # if the unit is currently in that state
            if unit.state == STATE_NEEDS_CHECKING:
                states_to_hide = {STATE_FUZZY, STATE_NEEDS_REWRITING}
                self.fields["fuzzy"].label = StringState(STATE_NEEDS_CHECKING).label
            elif unit.state == STATE_NEEDS_REWRITING:
                states_to_hide = {STATE_FUZZY, STATE_NEEDS_CHECKING}
                self.fields["fuzzy"].label = StringState(STATE_NEEDS_REWRITING).label
            else:
                states_to_hide = {STATE_NEEDS_CHECKING, STATE_NEEDS_REWRITING}
            self.fields["review"].choices = [
                (state, get_state_label(state, label, True))
                for state, label in StringState.choices
                if state not in {STATE_READONLY, STATE_EMPTY} | states_to_hide
            ]
        if not user_can_edit:
            state = StringState(unit.state)
            self.fields["review"].choices = [
                (
                    state,
                    get_state_label(state, state.label, translation.enable_review),
                )
            ]
            self.fields["review"].disabled = True
        self.user_can_edit = user_can_edit
        self.user = user
        self.fields["target"].widget.profile = user.profile
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
            Field("checksum"),
            Field("contentsum"),
            Field("translationsum"),
            InlineRadios("review", css_class="review_radio"),
            Field("explanation"),
        )
        if user_can_review or not user_can_edit:
            self.fields["fuzzy"].widget = forms.HiddenInput()
        else:
            self.fields["review"].widget = forms.HiddenInput()
        if component.is_glossary:
            if unit.is_source:
                self.fields["explanation"].label = gettext("Source string explanation")
            else:
                self.fields["explanation"].label = gettext("Translation explanation")
        else:
            self.fields["explanation"].widget = forms.HiddenInput()

        if component.project.commit_policy:
            commit_policy = f" {component.project.get_commit_policy_description()}"
            self.fields["review"].help_text += commit_policy
            self.fields["fuzzy"].help_text += commit_policy

    def clean(self) -> None:
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

        fuzzy_state = unit.state if unit.state in FUZZY_STATES else STATE_FUZZY

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
            cleaned_state = int(self.cleaned_data["review"])
            # if the unit is already in a fuzzy state and the new state is also
            # a fuzzy state, retain the unit's original fuzzy state.
            if cleaned_state in FUZZY_STATES:
                self.cleaned_data["state"] = fuzzy_state
            else:
                self.cleaned_data["state"] = cleaned_state
        elif self.cleaned_data["fuzzy"]:
            self.cleaned_data["state"] = fuzzy_state
        else:
            self.cleaned_data["state"] = STATE_TRANSLATED


class ZenTranslationForm(TranslationForm):
    def __init__(
        self, user: User, unit, *args, form_action: str | None = None, **kwargs
    ) -> None:
        super().__init__(user, unit, *args, **kwargs)
        self.helper.form_action = form_action or reverse(
            "save_zen", kwargs={"path": unit.translation.get_url_path()}
        )
        self.helper.form_tag = True
        self.helper.disable_csrf = False
        self.fields["target"].widget.attrs["zen-mode"] = True
        if not self.user_can_edit:
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

    def __init__(self, translation: Translation, *args, **kwargs) -> None:
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


class SimpleUploadForm(FieldDocsMixin, forms.Form):
    """Base form for uploading a file."""

    file = forms.FileField(
        label=gettext_lazy("File"),
        validators=[validate_translation_upload_size, validate_file_extension],
    )
    method = forms.ChoiceField(
        label=gettext_lazy("File upload mode"),
        choices=FileUploadMethod.choices,
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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("file"),
            Field("method", template="%s/layout/radioselect_upload_method.html"),
            Field("fuzzy"),
        )

    def get_field_doc(self, field: forms.Field) -> tuple[str, str] | None:
        return ("user/files", f"upload-{field.name}")

    def remove_translation_choice(self, value) -> None:
        """Remove given file upload method from choices."""
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

    def __init__(self, *args, **kwargs) -> None:
        self.review_permission: bool | PermissionResult = kwargs.pop(
            "review_permission", False
        )
        super().__init__(*args, **kwargs)
        self.helper.layout.fields.append(Field("conflicts"))

    def clean_conflicts(self) -> str:
        conflicts = cast("str", self.cleaned_data["conflicts"])
        if conflicts == "replace-approved" and not self.review_permission:
            reason = getattr(self.review_permission, "reason", None)
            raise ValidationError(
                reason or gettext("Insufficient privileges for reviewing strings.")
            )
        return conflicts


class ExtraUploadForm(UploadForm):
    """Advanced upload form for users who can override authorship."""

    author_name = forms.CharField(label=gettext_lazy("Author name"))
    author_email = EmailField(label=gettext_lazy("Author e-mail"))

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper.layout.fields.append(Field("author_name"))
        self.helper.layout.fields.append(Field("author_email"))


def get_upload_form(user: User, translation: Translation, *args, **kwargs):
    """Return correct upload form based on user permissions."""
    form: type[SimpleUploadForm]
    if user.has_perm("upload.authorship", translation):
        form = ExtraUploadForm
        kwargs["initial"] = {"author_name": user.full_name, "author_email": user.email}
    elif user.has_perm("upload.overwrite", translation):
        form = UploadForm
    else:
        form = SimpleUploadForm
    review_permission: bool | PermissionResult = True
    if form != SimpleUploadForm:
        review_permission = user.has_perm("unit.review", translation)
        kwargs["review_permission"] = review_permission
    result = form(*args, **kwargs)
    for method in [x[0] for x in result.fields["method"].choices]:
        if not check_upload_method_permissions(user, translation, method):
            result.remove_translation_choice(method)
    # Remove approved choice for non review projects
    if not review_permission and form != SimpleUploadForm:
        result.fields["conflicts"].choices = [
            choice
            for choice in result.fields["conflicts"].choices
            if choice[0] != "replace-approved"
        ]
    return result


class SearchForm(forms.Form):
    """Text-searching form."""

    q = QueryField()
    sort_by = forms.CharField(required=False, widget=forms.HiddenInput)
    checksum = ChecksumField(required=False)
    offset = forms.IntegerField(min_value=-1, required=False, widget=forms.HiddenInput)
    offset_kwargs: ClassVar[dict[str, str]] = {}

    @staticmethod
    def get_initial(request: AuthenticatedHttpRequest):
        if "q" in request.GET:
            return {"q": request.GET["q"]}
        return None

    def __init__(
        self,
        *,
        request: AuthenticatedHttpRequest,
        language: Language | None = None,
        show_builder=True,
        obj: Project
        | Translation
        | Component
        | ProjectLanguage
        | Category
        | CategoryLanguage
        | Workspace
        | Language
        | None = None,
        query_data: QueryDict | None = None,
        **kwargs,
    ) -> None:
        """Generate choices for other components in the same project."""
        self.user = request.user
        self.language = language
        sort_by = get_sort_name(request, obj, query_data=query_data)
        self.sort_name = sort_by["name"]
        self.sort_query = sort_by["query"]
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
        Reset form offset.

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
    offset_kwargs: ClassVar[dict[str, str]] = {
        "template": "snippets/position-field.html"
    }


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
            filter_kwargs: dict[str, Any] = {
                "pk": self.cleaned_data["merge"],
                "translation__component__project": project,
                "translation__language": translation.language,
            }
            if not translation.is_source:
                filter_kwargs["source"] = unit.source
            self.cleaned_data["merge_unit"] = Unit.objects.get(**filter_kwargs)
        except Unit.DoesNotExist as error:
            raise ValidationError(
                gettext("Could not find the merged string.")
            ) from error
        return self.cleaned_data


class RevertForm(UnitForm):
    """Form for reverting edits."""

    revert = forms.IntegerField()

    def clean(self):
        super().clean()
        if "revert" not in self.cleaned_data:
            return None
        try:
            change = Change.objects.get(pk=self.cleaned_data["revert"], unit=self.unit)
        except Change.DoesNotExist as error:
            raise ValidationError(
                gettext("Could not find the reverted change.")
            ) from error
        if not change.can_revert():
            raise ValidationError(gettext("Could not find the reverted change."))
        self.cleaned_data["revert_change"] = change
        return self.cleaned_data


class AutoForm(forms.Form):
    """Automatic translation form."""

    COMPONENT_SLUG_HELP_TEXT = gettext_lazy(
        "Enter slug of a component to use as source, keep blank to use all "
        "components in the current project."
    )
    COMPONENT_WORKSPACE_SLUG_HELP_TEXT = gettext_lazy(
        "Enter project and component slug or component ID to use as source, "
        "keep blank to use all components in the current workspace."
    )
    COMPONENT_SELECT_HELP_TEXT = gettext_lazy(
        "Turn on contribution to shared translation memory for the project to "
        "get access to additional components."
    )

    mode = forms.ChoiceField(
        label=gettext_lazy("Automatic translation mode"),
        initial="suggest",
    )
    q = QueryField(
        required=True,
        initial="state:<translated",
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
        widget=forms.RadioSelect,
    )
    component = forms.ChoiceField(
        label=gettext_lazy("Component"),
        required=False,
        help_text=COMPONENT_SLUG_HELP_TEXT,
        initial="",
    )
    engines = forms.MultipleChoiceField(
        label=gettext_lazy("Machine translation engines"), choices=[], required=False
    )
    threshold = forms.IntegerField(
        label=gettext_lazy("Score threshold"),
        initial=MACHINERY_DEFAULT_THRESHOLD,
        min_value=1,
        max_value=100,
    )

    def __init__(
        self, obj: Component | Project | Workspace | None, user=None, *args, **kwargs
    ) -> None:
        """Generate choices for other components in the same project."""
        auto_id = kwargs.pop("auto_id", "id_auto_%s")
        super().__init__(*args, auto_id=auto_id, **kwargs)
        if (
            self.is_bound
            and self.data.get("auto_source") == "mt"
            and self.data.get("component")
        ):
            self.data = self.data.copy()
            self.data["component"] = ""
        self.obj = obj
        self.project: Project | None = None
        machinery_settings = {}

        if isinstance(obj, Component):
            self.components = obj.project.component_set.filter(
                source_language=obj.source_language
            ) | Component.objects.filter(
                source_language_id=obj.source_language_id,
                project__contribute_shared_tm=True,
            ).exclude(project=obj.project)
            machinery_settings = obj.project.get_machinery_settings()
            self.project = obj.project
        elif isinstance(obj, Project):
            self.components = obj.component_set.filter(
                source_language_id__in=obj.source_language_ids
            ) | Component.objects.filter(
                source_language_id__in=obj.source_language_ids,
                project__contribute_shared_tm=True,
            ).exclude(project=obj)
            machinery_settings = obj.get_machinery_settings()
            self.project = obj
        elif isinstance(obj, Workspace):
            self.components = Component.objects.filter(project__workspace=obj)
            projects = Project.objects.filter(workspace=obj).order()
            if user is not None:
                self.components = self.components.filter_access(user)
                projects = user.allowed_projects.filter(workspace=obj).order()
            for project in projects:
                machinery_settings.update(project.get_machinery_settings())
        else:
            # Site-wide add-ons
            self.components = Component.objects.all()
            machinery_settings = Setting.objects.get_settings_dict(SettingCategory.MT)

        # Fetching first few entries is faster than doing a count query on possibly
        # thousands of components
        if len(self.components.values_list("id")[:30]) == 30:
            # Do not show choices when too many
            help_text = (
                self.COMPONENT_WORKSPACE_SLUG_HELP_TEXT
                if isinstance(obj, Workspace)
                else self.fields["component"].help_text
            )
            self.fields["component"] = forms.CharField(
                required=False,
                label=gettext("Component"),
                help_text=help_text,
            )
        else:
            choices = [
                (s.id, str(s))
                for s in self.components.order_project().prefetch_related("project")
            ]

            if isinstance(obj, Workspace):
                all_components_label = gettext("All components in current workspace")
            else:
                all_components_label = gettext("All components in current project")
            self.fields["component"].choices = [("", all_components_label), *choices]
            self.fields["component"].help_text = self.COMPONENT_SELECT_HELP_TEXT

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
            self.fields["engines"].initial = ["weblate"]

        if "q" not in self.initial:
            self.initial["q"] = "state:<translated"

        choices = [
            ("suggest", gettext("Add as suggestion")),
            ("translate", gettext("Add as translation")),
            ("fuzzy", gettext('Add as "Needing edit"')),
        ]
        if user is not None and (user.has_perm("unit.review", obj) or obj is None):
            choices.append(("approved", gettext("Add as approved translation")))
        self.fields["mode"].choices = choices

        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field("mode"),
            SearchField("q"),
            InlineRadios("auto_source"),
            Div("component", css_id="auto_source_others"),
            Div("engines", "threshold", css_id="auto_source_mt"),
        )

    def clean_component(self):
        if self.cleaned_data.get("auto_source") == "mt":
            return None
        component = self.cleaned_data["component"]
        if not component:
            return None
        if component.isdigit():
            try:
                result = self.components.get(pk=component)
            except Component.DoesNotExist as error:
                raise ValidationError(gettext("Component not found!")) from error
        elif "/" not in component:
            if self.project is None:
                raise ValidationError(
                    gettext("Enter component ID or project/component slug.")
                )
            try:
                result = self.components.get(slug=component, project=self.project)
            except (Component.DoesNotExist, Component.MultipleObjectsReturned) as error:
                raise ValidationError(gettext("Component not found!")) from error
        else:
            try:
                result = self.components.get_by_path(component)
            except Component.DoesNotExist as error:
                raise ValidationError(gettext("Component not found!")) from error
        if (
            isinstance(self.obj, Component)
            and result.source_language != self.obj.source_language
        ):
            raise ValidationError(
                gettext(
                    "Source component needs to have same source language as target one."
                )
            )
        return result.pk


class CommentForm(forms.Form):
    """Simple commenting form."""

    scope = forms.ChoiceField(
        label=gettext_lazy("Scope"),
        help_text=gettext_lazy(
            "Is your comment specific to this translation, or generic for all of them?"
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
    comment = NormalizedNewlineCharField(
        widget=MarkdownTextarea,
        label=gettext_lazy("New comment"),
        help_text=gettext_lazy("You can use Markdown and mention users by @username."),
        max_length=1000,
    )

    def __init__(self, translation: Translation, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        remove: set[str] = set()
        # Remove bug-report in case source review is not enabled
        if not translation.component.project.source_review:
            remove.add("report")
        # Remove translation comment when commenting on source
        if translation.is_source:
            remove.add("translation")
        self.fields["scope"].choices = [
            choice for choice in self.fields["scope"].choices if choice[0] not in remove
        ]


class EngageForm(forms.Form):
    """Form to choose language for engagement widgets."""

    lang = LanguageCodeChoiceField(
        Language.objects.none(),
        empty_label=gettext_lazy("All languages"),
        required=False,
        to_field_name="code",
    )
    component = forms.ModelChoiceField(
        Component.objects.none(),
        required=False,
        empty_label=gettext_lazy("All components"),
    )

    def __init__(self, user: User, project, *args, **kwargs) -> None:
        """Dynamically generate choices for used languages in the project."""
        super().__init__(*args, **kwargs)

        self.fields["lang"].queryset = project.languages
        self.fields["component"].queryset = (
            project.component_set.filter_access(user).prefetch().order()
        )


class FullLanguageForm(forms.Form):
    """Form for requesting a new language."""

    lang = forms.MultipleChoiceField(
        label=gettext_lazy("Languages"), choices=[], widget=forms.SelectMultiple
    )
    obj: Category | Project

    def __init__(self, user: User, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.user = user
        languages = self.get_lang_objects()
        self.fields["lang"].choices = languages.as_choices(user=user)

    def get_lang_objects(self) -> QuerySet[Language]:
        raise NotImplementedError


class RestrictedLanguageForm(forms.Form):
    lang = forms.ChoiceField(
        label=gettext_lazy("Language"), choices=[], widget=forms.Select
    )
    obj: Category | Project

    def __init__(self, user: User, *args, **kwargs) -> None:
        super().__init__(user, *args, **kwargs)
        self.fields["lang"].choices = [
            ("", gettext("Please choose")),
            *self.fields["lang"].choices,
        ]

    def get_lang_objects(self) -> QuerySet[Language]:
        project = self.obj.project if isinstance(self.obj, Category) else self.obj
        return super().get_lang_objects().filter_for_add(project)

    def clean_lang(self):
        # Compatibility with NewLanguageOwnerForm
        return [self.cleaned_data["lang"]]


class NewComponentLanguageOwnerForm(FullLanguageForm):
    def get_lang_objects(self) -> QuerySet[Language]:
        return self.component.get_all_available_languages()

    def __init__(self, user: User, component: Component, *args, **kwargs) -> None:
        self.component = component
        self.obj = component.project
        super().__init__(user, *args, **kwargs)


class NewComponentLanguageForm(RestrictedLanguageForm, NewComponentLanguageOwnerForm):
    """Form for requesting a new language."""


class NewProjectOrCategoryLanguageOwnerForm(FullLanguageForm):
    """Form for adding a new language to all components in a project or a category."""

    def get_lang_objects(self) -> QuerySet[Language]:
        # Get all child components
        components = self.obj.components_user_can_add_new_language(self.user)
        components_count = components.count()

        # Count source and target languages
        source_languages = components.annotate(count=Count("id")).values_list(
            "source_language", "count"
        )
        target_languages = components.annotate(
            count=Count("translation__id")
        ).values_list("translation__language", "count")

        # Summarize language count
        language_counter: dict[int, int] = defaultdict(int)
        for language_id, count in chain(source_languages, target_languages):
            language_counter[language_id] += count

        languages_in_all_components = [
            language_id
            for language_id, count in language_counter.items()
            if count >= components_count
        ]

        # Exclude already existing languages from the list
        return Language.objects.exclude(id__in=languages_in_all_components)

    def __init__(self, user: User, obj: Category | Project, *args, **kwargs) -> None:
        self.obj = obj
        super().__init__(user, *args, **kwargs)


class NewProjectOrCategoryLanguageForm(
    RestrictedLanguageForm, NewProjectOrCategoryLanguageOwnerForm
):
    pass


def get_new_project_or_category_language_form(
    request: AuthenticatedHttpRequest, obj: Category | Project
) -> type[NewProjectOrCategoryLanguageForm | NewProjectOrCategoryLanguageOwnerForm]:
    if not request.user.has_perm("translation.add", obj):
        raise PermissionDenied
    if request.user.has_perm("translation.add_more", obj):
        return NewProjectOrCategoryLanguageOwnerForm
    return NewProjectOrCategoryLanguageForm


def get_new_component_language_form(
    request: AuthenticatedHttpRequest, component: Component
) -> type[NewComponentLanguageOwnerForm | NewComponentLanguageForm]:
    """Return new language form for user."""
    if not request.user.has_perm("translation.add", component):
        raise PermissionDenied
    if request.user.has_perm("translation.add_more", component):
        return NewComponentLanguageOwnerForm
    return NewComponentLanguageForm


class ContextForm(FieldDocsMixin, forms.ModelForm):
    class Meta:
        model = Unit
        fields = ("explanation", "labels", "extra_flags")
        # ruff: ignore[mutable-class-default]
        widgets = {
            "labels": forms.CheckboxSelectMultiple(),
            "explanation": MarkdownTextarea,
        }
        # ruff: ignore[mutable-class-default]
        field_classes = {
            "extra_flags": FlagField,
        }

    doc_links: ClassVar[dict[str, tuple[str, str]]] = {
        "explanation": ("admin/translating", "additional-explanation"),
        "labels": ("devel/translations", "labels"),
        "extra_flags": ("admin/translating", "additional-flags"),
    }

    def get_field_doc(self, field: forms.Field) -> tuple[str, str] | None:
        return self.doc_links[field.name]

    def __init__(self, data=None, instance=None, user=None, **kwargs) -> None:
        kwargs["initial"] = {"labels": list(instance.all_labels)}
        super().__init__(data=data, instance=instance, **kwargs)
        project = instance.translation.component.project
        self.fields["labels"].queryset = project.label_set.order()
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
        self.instance.update_extra_flags(
            self.cleaned_data["extra_flags"], self.user, save=False
        )
        if commit:
            self.instance.save(same_content=True)
            self.instance.save_labels(self.cleaned_data["labels"], self.user)
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


class TeamAssignableUserMixin:
    allow_bot_user = False

    def clean_user(self) -> User | None:
        user = self.cleaned_data["user"]
        if user is not None:
            validate_team_assignable_user(user, allow_bot=self.allow_bot_user)
        return user


class UserContributionCleanupForm(UserManageForm):
    revert_edits = forms.BooleanField(
        required=False,
        label=gettext_lazy("Revert user edits"),
        help_text=gettext_lazy(
            "Revert the latest translation edits from this user in the current project."
        ),
    )
    reject_suggestions = forms.BooleanField(
        required=False,
        label=gettext_lazy("Reject user suggestions"),
        help_text=gettext_lazy(
            "Reject all pending suggestions from this user in the current project."
        ),
    )
    delete_comments = forms.BooleanField(
        required=False,
        label=gettext_lazy("Delete user comments"),
        help_text=gettext_lazy(
            "Delete all comments from this user in the current project."
        ),
    )


class UserAddTeamForm(TeamAssignableUserMixin, UserManageForm):
    make_admin = forms.BooleanField(
        required=False,
        initial=False,
        label=gettext_lazy("Team administrator"),
        help_text=gettext_lazy("Allow user to add or remove users from a team."),
    )
    limit_languages = LimitLanguagesField(Language.objects.none())

    def __init__(self, *args, team: Group | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        limit_field = self.fields["limit_languages"]
        if team and team.defining_project_id:
            languages = team.defining_project.languages
        else:
            languages = Language.objects.order()
        limit_field.queryset = languages
        limit_field.choices = get_language_code_choices(languages)


class UserBlockForm(UserContributionCleanupForm):
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
    note = forms.CharField(
        required=False,
        widget=forms.Textarea,
        label=gettext_lazy("Block note"),
        help_text=gettext_lazy(
            "Internal notes regarding blocking the user that are not visible to the user."
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        if "auto_id" not in kwargs:
            kwargs["auto_id"] = "id_block_%s"
        super().__init__(*args, **kwargs)
        self.order_fields(
            [
                "user",
                "expiry",
                "note",
                "revert_edits",
                "reject_suggestions",
                "delete_comments",
            ]
        )


class ReportsForm(forms.Form):
    layout_fields: ClassVar[tuple[str, ...]] = (
        "style",
        "period",
        "language",
        "sort_by",
        "sort_order",
    )

    style = forms.ChoiceField(
        label=gettext_lazy("Report format"),
        help_text=gettext_lazy("Choose a file format for the report"),
        choices=(
            ("rst", gettext_lazy("reStructuredText")),
            ("json", gettext_lazy("JSON")),
            ("html", gettext_lazy("HTML")),
        ),
    )
    period = DateRangeField(
        label=gettext_lazy("Report period"),
        required=True,
    )
    language = forms.ChoiceField(
        label=gettext_lazy("Language"),
        choices=[("", gettext_lazy("All languages"))],
        required=False,
    )
    sort_by = forms.ChoiceField(
        label=gettext_lazy("Sort by"),
        choices=[
            ("count", gettext_lazy("Strings translated")),
            ("date_joined", gettext_lazy("Date joined")),
        ],
        required=False,
    )
    sort_order = forms.ChoiceField(
        label=gettext_lazy("Sort order"),
        choices=[
            ("descending", gettext_lazy("Descending")),
            ("ascending", gettext_lazy("Ascending")),
        ],
    )

    def __init__(self, scope: dict[str, Model], *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(*(Field(field) for field in self.layout_fields))
        self.fields["language"].choices = get_report_language_choices(scope)


def get_report_language_choices(scope: dict[str, Model]):
    if not scope:
        languages = Language.objects.have_translation()
    elif "project" in scope:
        languages = Language.objects.filter(
            translation__component__project=scope["project"]
        ).distinct()
    elif "category" in scope:
        languages = Language.objects.filter(
            translation__component_id__in=scope["category"].all_component_ids
        ).distinct()
    elif "component" in scope:
        languages = Language.objects.filter(
            translation__component=scope["component"]
        ).exclude(pk=scope["component"].source_language_id)
    else:
        msg = f"Invalid scope: {scope}"
        raise ValueError(msg)
    return [("", gettext_lazy("All languages")), *languages.as_choices()]


class CountsReportsForm(ReportsForm):
    COUNTING_MODE_UNIQUE = "unique"
    COUNTING_MODE_ALL = "all"
    layout_fields = (*ReportsForm.layout_fields, "counting_mode")

    counting_mode = forms.ChoiceField(
        label=gettext_lazy("Counting mode"),
        help_text=gettext_lazy(
            "Choose whether repeated changes on the same string are counted once or "
            "as separate changes."
        ),
        choices=[
            (
                COUNTING_MODE_UNIQUE,
                gettext_lazy("Unique strings"),
            ),
            (
                COUNTING_MODE_ALL,
                gettext_lazy("All changes"),
            ),
        ],
        initial=COUNTING_MODE_UNIQUE,
        required=False,
    )


class CostEstimateReportsForm(forms.Form):
    layout_fields: ClassVar[tuple[str, ...]] = (
        "style",
        "language",
        "q",
        "base_rate",
        "tm_threshold",
        "rate_new",
        "rate_needs_editing",
        "rate_tm_100",
        "rate_tm_fuzzy",
        "rate_repetition",
    )

    style = forms.ChoiceField(
        label=gettext_lazy("Report format"),
        help_text=gettext_lazy("Choose a file format for the report"),
        choices=(
            ("rst", gettext_lazy("reStructuredText")),
            ("json", gettext_lazy("JSON")),
            ("html", gettext_lazy("HTML")),
        ),
    )
    language = forms.ChoiceField(
        label=gettext_lazy("Language"),
        choices=[("", gettext_lazy("All languages"))],
        required=False,
    )
    q = QueryField(
        required=True,
        initial="state:<translated",
        label=gettext_lazy("Search filter"),
    )
    base_rate = forms.DecimalField(
        label=gettext_lazy("Base rate"),
        help_text=gettext_lazy("Price per source word."),
        initial=1,
        min_value=0,
        max_digits=12,
        decimal_places=4,
    )
    tm_threshold = forms.IntegerField(
        label=gettext_lazy("Translation memory threshold"),
        initial=MACHINERY_DEFAULT_THRESHOLD,
        min_value=MIN_COST_ESTIMATE_TM_THRESHOLD,
        max_value=100,
    )
    rate_new = forms.DecimalField(
        label=gettext_lazy("New strings rate"),
        initial=100,
        min_value=0,
        max_digits=6,
        decimal_places=2,
    )
    rate_needs_editing = forms.DecimalField(
        label=gettext_lazy("Needs editing rate"),
        initial=50,
        min_value=0,
        max_digits=6,
        decimal_places=2,
    )
    rate_tm_100 = forms.DecimalField(
        label=gettext_lazy("Exact match rate"),
        initial=0,
        min_value=0,
        max_digits=6,
        decimal_places=2,
    )
    rate_tm_fuzzy = forms.DecimalField(
        label=gettext_lazy("Fuzzy match rate"),
        initial=50,
        min_value=0,
        max_digits=6,
        decimal_places=2,
    )
    rate_repetition = forms.DecimalField(
        label=gettext_lazy("Repetition rate"),
        initial=0,
        min_value=0,
        max_digits=6,
        decimal_places=2,
    )

    def __init__(self, scope: dict[str, Model], *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(*(Field(field) for field in self.layout_fields))
        self.fields["language"].choices = get_report_language_choices(scope)


class CleanRepoMixin:
    def clean_repo(self):
        repo = self.cleaned_data.get("repo")
        if not repo or not is_repo_link(repo) or "/" not in repo[10:]:
            return repo
        try:
            obj = Component.objects.get_linked(repo)
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
        # ruff: ignore[mutable-class-default]
        fields = []

    def __init__(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.request = request
        self.helper = FormHelper()
        self.helper.form_tag = False


InheritedSettingsScope = Literal["workspace", "project", "category"]


def get_inherited_settings_label(parent_scope: InheritedSettingsScope) -> str:
    if parent_scope == "workspace":
        return gettext("Inherit from workspace")
    if parent_scope == "project":
        return gettext("Inherit from project")
    return gettext("Inherit from category")


class InheritedSettingsFormMixin(forms.ModelForm):
    _inherited_setting_fields: set[str]
    _inherited_setting_restore_values: dict[str, Any]

    def is_inheritance_enabled(self, inherit_field: str) -> bool:
        if not self.is_bound:
            return bool(getattr(self.instance, inherit_field, False))
        field = self.fields[inherit_field]
        value = field.widget.value_from_datadict(
            self.data, self.files, self.add_prefix(inherit_field)
        )
        return bool(field.clean(value))

    def get_inherited_setting_value(self, field_name: str) -> str | Language | None:
        instance = self.instance
        if isinstance(instance, Project) and instance.workspace_id is not None:
            return getattr(instance.workspace, field_name)
        if isinstance(instance, Category):
            return instance.settings_parent.get_effective_setting(field_name)
        if isinstance(instance, Component):
            if instance.category_id is not None:
                return instance.category.get_effective_setting(field_name)
            return instance.project.get_effective_setting(field_name)
        return instance.get_effective_setting(field_name)

    def setup_inherited_setting_values(self, field_name: str) -> None:
        field = self.fields[field_name]
        inherited_value = self.get_inherited_setting_value(field_name)
        override_value = getattr(self.instance, field_name)
        inherited_value = field.prepare_value(inherited_value)
        override_value = field.prepare_value(override_value)
        field.widget.attrs["data-inherited-value"] = (
            "" if inherited_value is None else inherited_value
        )
        field.widget.attrs["data-override-value"] = (
            "" if override_value is None else override_value
        )

    def setup_inherited_settings(
        self, parent_scope: InheritedSettingsScope, *, has_parent: bool
    ) -> None:
        setup_message_setting_site_defaults(self.fields)
        self._inherited_setting_fields = set()
        for field_name in INHERITABLE_COMPONENT_SETTINGS:
            inherit_field = get_inherit_field_name(field_name)
            if inherit_field not in self.fields:
                continue
            self.fields[inherit_field].label = get_inherited_settings_label(
                parent_scope
            )
            if not has_parent:
                self.fields[inherit_field].initial = False
                self.fields[inherit_field].widget = forms.HiddenInput()
                continue
            if field_name in self.fields:
                self._inherited_setting_fields.add(field_name)
                self.setup_inherited_setting_values(field_name)
            if not self.is_inheritance_enabled(inherit_field):
                continue
            if field_name in self.fields:
                field = self.fields[field_name]
                effective_value = self.get_inherited_setting_value(field_name)
                self.initial[field_name] = effective_value
                field.initial = effective_value
                field.disabled = True
                note = gettext(
                    "Inherited value is shown. Disable inheritance to edit the stored override."
                )
                field.help_text = (
                    format_html("{} {}", field.help_text, note)
                    if field.help_text
                    else note
                )

    def preserve_inherited_values(self) -> None:
        self._inherited_setting_restore_values = {}
        for field_name in self._inherited_setting_fields:
            if (
                self.cleaned_data.get(get_inherit_field_name(field_name))
                and field_name in self.cleaned_data
            ):
                stored_value = getattr(self.instance, field_name)
                validate_with_effective_value = (
                    field_name == "license"
                    and self.fields[field_name].required
                    and not stored_value
                )
                if validate_with_effective_value:
                    self._inherited_setting_restore_values[field_name] = stored_value
                else:
                    self.cleaned_data[field_name] = stored_value

    def restore_inherited_values(self) -> None:
        for field_name, value in getattr(
            self, "_inherited_setting_restore_values", {}
        ).items():
            setattr(self.instance, field_name, value)

    def _post_clean(self) -> None:
        try:
            super()._post_clean()
        finally:
            self.restore_inherited_values()


def setup_message_setting_site_defaults(fields: dict[str, forms.Field]) -> None:
    for field_name in COMPONENT_MESSAGE_SETTINGS:
        if field_name not in fields:
            continue
        setting_name = f"DEFAULT_{field_name.upper()}"
        field = cast("SiteDefaultField", fields[field_name])
        field.site_default = True
        field.widget.attrs["data-site-default-value"] = getattr(settings, setting_name)


class SelectChecksWidget(SortedSelectMultiple):
    def __init__(self, attrs=None, choices=()) -> None:
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


class FormParamsWidget(forms.MultiWidget):
    template_name = "bootstrap5/labelled_multiwidget.html"
    subwidget_class = "file-format-param"

    def __init__(
        self,
        widgets: dict[str, forms.Widget],
        fields_order: list[tuple[str, str]],
        attrs=None,
    ) -> None:
        self.fields_order = fields_order
        super().__init__(widgets, attrs)

    def decompress(self, value: dict) -> list[Any]:
        initial_params: dict[str, Any] = {}
        for param_class in FILE_FORMATS_PARAMS:
            param = param_class()
            initial_params[param.get_identifier()] = param.get_field_kwargs().get(
                "initial"
            )
        value = {**initial_params, **(value or {})}
        return [value.get(param_name) for param_name in self.fields_order]

    def get_context(self, *args, **kwargs) -> dict[str, Any]:
        # Crispy injects `form-control` class to all subwidgets, which can conflict
        # with some of our widgets, so we need to remove it from checkboxes and selects
        for widget in self.widgets:
            classes = widget.attrs.get("class", "").split()
            if "form-control" in classes and (
                "form-check-input" in classes or "form-select" in classes
            ):
                widget.attrs["class"] = " ".join(
                    c for c in classes if c != "form-control"
                )
        context = super().get_context(*args, **kwargs)
        context["subwidget_class"] = self.subwidget_class
        return context


class FormParamsField(forms.MultiValueField):
    def __init__(self, encoder=None, decoder=None, **kwargs) -> None:
        fields = []
        subwidgets = {}

        self.fields_order: list[tuple] = []
        for file_param in FILE_FORMATS_PARAMS:
            field = file_param().get_field()
            fields.append(field)
            subwidgets[file_param.get_identifier()] = field.widget
            self.fields_order.append(file_param.get_identifier())

        widget = FormParamsWidget(subwidgets, self.fields_order)
        super().__init__(fields, widget=widget, require_all_fields=False, **kwargs)

    def compress(self, data_list) -> dict:
        compressed_value: dict[str, Any] = {}
        if data_list:
            update_data = {
                param_name: value
                for param_name, value in zip(self.fields_order, data_list, strict=False)
                if value is not None
            }
            compressed_value.update(update_data)
        return compressed_value


class ComponentDocsMixin(FieldDocsMixin):
    def get_field_doc(self, field: forms.Field) -> tuple[str, str] | None:
        if field.name in INHERITABLE_COMPONENT_FLAGS:
            return ("admin/workspaces", "workspace-inherited-settings")
        return ("admin/projects", f"component-{field.name.replace('_', '-')}")


class CategoryDocsMixin(FieldDocsMixin):
    def get_field_doc(self, field: forms.Field) -> tuple[str, str] | None:
        if field.name in INHERITABLE_COMPONENT_FLAGS:
            return ("admin/workspaces", "workspace-inherited-settings")
        return ("admin/projects", "category-settings")


class ProjectDocsMixin(FieldDocsMixin):
    def get_field_doc(self, field: forms.Field) -> tuple[str, str] | None:
        if field.name in INHERITABLE_COMPONENT_FLAGS:
            return ("admin/workspaces", "workspace-inherited-settings")
        return ("admin/projects", f"project-{field.name.replace('_', '-')}")


class SpamCheckMixin(forms.Form):
    spam_fields: ClassVar[tuple[str, ...]]

    def clean(self) -> None:
        data = self.cleaned_data
        check_values: list[str] = [
            data[field] for field in self.spam_fields if field in data
        ]
        if is_spam(self.request, check_values):
            raise ValidationError(
                gettext("This submission has been identified as spam!")
            )


class ComponentAntispamMixin(SpamCheckMixin):
    spam_fields = ("agreement",)


class CategoryAntispamMixin(SpamCheckMixin):
    spam_fields = ("agreement",)


class ProjectAntispamMixin(SpamCheckMixin):
    spam_fields = ("web", "instructions")


def get_vcs_push_categories() -> str:
    """Return JSON mapping of VCS identifier to push behavior category."""
    categories: dict[str, str] = {}
    for identifier, cls in VCS_REGISTRY.items():
        if issubclass(cls, GitMergeRequestBase):
            categories[identifier] = "merge_request"
        elif cls.pushes_to_different_location:
            categories[identifier] = "gerrit"
        else:
            categories[identifier] = "direct"
    return json.dumps(categories)


class ComponentSettingsForm(
    InheritedSettingsFormMixin,
    SettingsBaseForm,
    ComponentDocsMixin,
    ComponentAntispamMixin,
):
    """Component settings form."""

    class Meta:
        model = Component
        fields = (
            "name",
            "report_source_bugs",
            "inherit_license",
            "license",
            "inherit_agreement",
            "agreement",
            "hide_glossary_matches",
            "allow_translation_propagation",
            "contribute_project_tm",
            "enable_suggestions",
            "suggestion_voting",
            "suggestion_autoaccept",
            "priority",
            "check_flags",
            "enforced_checks",
            "inherit_commit_message",
            "commit_message",
            "inherit_add_message",
            "add_message",
            "inherit_delete_message",
            "delete_message",
            "inherit_merge_message",
            "merge_message",
            "inherit_addon_message",
            "addon_message",
            "inherit_pull_message",
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
            "file_format_params",
            "edit_template",
            "inherit_new_lang",
            "new_lang",
            "inherit_language_code_style",
            "language_code_style",
            "source_language",
            "new_base",
            "filemask",
            "screenshot_filemask",
            "template",
            "intermediate",
            "language_regex",
            "key_filter",
            "inherit_secondary_language",
            "secondary_language",
            "variant_regex",
            "restricted",
            "auto_lock_error",
            "manage_units",
            "is_glossary",
            "glossary_color",
        )
        # ruff: ignore[mutable-class-default]
        widgets = {
            "enforced_checks": SelectChecksWidget,
            "source_language": SortedSelect,
            "secondary_language": SortedSelect,
            "language_code_style": SortedSelect,
            "license": SearchableSelect,
        }
        # ruff: ignore[mutable-class-default]
        field_classes = {
            "enforced_checks": SelectChecksField,
            "file_format_params": FormParamsField,
            "check_flags": FlagField,
        }

    def __init__(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:
        super().__init__(request, *args, **kwargs)
        parent_scope: InheritedSettingsScope = (
            "category" if self.instance.category_id else "project"
        )
        self.setup_inherited_settings(parent_scope, has_parent=True)
        if self.hide_restricted:
            self.fields["restricted"].widget = forms.HiddenInput()
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    gettext("Basic"),
                    Fieldset(
                        gettext("Name"),
                        "name",
                        ContextDiv(
                            template="snippets/settings-organize.html",
                            context={
                                "object": self.instance,
                                "type": "component",
                            },
                        ),
                    ),
                    Fieldset(
                        gettext("License"),
                        InheritedSetting("license"),
                        InheritedSetting("agreement"),
                    ),
                    Fieldset(gettext("Upstream links"), "report_source_bugs"),
                    Fieldset(
                        gettext("Listing and access"),
                        "priority",
                        "restricted",
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
                        "hide_glossary_matches",
                        "allow_translation_propagation",
                        "contribute_project_tm",
                        "manage_units",
                        "check_flags",
                        "variant_regex",
                        "enforced_checks",
                        InheritedSetting("secondary_language"),
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
                        ContextDiv(
                            template="trans/vcs_push_help.html",
                            context={"vcs_push_categories": get_vcs_push_categories()},
                        ),
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
                    ContextDiv(
                        template="trans/messages_help.html",
                        context={"user": request.user},
                    ),
                    InheritedSetting("commit_message"),
                    InheritedSetting("add_message"),
                    InheritedSetting("delete_message"),
                    InheritedSetting("merge_message"),
                    InheritedSetting("addon_message"),
                    InheritedSetting("pull_message"),
                    css_id="messages",
                ),
                Tab(
                    gettext("Files"),
                    Fieldset(
                        gettext("Translation files"),
                        "file_format",
                        "filemask",
                        "language_regex",
                        "key_filter",
                        "source_language",
                        "file_format_params",
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
                        InheritedSetting("new_lang"),
                        InheritedSetting("language_code_style"),
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
        vcses: set[str] = {
            identifier
            for identifier in VCS_REGISTRY.git_based
            if VCS_REGISTRY[identifier].manual_component_creation
            or identifier == self.instance.vcs
        }
        if self.instance.vcs not in VCS_REGISTRY.git_based:
            vcses = {self.instance.vcs}
        self.fields["vcs"].choices = [
            c for c in self.fields["vcs"].choices if c[0] in vcses
        ]
        vcs_backend = VCS_REGISTRY.get(self.instance.vcs)
        if vcs_backend is not None and vcs_backend.component_lock_fields:
            # Integration-backed repository settings are managed by the
            # provider import flow; editing them would break authentication.
            for locked_field in vcs_backend.component_lock_fields:
                if locked_field in self.fields:
                    self.fields[locked_field].disabled = True
            for cleared_field in vcs_backend.component_clear_fields:
                if cleared_field in self.fields:
                    self.initial[cleared_field] = ""
                    self.fields[cleared_field].initial = ""
        self.patch_unlinking_linked_repository_settings()
        self.patch_linked_repository_settings()

    def get_linked_repository_component(self) -> Component | None:
        repo = self.data.get("repo") if self.is_bound else self.instance.repo
        if not repo:
            return None
        try:
            return Component.objects.get_linked(repo)
        except (Component.DoesNotExist, ValueError):
            return None

    def patch_unlinking_linked_repository_settings(self) -> None:
        if not self.is_bound or not self.instance.is_repo_link:
            return

        repo = self.data.get("repo") or ""
        if is_repo_link(repo):
            return

        data = copy.copy(self.data)
        for field_name in Component.LINKED_REPOSITORY_SETTINGS:
            if field_name not in data:
                data[field_name] = self.fields[field_name].prepare_value(
                    getattr(self.instance, field_name)
                )
        self.data = data

    def patch_linked_repository_settings(self) -> None:
        linked_component = self.get_linked_repository_component()
        if linked_component is None:
            return

        inherited_note = Component.LINKED_REPOSITORY_SETTING_MESSAGE
        for field_name in Component.LINKED_REPOSITORY_SETTINGS:
            field = self.fields[field_name]
            effective_value = getattr(linked_component, field_name)
            self.initial[field_name] = effective_value
            field.initial = effective_value
            field.disabled = True
            if field.help_text:
                field.help_text = format_html("{} {}", field.help_text, inherited_note)
            else:
                field.help_text = inherited_note

    @property
    def hide_restricted(self) -> bool:
        user = self.request.user
        if user.is_superuser:
            return False
        if settings.OFFER_HOSTING:
            return True
        return not any(
            "component.edit" in permissions
            for permissions, _langs in user.component_permissions[self.instance.pk]
        )

    def clean(self) -> None:
        super().clean()
        data = self.cleaned_data
        if self.hide_restricted:
            data["restricted"] = self.instance.restricted
        clean_integration_component_data(self, data, vcs=self.instance.vcs)

        repo = data.get("repo") or ""
        if is_repo_link(repo):
            for field_name in Component.LINKED_REPOSITORY_SETTINGS:
                data[field_name] = getattr(self.instance, field_name)

        if "file_format_params" in data:
            data["file_format_params"] = strip_unused_file_format_params(
                data["file_format"], data["file_format_params"]
            )
        self.preserve_inherited_values()


class ComponentCreateForm(
    InheritedSettingsFormMixin,
    SettingsBaseForm,
    ComponentDocsMixin,
    ComponentAntispamMixin,
):
    """Component creation form."""

    CREATE_INHERITABLE_SETTINGS: ClassVar[tuple[str, ...]] = (
        "license",
        "new_lang",
        "language_code_style",
    )

    detected_license = forms.CharField(required=False, widget=forms.HiddenInput)
    source_component = forms.ModelChoiceField(
        queryset=Component.objects.none(),
        required=False,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = Component
        # ruff: ignore[mutable-class-default]
        fields = [
            "project",
            "category",
            "name",
            "slug",
            "vcs",
            "repo",
            "branch",
            "push",
            "push_branch",
            "repoweb",
            "file_format",
            "file_format_params",
            "filemask",
            "template",
            "edit_template",
            "intermediate",
            "inherit_new_lang",
            "new_lang",
            "new_base",
            "inherit_license",
            "license",
            "inherit_language_code_style",
            "language_code_style",
            "language_regex",
            "key_filter",
            "source_language",
            "is_glossary",
        ]
        # ruff: ignore[mutable-class-default]
        widgets = {
            "source_language": SortedSelect,
            "language_code_style": SortedSelect,
            "license": SearchableSelect,
        }
        # ruff: ignore[mutable-class-default]
        field_classes = {
            "file_format_params": FormParamsField,
        }

    def __init__(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:
        source_component = None
        if (
            source_component_text := request.GET.get("source_component")
        ) and "file_format" in kwargs["initial"]:
            try:
                source_component_id = int(source_component_text)
            except (TypeError, ValueError):
                source_component_id = None
            if source_component_id is not None:
                source_component = (
                    Component.objects.filter_access(request.user)
                    .filter(pk=source_component_id)
                    .first()
                )
        if (
            source_component is not None
            and "file_format" in kwargs["initial"]
            and source_component.file_format_params
        ):
            supported_params = {
                param.get_identifier()
                for param in get_params_for_file_format(
                    kwargs["initial"]["file_format"]
                )
            }
            source_file_format_params = {
                k: v
                for k, v in source_component.file_format_params.items()
                if k in supported_params
            }
            initial_file_format_params = kwargs["initial"].get("file_format_params", {})
            if not isinstance(initial_file_format_params, dict):
                initial_file_format_params = {}
            kwargs["initial"]["file_format_params"] = {
                **source_file_format_params,
                **initial_file_format_params,
            }
        super().__init__(request, *args, **kwargs)
        self.setup_create_inherited_settings()
        self.helper.layout = Layout(
            "project",
            "category",
            "name",
            "slug",
            "vcs",
            "repo",
            "branch",
            "push",
            "push_branch",
            ContextDiv(
                template="trans/vcs_push_help.html",
                context={"vcs_push_categories": get_vcs_push_categories()},
            ),
            "repoweb",
            "file_format",
            "file_format_params",
            "filemask",
            "template",
            "edit_template",
            "intermediate",
            InheritedSetting("new_lang"),
            "new_base",
            InheritedSetting("license"),
            InheritedSetting("language_code_style"),
            "language_regex",
            "key_filter",
            "source_language",
            "is_glossary",
            "detected_license",
            "source_component",
        )

    def get_selected_parent(self) -> Project | Category | None:
        category = self.get_selected_model("category", Category)
        if category is not None:
            return category
        return self.get_selected_model("project", Project)

    def get_selected_model(self, field_name: str, model: type[Project | Category]):
        if self.is_bound:
            value = self.data.get(self.add_prefix(field_name))
        else:
            value = self.initial.get(field_name)
        if isinstance(value, model):
            return value
        if value in {None, ""}:
            return None
        try:
            return model.objects.get(pk=value)
        except (TypeError, ValueError, model.DoesNotExist):
            return None

    def setup_create_inherited_settings(self) -> None:
        parent = self.get_selected_parent()
        parent_scope: InheritedSettingsScope
        if isinstance(parent, Category):
            self.instance.category = parent
            self.instance.project = parent.project
            parent_scope = "category"
        elif isinstance(parent, Project):
            self.instance.project = parent
            parent_scope = "project"
        else:
            parent_scope = "project"

        for field_name in self.CREATE_INHERITABLE_SETTINGS:
            if field_name in self.initial:
                setattr(self.instance, field_name, self.initial[field_name])
            inherit_field = get_inherit_field_name(field_name)
            if inherit_field not in self.fields:
                continue
            if inherit_field in self.initial:
                setattr(
                    self.instance,
                    inherit_field,
                    self.fields[inherit_field].clean(self.initial[inherit_field]),
                )

        detected_license = self.initial.get("detected_license")
        if detected_license and detected_license == self.initial.get("license"):
            inherit_license = detected_license == self.get_inherited_setting_value(
                "license"
            )
            self.initial["inherit_license"] = inherit_license
            self.instance.inherit_license = inherit_license
        elif (
            not self.is_bound
            and "inherit_license" not in self.initial
            and not self.get_inherited_setting_value("license")
        ):
            self.initial["inherit_license"] = False
            self.instance.inherit_license = False

        self.setup_inherited_settings(parent_scope, has_parent=parent is not None)

    def disables_inheritance_for_explicit_setting(self, field: str) -> bool:
        inherit_field = get_inherit_field_name(field)
        if self.cleaned_data.get(inherit_field):
            return False
        if inherit_field in self.cleaned_data:
            return True
        if self.is_bound and self.add_prefix(field) in self.data:
            return True
        if field in self.changed_data:
            return True
        return field == "license" and self.cleaned_data.get(
            "detected_license"
        ) == self.cleaned_data.get("license")

    def clean(self) -> None:
        super().clean()
        data = self.cleaned_data
        clean_integration_component_data(self, data)

        if "file_format_params" in data:
            data["file_format_params"] = strip_unused_file_format_params(
                data["file_format"], data["file_format_params"]
            )
        self.preserve_inherited_values()
        for field in ("license", "new_lang", "language_code_style"):
            if self.disables_inheritance_for_explicit_setting(field):
                setattr(self.instance, get_inherit_field_name(field), False)


class ComponentNameForm(ComponentDocsMixin, ComponentAntispamMixin):
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

    def __init__(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:
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

    def __init__(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:
        if "instance" in kwargs:
            kwargs.pop("instance")
        if "auto_id" not in kwargs:
            kwargs["auto_id"] = "id_existing_%s"
        super().__init__(request, *args, **kwargs)


class ComponentBranchForm(ComponentSelectForm):
    branch = forms.ChoiceField(label=gettext_lazy("Repository branch"))

    instance = None

    def __init__(self, *args, **kwargs) -> None:
        kwargs["auto_id"] = "id_branch_%s"
        super().__init__(*args, **kwargs)
        self.branch_data: dict[int, list[str]] = {}

    def clean_component(self):
        component = self.cleaned_data["component"]
        self.fields["branch"].choices = [(x, x) for x in self.branch_data[component.pk]]
        return component

    def clean(self) -> None:
        form_fields = ("branch", "slug", "name")
        data = self.cleaned_data
        component = data.get("component")
        if not component or any(field not in data for field in form_fields):
            return
        kwargs = model_to_dict(component, exclude=["id", "links"])
        # We need an object, not integer here
        kwargs["source_language"] = component.source_language
        kwargs["project"] = component.project
        kwargs["category"] = component.category
        for field in form_fields:
            kwargs[field] = data[field]
        self.instance = Component(**kwargs)
        try:
            self.instance.full_clean()
        except ValidationError as error:
            # Can not raise directly, as this will contain errors
            # from fields not present here
            result: dict[str, list[str]] = {NON_FIELD_ERRORS: []}
            for key, value in error.message_dict.items():
                if key in self.fields:
                    result[key] = value
                else:
                    result[NON_FIELD_ERRORS].extend(value)
            raise ValidationError(error.messages) from error


class ComponentProjectForm(ComponentNameForm):
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(), label=gettext_lazy("Project")
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        label=gettext_lazy("Category"),
        widget=forms.HiddenInput,
        blank=True,
        required=False,
    )
    source_language = forms.ModelChoiceField(
        widget=SortedSelect,
        label=Component.source_language.field.verbose_name,
        help_text=Component.source_language.field.help_text,
        queryset=Language.objects.all(),
    )
    instance: Project

    def __init__(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:
        if "instance" in kwargs:
            kwargs.pop("instance")
        super().__init__(request, *args, **kwargs)
        # It might be overridden based on preset project
        self.fields["source_language"].initial = Language.objects.default_language
        self.request = request
        self.helper = FormHelper()
        self.helper.form_tag = False

    def clean(self) -> None:
        if "project" not in self.cleaned_data:
            return

        project = self.cleaned_data["project"]
        name = self.cleaned_data.get("name", "")
        slug = self.cleaned_data.get("slug", "")
        category = self.cleaned_data.get("category")

        fake = Component(project=project, category=category, name=name, slug=slug)
        fake.clean_unique_together()
        # Check if category is from this project
        fake.clean_category()


class ComponentScratchCreateForm(ComponentProjectForm):
    file_format = forms.ChoiceField(
        label=gettext_lazy("File format"),
        initial="po-mono",
        choices=FILE_FORMATS.get_choices(
            cond=lambda x: (
                bool(x.empty_file_template) or issubclass(x, BilingualUpdateMixin)
            )
        ),
    )
    file_format_params = FormParamsField()

    def __init__(self, *args, **kwargs) -> None:
        kwargs["auto_id"] = "id_scratchcreate_%s"
        super().__init__(*args, **kwargs)


class ComponentZipCreateForm(ComponentProjectForm):
    zipfile = forms.FileField(
        label=gettext_lazy("ZIP file containing translations"),
        validators=[
            validate_component_zip_upload_size,
            FileExtensionValidator(allowed_extensions=["zip"]),
        ],
        widget=forms.FileInput(attrs={"accept": ".zip,application/zip"}),
    )

    # ruff: ignore[mutable-class-default]
    field_order = [
        "zipfile",
        "project",
        "name",
        "slug",
    ]

    def __init__(self, *args, **kwargs) -> None:
        kwargs["auto_id"] = "id_zipcreate_%s"
        super().__init__(*args, **kwargs)


class ComponentDocCreateForm(ComponentProjectForm):
    docfile = forms.FileField(
        label=gettext_lazy("Document to translate"),
        validators=[validate_translation_upload_size, validate_file_extension],
    )

    target_language = forms.ModelChoiceField(
        widget=SortedSelect,
        label=gettext_lazy("Target language"),
        help_text=gettext_lazy("Target language of the document for bilingual files"),
        queryset=Language.objects.all(),
        required=False,
    )
    # ruff: ignore[mutable-class-default]
    field_order = [
        "docfile",
        "project",
        "name",
        "slug",
    ]

    def __init__(self, *args, **kwargs) -> None:
        kwargs["auto_id"] = "id_doccreate_%s"
        super().__init__(*args, **kwargs)


class ComponentInitCreateForm(CleanRepoMixin, ComponentProjectForm):
    """Component creation form."""

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
    instance: Component  # type: ignore[assignment]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Integration-backed backends are selected by provider import flows,
        # not manually from the generic VCS chooser.
        self.fields["vcs"].choices = [
            choice
            for choice in self.fields["vcs"].choices
            if VCS_REGISTRY[choice[0]].manual_component_creation
        ]

    def clean_instance(self, data) -> None:
        params = copy.copy(data)
        for field in ("detected_license", "discovery", "source_component"):
            params.pop(field, None)

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
        instance.clean_unique_together()
        instance.clean_repo()
        instance.clean_category()
        self.instance = instance

        # Create linked repos automatically
        repo = instance.suggest_repo_link()
        if repo:
            data["repo"] = repo
            data["branch"] = ""
            self.clean_instance(data)

    def clean(self) -> None:
        if not clean_integration_component_data(self, self.cleaned_data):
            return
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

    def render_choice(self, value: DiscoveryResult) -> str:
        context = cast("dict[str, str]", value.data.copy())
        try:
            format_cls = FILE_FORMATS[value["file_format"]]
            context["file_format_name"] = format_cls.name
            context["valid"] = True
        except KeyError:
            context["file_format_name"] = value["file_format"]
            context["valid"] = False
        context["origin"] = value.meta["origin"]
        return render_to_string("trans/discover-choice.html", context)

    def __init__(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:
        super().__init__(request, *args, **kwargs)
        # Hide all fields with exception of discovery
        for field, value in self.fields.items():
            if field == "discovery":
                continue
            value.widget = forms.HiddenInput()
        # Allow all VCS now (to handle zip file upload case)
        self.fields["vcs"].choices = VCS_REGISTRY.get_choices()
        self.discovered = self.perform_discovery(request, kwargs)
        # Can not use .extend here as it does not update widget
        self.fields["discovery"].choices += [
            (i, self.render_choice(value)) for i, value in enumerate(self.discovered)
        ]

    def perform_discovery(self, request: AuthenticatedHttpRequest, kwargs):
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
        request.session["create_discovery"] = [x.data for x in discovered]
        request.session["create_discovery_meta"] = [x.meta for x in discovered]
        return discovered

    def discover(self, eager: bool = False):
        return discover(
            self.instance.full_path,
            source_language=self.instance.source_language.code,
            eager=eager,
            hint=self.instance.filemask,
        )

    @staticmethod
    def get_discovery_data(value: DiscoveryResult) -> dict[str, Any]:
        data = cast("dict[str, Any]", value.match)
        file_format = data.get("file_format")
        file_format_params = data.get("file_format_params")
        if file_format_params is None:
            return data
        if not isinstance(file_format, str) or not isinstance(file_format_params, dict):
            data.pop("file_format_params", None)
            return data
        data["file_format_params"] = strip_unused_file_format_params(
            file_format,
            cast("FileFormatParams", file_format_params.copy()),
        )
        return data

    def clean(self) -> None:
        super().clean()
        discovery = self.cleaned_data.get("discovery")
        if discovery and discovery != "manual":
            self.cleaned_data.update(
                self.get_discovery_data(self.discovered[int(discovery)])
            )


class ComponentRenameForm(SettingsBaseForm, ComponentDocsMixin):
    """Component rename form."""

    class Meta:
        model = Component
        # ruff: ignore[mutable-class-default]
        fields = ["name", "slug", "project", "category"]

    def __init__(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:
        super().__init__(request, *args, **kwargs)
        self.fields["project"].queryset = request.user.managed_projects
        self.fields["category"].queryset = self.instance.project.category_set.all()


class ComponentLinkAddForm(forms.Form):
    """Form for sharing a component into a project with an optional category."""

    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        widget=SortedSelect,
        label=gettext_lazy("Project"),
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        required=False,
        empty_label="---------",
        widget=SortedSelect,
        label=gettext_lazy("Category"),
    )

    def __init__(self, *args, request=None, component=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        if request and component:
            managed = request.user.managed_projects.exclude(pk=component.project_id)
            self.fields["project"].queryset = managed
            self.fields["category"].queryset = Category.objects.filter(
                project__in=managed
            ).order()
            # Build project -> categories map for dynamic JS filtering
            categories = Category.objects.filter(project__in=managed).select_related(
                "category", "project"
            )
            mapping: dict[int, list[dict]] = defaultdict(list)
            for cat in categories:
                mapping[cat.project_id].append({"id": cat.id, "name": str(cat)})
            prefix = kwargs.get("prefix", "")
            target_id = f"#id_{prefix}-category" if prefix else "#id_category"
            self.fields["project"].widget.attrs["data-link-category-select"] = target_id
            self.fields["project"].widget.attrs["data-link-category-map"] = json.dumps(
                mapping
            )

    def clean(self):
        cleaned_data = super().clean()
        project = cleaned_data.get("project")
        category = cleaned_data.get("category")
        if project and category and category.project != project:
            self.add_error(
                "category",
                gettext("The category does not belong to the selected project."),
            )
        return cleaned_data


class ComponentLinkCategoryForm(forms.Form):
    """Form for updating the category of an existing component link."""

    link_id = forms.IntegerField(widget=forms.HiddenInput)
    category = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        required=False,
        empty_label="---------",
        widget=SortedSelect(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, project=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if project:
            self.fields["category"].queryset = Category.objects.filter(
                project=project
            ).order()


class CategoryRenameForm(SettingsBaseForm):
    """Category rename form."""

    class Meta:
        model = Category
        # ruff: ignore[mutable-class-default]
        fields = ["name", "slug", "project", "category"]

    def __init__(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:
        super().__init__(request, *args, **kwargs)
        self.fields["project"].queryset = request.user.managed_projects
        self.fields["category"].queryset = self.instance.project.category_set.exclude(
            pk=self.instance.pk
        )


class AddCategoryForm(SettingsBaseForm):
    class Meta:
        model = Category
        # ruff: ignore[mutable-class-default]
        fields = ["name", "slug"]

    def __init__(
        self, request: AuthenticatedHttpRequest, parent, *args, **kwargs
    ) -> None:
        self.parent = parent
        super().__init__(request, *args, **kwargs)

    def clean(self) -> None:
        if isinstance(self.parent, Category):
            self.instance.category = self.parent
            self.instance.project = self.parent.project
        else:
            self.instance.project = self.parent
        super().clean()


class CategorySettingsForm(
    InheritedSettingsFormMixin,
    SettingsBaseForm,
    CategoryDocsMixin,
    CategoryAntispamMixin,
):
    """Category settings form."""

    class Meta:
        model = Category
        fields = (
            "name",
            "inherit_license",
            "license",
            "inherit_agreement",
            "agreement",
            "check_flags",
            "inherit_secondary_language",
            "secondary_language",
            "inherit_new_lang",
            "new_lang",
            "inherit_language_code_style",
            "language_code_style",
            "inherit_commit_message",
            "commit_message",
            "inherit_add_message",
            "add_message",
            "inherit_delete_message",
            "delete_message",
            "inherit_merge_message",
            "merge_message",
            "inherit_addon_message",
            "addon_message",
            "inherit_pull_message",
            "pull_message",
        )
        # ruff: ignore[mutable-class-default]
        widgets = {
            "secondary_language": SortedSelect,
            "language_code_style": SortedSelect,
            "license": SearchableSelect,
        }

    def __init__(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:
        super().__init__(request, *args, **kwargs)
        parent_scope: InheritedSettingsScope = (
            "category" if self.instance.category_id else "project"
        )
        self.setup_inherited_settings(parent_scope, has_parent=True)
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    gettext("Basic"),
                    "name",
                    ContextDiv(
                        template="snippets/settings-organize.html",
                        context={
                            "object": self.instance,
                            "type": "category",
                        },
                    ),
                    Fieldset(
                        gettext("License"),
                        InheritedSetting("license"),
                        InheritedSetting("agreement"),
                    ),
                    css_id="basic",
                ),
                Tab(
                    gettext("Workflow"),
                    "check_flags",
                    InheritedSetting("secondary_language"),
                    InheritedSetting("new_lang"),
                    InheritedSetting("language_code_style"),
                    css_id="workflow",
                ),
                Tab(
                    gettext("Commit messages"),
                    InheritedSetting("commit_message"),
                    InheritedSetting("add_message"),
                    InheritedSetting("delete_message"),
                    InheritedSetting("merge_message"),
                    InheritedSetting("addon_message"),
                    InheritedSetting("pull_message"),
                    css_id="messages",
                ),
                template="layout/pills.html",
            )
        )

    def clean(self) -> None:
        super().clean()
        self.preserve_inherited_values()


class ProjectSettingsForm(
    InheritedSettingsFormMixin,
    SettingsBaseForm,
    ProjectDocsMixin,
    ProjectAntispamMixin,
):
    """Project settings form."""

    class Meta:
        model = Project
        fields = (
            "name",
            "web",
            "instructions",
            "use_shared_tm",
            "contribute_shared_tm",
            "use_workspace_tm",
            "contribute_workspace_tm",
            "autoclean_tm",
            "enable_hooks",
            "language_aliases",
            "inherit_license",
            "license",
            "inherit_agreement",
            "agreement",
            "inherit_new_lang",
            "new_lang",
            "inherit_language_code_style",
            "language_code_style",
            "inherit_secondary_language",
            "secondary_language",
            "access_control",
            "enforced_2fa",
            "translation_review",
            "source_review",
            "commit_policy",
            "check_flags",
            "inherit_commit_message",
            "commit_message",
            "inherit_add_message",
            "add_message",
            "inherit_delete_message",
            "delete_message",
            "inherit_merge_message",
            "merge_message",
            "inherit_addon_message",
            "addon_message",
            "inherit_pull_message",
            "pull_message",
        )
        # ruff: ignore[mutable-class-default]
        widgets = {
            "access_control": forms.RadioSelect,
            "instructions": MarkdownTextarea,
            "language_aliases": forms.TextInput,
            "secondary_language": SortedSelect,
            "language_code_style": SortedSelect,
            "license": SearchableSelect,
        }
        # ruff: ignore[mutable-class-default]
        field_classes = {
            "check_flags": FlagField,
        }

    def get_unlicensed_components(self, project_license: str) -> list[Component]:
        categories_by_id = {
            category.pk: category for category in self.instance.category_set.all()
        }
        category_license_cache: dict[int, str] = {}

        def get_category_license(category: Category) -> str:
            if category.pk in category_license_cache:
                return category_license_cache[category.pk]
            if category.inherit_license:
                if category.category_id is None:
                    license_value = project_license
                else:
                    license_value = get_category_license(
                        categories_by_id[category.category_id]
                    )
            else:
                license_value = category.license
            category_license_cache[category.pk] = license_value
            return license_value

        unlicensed_categories = [
            category_id
            for category_id, category in categories_by_id.items()
            if not get_category_license(category)
        ]
        components_filter = Q(inherit_license=False, license="")
        if not project_license:
            components_filter |= Q(inherit_license=True, category__isnull=True)
        if unlicensed_categories:
            components_filter |= Q(
                inherit_license=True, category_id__in=unlicensed_categories
            )
        return list(self.instance.component_set.filter(components_filter))

    def clean(self) -> None:
        data = self.cleaned_data
        if settings.OFFER_HOSTING:
            data["contribute_shared_tm"] = data["use_shared_tm"]
            data["contribute_workspace_tm"] = data["use_workspace_tm"]

        # ACCESS_PUBLIC = 0, so the condition can not be simplified to not data["access_control"]
        if (
            "access_control" not in data
            or data["access_control"] is None
            # ruff: ignore[compare-to-empty-string]
            or data["access_control"] == ""
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
        if self.changed_access and self.instance.needs_license(access):
            project_license = data.get("license", self.instance.license)
            if (
                data.get("inherit_license", self.instance.inherit_license)
                and self.instance.workspace_id
            ):
                project_license = self.instance.workspace.license
            unlicensed = self.get_unlicensed_components(project_license)
            if unlicensed:
                raise ValidationError(
                    {
                        "access_control": format_html(
                            "{} {}",
                            gettext(
                                "You must specify a license for these components to make them publicly accessible:"
                            ),
                            format_html_join_comma(
                                '<a href="{}">{}</a>',
                                (
                                    (component.get_absolute_url(), component.name)
                                    for component in unlicensed
                                ),
                            ),
                        )
                    }
                )

        if (
            data.get("commit_policy") != self.instance.commit_policy
            and data.get("commit_policy") == CommitPolicyChoices.APPROVED_ONLY
            and not data.get("translation_review", self.instance.translation_review)
        ):
            raise ValidationError(
                {
                    "commit_policy": gettext(
                        "Approved-only commit policy requires translation reviews to be enabled. "
                        "Please enable translation reviews first or choose a different commit policy."
                    )
                }
            )

        if (
            data.get("translation_review") != self.instance.translation_review
            and not data.get("translation_review")
            and data.get("commit_policy", self.instance.commit_policy)
            == CommitPolicyChoices.APPROVED_ONLY
        ):
            raise ValidationError(
                {
                    "translation_review": gettext(
                        "Translation reviews are required for approved-only commit policy. "
                        "Please choose a different commit policy before disabling translation reviews."
                    )
                }
            )

        self.preserve_inherited_values()

    def __init__(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:
        super().__init__(request, *args, **kwargs)
        parent_scope: InheritedSettingsScope = "workspace"
        self.setup_inherited_settings(
            parent_scope, has_parent=self.instance.workspace_id is not None
        )
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
                    ContextDiv(
                        template="snippets/settings-organize.html",
                        context={
                            "object": self.instance,
                            "type": "project",
                        },
                    ),
                    "web",
                    "instructions",
                    Fieldset(
                        gettext("License"),
                        InheritedSetting("license"),
                        InheritedSetting("agreement"),
                    ),
                    css_id="basic",
                ),
                Tab(
                    gettext("Access"),
                    InlineRadios(
                        "access_control",
                        template="%s/layout/radioselect_access.html",
                        **disabled,
                    ),
                    "enforced_2fa",
                    css_id="access",
                ),
                Tab(
                    gettext("Workflow"),
                    "use_shared_tm",
                    "contribute_shared_tm",
                    "use_workspace_tm",
                    "contribute_workspace_tm",
                    "autoclean_tm",
                    "check_flags",
                    "enable_hooks",
                    "language_aliases",
                    InheritedSetting("secondary_language"),
                    InheritedSetting("new_lang"),
                    InheritedSetting("language_code_style"),
                    "translation_review",
                    "source_review",
                    "commit_policy",
                    ContextDiv(
                        template="snippets/project-workflow-settings.html",
                        context={
                            "object": self.instance,
                            "project_languages": self.instance.project_languages.preload(),
                            "custom_workflows": set(
                                self.instance.workflowsetting_set.values_list(
                                    "language_id", flat=True
                                )
                            ),
                        },
                    ),
                    css_id="workflow",
                ),
                Tab(
                    gettext("Commit messages"),
                    InheritedSetting("commit_message"),
                    InheritedSetting("add_message"),
                    InheritedSetting("delete_message"),
                    InheritedSetting("merge_message"),
                    InheritedSetting("addon_message"),
                    InheritedSetting("pull_message"),
                    css_id="messages",
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
            self.fields["contribute_workspace_tm"].widget = forms.HiddenInput()
            self.fields["use_workspace_tm"].help_text = gettext(
                "Uses and contributes to the pool of shared translations "
                "between projects in the workspace."
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
        # ruff: ignore[mutable-class-default]
        fields = ["name", "slug"]


class ProjectMoveForm(forms.Form):
    """Project workspace move form."""

    workspace = forms.Field(label=gettext_lazy("Workspace"))

    def __init__(
        self, request: AuthenticatedHttpRequest, *args, instance: Project, **kwargs
    ) -> None:
        self.request = request
        self.instance = instance
        self.allow_standalone = instance.workspace_id is not None and (
            request.user.has_perm("project.add")
        )
        self.target_workspaces = get_project_move_target_workspaces(
            request.user, instance
        )
        self.use_uuid_input = (
            self.target_workspaces.count() > PROJECT_MOVE_WORKSPACE_SELECT_LIMIT
        )
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False

        if self.use_uuid_input:
            help_text = gettext(
                "Enter the UUID of a workspace where you have permission to edit "
                "settings and add projects."
            )
            if self.allow_standalone:
                help_text = gettext(
                    "Enter the UUID of a workspace where you have permission to edit "
                    "settings and add projects, or leave empty to move the project "
                    "out of a workspace."
                )
            self.fields["workspace"] = forms.UUIDField(
                label=gettext_lazy("Workspace"),
                required=not self.allow_standalone,
                help_text=help_text,
            )
        else:
            self.fields["workspace"] = forms.ModelChoiceField(
                label=gettext_lazy("Workspace"),
                queryset=self.target_workspaces,
                required=not self.allow_standalone,
                empty_label=gettext("No workspace") if self.allow_standalone else None,
            )

    def clean_workspace(self):
        workspace = self.cleaned_data["workspace"]
        if self.use_uuid_input and workspace is not None:
            try:
                workspace = Workspace.objects.get(pk=workspace)
            except Workspace.DoesNotExist as exc:
                raise ValidationError(gettext("No matching workspace found.")) from exc

        if validation_error := get_project_workspace_move_error(
            self.request.user, self.instance, workspace, reject_unchanged=True
        ):
            raise ValidationError(validation_error)
        return workspace

    def save(self) -> Project:
        self.instance.workspace = self.cleaned_data["workspace"]
        self.instance.save(update_fields=["workspace"])
        return self.instance


class WorkspaceMixin(forms.Form):
    # This is fake field with is either hidden or configured
    # in the view
    workspace = forms.ModelChoiceField(
        label=gettext_lazy("Workspace"),
        queryset=Workspace.objects.none(),
        required=False,
        empty_label=None,
    )


class ProjectCreateForm(
    WorkspaceMixin, SettingsBaseForm, ProjectDocsMixin, ProjectAntispamMixin
):
    """Project creation form."""

    class Meta:
        model = Project
        fields = ("name", "slug", "web", "instructions", "license", "workspace")
        # ruff: ignore[mutable-class-default]
        widgets = {
            "license": SearchableSelect,
        }


class ProjectImportCreateForm(ProjectCreateForm):
    class Meta:
        model = Project
        fields = ("name", "slug", "workspace")

    def __init__(
        self, request: AuthenticatedHttpRequest, projectbackup, *args, **kwargs
    ) -> None:
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
            Field("workspace"),
        )


class ProjectImportForm(WorkspaceMixin, forms.Form):
    """Component base form."""

    zipfile = forms.FileField(
        label=gettext_lazy("ZIP file containing project backup"),
        validators=[
            validate_project_backup_upload_size,
            FileExtensionValidator(allowed_extensions=["zip"]),
        ],
        widget=forms.FileInput(attrs={"accept": ".zip,application/zip"}),
    )

    def __init__(
        self, request: AuthenticatedHttpRequest, projectbackup=None, *args, **kwargs
    ) -> None:
        kwargs.pop("instance", None)
        super().__init__(*args, **kwargs)
        self.request = request
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("zipfile"),
            Field("workspace"),
        )

    def clean_zipfile(self):
        zipfile = self.cleaned_data["zipfile"]
        backup = ProjectBackup(fileio=zipfile)
        try:
            backup.validate()
        except jsonschema.exceptions.ValidationError as error:
            version = backup.data.get("metadata", {}).get("version", "unknown")
            error_message = gettext(
                "The backup is from an incompatible version (%(version)s). Please upgrade your Weblate instance."
            ) % {"version": version}
            raise ValidationError(
                gettext("Could not load project backup: %s") % error_message
            ) from error
        except Exception as error:
            raise ValidationError(
                gettext("Could not load project backup: %s") % error
            ) from error
        self.cleaned_data["projectbackup"] = backup
        return zipfile


class ReplaceForm(forms.Form):
    q = QueryField(
        required=False,
        help_text=gettext_lazy("Optional additional filter applied to the strings"),
    )
    path = forms.CharField(widget=forms.HiddenInput, required=False)
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

    def __init__(self, obj: URLMixin, data: dict | None = None) -> None:
        path = getattr(obj, "full_slug", "/".join(obj.get_url_path()))
        super().__init__(data=data, auto_id="id_replace_%s", initial={"path": path})
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            SearchField("q"),
            Field("path"),
            Field("search"),
            Field("replacement"),
            Div(template="snippets/replace-help.html"),
        )


class ReplaceConfirmForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.HiddenInput)
    path = forms.CharField(required=False, widget=forms.HiddenInput)
    search = forms.CharField(
        min_length=1, required=True, strip=False, widget=forms.HiddenInput
    )
    replacement = forms.CharField(
        min_length=1, required=True, strip=False, widget=forms.HiddenInput
    )
    units = forms.ModelMultipleChoiceField(queryset=Unit.objects.none(), required=False)
    confirm = forms.BooleanField(required=True, initial=True, widget=forms.HiddenInput)

    def __init__(self, units, *args, **kwargs) -> None:
        kwargs.setdefault("auto_id", False)
        super().__init__(*args, **kwargs)
        self.fields["units"].queryset = units


class MatrixLanguageForm(forms.Form):
    """Form for requesting a new language."""

    lang = forms.MultipleChoiceField(
        label=gettext_lazy("Languages"), choices=[], widget=forms.SelectMultiple
    )

    def __init__(self, component, *args, **kwargs) -> None:
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

    def __init__(
        self,
        translation: Translation,
        user: User,
        data: dict | None = None,
        initial: dict | None = None,
        is_source_plural: Literal[True] | None = None,
        auto_id: str = "id_%s",
    ) -> None:
        super().__init__(data=data, initial=initial, auto_id=auto_id)
        self.translation = translation
        self.user = user
        self.is_source_plural = is_source_plural
        self.patch_fields()

    def patch_fields(self) -> None:
        self.fields["variant"].queryset = self.translation.unit_set.all()

    def clean(self) -> None:
        try:
            data = self.as_kwargs()
        except KeyError:
            # Probably the validation of some fields has failed
            return
        self.translation.validate_new_unit_data(**data)

    def get_glossary_flags(self) -> str:
        return ""

    def as_kwargs(self) -> NewUnitParams:
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
            "You can edit this later, as with any other string in the source language."
        ),
        required=True,
    )

    def patch_fields(self) -> None:
        super().patch_fields()
        self.fields["source"].widget.profile = self.user.profile
        self.fields["source"].widget.is_source_plural = self.is_source_plural
        self.fields["source"].initial = Unit(translation=self.translation, id_hash=0)


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

    def patch_fields(self) -> None:
        super().patch_fields()
        self.fields["context"].label = self.translation.component.context_label
        self.fields["source"].widget.profile = self.user.profile
        self.fields["source"].widget.is_source_plural = self.is_source_plural
        self.fields["source"].initial = Unit(
            translation=self.translation.component.source_translation, id_hash=0
        )


class NewBilingualUnitForm(NewBilingualSourceUnitForm):
    target = PluralField(
        label=gettext_lazy("Translated string"),
        help_text=gettext_lazy(
            "You can edit this later, as with any other string in the translation."
        ),
        required=True,
    )

    def patch_fields(self) -> None:
        super().patch_fields()
        self.fields["target"].widget.profile = self.user.profile
        self.fields["target"].widget.is_source_plural = self.is_source_plural
        self.fields["target"].initial = Unit(translation=self.translation, id_hash=0)


class GlossaryAddMixin(NewUnitBaseForm):
    terminology = forms.BooleanField(
        label=gettext_lazy("Terminology"),
        help_text=gettext_lazy("String will be part of the glossary in all languages"),
        required=False,
    )
    forbidden = forms.BooleanField(
        label=gettext_lazy("Forbidden translation"),
        help_text=gettext_lazy(
            "Mark this option for translations that should not be used."
        ),
        required=False,
    )
    read_only = forms.BooleanField(
        label=gettext_lazy("Untranslatable term"),
        help_text=gettext_lazy(
            "Mark this option if the sentence should stay as in the source language, without change."
        ),
        required=False,
    )

    def can_edit_terminology(self) -> bool:
        return (
            self.user.has_perm("glossary.terminology", self.translation)
            or self.translation.is_source
        )

    def patch_fields(self) -> None:
        super().patch_fields()
        if not self.can_edit_terminology():
            self.fields["terminology"].widget = forms.HiddenInput()

    def get_glossary_flags(self) -> str:
        result = []
        if self.cleaned_data.get("terminology"):
            result.append("terminology")
        if self.cleaned_data.get("forbidden"):
            result.append("forbidden")
        if self.cleaned_data.get("read_only"):
            result.append("read-only")
        return ", ".join(result)

    def clean(self) -> None:
        if not self.can_edit_terminology() and self.cleaned_data.get("terminology"):
            raise ValidationError(
                gettext("You do not have permission to create terminology.")
            )
        super().clean()


class NewBilingualGlossarySourceUnitForm(GlossaryAddMixin, NewBilingualSourceUnitForm):
    def patch_fields(self) -> None:
        super().patch_fields()
        self.fields["terminology"].initial = True


class NewBilingualGlossaryUnitForm(GlossaryAddMixin, NewBilingualUnitForm):
    pass


def get_new_unit_form(
    translation: Translation,
    user: User,
    data: dict | None = None,
    initial: dict | None = None,
    is_source_plural: Literal[True] | None = None,
):
    if translation.component.has_template():
        return NewMonolingualUnitForm(
            translation,
            user,
            data=data,
            initial=initial,
            is_source_plural=is_source_plural,
        )
    if translation.component.is_glossary:
        if translation.is_source:
            return NewBilingualGlossarySourceUnitForm(
                translation,
                user,
                data=data,
                initial=initial,
                is_source_plural=is_source_plural,
            )
        return NewBilingualGlossaryUnitForm(
            translation,
            user,
            data=data,
            initial=initial,
            is_source_plural=is_source_plural,
        )
    if translation.is_source:
        return NewBilingualSourceUnitForm(
            translation,
            user,
            data=data,
            initial=initial,
            is_source_plural=is_source_plural,
        )
    return NewBilingualUnitForm(
        translation,
        user,
        data=data,
        initial=initial,
        is_source_plural=is_source_plural,
    )


class BulkEditForm(forms.Form):
    q = QueryField(required=True)
    state = forms.ChoiceField(
        label=gettext_lazy("State to set"),
        choices=[(-1, gettext_lazy("Do not change"))],
    )
    path = forms.CharField(widget=forms.HiddenInput, required=False)
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

    def __init__(
        self,
        user: User | None,
        obj: Project
        | Translation
        | Component
        | ProjectLanguage
        | Category
        | CategoryLanguage
        | Workspace
        | None,
        *args,
        **kwargs,
    ) -> None:
        project = kwargs.pop("project", None)
        labels = kwargs.pop("labels", None)
        kwargs["auto_id"] = "id_bulk_%s"
        if obj is not None:
            kwargs["initial"] = {
                "path": getattr(obj, "full_slug", "/".join(obj.get_url_path()))
            }
        super().__init__(*args, **kwargs)
        if labels is None:
            # Labels are project-scoped, so non-project bulk edit scopes do not
            # offer label operations to avoid applying labels across projects.
            labels = (
                Label.objects.none() if project is None else project.label_set.order()
            )
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

        # Special case for list_addons
        if isinstance(obj, Component) and obj.pk == -1:
            show_review = False
        choices.extend(
            (state, get_state_label(state, label, show_review))
            for state, label in StringState.choices
            if state not in excluded
        )
        self.fields["state"].choices = choices

        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(template="snippets/bulk-help.html"),
            SearchField("q"),
            Field("path"),
            Field("state"),
            Field("add_flags"),
            Field("remove_flags"),
        )
        if labels:
            self.helper.layout.append(InlineCheckboxes("add_labels"))
            self.helper.layout.append(InlineCheckboxes("remove_labels"))


class ContributorAgreementForm(forms.Form):
    confirm = forms.BooleanField(
        label=gettext_lazy("I accept the contributor license agreement"), required=True
    )
    next = forms.CharField(required=False, widget=forms.HiddenInput)


class BaseDeleteForm(forms.Form):
    confirm = forms.CharField(required=True)
    warning_template = ""

    def __init__(self, obj, *args, **kwargs) -> None:
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

    def clean(self) -> None:
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
            for addon in obj.component.addons_cache.addons
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

    def get_template_context(self, obj):
        context = super().get_template_context(obj)
        components = obj.component_set.order()
        context["components"] = components
        context["components_count"] = components.count()
        return context


class CategoryDeleteForm(BaseDeleteForm):
    confirm = forms.CharField(
        label=gettext_lazy("Removal confirmation"),
        help_text=gettext_lazy("Please type in the slug of the category to confirm."),
        required=True,
    )
    warning_template = "trans/delete-category.html"


class ProjectLanguageDeleteForm(BaseDeleteForm):
    confirm = forms.CharField(
        label=gettext_lazy("Removal confirmation"),
        help_text=gettext_lazy(
            "Please type in the slug of the project and language to confirm."
        ),
        required=True,
    )
    warning_template = "trans/delete-project-language.html"


class CategoryLanguageDeleteForm(BaseDeleteForm):
    confirm = forms.CharField(
        label=gettext_lazy("Removal confirmation"),
        help_text=gettext_lazy(
            "Please type in the slug of the category and language to confirm."
        ),
        required=True,
    )
    warning_template = "trans/delete-category-language.html"


class AnnouncementForm(forms.ModelForm):
    """Announcement posting form."""

    class Meta:
        model = Announcement
        # ruff: ignore[mutable-class-default]
        fields = ["message", "severity", "expiry", "notify"]
        # ruff: ignore[mutable-class-default]
        widgets = {
            "expiry": WeblateDateInput(),
            "message": MarkdownTextarea,
        }


class ChangesForm(forms.Form):
    action = forms.MultipleChoiceField(
        label=gettext_lazy("Action"),
        required=False,
        widget=SortedSelectMultiple,
        choices=ActionEvents.choices,
    )
    user = UserField(
        label=gettext_lazy("Author username"), required=False, help_text=None
    )
    exclude_user = UserField(
        label=gettext_lazy("Exclude author (username)"), required=False, help_text=None
    )
    period = DateRangeField(
        label=gettext_lazy("Date range"),
        required=False,
    )

    def items(self):
        items = []
        for param in sorted(self.cleaned_data):
            value = self.cleaned_data[param]
            # We don't care about empty values
            if not value:
                continue
            if (
                isinstance(value, dict)
                and "start_date" in value
                and "end_date" in value
            ):
                # Convert date to string
                start_date = value["start_date"].strftime("%m/%d/%Y")
                end_date = value["end_date"].strftime("%m/%d/%Y")
                items.append((param, f"{start_date} - {end_date}"))
            elif isinstance(value, User):
                items.append((param, value.username))
            elif isinstance(value, list):
                items.extend((param, part) for part in value)
            else:
                # It should be a string here
                items.append((param, value))
        return items

    def urlencode(self):
        return urlencode(self.items())


class LabelForm(forms.ModelForm):
    class Meta:
        model = Label
        fields = ("name", "description", "color", "project")
        # ruff: ignore[mutable-class-default]
        widgets = {
            "color": ColorWidget(),
            "project": forms.HiddenInput(),
        }

    def clean_project(self):
        # Ignore any passed value, override by current one
        return self.project

    def __init__(self, project: Project, *args, **kwargs) -> None:
        kwargs["initial"] = {"project": project}
        super().__init__(*args, **kwargs)
        self.project = project
        self.helper = FormHelper(self)
        self.helper.form_tag = False


class ProjectTokenCreateForm(forms.ModelForm):
    class Meta:
        model = User
        # ruff: ignore[mutable-class-default]
        fields = ["full_name", "date_expires"]
        # ruff: ignore[mutable-class-default]
        widgets = {
            "date_expires": WeblateDateInput(),
        }

    def __init__(self, project, *args, **kwargs) -> None:
        self.project = project
        super().__init__(*args, **kwargs)

    def save(self, *args, acting_user: User | None = None, **kwargs):
        self.instance.is_bot = True
        base_name = name = f"bot-{self.project.slug}-{slugify(self.instance.full_name)}"
        while User.objects.filter(
            Q(username=name) | Q(email=f"{name}@bots.noreply.weblate.org")
        ).exists():
            name = f"{base_name}-{token_hex(2)}"
        self.instance.username = name
        self.instance.email = f"{name}@bots.noreply.weblate.org"
        result = super().save(*args, **kwargs)
        self.project.add_user(self.instance, "Administration", allow_bot=True)
        AuditLog.objects.create(
            self.instance,
            None,
            "token-created",
            project=self.project.name,
            username=acting_user.username if acting_user is not None else None,
        )
        return result

    def clean_date_expires(self):
        expires = self.cleaned_data["date_expires"]
        if expires is None:
            return expires
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

    def __init__(self, project, *args, **kwargs) -> None:
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

    def __init__(
        self,
        project,
        *args,
        group_queryset: QuerySet[Group] | None = None,
        limit_language_choices: list[tuple[str, str]] | None = None,
        **kwargs,
    ) -> None:
        self.project = project
        super().__init__(*args, **kwargs)
        self.fields["user"].widget = forms.HiddenInput()
        groups_queryset = (
            group_queryset
            if group_queryset is not None
            else project.defined_groups.all()
        )
        groups = list(groups_queryset)
        self.fields["groups"].queryset = groups_queryset
        selected_group_ids = self.get_selected_group_ids()
        limit_language_queryset = project.languages
        if limit_language_choices is None:
            limit_language_choices = get_language_code_choices(limit_language_queryset)
        for group in groups:
            self.fields[self.get_limit_languages_field(group)] = LimitLanguagesField(
                limit_language_queryset,
                help_text=None,
                hide_placeholder=True,
                language_choices=limit_language_choices,
            )
            limit_field = self.fields[self.get_limit_languages_field(group)]
            limit_field.disabled = str(group.pk) not in selected_group_ids
            limit_field.widget.attrs["aria-label"] = gettext(
                "Limit languages for %(team)s"
            ) % {"team": group}
        self.membership_fields = [
            {
                "group": group,
                "value": str(group.pk),
                "checkbox_id": f"{self['groups'].id_for_label}_{index}",
                "checked": str(group.pk) in selected_group_ids,
                "limit_field": self[self.get_limit_languages_field(group)],
            }
            for index, group in enumerate(groups)
        ]

    def get_selected_group_ids(self) -> set[str]:
        if self.is_bound:
            field_name = self.add_prefix("groups")
            values = self.fields["groups"].widget.value_from_datadict(
                self.data, self.files, field_name
            )
            if values is None:
                return set()
            if isinstance(values, (list, tuple)):
                return {str(value) for value in values}
            return {str(values)}
        groups = self.initial.get("groups", ())
        return {str(group.pk) for group in groups}

    @staticmethod
    def get_limit_languages_field(group: Group) -> str:
        return f"limit_languages_{group.pk}"

    def get_limit_languages(self, group: Group):
        return self.cleaned_data[self.get_limit_languages_field(group)]

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        user = cleaned_data.get("user")
        groups = cleaned_data.get("groups")
        if user and groups:
            current_group_ids = set(
                user.groups.filter(defining_project=self.project).values_list(
                    "id", flat=True
                )
            )
            added_group_ids = set(groups.values_list("id", flat=True))
            if added_group_ids - current_group_ids:
                validate_team_assignable_user(user, allow_bot=True)
        if user and user.is_bot and not groups:
            raise ValidationError(
                gettext_lazy("At least one team is required for a project token.")
            )
        return cleaned_data


class ProjectFilterForm(forms.Form):
    owned = UserField(required=False)
    watched = UserField(required=False)


class WorkflowSettingForm(FieldDocsMixin, forms.ModelForm):
    enable = forms.BooleanField(
        label=gettext_lazy("Customize translation workflow for this language"),
        help_text=gettext_lazy(
            "The translation workflow is configured at project and component. "
            "By enabling customization here, you override these settings for this language."
        ),
        required=False,
        initial=False,
    )

    class Meta:
        model = WorkflowSetting
        # ruff: ignore[mutable-class-default]
        fields = [
            "translation_review",
            "enable_suggestions",
            "suggestion_voting",
            "suggestion_autoaccept",
        ]

    def __init__(
        self,
        data=None,
        files=None,
        *,
        instance: WorkflowSetting | None = None,
        prefix=None,
        initial=None,
        project: Project | None = None,
        **kwargs,
    ) -> None:
        if instance is not None:
            # The enable field indicates presence of the instance,
            # untoggling it removes it
            initial = {"enable": True}
        elif project is not None:
            # Default review setting based on the project one
            initial = {"translation_review": project.translation_review}

        self.project = project
        self.instance = instance
        super().__init__(
            data, files, instance=instance, initial=initial, prefix="workflow", **kwargs
        )
        if self.project:
            enable_field = self.fields["enable"]
            enable_field.label = gettext(
                "Customize translation workflow for this language in this project"
            )
            enable_field.help_text = gettext(
                "The translation workflow is configured at project, component, and language. "
                "By enabling customization here, you override these settings for this language in this project."
            )

        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("enable", template="bootstrap5/layout/switch.html"),
            HTML(
                format_html(
                    '<p id="workflow-enable-hint" class="text-muted">{}</p>',
                    gettext("Turn on customization above to change these settings."),
                )
            ),
            Div(
                Field("translation_review"),
                Field("enable_suggestions"),
                Field("suggestion_voting"),
                Field("suggestion_autoaccept"),
                css_id="workflow-enable-target",
            ),
        )

    def clean_translation_review(self) -> bool | None:
        if "translation_review" not in self.cleaned_data:
            return None
        translation_review = self.cleaned_data["translation_review"]
        if not self.project:
            return translation_review
        if translation_review and not self.project.enable_review:
            msg = "Please turn on reviews on the project first."
            raise ValidationError(msg)
        return translation_review

    def save(self, commit: bool = True):
        if self.cleaned_data["enable"]:
            return super().save(commit=commit)
        if self.instance and self.instance.pk:
            self.instance.delete()
            self.instance = None
        return self.instance

    def get_field_doc(self, field: forms.Field) -> tuple[str, str] | None:
        if field.name == "enable":
            return ("workflows", "workflow-customization")
        return None
