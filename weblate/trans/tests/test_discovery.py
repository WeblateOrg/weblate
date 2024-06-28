# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test.utils import override_settings

from weblate.trans.discovery import ComponentDiscovery
from weblate.trans.tests.test_models import RepoTestCase


class ComponentDiscoveryTest(RepoTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.component = self.create_component()
        self.discovery = ComponentDiscovery(
            self.component,
            file_format="po",
            match=r"(?P<component>[^/]*)/(?P<language>[^/]*)\.po",
            name_template="{{ component|title }}",
            language_regex="^(?!xx).*$",
        )

    def test_matched_files(self) -> None:
        self.assertEqual(
            sorted(self.discovery.matched_files),
            sorted(
                [
                    "po-link/cs.po",
                    "po-link/de.po",
                    "po-link/it.po",
                    "po-mono/cs.po",
                    "po-mono/de.po",
                    "po-mono/en.po",
                    "po-mono/it.po",
                    "po/cs.po",
                    "po/de.po",
                    "po/it.po",
                    "second-po/cs.po",
                    "second-po/de.po",
                ]
            ),
        )

    def test_matched_components(self) -> None:
        self.assertEqual(
            self.discovery.matched_components,
            {
                "po/*.po": {
                    "files": {"po/cs.po", "po/de.po", "po/it.po"},
                    "files_langs": {
                        ("po/cs.po", "cs"),
                        ("po/de.po", "de"),
                        ("po/it.po", "it"),
                    },
                    "languages": {"cs", "de", "it"},
                    "mask": "po/*.po",
                    "name": "Po",
                    "slug": "po",
                    "base_file": "",
                    "new_base": "",
                    "intermediate": "",
                },
                "po-link/*.po": {
                    "files": {"po-link/cs.po", "po-link/de.po", "po-link/it.po"},
                    "files_langs": {
                        ("po-link/cs.po", "cs"),
                        ("po-link/de.po", "de"),
                        ("po-link/it.po", "it"),
                    },
                    "languages": {"cs", "de", "it"},
                    "mask": "po-link/*.po",
                    "name": "Po-Link",
                    "slug": "po-link",
                    "base_file": "",
                    "new_base": "",
                    "intermediate": "",
                },
                "po-mono/*.po": {
                    "files": {
                        "po-mono/cs.po",
                        "po-mono/de.po",
                        "po-mono/it.po",
                        "po-mono/en.po",
                    },
                    "files_langs": {
                        ("po-mono/cs.po", "cs"),
                        ("po-mono/de.po", "de"),
                        ("po-mono/it.po", "it"),
                        ("po-mono/en.po", "en"),
                    },
                    "languages": {"cs", "de", "it", "en"},
                    "mask": "po-mono/*.po",
                    "name": "Po-Mono",
                    "slug": "po-mono",
                    "base_file": "",
                    "new_base": "",
                    "intermediate": "",
                },
                "second-po/*.po": {
                    "files": {"second-po/cs.po", "second-po/de.po"},
                    "files_langs": {
                        ("second-po/cs.po", "cs"),
                        ("second-po/de.po", "de"),
                    },
                    "languages": {"cs", "de"},
                    "mask": "second-po/*.po",
                    "name": "Second-Po",
                    "slug": "second-po",
                    "base_file": "",
                    "new_base": "",
                    "intermediate": "",
                },
            },
        )

    def test_perform(self) -> None:
        # Preview should not create anything
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            created, matched, deleted, skipped = self.discovery.perform(preview=True)
        self.assertEqual(len(created), 3)
        self.assertEqual(len(matched), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(skipped), 1)

        # Create components
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            created, matched, deleted, skipped = self.discovery.perform()
        self.assertEqual(len(created), 3)
        self.assertEqual(len(matched), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(skipped), 1)

        # Test second call does nothing
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            created, matched, deleted, skipped = self.discovery.perform()
        self.assertEqual(len(created), 0)
        self.assertEqual(len(matched), 3)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(skipped), 1)

        # Remove some files
        repository = self.component.repository
        with repository.lock:
            repository.remove(
                ["po-link", "second-po/cs.po", "second-po/de.po"], "Remove some files"
            )

        # Create new discover as it caches matches
        discovery = ComponentDiscovery(
            self.component,
            file_format="po",
            match=r"(?P<component>[^/]*)/(?P<language>[^/]*)\.po",
            name_template="{{ component|title }}",
            language_regex="^(?!xx).*$",
        )

        # Test component removal preview
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            created, matched, deleted, skipped = discovery.perform(
                preview=True, remove=True
            )
        self.assertEqual(len(created), 0)
        self.assertEqual(len(matched), 1)
        self.assertEqual(len(deleted), 2)
        self.assertEqual(len(skipped), 1)

        # Test component removal
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            created, matched, deleted, skipped = discovery.perform(remove=True)
        self.assertEqual(len(created), 0)
        self.assertEqual(len(matched), 1)
        self.assertEqual(len(deleted), 2)
        self.assertEqual(len(skipped), 1)

        # Components should be now removed
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            created, matched, deleted, skipped = discovery.perform(remove=True)
        self.assertEqual(len(created), 0)
        self.assertEqual(len(matched), 1)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(skipped), 1)

    def test_duplicates(self) -> None:
        # Create all components with desired name po
        discovery = ComponentDiscovery(
            self.component,
            match=r"[^/]*(?P<component>po)[^/]*/(?P<language>[^/]*)\.po",
            name_template="{{ component|title }}",
            language_regex="^(?!xx).*$",
            file_format="po",
        )
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            created, matched, deleted, skipped = discovery.perform()
        self.assertEqual(len(created), 3)
        self.assertEqual(len(matched), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(skipped), 1)

    def test_multi_language(self) -> None:
        discovery = ComponentDiscovery(
            self.component,
            match=r"localization/(?P<language>[^/]*)/"
            r"(?P<component>[^/]*)\.(?P=language)\.po",
            name_template="{{ component }}",
            file_format="po",
        )
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            created, matched, deleted, skipped = discovery.perform()
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0][0]["mask"], "localization/*/component.*.po")
        self.assertEqual(len(matched), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(skipped), 0)

    def test_named_group(self) -> None:
        discovery = ComponentDiscovery(
            self.component,
            match=r"(?P<path>[^/]+)/(?P<language>[^/]*)/"
            r"(?P<component>[^/]*)\.(?P=language)\.po",
            name_template="{{ path }}: {{ component }}",
            file_format="po",
        )
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            created, matched, deleted, skipped = discovery.perform()
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0][0]["mask"], "localization/*/component.*.po")
        self.assertEqual(created[0][0]["name"], "localization: component")
        self.assertEqual(len(matched), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(skipped), 0)
