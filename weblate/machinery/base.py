# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Base code for machine translation services."""

from __future__ import annotations

import random
import re
import time
from collections import defaultdict
from collections.abc import Iterable, Iterator
from hashlib import md5
from html import escape, unescape
from itertools import chain
from typing import TYPE_CHECKING, TypedDict
from urllib.parse import quote

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.functional import cached_property
from django.utils.translation import gettext
from requests.exceptions import HTTPError, RequestException

from weblate.checks.utils import highlight_string
from weblate.lang.models import Language, PluralMapper
from weblate.utils.errors import report_error
from weblate.utils.hash import calculate_dict_hash, calculate_hash, hash_to_checksum
from weblate.utils.requests import request
from weblate.utils.search import Comparer
from weblate.utils.site import get_site_url

if TYPE_CHECKING:
    from requests.auth import AuthBase

    from weblate.auth.models import User
    from weblate.machinery.forms import BaseMachineryForm
    from weblate.trans.models import Unit


def get_machinery_language(language):
    if language.code.endswith("_devel"):
        return Language.objects.get(code=language.code[:-6])
    return language


class MachineTranslationError(Exception):
    """Generic Machine translation error."""


class MachineryRateLimitError(MachineTranslationError):
    """Raised when rate limiting is detected."""


class UnsupportedLanguageError(MachineTranslationError):
    """Raised when language is not supported."""


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


class TranslationResultDict(TypedDict, total=False):
    text: str
    quality: int
    service: str
    source: str
    # TODO: only following are actually optional, but this can be specified
    # in Python 3.11+, mark these by NotRequired
    show_quality: bool
    origin: str
    origin_url: str


class UnitMemoryResultDict(TypedDict, total=False):
    quality: list[int]
    translation: list[str]
    origin: list[None | BatchMachineTranslation]


DownloadTranslations = Iterable[TranslationResultDict]
DownloadMultipleTranslations = dict[str, list[TranslationResultDict]]


class BatchMachineTranslation:
    """Generic object for machine translation services."""

    name = "MT"
    max_score = 100
    rank_boost = 0
    cache_translations = True
    language_map: dict[str, str] = {}
    same_languages = False
    do_cleanup = True
    # Batch size is currently used in autotranslate
    batch_size = 20
    accounting_key = "external"
    force_uncleanup = False
    hightlight_syntax = False
    settings_form: None | type[BaseMachineryForm] = None
    request_timeout = 5
    is_available = True
    replacement_start = "[X"
    replacement_end = "X]"

    @classmethod
    def get_rank(cls):
        return cls.max_score + cls.rank_boost

    def __init__(self, settings: SettingsDict) -> None:
        """Create new machine translation object."""
        self.mtid = self.get_identifier()
        self.rate_limit_cache = f"{self.mtid}-rate-limit"
        self.languages_cache = f"{self.mtid}-languages"
        self.comparer = Comparer()
        self.supported_languages_error: None | Exception = None
        self.supported_languages_error_age: float = 0
        self.settings = settings

    def delete_cache(self) -> None:
        cache.delete_many([self.rate_limit_cache, self.languages_cache])

    def validate_settings(self) -> None:
        try:
            self.download_languages()
        except Exception as error:
            raise ValidationError(
                gettext("Could not fetch supported languages: %s") % error
            ) from error
        try:
            self.download_multiple_translations("en", "de", [("test", None)], None, 75)
        except Exception as error:
            raise ValidationError(
                gettext("Could not fetch translation: %s") % error
            ) from error

    @property
    def api_base_url(self):
        base = self.settings["url"]
        if base.endswith("/"):
            base = base.rstrip("/")
        return base

    def get_api_url(self, *parts):
        """Generate service URL gracefully handle trailing slashes."""
        return "/".join(
            chain([self.api_base_url], (quote(part, b"") for part in parts))
        )

    @classmethod
    def get_identifier(cls):
        return cls.name.lower().replace(" ", "-")

    @classmethod
    def get_doc_anchor(cls) -> str:
        return f"mt-{cls.get_identifier()}"

    def account_usage(self, project, delta: int = 1) -> None:
        key = f"machinery-accounting:{self.accounting_key}:{project.id}"
        try:
            cache.incr(key, delta=delta)
        except ValueError:
            cache.set(key, delta, 24 * 3600)

    def get_headers(self) -> dict[str, str]:
        """Add authentication headers to request."""
        return {}

    def get_auth(self) -> None | tuple[str, str] | AuthBase:
        return None

    def check_failure(self, response) -> None:
        # Directly raise error as last resort, subclass can prepend this
        # with something more clever
        response.raise_for_status()

    def request(self, method, url, skip_auth=False, **kwargs):
        """Perform JSON request."""
        # Create custom headers
        headers = {
            "Referer": get_site_url(),
            "Accept": "application/json; charset=utf-8",
        }
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        # Optional authentication
        if not skip_auth:
            headers.update(self.get_headers())

        # Fire request
        response = request(
            method,
            url,
            headers=headers,
            timeout=self.request_timeout,
            auth=self.get_auth(),
            **kwargs,
        )

        self.check_failure(response)

        return response

    def download_languages(self):
        """Download list of supported languages from a service."""
        return []

    def map_language_code(self, code: str) -> str:
        """Map language code to service specific."""
        if code.endswith("_devel"):
            code = code[:-6]
        if code in self.language_map:
            return self.language_map[code]
        return code

    def report_error(
        self, cause: str, extra_log: str | None = None, message: bool = False
    ) -> None:
        """Report error situations."""
        report_error(
            f"machinery[{self.name}]: {cause}", extra_log=extra_log, message=message
        )

    @cached_property
    def supported_languages(self):
        """Return list of supported languages."""
        # Try using list from cache
        languages_cache = cache.get(self.languages_cache)
        if languages_cache is not None:
            # hiredis-py 3 makes list from set
            return set(languages_cache)

        if self.is_rate_limited():
            return set()

        # Download
        try:
            languages = set(self.download_languages())
        except Exception as exc:
            self.supported_languages_error = exc
            self.supported_languages_error_age = time.time()
            self.report_error("Could not fetch languages, using defaults")
            return set()

        # Update cache
        cache.set(self.languages_cache, languages, 3600 * 48)
        return languages

    def is_supported(self, source, language):
        """Check whether given language combination is supported."""
        return (
            language in self.supported_languages
            and source in self.supported_languages
            and source != language
        )

    def is_rate_limited(self):
        return cache.get(self.rate_limit_cache, False)

    def set_rate_limit(self):
        return cache.set(self.rate_limit_cache, True, 1800)

    def is_rate_limit_error(self, exc) -> bool:
        if isinstance(exc, MachineryRateLimitError):
            return True
        if not isinstance(exc, HTTPError):
            return False
        # Apply rate limiting for following status codes:
        # HTTP 456 Client Error: Quota Exceeded (DeepL)
        # HTTP 429 Too Many Requests
        # HTTP 401 Unauthorized
        # HTTP 403 Forbidden
        # HTTP 503 Service Unavailable
        return exc.response.status_code in {456, 429, 401, 403, 503}

    def get_cache_key(
        self, scope: str, *, parts: Iterable[str | int] = (), text: None | str = None
    ) -> str:
        """
        Cache key for caching translations.

        Used to avoid fetching same translations again.

        This includes project ID for project scoped entries via
        Project.get_machinery_settings.
        """
        key = [
            "mt",
            self.mtid,
            scope,
            calculate_dict_hash(self.settings),
            *parts,
        ]
        if text is not None:
            key.append(calculate_hash(text))

        return ":".join(str(part) for part in key)

    def unescape_text(self, text: str):
        """Unescaping of the text with replacements."""
        return text

    def escape_text(self, text: str):
        """Escaping of the text with replacements."""
        return text

    def make_re_placeholder(self, text: str):
        """Convert placeholder into a regular expression."""
        # Allow additional space before ]
        return re.escape(text[:-1]) + " *" + re.escape(text[-1:])

    def format_replacement(
        self, h_start: int, h_end: int, h_text: str, h_kind: None | Unit
    ) -> str:
        """Generate a single replacement."""
        return f"{self.replacement_start}{h_start}{self.replacement_end}"

    def get_highlights(
        self, text: str, unit
    ) -> Iterable[tuple[int, int, str, None | Unit]]:
        for h_start, h_end, h_text in highlight_string(
            text, unit, hightlight_syntax=self.hightlight_syntax
        ):
            yield h_start, h_end, h_text, None

    def cleanup_text(self, text: str, unit: Unit) -> tuple[str, dict[str, str]]:
        """Remove placeholder to avoid confusing the machine translation."""
        replacements: dict[str, str] = {}
        if not self.do_cleanup:
            return text, replacements

        parts = []
        start = 0
        for h_start, h_end, h_text, h_kind in self.get_highlights(text, unit):
            parts.append(self.escape_text(text[start:h_start]))
            h_text = self.escape_text(h_text)
            placeholder = self.format_replacement(h_start, h_end, h_text, h_kind)
            replacements[placeholder] = h_text
            parts.append(placeholder)
            start = h_end

        parts.append(self.escape_text(text[start:]))

        return "".join(parts), replacements

    def uncleanup_text(self, replacements: dict[str, str], text: str) -> str:
        for source, target in replacements.items():
            text = re.sub(self.make_re_placeholder(source), target, text)
        return self.unescape_text(text)

    def uncleanup_results(
        self, replacements: dict[str, str], results: list[TranslationResultDict]
    ) -> None:
        """Reverts replacements done by cleanup_text."""
        for result in results:
            result["text"] = self.uncleanup_text(replacements, result["text"])
            result["source"] = self.uncleanup_text(replacements, result["source"])

    def get_language_possibilities(self, language: Language) -> Iterator[str]:
        code = language.code
        mapped_code = self.map_language_code(code)
        if not mapped_code:
            return
        yield mapped_code
        code = code.replace("-", "_")
        while "_" in code:
            code = code.rsplit("_", 1)[0]
            yield self.map_language_code(code)

    def get_languages(
        self, source_language: Language, target_language: Language
    ) -> tuple[str, str]:
        if source_language == target_language and not self.same_languages:
            raise UnsupportedLanguageError("Same languages")

        for source in self.get_language_possibilities(source_language):
            for target in self.get_language_possibilities(target_language):
                if self.is_supported(source, target):
                    return source, target

        if self.supported_languages_error:
            if self.supported_languages_error_age + 3600 > time.time():
                raise MachineTranslationError(repr(self.supported_languages_error))
            self.supported_languages_error = None
            self.supported_languages_error_age = 0

        raise UnsupportedLanguageError("Not supported")

    def get_cached(self, source, language, text, threshold, replacements):
        if not self.cache_translations:
            return None, None
        cache_key = self.get_cache_key(
            "translation", parts=(source, language, threshold), text=text
        )
        result = cache.get(cache_key)
        if result and (replacements or self.force_uncleanup):
            self.uncleanup_results(replacements, result)
        return cache_key, result

    def search(self, unit, text, user: User):
        """Search for known translations of `text`."""
        translation = unit.translation
        try:
            source, language = self.get_languages(
                translation.component.source_language, translation.language
            )
        except UnsupportedLanguageError:
            unit.translation.log_debug(
                "machinery failed: not supported language pair: %s - %s",
                translation.component.source_language.code,
                translation.language.code,
            )
            return []

        self.account_usage(translation.component.project)
        return self._translate(source, language, [(text, unit)], user, threshold=10)[
            text
        ]

    def translate(self, unit, user=None, threshold: int = 75):
        """Return list of machine translations."""
        translation = unit.translation
        try:
            source, language = self.get_languages(
                translation.component.source_language, translation.language
            )
        except UnsupportedLanguageError:
            unit.translation.log_debug(
                "machinery failed: not supported language pair: %s - %s",
                translation.component.source_language.code,
                translation.language.code,
            )
            return []

        self.account_usage(translation.component.project)

        source_plural = translation.component.source_language.plural
        target_plural = translation.plural
        plural_mapper = PluralMapper(source_plural, target_plural)
        plural_mapper.map_units([unit])
        translations = self._translate(
            source,
            language,
            [(text, unit) for text in unit.plural_map],
            user,
            threshold=threshold,
        )
        return [translations[text] for text in unit.plural_map]

    def download_multiple_translations(
        self,
        source,
        language,
        sources: list[tuple[str, Unit | None]],
        user=None,
        threshold: int = 75,
    ) -> DownloadMultipleTranslations:
        """
        Download dictionary of a lists of possible translations from a service.

        Should return dict with translation text, translation quality, source of
        translation, source string.

        You can use self.name as source of translation, if you can not give
        better hint and text parameter as source string if you do no fuzzy
        matching.
        """
        raise NotImplementedError

    def _translate(
        self,
        source,
        language,
        sources: list[tuple[str, Unit]],
        user=None,
        threshold: int = 75,
    ) -> DownloadMultipleTranslations:
        output: DownloadMultipleTranslations = {}
        pending = defaultdict(list)
        for text, unit in sources:
            original_source = text
            text, replacements = self.cleanup_text(text, unit)

            if not text or self.is_rate_limited():
                output[original_source] = []
                continue

            # Try cached results
            cache_key, result = self.get_cached(
                source, language, text, threshold, replacements
            )
            if result is not None:
                output[original_source] = result
                continue

            pending[text].append((unit, original_source, replacements))

        # Fetch pending strings to translate
        if pending:
            # Unit is only used in WeblateMemory and it is used only to get a project
            # so it doesn't matter we potentionally flatten this.
            try:
                translations = self.download_multiple_translations(
                    source,
                    language,
                    [
                        (text, occurrences[0][0])
                        for text, occurrences in pending.items()
                    ],
                    user,
                    threshold,
                )
            except Exception as exc:
                if self.is_rate_limit_error(exc):
                    self.set_rate_limit()

                self.report_error("Could not fetch translations")
                if isinstance(exc, MachineTranslationError):
                    raise
                raise MachineTranslationError(self.get_error_message(exc)) from exc

            # Postprocess translations
            for text, result in translations.items():
                for _unit, original_source, replacements in pending[text]:
                    # Always operate on copy of the dictionaries
                    partial = [x.copy() for x in result]

                    for item in partial:
                        item["original_source"] = original_source
                    if cache_key:
                        cache.set(cache_key, partial, 30 * 86400)
                    if replacements or self.force_uncleanup:
                        self.uncleanup_results(replacements, partial)
                    output[original_source] = partial
        return output

    def get_error_message(self, exc: Exception) -> str:
        if isinstance(exc, RequestException) and exc.response and exc.response.text:
            return f"{exc.__class__.__name__}: {exc}: {exc.response.text}"
        return f"{exc.__class__.__name__}: {exc}"

    def signed_salt(self, appid, secret, text):
        """Generate salt and sign as used by Chinese services."""
        salt = str(random.randint(0, 10000000000))  # noqa: S311

        payload = appid + text + salt + secret
        digest = md5(payload.encode(), usedforsecurity=False).hexdigest()

        return salt, digest

    def batch_translate(self, units, user=None, threshold: int = 75) -> None:
        try:
            translation = units[0].translation
        except IndexError:
            return
        try:
            source, language = self.get_languages(
                translation.component.source_language, translation.language
            )
        except UnsupportedLanguageError:
            return

        self.account_usage(translation.component.project, delta=len(units))

        source_plural = translation.component.source_language.plural
        target_plural = translation.plural
        plural_mapper = PluralMapper(source_plural, target_plural)
        plural_mapper.map_units(units)

        sources = [(text, unit) for unit in units for text in unit.plural_map]
        translations = self._translate(source, language, sources, user, threshold)

        for unit in units:
            result: UnitMemoryResultDict = unit.machinery
            if min(result.get("quality", ()), default=0) >= self.max_score:
                continue
            translation_lists = [translations[text] for text in unit.plural_map]
            plural_count = len(translation_lists)
            translation = result.setdefault("translation", [""] * plural_count)
            quality = result.setdefault("quality", [0] * plural_count)
            origin = result.setdefault("origin", [None] * plural_count)
            for plural, possible_translations in enumerate(translation_lists):
                for item in possible_translations:
                    if quality[plural] > item["quality"]:
                        continue
                    quality[plural] = item["quality"]
                    translation[plural] = item["text"]
                    origin[plural] = self

    @cached_property
    def user(self):
        """Weblate user used to track changes by this engine."""
        from weblate.auth.models import User

        return User.objects.get_or_create_bot("mt", self.get_identifier(), self.name)


class MachineTranslation(BatchMachineTranslation):
    def download_translations(
        self,
        source,
        language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ) -> DownloadTranslations:
        """
        Download list of possible translations from a service.

        Should return dict with translation text, translation quality, source of
        translation, source string.

        You can use self.name as source of translation, if you can not give
        better hint and text parameter as source string if you do no fuzzy
        matching.
        """
        raise NotImplementedError

    def download_multiple_translations(
        self,
        source,
        language,
        sources: list[tuple[str, Unit | None]],
        user=None,
        threshold: int = 75,
    ) -> DownloadMultipleTranslations:
        return {
            text: list(
                self.download_translations(
                    source, language, text, unit, user, threshold=threshold
                )
            )
            for text, unit in sources
        }


class InternalMachineTranslation(MachineTranslation):
    do_cleanup = False
    accounting_key = "internal"
    cache_translations = False

    def is_supported(self, source: Language, language: Language) -> bool:
        """Any language is supported."""
        return True

    def is_rate_limited(self) -> bool:
        """Disable rate limiting."""
        return False

    def get_language_possibilities(self, language: Language) -> Iterator[Language]:
        yield get_machinery_language(language)


class GlossaryMachineTranslationMixin(MachineTranslation):
    glossary_name_format = (
        "weblate:{project}:{source_language}:{target_language}:{checksum}"
    )
    glossary_count_limit = 0

    def is_glossary_supported(self, source_language: str, target_language: str) -> bool:
        return True

    def list_glossaries(self) -> dict[str, str]:
        """
        List glossaries from the service.

        Returns dictionary with names and id.
        """
        raise NotImplementedError

    def delete_glossary(self, glossary_id: str) -> None:
        raise NotImplementedError

    def delete_oldest_glossary(self) -> None:
        raise NotImplementedError

    def create_glossary(
        self, source_language: str, target_language: str, name: str, tsv: str
    ) -> None:
        raise NotImplementedError

    def get_glossaries(self, use_cache: bool = True):
        cache_key = self.get_cache_key("glossaries")
        if use_cache:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

        result = self.list_glossaries()

        cache.set(cache_key, result, 24 * 3600)
        return result

    def get_glossary_id(
        self, source_language: str, target_language: str, unit: Unit | None
    ) -> int | str | None:
        from weblate.glossary.models import get_glossary_tsv

        if unit is None:
            return None

        translation = unit.translation

        # Check glossary support for a language pair
        if not self.is_glossary_supported(source_language, target_language):
            return None

        # Check if there is a glossary
        glossary_tsv = get_glossary_tsv(translation)
        if not glossary_tsv:
            return None

        # Calculate hash to check for changes
        glossary_checksum = hash_to_checksum(calculate_hash(glossary_tsv))
        glossary_name = self.glossary_name_format.format(
            project=translation.component.project.id,
            source_language=source_language,
            target_language=target_language,
            checksum=glossary_checksum,
        )

        # Fetch list of glossaries
        glossaries = self.get_glossaries()
        if glossary_name in glossaries:
            return glossaries[glossary_name]

        # Remove stale glossaries for this language pair
        hashless_name = self.glossary_name_format.format(
            project=translation.component.project.id,
            source_language=source_language,
            target_language=target_language,
            checksum="",
        )
        for name, glossary_id in glossaries.items():
            if name.startswith(hashless_name):
                translation.log_debug(
                    "%s: removing stale glossary %s (%s)", self.mtid, name, glossary_id
                )
                self.delete_glossary(glossary_id)

        # Ensure we are in service limits
        if (
            self.glossary_count_limit
            and len(glossaries) + 1 >= self.glossary_count_limit
        ):
            translation.log_debug(
                "%s: approached limit of %d glossaries, removing oldest glossary",
                self.mtid,
                self.glossary_count_limit,
            )
            self.delete_oldest_glossary()

        # Create new glossary
        translation.log_debug("%s: creating glossary %s", self.mtid, glossary_name)
        self.create_glossary(
            source_language, target_language, glossary_name, glossary_tsv
        )

        # Fetch glossaries again, without using cache
        glossaries = self.get_glossaries(use_cache=False)
        return glossaries[glossary_name]


class XMLMachineTranslationMixin:
    hightlight_syntax = True

    def unescape_text(self, text: str) -> str:
        """Unescaping of the text with replacements."""
        return unescape(text)

    def escape_text(self, text: str) -> str:
        """Escaping of the text with replacements."""
        return escape(text)

    def format_replacement(
        self, h_start: int, h_end: int, h_text: str, h_kind: None | Unit
    ) -> str:
        """Generate a single replacement."""
        raise NotImplementedError

    def make_re_placeholder(self, text: str) -> str:
        return re.escape(text)


class ResponseStatusMachineTranslation(MachineTranslation):
    def check_failure(self, response) -> None:
        payload = response.json()

        # Check response status
        if payload["responseStatus"] != 200:
            raise MachineTranslationError(payload["responseDetails"])

        super().check_failure(response)
