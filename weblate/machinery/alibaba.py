# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


import json

from aliyunsdkalimt.request.v20181012 import TranslateGeneralRequest
from aliyunsdkcore.client import AcsClient
from django.utils.functional import cached_property

from .base import DownloadTranslations, MachineTranslation, MachineTranslationError
from .forms import AlibabaMachineryForm


class AlibabaTranslation(MachineTranslation):
    """Alibaba API machine translation support."""

    name = "Alibaba"
    max_score = 80

    language_map = {
        "zh_Hans": "zh",
        "zh_Hant": "zh-tw",
    }

    settings_form = AlibabaMachineryForm

    @cached_property
    def client(self):
        return AcsClient(
            ak=self.settings["key"],
            secret=self.settings["secret"],
            region_id=self.settings["region"],
        )

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
            "ba",
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
        threshold: int = 75,
    ) -> DownloadTranslations:
        """Download list of possible translations from a service."""
        # Create an API request and set the request parameters.
        request = TranslateGeneralRequest.TranslateGeneralRequest()
        request.set_SourceLanguage(source_language)  # source language
        request.set_SourceText(text)  # original
        request.set_TargetLanguage(target_language)
        request.set_FormatType("text")
        request.set_method("POST")

        # Initiate the API request and obtain the response.
        response = self.client.do_action_with_exception(request)
        payload = json.loads(response)
        if "Message" in payload:
            msg = f"Error {payload['Code']}: {payload['Message']}"
            raise MachineTranslationError(msg)

        yield {
            "text": payload["Data"]["Translated"],
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }
