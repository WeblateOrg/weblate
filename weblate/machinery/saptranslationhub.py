# Copyright © Manuel Laggner <manuel.laggner@egger.com>
# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import DownloadTranslations, MachineTranslation
from .forms import SAPMachineryForm

if TYPE_CHECKING:
    from requests.auth import AuthBase


class SAPTranslationHub(MachineTranslation):
    # https://api.sap.com/api/translationhub/overview
    name = "SAP Translation Hub"
    settings_form = SAPMachineryForm

    @property
    def api_base_url(self):
        base = super().api_base_url
        if base.endswith("/v1"):
            return base
        return f"{base}/v1"

    def get_headers(self):
        """Add authentication headers to request."""
        # to access the sandbox
        result = {}
        if self.settings["key"]:
            result["APIKey"] = self.settings["key"]

        return result

    def get_auth(self) -> tuple[str, str] | AuthBase | None:
        # to access the productive API
        if self.settings["username"] and self.settings["password"]:
            return (self.settings["username"], self.settings["password"])
        return None

    def download_languages(self):
        """Get all available languages from SAP Translation Hub."""
        # get all available languages
        response = self.request("get", self.get_api_url("languages"))
        payload = response.json()

        return [d["id"] for d in payload["languages"]]

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
        # should the machine translation service be used?
        # (rather than only the term database)
        enable_mt = self.settings["enable_mt"]

        # build the json body
        data = {
            "targetLanguages": [target_language],
            "sourceLanguage": source_language,
            "enableMT": enable_mt,
            "enableTranslationQualityEstimation": enable_mt,
            "units": [{"value": text}],
        }

        # Include domain if set
        domain = self.settings.get("domain")
        if domain:
            data["domain"] = domain

        # perform the request
        response = self.request("post", self.get_api_url("translate"), json=data)
        payload = response.json()

        # prepare the translations for weblate
        for item in payload["units"]:
            for translation in item["translations"]:
                quality = translation.get("qualityIndex", 100)
                if quality < threshold:
                    continue
                yield {
                    "text": translation["value"],
                    "quality": quality,
                    "show_quality": "qualityIndex" in translation,
                    "service": self.name,
                    "source": text,
                }
