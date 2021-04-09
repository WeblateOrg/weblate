#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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
from hashlib import md5
from typing import Dict

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.utils.functional import cached_property
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
    if language.code == "en_devel":
        return Language.objects.english
    return language


class MachineTranslationError(Exception):
    """Generic Machine translation error."""


class MissingConfiguration(ImproperlyConfigured):
    """Exception raised when configuraiton is wrong."""


class MachineryRateLimit(MachineTranslationError):
    """Raised when rate limiting is detected."""


class MachineTranslation:
    """Generic object for machine translation services."""

    name = "MT"
    max_score = 100
    rank_boost = 0
    cache_translations = True
    language_map: Dict[str, str] = {}
    same_languages = False
    do_cleanup = True

    @classmethod
    def get_rank(cls):
        return cls.max_score + cls.rank_boost

    def __init__(self):
        """Create new machine translation object."""
        self.mtid = self.name.lower().replace(" ", "-")
        self.rate_limit_cache = "{}-rate-limit".format(self.mtid)
        self.languages_cache = "{}-languages".format(self.mtid)
        self.comparer = Comparer()
        self.supported_languages_error = None

    def delete_cache(self):
        cache.delete_many([self.rate_limit_cache, self.languages_cache])

    def get_identifier(self):
        return self.mtid

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
        return request(method, url, headers=headers, timeout=5.0, **kwargs)

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

    def download_translations(self, source, language, text, unit, user, search):
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
        if code == "en_devel":
            code = "en"
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
        # HTTP 429 Too Many Requests
        # HTTP 401 Unauthorized
        # HTTP 403 Forbidden
        # HTTP 503 Service Unavailable
        if exc.response.status_code in (429, 401, 403, 503):
            return True
        return False

    def translate_cache_key(self, source, language, text):
        if not self.cache_translations:
            return None
        return "mt:{}:{}:{}".format(
            self.mtid, calculate_hash(source, language), calculate_hash(text)
        )

    def cleanup_text(self, unit):
        """Removes placeholder to avoid confusing the machine translation."""
        text = unit.source_string
        replacements = {}
        if not self.do_cleanup:
            return text, replacements

        highlights = highlight_string(text, unit)
        parts = []
        start = 0
        for h_start, h_end, h_text in highlights:
            parts.append(text[start:h_start])
            placeholder = f"[{h_start}]"
            replacements[placeholder] = h_text
            parts.append(placeholder)
            start = h_end

        parts.append(text[start:])

        return "".join(parts), replacements

    def uncleanup_results(self, replacements, results):
        """Reverts replacements done by cleanup_text."""
        keys = ["text", "source"]
        for result in results:
            for key in keys:
                text = result[key]
                for source, target in replacements.items():
                    text = text.replace(source, target)
                result[key] = text

    def translate(self, unit, user=None, search=None, language=None, source=None):
        """Return list of machine translations."""
        # source and language are set only for recursive calls when
        # tweaking the language codes
        if source is None:
            language = self.convert_language(unit.translation.language)
            source = self.convert_language(
                unit.translation.component.project.source_language
            )

        if search:
            replacements = {}
            text = search
        else:
            text, replacements = self.cleanup_text(unit)

        if (
            not text
            or self.is_rate_limited()
            or (source == language and not self.same_languages)
        ):
            return []

        if not self.is_supported(source, language):
            # Try without country code
            source = source.replace("-", "_")
            if "_" in source:
                source = source.split("_")[0]
                return self.translate(
                    unit, user=user, search=search, language=language, source=source
                )
            language = language.replace("-", "_")
            if "_" in language:
                language = language.split("_")[0]
                return self.translate(
                    unit, user=user, search=search, language=language, source=source
                )
            if self.supported_languages_error:
                raise MachineTranslationError(repr(self.supported_languages_error))
            return []

        cache_key = self.translate_cache_key(source, language, text)
        if cache_key:
            result = cache.get(cache_key)
            if result is not None:
                return result

        try:
            result = list(
                self.download_translations(
                    source, language, text, unit, user, search=bool(search)
                )
            )
            if replacements:
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
        return "{0}: {1}".format(exc.__class__.__name__, str(exc))

    def signed_salt(self, appid, secret, text):
        """Generates salt and sign as used by Chinese services."""
        salt = str(random.randint(0, 10000000000))

        payload = appid + text + salt + secret
        digest = md5(payload.encode()).hexdigest()  # nosec

        return salt, digest
