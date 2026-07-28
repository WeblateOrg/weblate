# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from django.db.models import Q
from django.utils.translation import gettext_lazy

if TYPE_CHECKING:
    from collections.abc import Collection, MutableMapping

NEW_LANG_CHOICES = (
    # Translators: Action when adding new translation
    ("contact", gettext_lazy("Contact maintainers")),
    # Translators: Action when adding new translation
    ("url", gettext_lazy("Point to translation instructions URL")),
    # Translators: Action when adding new translation
    ("add", gettext_lazy("Create new language file")),
    # Translators: Action when adding new translation
    ("none", gettext_lazy("Disable adding new translations")),
)

LANGUAGE_CODE_STYLE_CHOICES = (
    ("", gettext_lazy("Default based on the file format")),
    ("posix", gettext_lazy("POSIX style using underscore as a separator")),
    (
        "posix_lowercase",
        gettext_lazy("POSIX style using underscore as a separator, lower cased"),
    ),
    ("bcp", gettext_lazy("BCP style using hyphen as a separator")),
    (
        "posix_long",
        gettext_lazy(
            "POSIX style using underscore as a separator, including country code"
        ),
    ),
    (
        "posix_long_lowercase",
        gettext_lazy(
            "POSIX style using underscore as a separator, including country code, lower cased"
        ),
    ),
    (
        "bcp_long",
        gettext_lazy("BCP style using hyphen as a separator, including country code"),
    ),
    (
        "bcp_legacy",
        gettext_lazy("BCP style using hyphen as a separator, legacy language codes"),
    ),
    ("bcp_lower", gettext_lazy("BCP style using hyphen as a separator, lower cased")),
    ("android", gettext_lazy("Android style")),
    ("appstore", gettext_lazy("Apple App Store metadata style")),
    ("googleplay", gettext_lazy("Google Play metadata style")),
    ("linux", gettext_lazy("Linux style")),
    ("linux_lowercase", gettext_lazy("Linux style, lower cased")),
)

INHERITABLE_COMPONENT_SETTINGS = (
    "license",
    "agreement",
    "new_lang",
    "language_code_style",
    "secondary_language",
    "commit_message",
    "add_message",
    "delete_message",
    "merge_message",
    "addon_message",
    "pull_message",
)

type InheritableStringSetting = Literal[
    "license",
    "agreement",
    "new_lang",
    "language_code_style",
    "commit_message",
    "add_message",
    "delete_message",
    "merge_message",
    "addon_message",
    "pull_message",
]
type InheritableLanguageSetting = Literal["secondary_language"]

COMPONENT_MESSAGE_SETTINGS = (
    "commit_message",
    "add_message",
    "delete_message",
    "merge_message",
    "addon_message",
    "pull_message",
)

HUGE_INHERITABLE_SETTINGS = COMPONENT_MESSAGE_SETTINGS


def get_inherit_field_name(field: str) -> str:
    return f"inherit_{field}"


def get_inheritable_setting_value(obj: object, field: str) -> object:
    if field == "secondary_language":
        return getattr(obj, "secondary_language_id", None)
    return getattr(obj, field)


INHERITABLE_COMPONENT_FLAGS = tuple(
    get_inherit_field_name(field) for field in INHERITABLE_COMPONENT_SETTINGS
)

DISABLED_NEW_LANGUAGE_MODES = ("none", "url")


def get_disabled_project_new_language_filter(prefix: str = "project__") -> Q:
    """Return filter matching projects whose effective new-language mode is disabled."""
    return (
        Q(
            **{
                f"{prefix}inherit_new_lang": False,
                f"{prefix}new_lang__in": DISABLED_NEW_LANGUAGE_MODES,
            }
        )
        | Q(
            **{
                f"{prefix}inherit_new_lang": True,
                f"{prefix}workspace__isnull": True,
                f"{prefix}new_lang__in": DISABLED_NEW_LANGUAGE_MODES,
            }
        )
        | Q(
            **{
                f"{prefix}inherit_new_lang": True,
                f"{prefix}workspace__new_lang__in": DISABLED_NEW_LANGUAGE_MODES,
            }
        )
    )


def get_disabled_component_new_language_filter() -> Q:
    """Return filter matching components whose effective new-language mode is disabled."""
    project_disabled = get_disabled_project_new_language_filter()
    category_disabled = (
        Q(
            category__inherit_new_lang=False,
            category__new_lang__in=DISABLED_NEW_LANGUAGE_MODES,
        )
        | Q(category__inherit_new_lang=True, category__category__isnull=True)
        & project_disabled
        | Q(
            category__inherit_new_lang=True,
            category__category__inherit_new_lang=False,
            category__category__new_lang__in=DISABLED_NEW_LANGUAGE_MODES,
        )
        | Q(
            category__inherit_new_lang=True,
            category__category__inherit_new_lang=True,
            category__category__category__isnull=True,
        )
        & project_disabled
        | Q(
            category__inherit_new_lang=True,
            category__category__inherit_new_lang=True,
            category__category__category__inherit_new_lang=False,
            category__category__category__new_lang__in=DISABLED_NEW_LANGUAGE_MODES,
        )
        | Q(
            category__inherit_new_lang=True,
            category__category__inherit_new_lang=True,
            category__category__category__inherit_new_lang=True,
        )
        & project_disabled
    )
    return Q(new_lang__in=DISABLED_NEW_LANGUAGE_MODES, inherit_new_lang=False) | Q(
        inherit_new_lang=True
    ) & (Q(category__isnull=True) & project_disabled | category_disabled)


def apply_create_inheritance_defaults(
    values: MutableMapping[str, object],
    explicit_fields: Collection[str],
    *,
    preserve_existing: bool = False,
) -> None:
    for field in INHERITABLE_COMPONENT_SETTINGS:
        inherit_field = get_inherit_field_name(field)
        if inherit_field in explicit_fields:
            continue
        if preserve_existing and inherit_field in values:
            continue
        values[inherit_field] = field not in explicit_fields
