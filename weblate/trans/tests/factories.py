# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Lightweight factories for unsaved trans model test objects."""

from __future__ import annotations

from itertools import count
from typing import TYPE_CHECKING
from zlib import adler32

from translate.lang.data import languages

from weblate.checks.flags import Flags
from weblate.checks.models import Check
from weblate.lang.models import Language, Plural
from weblate.trans.models import Component, Project, Translation, Unit
from weblate.trans.util import join_plural
from weblate.utils.state import STATE_TRANSLATED

if TYPE_CHECKING:
    from weblate.checks.base import BaseCheck


_id_counter = count(1)


def _stable_id(value: str) -> int:
    return adler32(value.encode()) or next(_id_counter)


def make_language(code: str = "cs") -> Language:
    """Create an unsaved language with plural information."""
    language = Language(id=-_stable_id(f"language:{code}"), code=code, name=code)
    try:
        _, number, formula = languages[code]
    except KeyError:
        plural = Plural(language=language)
    else:
        plural = Plural(language=language, number=number, formula=formula)
    plural.id = -_stable_id(f"plural:{code}")
    language.__dict__["plural"] = plural
    return language


def make_project() -> Project:
    """Create an unsaved project for tests."""
    project = Project(
        id=1,
        name="MockProject",
        slug="mock",
        web="https://example.com/",
        use_shared_tm=True,
        translation_review=False,
        source_review=False,
    )
    project.__dict__["glossaries"] = []
    return project


def make_component(
    *,
    project: Project | None = None,
    source_language: str | Language = "en",
) -> Component:
    """Create an unsaved component for tests."""
    if project is None:
        project = make_project()
    if isinstance(source_language, str):
        source_language = make_language(source_language)
    return Component(
        id=1,
        project=project,
        name="MockComponent",
        slug="mock",
        source_language=source_language,
        file_format="po",
        filemask="*.po",
        template="",
        hide_glossary_matches=False,
        allow_translation_propagation=True,
        check_flags="",
        enforced_checks=[],
    )


def make_translation(
    *,
    code: str = "cs",
    component: Component | None = None,
    source_language: str = "en",
    is_source: bool = False,
) -> Translation:
    """Create an unsaved translation for tests."""
    if component is None:
        component = make_component(source_language=source_language)
    language = component.source_language if is_source else make_language(code)
    translation = Translation(
        id=1,
        component=component,
        language=language,
        plural=language.plural,
        language_code=language.code,
        filename=f"{language.code}.po",
        check_flags="",
    )
    translation.__dict__["is_template"] = False
    translation.__dict__["is_source"] = is_source
    return translation


def _format_plural(value: str | list[str] | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return join_plural(value)


def _make_id_hash(id_hash: int | str | None) -> int:
    if id_hash is None:
        return next(_id_counter)
    if isinstance(id_hash, int):
        return id_hash
    return _stable_id(f"unit:{id_hash}")


def make_unit(
    id_hash: int | str | None = None,
    flags: str | Flags | list[str] = "",
    code: str = "cs",
    source: str | list[str] = "",
    note: str = "",
    is_source: bool | None = None,
    target: str | list[str] = "",
    context: str = "",
    *,
    state: int = STATE_TRANSLATED,
) -> Unit:
    """Create an unsaved unit with real model objects."""
    unit_id = _make_id_hash(id_hash)
    source_text = _format_plural(source)
    target_text = _format_plural(target)
    source_language = "en"
    source_translation = make_translation(code=source_language, is_source=True)
    if is_source is True:
        translation = source_translation
    else:
        translation = make_translation(
            code=code,
            component=source_translation.component,
            source_language=source_language,
            is_source=False,
        )

    unit = Unit(
        id=-unit_id,
        id_hash=unit_id,
        translation=translation,
        position=unit_id,
        context=context,
        note=note,
        flags=Flags(flags).format(),
        source=source_text,
        target=target_text,
        state=state,
    )
    unit.__dict__["all_checks"] = []
    if is_source is True:
        unit.source_unit = unit
        unit.source_unit_id = unit.id
    else:
        source_unit = Unit(
            id=-(unit_id + 1000000),
            id_hash=unit_id,
            translation=source_translation,
            position=unit_id,
            context=context,
            note=note,
            flags=Flags(flags).format(),
            source=source_text,
            target=source_text,
            state=STATE_TRANSLATED,
        )
        source_unit.__dict__["all_checks"] = []
        source_unit.source_unit = source_unit
        source_unit.source_unit_id = source_unit.id
        unit.source_unit = source_unit
        unit.source_unit_id = source_unit.id
    return unit


def make_check(unit: Unit, check: BaseCheck | str) -> Check:
    """Create an unsaved check model for a unit."""
    name = check if isinstance(check, str) else check.check_id
    return Check(unit=unit, name=name, dismissed=False)


def set_unit_flags(unit: Unit, flags: str | Flags | list[str]) -> None:
    """Set unit flags and clear cached derived flags."""
    unit.flags = Flags(flags).format()
    unit.__dict__.pop("all_flags", None)


def set_unit_source(unit: Unit, source: str | list[str]) -> None:
    """Set unit source and clear cached source-derived values."""
    unit.source = _format_plural(source)
    unit.__dict__.pop("is_plural", None)
    unit.__dict__.pop("source_string", None)
