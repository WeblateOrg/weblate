# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.test import SimpleTestCase

if TYPE_CHECKING:
    from types import ModuleType


def load_sbom_module() -> ModuleType:
    script = Path(__file__).resolve().parents[3] / "scripts" / "reproducible-sbom.py"
    spec = importlib.util.spec_from_file_location("reproducible_sbom", script)
    if spec is None or spec.loader is None:
        msg = "Could not load reproducible-sbom.py"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SBOMTest(SimpleTestCase):
    @staticmethod
    def get_sbom() -> dict[str, Any]:
        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.7",
            "serialNumber": "urn:uuid:00000000-0000-5000-8000-000000000000",
            "version": 1,
            "metadata": {
                "timestamp": "2026-05-25T00:00:00Z",
                "tools": [
                    {
                        "vendor": "Astral Software Inc.",
                        "name": "uv",
                        "version": "0.11.16",
                    }
                ],
                "component": {
                    "type": "application",
                    "bom-ref": "weblate-client-libs@2026.6.0",
                    "name": "client",
                    "version": "2026.6.0",
                },
            },
            "components": [
                {
                    "type": "library",
                    "bom-ref": "weblate-1@2026.6",
                    "name": "weblate",
                    "version": "2026.6",
                },
                {
                    "type": "library",
                    "bom-ref": "aeidon-2@1.16",
                    "name": "aeidon",
                    "version": "1.16",
                    "purl": "pkg:pypi/aeidon@1.16",
                },
            ],
            "dependencies": [
                {
                    "ref": "weblate-1@2026.6",
                    "dependsOn": ["aeidon-2@1.16"],
                }
            ],
        }

    def test_update_metadata(self) -> None:
        module = load_sbom_module()
        data = self.get_sbom()

        module.update_sbom(data, "1700000000")

        metadata = data["metadata"]
        self.assertEqual(metadata["timestamp"], "2023-11-14T22:13:20Z")
        self.assertEqual(metadata["authors"], [module.WEBLATE_AUTHOR])
        self.assertEqual(metadata["manufacturer"], module.WEBLATE_ORGANIZATION)
        self.assertEqual(metadata["supplier"], module.WEBLATE_ORGANIZATION)
        self.assertEqual(metadata["lifecycles"], [module.GENERATION_LIFECYCLE])
        self.assertIn(
            {
                "name": module.GENERATION_CONTEXT_PROPERTY,
                "value": module.GENERATION_CONTEXT,
            },
            metadata["properties"],
        )
        self.assertEqual(metadata["component"]["name"], "weblate")
        self.assertEqual(metadata["component"]["type"], "application")
        self.assertEqual(metadata["component"]["purl"], "pkg:pypi/weblate@2026.6")

        python_component = data["components"][1]
        self.assertNotIn("hashes", python_component)
        self.assertNotIn("licenses", python_component)
        module.validate_sbom(data)

    def test_preserve_existing_timestamp(self) -> None:
        module = load_sbom_module()
        data = self.get_sbom()

        module.update_sbom(data)

        self.assertEqual(data["metadata"]["timestamp"], "2026-05-25T00:00:00Z")
        module.validate_sbom(data)

    def test_stable_serial_number(self) -> None:
        module = load_sbom_module()
        data = self.get_sbom()
        same_data = copy.deepcopy(data)

        module.update_sbom(data, "1700000000")
        module.update_sbom(same_data, "1700000000")

        self.assertEqual(data["serialNumber"], same_data["serialNumber"])
        self.assertRegex(
            data["serialNumber"],
            r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-",
        )

    def test_validate_requires_document_metadata(self) -> None:
        module = load_sbom_module()
        data = self.get_sbom()
        module.update_sbom(data, "1700000000")
        del data["metadata"]["timestamp"]

        with self.assertRaises(module.SBOMValidationError):
            module.validate_sbom(data)
