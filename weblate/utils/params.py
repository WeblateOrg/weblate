# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Shared building blocks for scoped component parameters.

Weblate exposes several families of typed per-component settings which only
apply to a subset of components: :mod:`weblate.trans.file_format_params` are
scoped by file format, :mod:`weblate.vcs.params` by version control system.
Both share form field construction, value coercion and scope matching
implemented here; only the scope they are keyed by differs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, TypedDict, cast

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from django_stubs_ext import StrOrPromise


class FieldKwargsDict(TypedDict, total=False):
    min_value: int
    max_value: int
    min_length: int


class BaseParam:
    """
    Single scoped parameter definition.

    Subclasses declare which scopes they apply to (file formats, VCS backends,
    …) by implementing :meth:`get_scopes`. The special ``*`` scope matches
    everything.
    """

    name: str
    field_class: type[forms.Field] = forms.CharField
    label: StrOrPromise = ""
    default: str | int | bool
    field_kwargs: ClassVar[FieldKwargsDict] = {}
    choices: ClassVar[list[tuple[str | int, StrOrPromise]] | None] = None
    help_text: StrOrPromise | None = None

    #: CSS class marking a rendered subwidget, used to toggle its visibility.
    widget_css_class: ClassVar[str] = "param"
    #: Widget attribute carrying the space separated list of matching scopes.
    scope_attribute: ClassVar[str] = "scopes"

    @classmethod
    def get_identifier(cls) -> str:
        return cls.name

    @classmethod
    def get_scopes(cls) -> Sequence[str]:
        """Return scopes (file formats, VCS backends, …) this applies to."""
        raise NotImplementedError

    def get_field(self) -> forms.Field:
        widget = self.field_class.widget(attrs=self.get_widget_attrs())
        return self.field_class(widget=widget, **self.get_field_kwargs())

    def get_widget_attrs(self) -> dict:
        field_classes = [f"{self.widget_css_class}-field"]

        if self.field_class == forms.BooleanField:
            field_classes.append("form-check-input")
        elif self.field_class == forms.ChoiceField:
            field_classes.append("form-select")
        else:
            field_classes.append("form-control")

        attrs = {
            "label": self.label,
            self.scope_attribute: " ".join(self.get_scopes()),
            "class": " ".join(field_classes),
        }
        if self.help_text:
            attrs["help_text"] = self.help_text
        return attrs

    def get_field_kwargs(self) -> dict:
        kwargs = cast("dict", self.field_kwargs.copy())
        kwargs.update({"required": False, "initial": self.default})
        if self.choices is not None:
            kwargs["choices"] = self.choices
        if self.help_text:
            kwargs["help_text"] = self.help_text
        return kwargs

    @classmethod
    def get_value(cls, params: Mapping[str, Any] | None):
        if params is None:
            return cls.default
        value = params.get(cls.name, cls.default)
        if value is None:
            return cls.default
        try:
            result = cls().get_field().clean(value)
        except ValidationError:
            return cls.default
        if result is None:
            return cls.default
        if cls.choices is not None:
            # ChoiceField normalizes submitted values to strings, including
            # choices declared as integers. Return the declared choice value
            # so consumers retain the parameter's original type.
            for choice, _label in cls.choices:
                if str(result) == str(choice):
                    return choice
            # A choice field which is not required cleans a missing value to an
            # empty string, so stored values are not guaranteed to be valid
            # choices. Consumers pass these straight to storage backends and
            # hosting APIs, so never hand out something outside the choices.
            return cls.default
        return result

    @classmethod
    def supports_all_scopes(cls) -> bool:
        return "*" in cls.get_scopes()

    @classmethod
    def supports_scope(cls, scope: str) -> bool:
        return cls.supports_all_scopes() or scope in cls.get_scopes()


def get_params_for_scope[T: type[BaseParam]](
    params: Sequence[T], scope: str
) -> list[T]:
    """Get all registered parameters applicable to a given scope."""
    return [param for param in params if param.supports_scope(scope)]


def get_default_params_for_scope(
    params: Sequence[type[BaseParam]], scope: str
) -> dict[str, str | int | bool]:
    """Get default values of all parameters applicable to a given scope."""
    return {param.name: param.default for param in get_params_for_scope(params, scope)}


def get_param_by_name[T: type[BaseParam]](params: Sequence[T], name: str) -> T:
    """Get parameter class for given name."""
    for param in params:
        if param.name == name:
            return param
    msg = f"Unknown parameter: {name}"
    raise ValueError(msg)


def validate_params(
    params: Sequence[type[BaseParam]], value: dict | None, unknown_message: str
) -> None:
    """
    Validate stored parameters against the form fields they are edited with.

    ``unknown_message`` is a translated format string consuming a
    ``%(param_name)s`` placeholder.
    """
    if value is None:
        return

    if not isinstance(value, dict):
        raise ValidationError(
            gettext("Parameters must be a dictionary of key-value pairs.")
        )

    known = {param.name: param for param in params}

    for param_name, param_value in value.items():
        if param_name not in known:
            raise ValidationError(unknown_message % {"param_name": param_name})
        known[param_name]().get_field().clean(param_value)
