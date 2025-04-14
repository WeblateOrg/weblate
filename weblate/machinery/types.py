# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, NotRequired, TypeAlias, TypedDict

from django.db.models import TextChoices
from django.utils.translation import pgettext_lazy

if TYPE_CHECKING:
    from .base import BatchMachineTranslation


class SourceLanguageChoices(TextChoices):
    AUTO = "auto", pgettext_lazy("Source language selection", "Automatic selection")
    SOURCE = (
        "source",
        pgettext_lazy("Source language selection", "Component source language"),
    )
    SECONDARY = (
        "secondary",
        pgettext_lazy(
            "Source language selection",
            "Secondary language defined in project or component",
        ),
    )


class SettingsDict(TypedDict, total=False):
    key: str
    url: str
    secret: str
    email: str
    username: str
    password: str
    enable_mt: bool
    domain: str
    base_url: str
    endpoint_url: str
    region: str
    credentials: str
    project: str
    location: str
    formality: str
    model: str
    persona: str
    style: str
    custom_model: str
    bucket_name: str
    context_vector: str
    deployment: str
    azure_endpoint: str
    source_language: SourceLanguageChoices


class TranslationResultDict(TypedDict):
    text: str
    quality: int
    service: str
    source: str
    original_source: NotRequired[str]
    show_quality: NotRequired[bool]
    origin: NotRequired[str | None]
    origin_url: NotRequired[str]
    delete_url: NotRequired[str]


class UnitMemoryResultDict(TypedDict, total=False):
    quality: list[int]
    translation: list[str]
    origin: list[BatchMachineTranslation | None]


DownloadTranslations: TypeAlias = Iterable[TranslationResultDict]
DownloadMultipleTranslations: TypeAlias = dict[str, list[TranslationResultDict]]
