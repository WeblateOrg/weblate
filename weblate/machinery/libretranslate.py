# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Seth Falco <seth@falco.fun>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from weblate.machinery.base import MachineTranslation

from .forms import LibreTranslateMachineryForm


class LibreTranslateTranslation(MachineTranslation):
    """LibreTranslate machine translation support."""

    name = "LibreTranslate"
    max_score = 89
    language_map = {
        "zh_hans": "zh",
    }
    settings_form = LibreTranslateMachineryForm
    request_timeout = 20

    def download_languages(self):
        response = self.request(
            "get",
            self.get_api_url("languages"),
        )
        return [x["code"] for x in response.json()]

    def download_translations(
        self,
        source,
        language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ):
        """Download list of possible translations from a service."""
        response = self.request(
            "post",
            self.get_api_url("translate"),
            data={
                "api_key": self.settings["key"],
                "q": text,
                "source": source,
                "target": language,
            },
        )
        payload = response.json()

        yield {
            "text": payload["translatedText"],
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }
