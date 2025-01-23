# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

from weblate.glossary.models import get_glossary_terms

from .base import (
    DownloadTranslations,
    MachineTranslation,
    MachineTranslationError,
    SettingsDict,
    XMLMachineTranslationMixin,
)
from .forms import MicrosoftMachineryForm

if TYPE_CHECKING:
    from weblate.trans.models import Unit

TOKEN_URL = "https://{0}{1}/sts/v1.0/issueToken?Subscription-Key={2}"  # noqa: S105
TOKEN_EXPIRY = timedelta(minutes=9)


class MicrosoftCognitiveTranslation(XMLMachineTranslationMixin, MachineTranslation):
    """Microsoft Cognitive Services Translator API support."""

    name = "Azure AI Translator"
    max_score = 90
    settings_form = MicrosoftMachineryForm

    language_map = {
        "zh_TW": "zh-Hant",
        "zh_CN": "zh-Hans",
        "yue_Hant": "yue",
        "tlh": "tlh-Latn",
        "tlh_Qaak": "tlh-Piqd",
        "lg": "lug",
        "mn": "mn-Cyrl",
        "pt_BR": "pt",
        "rn": "run",
        "sr": "sr-Cyrl",
    }

    @classmethod
    def get_identifier(cls) -> str:
        return "microsoft-translator"

    def __init__(self, settings: SettingsDict) -> None:
        """Check configuration."""
        super().__init__(settings)
        self._access_token: str | None = None
        self._token_expiry: datetime | None = None

        # check settings for Microsoft region prefix
        region = "" if not self.settings["region"] else f"{self.settings['region']}."

        self._cognitive_token_url = TOKEN_URL.format(
            region,
            self.settings["endpoint_url"],
            self.settings["key"],
        )

    def get_url(self, suffix) -> str:
        return f"https://{self.settings['base_url']}/{suffix}"

    def is_token_expired(self):
        """Check whether token is about to expire."""
        return self._token_expiry is None or self._token_expiry <= timezone.now()

    def get_headers(self) -> dict[str, str]:
        """Add authentication headers to request."""
        return {"Authorization": f"Bearer {self.access_token}"}

    @property
    def access_token(self):
        """Obtain and caches access token."""
        if self._access_token is None or self.is_token_expired():
            self._access_token = self.request(
                "post", self._cognitive_token_url, skip_auth=True
            ).text
            self._token_expiry = timezone.now() + TOKEN_EXPIRY

        return self._access_token

    def map_language_code(self, code):
        """Convert language to service specific code."""
        code = super().map_language_code(code).replace("_", "-")
        if "-" in code:
            lang, country = code.split("-", 1)
            if len(country) == 2:
                country = country.lower()
            code = f"{lang}-{country}"
        return code

    def check_failure(self, response) -> None:
        # Microsoft tends to use utf-8-sig instead of plain utf-8
        response.encoding = response.apparent_encoding
        super().check_failure(response)
        if (
            response.url.startswith("https://api.cognitive.microsofttranslator.com/")
            and response.status_code == 200
        ):
            payload = response.json()

            # We should get an object, string usually means an error
            if isinstance(payload, str):
                raise MachineTranslationError(payload)

    def download_languages(self):
        """
        Download list of supported languages from a service.

        Example of the response:

        ['af', 'ar', 'bs-Latn', 'bg', 'ca', 'zh-CHS', 'zh-CHT', 'yue', 'hr', 'cs', 'da',
        'nl', 'en', 'et', 'fj', 'fil', 'fi', 'fr', 'de', 'el', 'ht', 'he', 'hi', 'mww',
        'h', 'id', 'it', 'ja', 'sw', 'tlh', 'tlh-Qaak', 'ko', 'lv', 'lt', 'mg', 'ms',
        'mt', 'yua', 'no', 'otq', 'fa', 'pl', 'pt', 'ro', 'r', 'sm', 'sr-Cyrl',
        'sr-Latn', 'sk', 'sl', 'es', 'sv', 'ty', 'th', 'to', 'tr', 'uk', 'ur', 'vi',
        'cy']
        """
        response = self.request(
            "get", self.get_url("languages"), params={"api-version": "3.0"}
        )
        # Microsoft tends to use utf-8-sig instead of plain utf-8
        response.encoding = response.apparent_encoding
        payload = response.json()

        return payload["translation"].keys()

    def download_translations(
        self,
        source_language,
        target_language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ) -> DownloadTranslations:
        """Download list of possible translations from a service."""
        args = {
            "api-version": "3.0",
            "from": source_language,
            "to": target_language,
            "category": self.settings.get("category", "general"),
            "textType": "html",
        }
        response = self.request(
            "post", self.get_url("translate"), params=args, json=[{"Text": text[:5000]}]
        )
        # Microsoft tends to use utf-8-sig instead of plain utf-8
        response.encoding = "utf-8-sig"
        payload = response.json()
        yield {
            "text": payload[0]["translations"][0]["text"],
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }

    def format_replacement(
        self, h_start: int, h_end: int, h_text: str, h_kind: Unit | None
    ):
        """Generate a single replacement."""
        if h_kind is None:
            return f'<span class="notranslate" id="{h_start}">{self.escape_text(h_text)}</span>'
        # Glossary
        flags = h_kind.all_flags
        if "forbidden" in flags:
            return h_text
        if "read-only" in flags:
            # Use terminology format
            return self.format_replacement(h_start, h_end, h_text, None)
        return f'<mstrans:dictionary translation="{self.escape_text(h_kind.target)}">{self.escape_text(h_text)}</mstrans:dictionary>'

    def get_highlights(self, text, unit):
        result = list(super().get_highlights(text, unit))

        for term in get_glossary_terms(unit, include_variants=False):
            for start, end in term.glossary_positions:
                glossary_highlight = (start, end, text[start:end], term)
                handled = False
                for i, (h_start, _h_end, _h_text, _h_kind) in enumerate(result):
                    if start < h_start:
                        if end > h_start:
                            # Skip as overlaps
                            break
                        # Insert before
                        result.insert(i, glossary_highlight)
                        handled = True
                        break
                if not handled and (not result or result[-1][1] < start):
                    result.append(glossary_highlight)

        yield from result
