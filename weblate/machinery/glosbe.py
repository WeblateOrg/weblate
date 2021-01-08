#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from weblate.machinery.base import MachineTranslation


class GlosbeTranslation(MachineTranslation):
    """Glosbe machine translation support."""

    name = "Glosbe"
    max_score = 90
    do_cleanup = False

    def map_code_code(self, code):
        """Convert language to service specific code."""
        return code.replace("_", "-").split("-")[0].lower()

    def is_supported(self, source, language):
        """Any language is supported."""
        return True

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
        """Download list of possible translations from a service."""
        params = {"from": source, "dest": language, "format": "json", "phrase": text}
        response = self.request(
            "get", "https://glosbe.com/gapi/translate", params=params
        )
        payload = response.json()

        if "tuc" not in payload:
            return

        for match in payload["tuc"]:
            if "phrase" not in match or match["phrase"] is None:
                continue
            yield {
                "text": match["phrase"]["text"],
                "quality": self.max_score,
                "service": self.name,
                "source": text,
            }
