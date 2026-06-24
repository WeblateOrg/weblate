# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import ClassVar

from .forms import MistralMachineryForm
from .openai import OpenAITranslation


class MistralTranslation(OpenAITranslation):
    """
    Mistral machine translation integration.

    Configurable machine translation interface that uses Mistral language
    models through its OpenAI-compatible API.
    """

    name = "Mistral"
    trusted_error_hosts: ClassVar[set[str]] = {"api.mistral.ai"}

    settings_form = MistralMachineryForm
    version_added = "2026.7"

    def get_runtime_base_url(self) -> str:
        return self.settings.get("base_url") or "https://api.mistral.ai/v1"
