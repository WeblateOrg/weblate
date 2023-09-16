# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Sun Zhigang <hzsunzhigang@corp.netease.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import random
import time
from hashlib import sha1

from .base import MachineTranslation, MachineTranslationError
from .forms import KeySecretMachineryForm

NETEASE_API_ROOT = "https://jianwai.netease.com/api/text/trans"


class NeteaseSightTranslation(MachineTranslation):
    """Netease Sight API machine translation support."""

    name = "Netease Sight"
    max_score = 90

    # Map codes used by Netease Sight to codes used by Weblate
    language_map = {"zh_Hans": "zh"}
    settings_form = KeySecretMachineryForm

    def download_languages(self):
        """List of supported languages."""
        return ["zh", "en"]

    def get_authentication(self):
        """Hook for backends to allow add authentication headers to request."""
        nonce = str(random.randint(1000, 99999999))  # noqa: S311
        timestamp = str(int(1000 * time.monotonic()))

        sign = self.settings["secret"] + nonce + timestamp
        sign = sign.encode()
        sign = sha1(sign, usedforsecurity=False).hexdigest()

        return {
            "Content-Type": "application/json",
            "appkey": self.settings["key"],
            "nonce": nonce,
            "timestamp": timestamp,
            "signature": sign,
        }

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
            "post", NETEASE_API_ROOT, json={"lang": source, "content": text}
        )
        payload = response.json()

        if not payload["success"]:
            raise MachineTranslationError(payload["message"])

        translation = payload["relatedObject"]["content"][0]["transContent"]

        yield {
            "text": translation,
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }
