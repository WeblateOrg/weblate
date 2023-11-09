# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Base code for machine translation services."""

from __future__ import annotations

import random
import re
import time
from hashlib import md5
from itertools import chain
from urllib.parse import quote

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.functional import cached_property
from django.utils.translation import gettext
from requests.exceptions import HTTPError

from weblate.checks.utils import highlight_string
from weblate.lang.models import Language, PluralMapper
from weblate.logger import LOGGER
from weblate.utils.errors import report_error
from weblate.utils.hash import calculate_hash
from weblate.utils.requests import request
from weblate.utils.search import Comparer
from weblate.utils.site import get_site_url


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


class MachineTranslation:
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
    settings_form = None
    validate_payload = ("en", "de", "test", None, None, 75)
    request_timeout = 5

    @classmethod
    def get_rank(cls):
        return cls.max_score + cls.rank_boost

    def __init__(self, settings: dict[str, str]):
        """Create new machine translation object."""
        self.mtid = self.get_identifier()
        self.rate_limit_cache = f"{self.mtid}-rate-limit"
        self.languages_cache = f"{self.mtid}-languages"
        self.comparer = Comparer()
        self.supported_languages_error = None
        self.supported_languages_error_age = 0
        self.settings = settings

    def delete_cache(self):
        cache.delete_many([self.rate_limit_cache, self.languages_cache])

    def validate_settings(self):
        try:
            self.download_languages()
        except Exception as error:
            raise ValidationError(
                gettext("Could not fetch supported languages: %s") % error
            )
        try:
            self.download_translations(*self.validate_payload)
        except Exception as error:
            raise ValidationError(gettext("Could not fetch translation: %s") % error)

    @property
    def api_base_url(self):
        base = self.settings["url"]
        if base.endswith("/"):
            base = base.rstrip("/")
        return base

    def get_api_url(self, *parts):
        """Generates service URL gracefully handle trailing slashes."""
        return "/".join(
            chain([self.api_base_url], (quote(part, b"") for part in parts))
        )

    @classmethod
    def get_identifier(cls):
        return cls.name.lower().replace(" ", "-")

    @classmethod
    def get_doc_anchor(cls):
        return f"mt-{cls.get_identifier()}"

    def account_usage(self, project, delta: int = 1):
        key = f"machinery-accounting:{self.accounting_key}:{project.id}"
        try:
            cache.incr(key, delta=delta)
        except ValueError:
            cache.set(key, delta, 24 * 3600)

    def get_authentication(self):
        """Hook for backends to allow add authentication headers to request."""
        return {}

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
            headers.update(self.get_authentication())

        # Fire request
        response = request(
            method, url, headers=headers, timeout=self.request_timeout, **kwargs
        )

        # Directly raise error when response is empty
        if response.content:
            response.raise_for_status()

        return response

    def request_status(self, method, url, **kwargs):
        response = self.request(method, url, **kwargs)
        payload = response.json()

        # Check response status
        if payload["responseStatus"] != 200:
            raise MachineTranslationError(payload["responseDetails"])

        # Return data
        return payload

    def download_languages(self):
        """Download list of supported languages from a service."""
        return []

    def download_translations(
        self,
        source,
        language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ):
        """
        Download list of possible translations from a service.

        Should return dict with translation text, translation quality, source of
        translation, source string.

        You can use self.name as source of translation, if you can not give
        better hint and text parameter as source string if you do no fuzzy
        matching.
        """
        raise NotImplementedError

    def map_language_code(self, code):
        """Map language code to service specific."""
        if code.endswith("_devel"):
            code = code[:-6]
        if code in self.language_map:
            return self.language_map[code]
        return code

    def report_error(self, message):
        """Wrapper for handling error situations."""
        report_error(cause="Machinery error")
        LOGGER.error(message, self.name)

    @cached_property
    def supported_languages(self):
        """Return list of supported languages."""
        # Try using list from cache
        languages = cache.get(self.languages_cache)
        if languages is not None:
            return languages

        if self.is_rate_limited():
            return set()

        # Download
        try:
            languages = set(self.download_languages())
        except Exception as exc:
            self.supported_languages_error = exc
            self.supported_languages_error_age = time.time()
            self.report_error("Could not fetch languages from %s, using defaults")
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

    def is_rate_limit_error(self, exc):
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
        if exc.response.status_code in (456, 429, 401, 403, 503):
            return True
        return False

    def translate_cache_key(self, source, language, text, threshold):
        return "mt:{}:{}:{}:{}".format(
            self.mtid,
            calculate_hash(source, language),
            calculate_hash(text),
            threshold,
        )

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

    def format_replacement(self, h_start: int, h_end: int, h_text: str):
        """Generates a single replacement."""
        return f"[X{h_start}X]"

    def cleanup_text(self, text, unit):
        """Removes placeholder to avoid confusing the machine translation."""
        replacements = {}
        if not self.do_cleanup:
            return text, replacements

        highlights = highlight_string(
            text, unit, hightlight_syntax=self.hightlight_syntax
        )
        parts = []
        start = 0
        for h_start, h_end, h_text in highlights:
            parts.append(self.escape_text(text[start:h_start]))
            h_text = self.escape_text(h_text)
            placeholder = self.format_replacement(h_start, h_end, h_text)
            replacements[placeholder] = h_text
            parts.append(placeholder)
            start = h_end

        parts.append(self.escape_text(text[start:]))

        return "".join(parts), replacements

    def uncleanup_text(self, replacements: dict[str, str], text: str) -> str:
        for source, target in replacements.items():
            text = re.sub(self.make_re_placeholder(source), target, text)
        return self.unescape_text(text)

    def uncleanup_results(self, replacements: dict[str, str], results: list[str]):
        """Reverts replacements done by cleanup_text."""
        keys = ("text", "source")
        for result in results:
            for key in keys:
                result[key] = self.uncleanup_text(replacements, result[key])

    def get_language_possibilities(self, language):
        code = language.code
        yield self.map_language_code(code)
        code = code.replace("-", "_")
        while "_" in code:
            code = code.rsplit("_", 1)[0]
            yield self.map_language_code(code)

    def get_languages(self, source_language, target_language):
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
        cache_key = self.translate_cache_key(source, language, text, threshold)
        result = cache.get(cache_key)
        if result and (replacements or self.force_uncleanup):
            self.uncleanup_results(replacements, result)
        return cache_key, result

    def search(self, unit, text, user):
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
        return self._translate(source, language, text, unit, user, threshold=10)

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
        return [
            self._translate(source, language, text, unit, user, threshold=threshold)
            for text in plural_mapper.map(unit)
        ]

    def _translate(self, source, language, text, unit, user=None, threshold: int = 75):
        original_source = text
        text, replacements = self.cleanup_text(text, unit)

        if not text or self.is_rate_limited():
            return []

        cache_key, result = self.get_cached(
            source, language, text, threshold, replacements
        )
        if result is not None:
            return result

        try:
            result = [
                item
                for item in self.download_translations(
                    source,
                    language,
                    text,
                    unit,
                    user,
                    threshold=threshold,
                )
                if item["quality"] >= threshold
            ]
        except Exception as exc:
            if self.is_rate_limit_error(exc):
                self.set_rate_limit()

            self.report_error("Could not fetch translations from %s")
            if isinstance(exc, MachineTranslationError):
                raise
            raise MachineTranslationError(self.get_error_message(exc)) from exc
        for item in result:
            item["original_source"] = original_source
        if cache_key:
            cache.set(cache_key, result, 30 * 86400)
        if replacements or self.force_uncleanup:
            self.uncleanup_results(replacements, result)
        return result

    def get_error_message(self, exc):
        return f"{exc.__class__.__name__}: {exc}"

    def signed_salt(self, appid, secret, text):
        """Generates salt and sign as used by Chinese services."""
        salt = str(random.randint(0, 10000000000))  # noqa: S311

        payload = appid + text + salt + secret
        digest = md5(payload.encode(), usedforsecurity=False).hexdigest()

        return salt, digest

    def batch_translate(self, units, user=None, threshold: int = 75):
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
        for unit in units:
            result = unit.machinery
            if result is None:
                result = unit.machinery = {}
            elif min(result.get("quality", ()), default=0) >= self.max_score:
                continue
            translation_lists = [
                self._translate(source, language, text, unit, user, threshold=threshold)
                for text in plural_mapper.map(unit)
            ]
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


class InternalMachineTranslation(MachineTranslation):
    do_cleanup = False
    accounting_key = "internal"
    cache_translations = False

    def is_supported(self, source, language):
        """Any language is supported."""
        return True

    def is_rate_limited(self):
        """Disable rate limiting."""
        return False

    def get_language_possibilities(self, language):
        yield get_machinery_language(language)
