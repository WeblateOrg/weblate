# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import base64
import hmac
from datetime import UTC, datetime
from hashlib import sha1
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import quote
from uuid import uuid4

from requests.exceptions import JSONDecodeError

from .base import (
    MACHINERY_DEFAULT_THRESHOLD,
    MachineTranslation,
    MachineTranslationError,
)
from .forms import AlibabaMachineryForm

if TYPE_CHECKING:
    from collections.abc import Mapping

    from requests import Response

    from .base import DownloadTranslations


ALIBABA_API_VERSION = "2018-10-12"
ALIBABA_ENDPOINTS = {
    "ap-southeast-1": "mt.ap-southeast-1.aliyuncs.com",
    "cn-hangzhou": "mt.cn-hangzhou.aliyuncs.com",
}
ALIBABA_DEFAULT_ENDPOINT = "mt.aliyuncs.com"
ALIBABA_SIGNATURE_METHOD = "HMAC-SHA1"
ALIBABA_SIGNATURE_VERSION = "1.0"
ALIBABA_TRANSLATE_ACTION = "TranslateGeneral"


def _get_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_nonce() -> str:
    return uuid4().hex


def _quote(value: object) -> str:
    return quote(str(value), safe="-_.~")


def _canonicalize(params: Mapping[str, str]) -> str:
    return "&".join(
        f"{_quote(key)}={_quote(value)}" for key, value in sorted(params.items())
    )


def _sign_request(method: str, params: Mapping[str, str], secret: str) -> str:
    string_to_sign = f"{method}&%2F&{_quote(_canonicalize(params))}"
    digest = hmac.new(f"{secret}&".encode(), string_to_sign.encode(), sha1).digest()
    return base64.b64encode(digest).decode()


def _resolve_endpoint(region: str) -> str:
    return ALIBABA_ENDPOINTS.get(region, ALIBABA_DEFAULT_ENDPOINT)


class AlibabaTranslation(MachineTranslation):
    """Alibaba API machine translation support."""

    name = "Alibaba"
    max_score = 80

    language_map: ClassVar[dict[str, str]] = {
        "zh_Hans": "zh",
        "zh_Hant": "zh-tw",
    }

    version_added = "5.3"

    settings_form = AlibabaMachineryForm

    def get_api_url(self, *_parts: str) -> str:
        return f"https://{_resolve_endpoint(self.settings['region'])}/"

    def get_query_params(self, body_params: Mapping[str, str]) -> dict[str, str]:
        query_params = {
            "Action": ALIBABA_TRANSLATE_ACTION,
            "Version": ALIBABA_API_VERSION,
            "Format": "JSON",
            "RegionId": self.settings["region"],
            "Timestamp": _get_timestamp(),
            "SignatureMethod": ALIBABA_SIGNATURE_METHOD,
            "SignatureType": "",
            "SignatureVersion": ALIBABA_SIGNATURE_VERSION,
            "SignatureNonce": _get_nonce(),
            "AccessKeyId": self.settings["key"],
        }
        sign_params = {**query_params, **body_params}
        query_params["Signature"] = _sign_request(
            "POST", sign_params, self.settings["secret"]
        )
        return query_params

    def check_failure(self, response: Response) -> None:
        try:
            payload = response.json()
        except JSONDecodeError:
            super().check_failure(response)
            return

        if isinstance(payload, dict) and "Message" in payload:
            msg = f"Error {payload.get('Code')}: {payload['Message']}"
            raise MachineTranslationError(msg)

        super().check_failure(response)

    def download_languages(self):
        """List of supported languages."""
        return [
            "ab",
            "sq",
            "ak",
            "ar",
            "an",
            "am",
            "as",
            "az",
            "ast",
            "nch",
            "ee",
            "ay",
            "ga",
            "et",
            "oj",
            "oc",
            "or",
            "om",
            "os",
            "tpi",
            "ba",  # codespell:ignore
            "eu",
            "be",
            "ber",
            "bm",
            "pag",
            "bg",
            "se",
            "bem",
            "byn",
            "bi",
            "bal",
            "is",
            "pl",
            "bs",
            "fa",
            "bho",
            "br",
            "ch",
            "cbk",
            "cv",
            "ts",
            "tt",
            "da",
            "shn",
            "tet",
            "de",
            "nds",
            "sco",
            "dv",
            "kdx",
            "dtp",
            "ru",
            "fo",  # codespell:ignore fo
            "fr",
            "sa",
            "fil",
            "fj",
            "fi",
            "fur",
            "fvr",
            "kg",
            "km",
            "ngu",
            "kl",
            "ka",
            "gos",
            "gu",
            "gn",
            "kk",
            "ht",
            "ko",
            "ha",
            "nl",
            "cnr",
            "hup",
            "gil",
            "rn",
            "quc",
            "ky",
            "gl",
            "ca",
            "cs",
            "kab",
            "kn",
            "kr",
            "csb",
            "kha",
            "kw",
            "xh",
            "co",
            "mus",
            "crh",
            "tlh",
            "hbs",
            "qu",
            "ks",
            "ku",
            "la",
            "ltg",
            "lv",
            "lo",
            "lt",
            "li",
            "ln",
            "lg",
            "lb",
            "rue",
            "rw",
            "ro",
            "rm",
            "rom",
            "jbo",
            "mg",
            "gv",
            "mt",
            "mr",
            "ml",
            "ms",
            "chm",
            "mk",
            "mh",
            "kek",
            "mai",
            "mfe",
            "mi",
            "mn",
            "bn",
            "my",
            "hmn",
            "umb",
            "nv",
            "af",
            "ne",
            "niu",
            "no",
            "pmn",
            "pap",
            "pa",
            "pt",
            "ps",
            "ny",
            "tw",
            "chr",
            "ja",
            "sv",
            "sm",
            "sg",
            "si",
            "hsb",
            "eo",
            "sl",
            "sw",
            "so",
            "sk",
            "tl",
            "tg",
            "ty",
            "te",  # codespell:ignore te
            "ta",
            "th",
            "to",
            "toi",  # codespell:ignore toi
            "ti",
            "tvl",
            "tyv",
            "tr",
            "tk",
            "wa",
            "war",
            "cy",
            "ve",
            "vo",
            "wo",
            "udm",
            "ur",
            "uz",
            "es",
            "ie",
            "fy",
            "szl",
            "he",
            "hil",
            "haw",
            "el",
            "lfn",
            "sd",
            "hu",
            "sn",
            "ceb",
            "syr",
            "su",
            "hy",
            "ace",
            "iba",
            "ig",
            "io",
            "ilo",
            "iu",
            "it",
            "yi",
            "ia",
            "hi",
            "id",
            "inh",  # codespell:ignore inh
            "en",
            "yo",
            "vi",
            "zza",
            "jv",
            "zh",
            "zh-tw",
            "yue",
            "zu",
        ]

    def download_translations(
        self,
        source_language,
        target_language,
        text: str,
        unit,
        user,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
    ) -> DownloadTranslations:
        """Download list of possible translations from a service."""
        body_params = {
            "SourceLanguage": source_language,
            "SourceText": text,
            "TargetLanguage": target_language,
            "FormatType": "text",
        }

        response = self.request(
            "post",
            self.get_api_url(),
            params=self.get_query_params(body_params),
            data=body_params,
        )
        payload = response.json()
        yield {
            "text": payload["Data"]["Translated"],
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }
