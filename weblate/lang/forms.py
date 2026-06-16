# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout
from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy

from weblate.lang.models import Language, Plural
from weblate.utils.forms import ContextDiv

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.db.models import QuerySet
    from django_stubs_ext import StrOrPromise


def validate_language_code(value: str) -> None:
    # Keep API/form validation aligned with Language.code. Existence is still
    # checked by the queryset lookup.
    # ruff: ignore[private-member-access]
    Language._meta.get_field("code").clean(value, None)


class LanguageCodeChoiceField(forms.ModelChoiceField):
    def to_python(self, value):
        # Add explicit validation here to avoid DataError on invalid input
        # such as: PostgreSQL text fields cannot contain NUL (0x00) bytes
        if value:
            validate_language_code(value)
        return super().to_python(value)


class LanguageCodeMultipleChoiceField(forms.ModelMultipleChoiceField):
    def clean(self, value: object) -> QuerySet[Language]:
        values: Iterable[object]
        if value is None:
            values = ()
        elif isinstance(value, str):
            values = (value,)
        else:
            values = cast("Iterable[object]", value)
        for item in values:
            if isinstance(item, str):
                validate_language_code(item)
        return super().clean(value)

    def label_from_instance(self, obj: Language) -> str:
        return get_language_code_label(obj)


def get_language_code_label(language: Language) -> str:
    return f"{language.get_localized_name()} ({language.code})"


def get_language_code_choices(
    languages: Iterable[Language],
) -> list[tuple[str, str]]:
    return [
        (language.code, get_language_code_label(language)) for language in languages
    ]


LIMIT_LANGUAGES_HELP_TEXT: StrOrPromise = gettext_lazy(
    "Leave empty to use the team's language selection without additional limit."
)


class LimitLanguagesField(LanguageCodeMultipleChoiceField):
    def __init__(
        self,
        queryset: QuerySet[Language],
        *,
        help_text: StrOrPromise | None = LIMIT_LANGUAGES_HELP_TEXT,
        hide_placeholder: bool = False,
        language_choices: Iterable[tuple[str, str]] | None = None,
        **kwargs: object,
    ) -> None:
        kwargs.setdefault("required", False)
        kwargs.setdefault("label", gettext_lazy("Language limit"))
        kwargs.setdefault("to_field_name", "code")
        if help_text is not None:
            kwargs.setdefault("help_text", help_text)
        super().__init__(queryset, **kwargs)
        if language_choices is not None:
            self.choices = language_choices
        self.widget.attrs["data-placeholder"] = gettext_lazy("No language limit")
        if hide_placeholder:
            self.widget.attrs["data-hide-placeholder"] = "true"


class LanguageForm(forms.ModelForm):
    class Meta:
        model = Language
        # ruff: ignore[mutable-class-default]
        fields = [
            "code",
            "name",
            "direction",
            "population",
        ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            ContextDiv(
                template="lang/language_edit_warning.html",
                context={"update_languages": settings.UPDATE_LANGUAGES},
            ),
            Field("code"),
            Field("name"),
            Field("direction"),
            Field("population"),
        )

    @staticmethod
    def get_field_doc(field):
        return ("admin/languages", f"language-{field.name}")


class PluralForm(forms.ModelForm):
    class Meta:
        model = Plural
        # ruff: ignore[mutable-class-default]
        fields = [
            "number",
            "formula",
        ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False

    @staticmethod
    def get_field_doc(field):
        return ("admin/languages", f"plural-{field.name}")
