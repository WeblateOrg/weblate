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
"""Base code for machine translation services."""

import random
import time
from hashlib import md5
from typing import Dict, List

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from requests.exceptions import HTTPError

from weblate.checks.utils import highlight_string
from weblate.lang.models import Language
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


class MachineryRateLimit(MachineTranslationError):
    """Raised when rate limiting is detected."""


class UnsupportedLanguage(MachineTranslationError):
    """Raised when language is not supported."""


class MachineTranslation:
    """Generic object for machine translation services."""

    name = "MT"
    max_score = 100
    rank_boost = 0
    cache_translations = True
    language_map: Dict[str, str] = {}
    same_languages = False
    do_cleanup = True
    batch_size = 20
    accounting_key = "external"
    force_uncleanup = False
    hightlight_syntax = False
    settings_form = None
    validate_payload = ("en", "de", "test", None, None, False, 75)

    @classmethod
    def get_rank(cls):
        return cls.max_score + cls.rank_boost

    def __init__(self, settings: Dict[str, str]):
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

    @staticmethod
    def migrate_settings():
        # TODO: Drop in Weblate 5.1
        return {}

    def validate_settings(self):
        try:
            self.download_languages()
        except Exception as error:
            raise ValidationError(_("Failed to fetch supported languages: %s") % error)
        try:
            self.download_translations(*self.validate_payload)
        except Exception as error:
            raise ValidationError(_("Failed to fetch translation: %s") % error)

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
            cache.set(key, delta)

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
        response = request(method, url, headers=headers, timeout=5.0, **kwargs)

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
        search: bool,
        threshold: int = 75,
    ):
        """Download list of possible translations from a service.

        Should return dict with translation text, translation quality, source of
        translation, source string.

        You can use self.name as source of translation, if you can not give
        better hint and text parameter as source string if you do no fuzzy
        matching.
        """
        raise NotImplementedError()

    def map_language_code(self, code):
        """Map language code to service specific."""
        if code.endswith("_devel"):
            code = code[:-6]
        if code in self.language_map:
            return self.language_map[code]
        return code

    def convert_language(self, language):
        """Convert language to service specific object."""
        return self.map_language_code(language.code)

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
            self.report_error("Failed to fetch languages from %s, using defaults")
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
        if isinstance(exc, MachineryRateLimit):
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
        if not self.cache_translations:
            return None
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

    def format_replacement(self, h_start: int, h_end: int, h_text: str):
        """Generates a single replacement."""
        return f"[X{h_start}X]"

    def cleanup_text(self, unit):
        """Removes placeholder to avoid confusing the machine translation."""
        text = unit.source_string
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

    def uncleanup_results(self, replacements: Dict[str, str], results: List[str]):
        """Reverts replacements done by cleanup_text."""
        keys = ("text", "source")
        for result in results:
            for key in keys:
                text = result[key]
                for source, target in replacements.items():
                    text = text.replace(source, target)
                result[key] = self.unescape_text(text)

    def get_variants(self, language):
        code = self.convert_language(language)
        yield code
        if not isinstance(code, str):
            return
        code = code.replace("-", "_")
        if "_" in code:
            yield code.split("_")[0]

    def get_languages(self, source_language, target_language):

        if source_language == target_language and not self.same_languages:
            raise UnsupportedLanguage("Same languages")

        for source in self.get_variants(source_language):
            for target in self.get_variants(target_language):
                if self.is_supported(source, target):
                    return source, target

        if self.supported_languages_error:
            if self.supported_languages_error_age + 3600 > time.time():
                raise MachineTranslationError(repr(self.supported_languages_error))
            self.supported_languages_error = None
            self.supported_languages_error_age = 0

        raise UnsupportedLanguage("Not supported")

    def get_cached(self, source, language, text, threshold, replacements):
        cache_key = self.translate_cache_key(source, language, text, threshold)
        if cache_key:
            result = cache.get(cache_key)
            if result and (replacements or self.force_uncleanup):
                self.uncleanup_results(replacements, result)
            return cache_key, result
        return cache_key, None

    def translate(self, unit, user=None, search=None, threshold: int = 75):
        """Return list of machine translations."""
        translation = unit.translation
        try:
            source, language = self.get_languages(
                translation.component.source_language, translation.language
            )
        except UnsupportedLanguage:
            unit.translation.log_debug(
                "machinery failed: not supported language pair: %s - %s",
                translation.component.source_language.code,
                translation.language.code,
            )
            return []

        self.account_usage(translation.component.project)
        return self._translate(source, language, unit, user, search, threshold)

    def _translate(
        self, source, language, unit, user=None, search=None, threshold: int = 75
    ):
        if search:
            replacements = {}
            text = search
        else:
            text, replacements = self.cleanup_text(unit)

        if not text or self.is_rate_limited():
            return []

        cache_key, result = self.get_cached(
            source, language, text, threshold, replacements
        )
        if result is not None:
            return result

        try:
            result = list(
                self.download_translations(
                    source,
                    language,
                    text,
                    unit,
                    user,
                    search=bool(search),
                    threshold=threshold,
                )
            )
            if replacements or self.force_uncleanup:
                self.uncleanup_results(replacements, result)
            if cache_key:
                cache.set(cache_key, result, 30 * 86400)
            return result
        except Exception as exc:
            if self.is_rate_limit_error(exc):
                self.set_rate_limit()

            self.report_error("Failed to fetch translations from %s")
            if isinstance(exc, MachineTranslationError):
                raise
            raise MachineTranslationError(self.get_error_message(exc))

    def get_error_message(self, exc):
        return f"{exc.__class__.__name__}: {exc}"

    def signed_salt(self, appid, secret, text):
        """Generates salt and sign as used by Chinese services."""
        salt = str(random.randint(0, 10000000000))

        payload = appid + text + salt + secret
        digest = md5(payload.encode()).hexdigest()  # nosec

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
        except UnsupportedLanguage:
            return

        self.account_usage(translation.component.project, delta=len(units))
        self._batch_translate(source, language, units, user=user, threshold=threshold)

    def _batch_translate(self, source, language, units, user=None, threshold: int = 75):
        for unit in units:
            result = unit.machinery
            if result["best"] >= self.max_score:
                continue
            for item in self._translate(
                source, language, unit, user=user, threshold=threshold
            ):
                if result["best"] > item["quality"]:
                    continue
                result["best"] = item["quality"]
                result["translation"] = item["text"]
