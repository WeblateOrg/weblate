# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import urlsplit, urlunsplit

from dateutil.parser import isoparse
from django.core.cache import cache
from requests.exceptions import HTTPError, RequestException

from .base import (
    MACHINERY_DEFAULT_THRESHOLD,
    BatchMachineTranslation,
    GlossaryAlreadyExistsError,
    GlossaryDoesNotExistError,
    GlossaryMachineTranslationMixin,
    MachineTranslationError,
    XMLMachineTranslationMixin,
)
from .forms import DeepLMachineryForm

if TYPE_CHECKING:
    from collections.abc import Iterator

    from weblate.auth.models import User
    from weblate.lang.models import Language
    from weblate.trans.models import Unit

    from .base import (
        DownloadMultipleTranslations,
    )


class DeepLTranslation(
    XMLMachineTranslationMixin, GlossaryMachineTranslationMixin, BatchMachineTranslation
):
    """DeepL (Linguee) machine translation support."""

    name = "DeepL"
    # This seems to be currently best MT service, so score it a bit
    # better than other ones.
    max_score = 91
    language_map: ClassVar[dict[str, str]] = {
        "pt@formal": "pt-pt@formal",
        "pt@informal": "pt-pt@informal",
    }
    target_language_map: ClassVar[dict[str, str]] = {
        "PT": "PT-PT",
    }
    trusted_error_hosts: ClassVar[set[str]] = {
        "api.deepl.com",
        "api-free.deepl.com",
    }
    highlight_syntax = True
    settings_form = DeepLMachineryForm
    glossary_count_limit = 1000
    glossary_languages_cache_version: ClassVar[int] = 2

    @property
    def api_base_url(self):
        url = super().api_base_url
        parsed = urlsplit(url)
        path = parsed.path.rstrip("/")
        path_parts = path.split("/")
        if (
            path_parts
            and path_parts[-1].startswith("v")
            and path_parts[-1][1:].isdigit()
        ):
            if path_parts[-1] == "v1":
                msg = "DeepL API v1 is no longer supported."
                raise MachineTranslationError(msg)
            parsed = parsed._replace(path="/".join(path_parts[:-1]))
        if self.settings["key"].endswith(":fx") and parsed.hostname == "api.deepl.com":
            return urlunsplit(parsed._replace(netloc="api-free.deepl.com"))
        return urlunsplit(parsed)

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("_", "-").upper()

    def get_language_possibilities(self, language: Language) -> Iterator[str]:
        for value in super().get_language_possibilities(language):
            yield value
            # Add variant without suffix, this is needed for source languages
            # as DeepL does not differentiate most language variants on the source
            # string side.
            if "-" in value:
                yield value.split("-", 1)[0]

    def get_target_language_possibilities(self, language: Language) -> Iterator[str]:
        seen: set[str] = set()
        base_code = self.map_language_code(language.code)

        for value in super().get_language_possibilities(language):
            if value not in seen:
                seen.add(value)
                yield value

        mapped_value = self.target_language_map.get(base_code)
        if mapped_value and mapped_value not in seen:
            yield mapped_value

    def get_headers(self) -> dict[str, str]:
        return {"Authorization": f"DeepL-Auth-Key {self.settings['key']}"}

    def delete_cache(self) -> None:
        """Delete general caches and DeepL-specific glossary support cache."""
        super().delete_cache()
        cache.delete(self.get_cache_key("glossary_languages"))
        cache.delete(self.get_glossary_languages_cache_key())

    def get_glossary_languages_cache_key(self) -> str:
        return self.get_cache_key(
            "glossary_languages", parts=(self.glossary_languages_cache_version,)
        )

    def get_error_message(self, exc):
        if isinstance(exc, RequestException) and exc.response is not None:
            try:
                data = exc.response.json()
            except ValueError:
                pass
            else:
                try:
                    return data["message"]
                except KeyError:
                    pass

        if isinstance(exc, HTTPError) and exc.response.status_code == 456:
            return "Quota exceeded. The character limit has been reached."

        return super().get_error_message(exc)

    def download_languages(self):
        response = self.request(
            "get",
            self.get_api_url("v3", "languages"),
            params={"resource": "translate_text"},
        )
        languages = response.json()

        source_languages = {
            item["lang"].upper() for item in languages if item["usable_as_source"]
        }
        # Plain English is not listed, but is supported
        target_languages = {"EN"}

        # Handle formality extensions
        for item in languages:
            if not item["usable_as_target"]:
                continue
            lang_code = item["lang"].upper()
            target_languages.add(lang_code)
            if "formality" in item.get("features", {}):
                target_languages.add(f"{lang_code}@FORMAL")
                target_languages.add(f"{lang_code}@INFORMAL")

        return (
            (source, target)
            for source in source_languages
            for target in target_languages
        )

    def is_supported(self, source_language, target_language):
        """Check whether given language combination is supported."""
        return (source_language, target_language) in self.supported_languages

    def download_multiple_translations(
        self,
        source_language,
        target_language,
        sources: list[tuple[str, Unit | None]],
        user: User | None = None,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
    ) -> DownloadMultipleTranslations:
        """Download list of possible translations from a service."""
        texts = [text for text, _unit in sources]
        unit = sources[0][1]

        glossary_id = self.get_glossary_id(source_language, target_language, unit)

        params = {
            "text": texts,
            "source_lang": source_language,
            "target_lang": target_language,
            "formality": self.settings.get("formality", "default"),
            "tag_handling": "xml",
            "ignore_tags": ["x"],
        }
        if context := self.settings.get("context", ""):
            params["context"] = context
        if target_language.endswith("@FORMAL"):
            params["target_lang"] = target_language[:-7]
            params["formality"] = "more"
        elif target_language.endswith("@INFORMAL"):
            params["target_lang"] = target_language[:-9]
            params["formality"] = "less"
        if glossary_id is not None:
            params["glossary_id"] = glossary_id
        if self.settings.get("next_gen"):
            params["model_type"] = "prefer_quality_optimized"

        response = self.request(
            "post",
            self.get_api_url("v2", "translate"),
            json=params,
        )
        payload = response.json()

        result: DownloadMultipleTranslations = {}
        for index, text in enumerate(texts):
            result[text] = [
                {
                    "text": payload["translations"][index]["text"],
                    "quality": self.max_score,
                    "service": self.name,
                    "source": text,
                }
            ]
        return result

    def format_replacement(
        self, h_start: int, h_end: int, h_text: str, h_kind: Unit | None
    ) -> str:
        """Generate a single replacement."""
        return f'<x id="{h_start}"></x>'

    def get_glossary_language_code(self, language: str) -> str:
        return language.split("-", 1)[0].lower()

    def get_glossary_dictionary(
        self, source_language: str, target_language: str, tsv: str
    ) -> dict[str, str]:
        return {
            "source_lang": self.get_glossary_language_code(source_language),
            "target_lang": self.get_glossary_language_code(target_language),
            "entries": tsv,
            "entries_format": "tsv",
        }

    def is_glossary_supported(self, source_language: str, target_language: str) -> bool:
        cache_key = self.get_glossary_languages_cache_key()
        languages_cache = cache.get(cache_key)
        if languages_cache is not None:
            source_languages, target_languages = languages_cache
        else:
            response = self.request(
                "get",
                self.get_api_url("v3", "languages"),
                params={"resource": "glossary"},
            )
            languages = response.json()
            source_languages = {
                language["lang"].upper()
                for language in languages
                if language["usable_as_source"]
            }
            target_languages = {
                language["lang"].upper()
                for language in languages
                if language["usable_as_target"]
            }

            cache.set(cache_key, (source_languages, target_languages), 24 * 3600)

        source_language = self.get_glossary_language_code(source_language).upper()
        target_language = target_language.upper()
        target_language_root = self.get_glossary_language_code(target_language).upper()
        return source_language in source_languages and (
            target_language in target_languages
            or target_language_root in target_languages
        )

    def list_glossaries(self) -> dict[str, str]:
        response = self.request("get", self.get_api_url("v3", "glossaries"))
        return {
            glossary["name"]: glossary["glossary_id"]
            for glossary in response.json()["glossaries"]
        }

    def delete_oldest_glossary(self) -> None:
        response = self.request("get", self.get_api_url("v3", "glossaries"))
        glossaries = sorted(
            response.json()["glossaries"],
            key=lambda glossary: isoparse(glossary["creation_time"]),
        )
        if glossaries:
            self.delete_glossary(glossaries[0]["glossary_id"])

    def delete_glossary(self, glossary_id: str) -> None:
        """
        Delete glossary from service.

        :param glossary_id: ID of the glossary to delete
        :raises GlossaryDoesNotExistError: If the glossary does not exist
        """
        try:
            self.request(
                "delete",
                self.get_api_url("v3", "glossaries", glossary_id),
            )
        except HTTPError as error:
            if error.response.status_code in {400, 404}:
                raise GlossaryDoesNotExistError from error

    def update_glossary(
        self,
        glossary_id: str,
        source_language: str,
        target_language: str,
        name: str,
        tsv: str,
    ) -> None:
        try:
            self.request(
                "put",
                self.get_api_url("v3", "glossaries", glossary_id, "dictionaries"),
                json=self.get_glossary_dictionary(
                    source_language, target_language, tsv
                ),
            )
            self.request(
                "patch",
                self.get_api_url("v3", "glossaries", glossary_id),
                json={"name": name},
            )
        except HTTPError as error:
            if error.response.status_code == 404:
                raise GlossaryDoesNotExistError from error
            raise

    def create_glossary(
        self, source_language: str, target_language: str, name: str, tsv: str
    ) -> None:
        self.request(
            "post",
            self.get_api_url("v3", "glossaries"),
            json={
                "name": name,
                "dictionaries": [
                    self.get_glossary_dictionary(source_language, target_language, tsv)
                ],
            },
        )

    def get_glossary_id(
        self, source_language: str, target_language: str, unit: Unit | None
    ) -> str | None:
        # ruff: ignore[import-outside-top-level]
        from weblate.glossary.models import get_glossary_tsv

        if unit is None:
            return None

        translation = unit.translation

        if not self.is_glossary_supported(source_language, target_language):
            return None

        glossary_tsv = get_glossary_tsv(translation)
        if not glossary_tsv:
            return None

        glossary_checksum = self.tsv_checksum(glossary_tsv)
        glossary_name = self.glossary_name_format.format(
            project=translation.component.project.id,
            source_language=source_language,
            target_language=target_language,
            checksum=glossary_checksum,
        )

        glossaries = self.get_glossaries()
        if glossary_name in glossaries:
            return glossaries[glossary_name]

        hashless_name = self.glossary_name_format.format(
            project=translation.component.project.id,
            source_language=source_language,
            target_language=target_language,
            checksum="",
        )
        stale_glossaries = [
            (name, glossary_id)
            for name, glossary_id in glossaries.items()
            if name.startswith(hashless_name)
        ]
        for name, glossary_id in stale_glossaries:
            translation.log_debug(
                "%s: updating stale glossary %s (%s)", self.mtid, name, glossary_id
            )
            with contextlib.suppress(GlossaryDoesNotExistError):
                self.update_glossary(
                    glossary_id,
                    source_language,
                    target_language,
                    glossary_name,
                    glossary_tsv,
                )
                glossaries = self.get_glossaries(use_cache=False)
                if glossary_name in glossaries:
                    return glossaries[glossary_name]

        for name, glossary_id in stale_glossaries:
            translation.log_debug(
                "%s: removing stale glossary %s (%s)", self.mtid, name, glossary_id
            )
            with contextlib.suppress(GlossaryDoesNotExistError):
                self.delete_glossary(glossary_id)

        glossary_count_limit = self.get_glossary_count_limit()
        if glossary_count_limit and len(glossaries) + 1 >= glossary_count_limit:
            translation.log_debug(
                "%s: approached limit of %d glossaries, removing oldest glossary",
                self.mtid,
                self.glossary_count_limit,
            )
            with contextlib.suppress(GlossaryDoesNotExistError):
                self.delete_oldest_glossary()

        translation.log_debug("%s: creating glossary %s", self.mtid, glossary_name)
        with contextlib.suppress(GlossaryAlreadyExistsError):
            self.create_glossary(
                source_language, target_language, glossary_name, glossary_tsv
            )

        glossaries = self.get_glossaries(use_cache=False)
        return glossaries[glossary_name]

    def get_glossary_count_limit(self) -> int:
        # Free tier has lower limit on glossaries
        if urlsplit(self.api_base_url).hostname == "api-free.deepl.com":
            return 1
        return super().get_glossary_count_limit()
