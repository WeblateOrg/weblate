#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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


from weblate.trans.discovery import ComponentDiscovery
from weblate.trans.tests.test_models import RepoTestCase


class ComponentDiscoveryTest(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.component = self.create_component()
        self.discovery = ComponentDiscovery(
            self.component,
            file_format="po",
            match=r"(?P<component>[^/]*)/(?P<language>[^/]*)\.po",
            name_template="{{ component|title }}",
            language_regex="^(?!xx).*$",
        )

    def test_matched_files(self):
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

    def test_matched_components(self):
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
                },
            },
        )

    def test_perform(self):
        # Preview should not create anything
        created, matched, deleted = self.discovery.perform(preview=True)
        self.assertEqual(len(created), 3)
        self.assertEqual(len(matched), 0)
        self.assertEqual(len(deleted), 0)

        # Create components
        created, matched, deleted = self.discovery.perform()
        self.assertEqual(len(created), 3)
        self.assertEqual(len(matched), 0)
        self.assertEqual(len(deleted), 0)

        # Test second call does nothing
        created, matched, deleted = self.discovery.perform()
        self.assertEqual(len(created), 0)
        self.assertEqual(len(matched), 3)
        self.assertEqual(len(deleted), 0)

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
        created, matched, deleted = discovery.perform(preview=True, remove=True)
        self.assertEqual(len(created), 0)
        self.assertEqual(len(matched), 1)
        self.assertEqual(len(deleted), 2)

        # Test component removal
        created, matched, deleted = discovery.perform(remove=True)
        self.assertEqual(len(created), 0)
        self.assertEqual(len(matched), 1)
        self.assertEqual(len(deleted), 2)

        # Components should be now removed
        created, matched, deleted = discovery.perform(remove=True)
        self.assertEqual(len(created), 0)
        self.assertEqual(len(matched), 1)
        self.assertEqual(len(deleted), 0)

    def test_duplicates(self):
        # Create all components with desired name po
        discovery = ComponentDiscovery(
            self.component,
            match=r"[^/]*(?P<component>po)[^/]*/(?P<language>[^/]*)\.po",
            name_template="{{ component|title }}",
            language_regex="^(?!xx).*$",
            file_format="po",
        )
        created, matched, deleted = discovery.perform()
        self.assertEqual(len(created), 3)
        self.assertEqual(len(matched), 0)
        self.assertEqual(len(deleted), 0)

    def test_multi_language(self):
        discovery = ComponentDiscovery(
            self.component,
            match=r"localization/(?P<language>[^/]*)/"
            r"(?P<component>[^/]*)\.(?P=language)\.po",
            name_template="{{ component }}",
            file_format="po",
        )
        created, matched, deleted = discovery.perform()
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0][0]["mask"], "localization/*/component.*.po")
        self.assertEqual(len(matched), 0)
        self.assertEqual(len(deleted), 0)

    def test_named_group(self):
        discovery = ComponentDiscovery(
            self.component,
            match=r"(?P<path>[^/]+)/(?P<language>[^/]*)/"
            r"(?P<component>[^/]*)\.(?P=language)\.po",
            name_template="{{ path }}: {{ component }}",
            file_format="po",
        )
        created, matched, deleted = discovery.perform()
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0][0]["mask"], "localization/*/component.*.po")
        self.assertEqual(created[0][0]["name"], "localization: component")
        self.assertEqual(len(matched), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(deleted), 0)
