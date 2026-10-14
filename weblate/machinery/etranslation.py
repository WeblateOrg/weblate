# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, TypeGuard, cast
from uuid import UUID, uuid4

import httpx2
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.urls import reverse
from django.utils.translation import gettext, gettext_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from weblate.utils.site import check_domain, get_site_url

from .base import (
    MACHINERY_DEFAULT_THRESHOLD,
    MachineTranslation,
    MachineTranslationError,
)
from .forms import ETRANSLATION_DOMAIN_LABELS, ETranslationMachineryForm

if TYPE_CHECKING:
    from collections.abc import Iterator

    from weblate.auth.models import User
    from weblate.lang.models import Language
    from weblate.trans.models import Unit

    from .types import DownloadTranslations, SettingsDict


API_ROOT = "https://language-tools.ec.europa.eu/etranslation/api"
CALLBACK_TIMEOUT = 15
CALLBACK_CACHE_TIMEOUT = 60
MAX_TEXT_LENGTH = 5000
LANGUAGE_PAIR_SUFFIXES = {"QE", "LLM", "GLS"}
DOMAINS_CACHE_SCOPE = "domains-v2"
ERROR_DESCRIPTIONS = {
    -20007: gettext_lazy("Application is not authorized to use eTranslation"),
    -20013: gettext_lazy("The language pair is not supported by this domain"),
    -20021: gettext_lazy("The text is too long"),
    -20028: gettext_lazy("The concurrency quota was exceeded"),
    -20045: gettext_lazy("Quality estimation is not available for text snippets"),
    -20047: gettext_lazy("Quality estimation is not available"),
    -40003: gettext_lazy("The translation backend failed"),
    -40004: gettext_lazy("The translation request timed out"),
    -40005: gettext_lazy("Internal processing error"),
    -40011: gettext_lazy("The language pair is not available for this domain"),
}


def format_error(code: int, domain: str, message: str | None = None) -> str:
    if code in ERROR_DESCRIPTIONS:
        description = str(ERROR_DESCRIPTIONS[code])
    else:
        description = " ".join(message.split())[:200] if message else ""
        if description.isupper() and "_" in description:
            description = description.replace("_", " ").capitalize()
        if not description:
            description = gettext("Unknown error")
    return gettext(
        "eTranslation failed in domain %(domain)s: %(description)s (error code %(code)s)."
    ) % {"domain": domain, "description": description, "code": code}


def callback_cache_key(token: str) -> str:
    return f"etranslation:callback:{token}"


def is_json_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def is_traditional_chinese(code: str) -> bool:
    normalized = code.split("@", 1)[0].replace("-", "_").lower()
    return normalized in {"zh_hant", "zh_tw", "zh_hk"} or normalized.startswith(
        ("zh_hant_", "zh_tw_", "zh_hk_")
    )


@csrf_exempt
@login_not_required
@require_POST
def etranslation_callback(request: HttpRequest, token: UUID) -> HttpResponse:
    """Receive the result of a text snippet request."""
    key = callback_cache_key(token.hex)
    pending = cache.get(key)
    if pending is None:
        return HttpResponse(status=404)
    try:
        content_length = int(request.headers.get("content-length", "0"))
    except ValueError:
        return HttpResponseBadRequest()
    if content_length < 0 or content_length > 65536:
        return HttpResponseBadRequest()
    if request.content_type != "application/json":
        return HttpResponseBadRequest()
    body = request.read(65537)
    if len(body) > 65536:
        return HttpResponseBadRequest()
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest()
    if (
        not isinstance(payload, dict)
        or payload.get("externalReference") != token.hex
        or not is_json_integer(payload.get("requestId"))
        or payload["requestId"] <= 0
    ):
        return HttpResponseBadRequest()
    if pending["status"] != "pending":
        return HttpResponse()
    result: dict[str, object]
    if "translatedText" in payload:
        if payload.get("targetLanguage") != pending["target"] or not isinstance(
            payload["translatedText"], str
        ):
            return HttpResponseBadRequest()
        result = {"status": "success", "text": payload["translatedText"]}
    elif "errorCode" in payload:
        target_languages = payload.get("targetLanguages")
        if (
            not isinstance(target_languages, list)
            or pending["target"] not in target_languages
            or not is_json_integer(payload.get("errorCode"))
        ):
            return HttpResponseBadRequest()
        error_message = payload.get("errorMessage")
        result = {
            "status": "failure",
            "code": payload["errorCode"],
            "message": error_message[:200] if isinstance(error_message, str) else None,
        }
    else:
        return HttpResponseBadRequest()
    cache.set(key, result, CALLBACK_CACHE_TIMEOUT)
    return HttpResponse()


class ETranslation(MachineTranslation):
    """European Commission eTranslation text snippets."""

    name = "eTranslation"
    max_score = 90
    settings_form = ETranslationMachineryForm
    request_timeout = 10

    def __init__(self, configuration: SettingsDict) -> None:
        super().__init__(configuration)
        self.languages_cache = self.get_cache_key("languages-v2")

    def get_auth(self) -> tuple[str, str]:
        return self.settings["key"], self.settings["secret"]

    def map_language_code(self, code: str) -> str:
        code = super().map_language_code(code).split("@", 1)[0].replace("-", "_")
        if is_traditional_chinese(code):
            return "ZT"
        return code.split("_", 1)[0].upper()

    def get_language_possibilities(self, language: Language) -> Iterator[str]:
        if is_traditional_chinese(language.code):
            yield "ZT"
        else:
            yield from super().get_language_possibilities(language)

    def get_domains(self) -> dict[str, set[tuple[str, str]]]:
        cache_key = self.get_cache_key(DOMAINS_CACHE_SCOPE)
        if cached := cache.get(cache_key):
            return cached
        response = self.request("get", f"{API_ROOT}/getDomains")
        domains = self.parse_domains(response.json())
        cache.set(cache_key, domains, 3600)
        return domains

    async def aget_domains(self) -> dict[str, set[tuple[str, str]]]:
        cache_key = self.get_cache_key(DOMAINS_CACHE_SCOPE)
        if cached := await cache.aget(cache_key):
            return cached
        response = await self.arequest("get", f"{API_ROOT}/getDomains")
        domains = self.parse_domains(response.json())
        await cache.aset(cache_key, domains, 3600)
        return domains

    @staticmethod
    def parse_domains(payload: object) -> dict[str, set[tuple[str, str]]]:
        if not isinstance(payload, list):
            msg = gettext("Invalid eTranslation domains response")
            raise MachineTranslationError(msg)
        domains: dict[str, set[tuple[str, str]]] = {}
        for item in payload:
            if not isinstance(item, dict) or not isinstance(item.get("domain"), str):
                continue
            pairs = set()
            language_pairs = item.get("languagePairs")
            if not isinstance(language_pairs, list):
                continue
            for pair in language_pairs:
                if not isinstance(pair, str):
                    continue
                codes = pair.rstrip("-").upper().split("-")
                if (
                    len(codes) >= 2
                    and all(len(code) == 2 and code.isalpha() for code in codes[:2])
                    and all(suffix in LANGUAGE_PAIR_SUFFIXES for suffix in codes[2:])
                ):
                    pairs.add((codes[0], codes[1]))
            domains[item["domain"]] = pairs
        if not domains:
            msg = gettext("No eTranslation domains available")
            raise MachineTranslationError(msg)
        return domains

    def validate_settings(self) -> None:
        if not settings.ENABLE_HTTPS or not check_domain(settings.SITE_DOMAIN):
            raise ValidationError(
                gettext(
                    "eTranslation requires a public HTTPS site domain for callbacks."
                )
            )
        try:
            domains = self.get_domains()
        except (httpx2.HTTPError, ValueError, MachineTranslationError) as error:
            raise ValidationError(
                gettext("Could not fetch eTranslation domains: %s") % error
            ) from error
        configured = {self.settings.get("domain", "GEN")}
        configured.update((self.settings.get("component_domains") or {}).values())
        unknown = configured - domains.keys()
        if unknown:
            raise ValidationError(
                gettext("Unknown eTranslation domain: %s") % ", ".join(sorted(unknown))
            )

    def download_languages(self) -> set[tuple[str, str]]:
        domains = self.get_domains()
        configured = {self.settings.get("domain", "GEN")}
        configured.update((self.settings.get("component_domains") or {}).values())
        return set().union(*(domains.get(domain, set()) for domain in configured))

    def is_supported(self, source_language: str, target_language: str) -> bool:
        return (source_language, target_language) in self.supported_languages

    def get_domain(self, unit: Unit | None) -> str:
        overrides = self.settings.get("component_domains") or {}
        if unit is not None:
            path = unit.translation.component.full_slug
            if path in overrides:
                return overrides[path]
        return self.settings.get("domain", "GEN")

    def get_translation_cache_extra_parts(
        self, index: int, text: str, unit: Unit | None, source_occurrence: int
    ) -> tuple[str, ...]:
        return (self.get_domain(unit), "domain-origin-v1")

    @staticmethod
    def make_payload(
        token: UUID, source_language: str, target_language: str, text: str, domain: str
    ) -> dict:
        callback_url = get_site_url(reverse("etranslation-callback", args=[token]))
        return {
            "callerInformation": {"externalReference": token.hex},
            "textToTranslate": text,
            "sourceLanguage": source_language,
            "targetLanguages": [target_language],
            "domain": domain,
            "notifications": {
                "success": {"http": callback_url},
                "failure": {"http": callback_url},
            },
        }

    @staticmethod
    def raise_response_error(response: httpx2.Response, domain: str) -> None:
        try:
            payload = response.json()
        except ValueError:
            return
        if isinstance(payload, dict) and is_json_integer(payload.get("errorCode")):
            error_message = payload.get("errorMessage")
            msg = format_error(
                payload["errorCode"],
                domain,
                error_message if isinstance(error_message, str) else None,
            )
            raise MachineTranslationError(msg)

    @classmethod
    def check_request_id(cls, response: httpx2.Response, domain: str) -> None:
        cls.raise_response_error(response, domain)
        payload = response.json()
        request_id = payload.get("requestId") if isinstance(payload, dict) else None
        if not is_json_integer(request_id) or request_id <= 0:
            msg = gettext("Invalid eTranslation request ID")
            raise MachineTranslationError(msg)

    def callback_result(
        self, result: dict, text: str, domain: str
    ) -> DownloadTranslations | None:
        if result.get("status") == "success":
            return [
                {
                    "text": result["text"],
                    "quality": self.max_score,
                    "service": self.name,
                    "source": text,
                    "origin": cast(
                        "str", ETRANSLATION_DOMAIN_LABELS.get(domain, domain)
                    ),
                }
            ]
        if result.get("status") == "failure":
            msg = format_error(result["code"], domain, result.get("message"))
            raise MachineTranslationError(msg)
        return None

    def download_translations(
        self,
        source_language: str,
        target_language: str,
        text: str,
        unit: Unit | None,
        user: User | None,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
    ) -> DownloadTranslations:
        if not text or len(text) > MAX_TEXT_LENGTH:
            return []
        domain = self.get_domain(unit)
        if (source_language, target_language) not in self.get_domains().get(
            domain, set()
        ):
            return []
        token = uuid4()
        key = callback_cache_key(token.hex)
        cache.set(
            key,
            {"status": "pending", "target": target_language},
            CALLBACK_CACHE_TIMEOUT,
        )
        payload = self.make_payload(
            token, source_language, target_language, text, domain
        )
        try:
            try:
                response = self.request(
                    "post", f"{API_ROOT}/askTranslate", json=payload
                )
            except httpx2.HTTPStatusError as error:
                self.raise_response_error(error.response, domain)
                raise
            self.check_request_id(response, domain)
            deadline = time.monotonic() + CALLBACK_TIMEOUT
            while time.monotonic() < deadline:
                result = cache.get(key)
                if result and (
                    translation := self.callback_result(result, text, domain)
                ):
                    return translation
                time.sleep(0.1)
            msg = gettext("Timed out waiting for eTranslation callback")
            raise MachineTranslationError(msg)
        finally:
            cache.delete(key)

    async def adownload_translations(
        self,
        source_language: str,
        target_language: str,
        text: str,
        unit: Unit | None,
        user: User | None,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
    ) -> DownloadTranslations:
        if not text or len(text) > MAX_TEXT_LENGTH:
            return []
        domain = await sync_to_async(self.get_domain)(unit)
        if (source_language, target_language) not in (await self.aget_domains()).get(
            domain, set()
        ):
            return []
        token = uuid4()
        key = callback_cache_key(token.hex)
        await cache.aset(
            key,
            {"status": "pending", "target": target_language},
            CALLBACK_CACHE_TIMEOUT,
        )
        payload = self.make_payload(
            token, source_language, target_language, text, domain
        )
        try:
            try:
                response = await self.arequest(
                    "post", f"{API_ROOT}/askTranslate", json=payload
                )
            except httpx2.HTTPStatusError as error:
                self.raise_response_error(error.response, domain)
                raise
            self.check_request_id(response, domain)
            deadline = time.monotonic() + CALLBACK_TIMEOUT
            while time.monotonic() < deadline:
                result = await cache.aget(key)
                if result and (
                    translation := self.callback_result(result, text, domain)
                ):
                    return translation
                await asyncio.sleep(0.1)
            msg = gettext("Timed out waiting for eTranslation callback")
            raise MachineTranslationError(msg)
        finally:
            await cache.adelete(key)
