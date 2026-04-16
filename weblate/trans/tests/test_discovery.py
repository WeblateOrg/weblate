# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import pathlib
import tempfile
from typing import TYPE_CHECKING
from unittest.mock import call, patch

from django.test import SimpleTestCase
from django.test.utils import override_settings
from translation_finder import DiscoveryResult

from weblate.trans.discovery import (
    ComponentDiscovery,
    build_detected_discovery_preset,
    get_component_detected_discovery_presets,
    get_detected_discovery_preset_values_key,
    get_detected_discovery_presets_from_results,
)
from weblate.trans.tasks import create_component
from weblate.trans.tests.test_models import RepoTestCase
from weblate.utils.files import remove_tree

if TYPE_CHECKING:
    from translation_finder.discovery.result import ResultDict


class ComponentDiscoveryTest(RepoTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.component = self.create_component()
        self.discovery = ComponentDiscovery(
            self.component,
            file_format="po",
            match=r"(?P<component>[^/]*)/(?P<language>[^/]*)\.po",
            name_template="{{ component|title }}",
            language_regex="^(?!xx).+$",
        )

    def test_matched_files(self) -> None:
        self.assertEqual(
            sorted(self.discovery.matched_files),
            sorted(
                [
                    "po-brokenlink/cs.po",
                    "po-brokenlink/de.po",
                    "po-brokenlink/it.po",
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

    def test_match_timeout(self) -> None:
        with patch(
            "weblate.trans.discovery.regex_match",
            side_effect=TimeoutError,
        ):
            self.assertEqual(self.discovery.matches, [])
        self.assertEqual(len(self.discovery.errors), 1)
        self.assertEqual(
            self.discovery.errors[0][1],
            "The regular expression used to match discovered files is too complex and took too long to evaluate.",
        )

    def test_matched_components(self) -> None:
        self.maxDiff = None
        self.assertEqual(
            self.discovery.matched_components,
            {
                "po/*.po": {
                    "files": {"po/cs.po", "po/de.po", "po/it.po"},
                    "files_langs": (
                        ("po/cs.po", "cs"),
                        ("po/de.po", "de"),
                        ("po/it.po", "it"),
                    ),
                    "languages": {"cs", "de", "it"},
                    "mask": "po/*.po",
                    "name": "Po",
                    "slug": "po",
                    "base_file": "",
                    "new_base": "",
                    "intermediate": "",
                },
                "po-brokenlink/*.po": {
                    "files": {
                        "po-brokenlink/cs.po",
                        "po-brokenlink/de.po",
                        "po-brokenlink/it.po",
                    },
                    "files_langs": (
                        ("po-brokenlink/cs.po", "cs"),
                        ("po-brokenlink/de.po", "de"),
                        ("po-brokenlink/it.po", "it"),
                    ),
                    "languages": {"cs", "de", "it"},
                    "mask": "po-brokenlink/*.po",
                    "name": "Po-Brokenlink",
                    "slug": "po-brokenlink",
                    "base_file": "",
                    "new_base": "",
                    "intermediate": "",
                },
                "po-link/*.po": {
                    "files": {"po-link/cs.po", "po-link/de.po", "po-link/it.po"},
                    "files_langs": (
                        ("po-link/cs.po", "cs"),
                        ("po-link/de.po", "de"),
                        ("po-link/it.po", "it"),
                    ),
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
                    "files_langs": (
                        ("po-mono/cs.po", "cs"),
                        ("po-mono/de.po", "de"),
                        ("po-mono/en.po", "en"),
                        ("po-mono/it.po", "it"),
                    ),
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
                    "files_langs": (
                        ("second-po/cs.po", "cs"),
                        ("second-po/de.po", "de"),
                    ),
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

    def test_matched_components_for_filename_language_variants(self) -> None:
        docs = pathlib.Path(self.component.full_path) / "docs"
        docs.mkdir(exist_ok=True)
        for name in (
            "news_en.md",
            "news_cs.md",
            "guide_en.md",
            "news_pt_BR.md",
            "news_flash_pt_BR.md",
        ):
            (docs / name).write_text(f"# {name}\n", encoding="utf-8")

        discovery = ComponentDiscovery(
            self.component,
            file_format="markdown",
            match=r"(?:(?P<path>.*/))?(?P<component>.+?)_(?P<language>[A-Za-z]{2,3}(?:[_-][A-Za-z0-9]+)*)\.(?P<extension>[^/.]+)",
            name_template="{{ component }}",
            language_regex="^[^.]+$",
            path=os.fspath(docs),
        )

        self.assertEqual(
            discovery.matched_components,
            {
                "guide_*.md": {
                    "files": {"guide_en.md"},
                    "files_langs": (("guide_en.md", "en"),),
                    "languages": {"en"},
                    "mask": "guide_*.md",
                    "name": "guide",
                    "slug": "guide",
                    "base_file": "",
                    "new_base": "",
                    "intermediate": "",
                },
                "news_*.md": {
                    "files": {
                        "news_cs.md",
                        "news_en.md",
                        "news_pt_BR.md",
                    },
                    "files_langs": (
                        ("news_cs.md", "cs"),
                        ("news_en.md", "en"),
                        ("news_pt_BR.md", "pt_BR"),
                    ),
                    "languages": {"cs", "en", "pt_BR"},
                    "mask": "news_*.md",
                    "name": "news",
                    "slug": "news",
                    "base_file": "",
                    "new_base": "",
                    "intermediate": "",
                },
                "news_flash_*.md": {
                    "files": {"news_flash_pt_BR.md"},
                    "files_langs": (("news_flash_pt_BR.md", "pt_BR"),),
                    "languages": {"pt_BR"},
                    "mask": "news_flash_*.md",
                    "name": "news_flash",
                    "slug": "news_flash",
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
        self.assertEqual(len(created), 4)
        self.assertEqual(len(matched), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(skipped), 1)

        # Create components
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            created, matched, deleted, skipped = self.discovery.perform()
        self.assertEqual(len(created), 4)
        self.assertEqual(len(matched), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(skipped), 1)

        # Test second call does nothing
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            created, matched, deleted, skipped = self.discovery.perform()
        self.assertEqual(len(created), 0)
        self.assertEqual(len(matched), 4)
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
            language_regex="^(?!xx).+$",
        )

        # Test component removal preview
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            created, matched, deleted, skipped = discovery.perform(
                preview=True, remove=True
            )
        self.assertEqual(len(created), 0)
        self.assertEqual(len(matched), 2)
        self.assertEqual(len(deleted), 2)
        self.assertEqual(len(skipped), 1)

        # Test component removal
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            created, matched, deleted, skipped = discovery.perform(remove=True)
        self.assertEqual(len(created), 0)
        self.assertEqual(len(matched), 2)
        self.assertEqual(len(deleted), 2)
        self.assertEqual(len(skipped), 1)

        # Components should be now removed
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            created, matched, deleted, skipped = discovery.perform(remove=True)
        self.assertEqual(len(created), 0)
        self.assertEqual(len(matched), 2)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(skipped), 1)

    def test_create_component_tolerates_missing_copy_from_addons_source(self) -> None:
        source_component = self._create_component(
            "po",
            "po/*.po",
            name="copy-source",
            slug="copy-source",
            project=self.component.project,
        )
        source_component.addon_set.create(name="weblate.gettext.linguas")
        copy_from = source_component.pk
        source_component.delete()

        result = create_component(
            copy_from=copy_from,
            copy_addons=True,
            in_task=True,
            name="copy-target",
            slug="copy-target",
            project=self.component.project.pk,
            vcs=self.component.vcs,
            repo=self.component.get_repo_link_url(),
            file_format=self.component.file_format,
            filemask=self.component.filemask,
            new_base=self.component.new_base,
            new_lang=self.component.new_lang,
            language_regex=self.component.language_regex,
            source_language=self.component.source_language.pk,
        )

        component = self.component.project.component_set.get(pk=result["component"])
        self.assertEqual(component.slug, "copy-target")
        self.assertFalse(component.addon_set.exists())

    def test_duplicates(self) -> None:
        # Create all components with desired name po
        discovery = ComponentDiscovery(
            self.component,
            match=r"[^/]*(?P<component>po)[^/]*/(?P<language>[^/]*)\.po",
            name_template="{{ component|title }}",
            language_regex="^(?!xx).+$",
            file_format="po",
        )
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            created, matched, deleted, skipped = discovery.perform()
        self.assertEqual(len(created), 4)
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

    def test_skip_reason_rejects_symlinked_auxiliary_file(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(b"outside repository")
        self.addCleanup(os.unlink, handle.name)

        linked_name = "discovery-base.pot"
        linked_path = os.path.join(self.component.full_path, linked_name)
        os.symlink(handle.name, linked_path)

        reason = self.discovery.get_skip_reason(
            {
                "mask": "discovered/*.po",
                "base_file": linked_name,
                "new_base": "",
                "intermediate": "",
            }
        )

        self.assertEqual(reason, "discovery-base.pot (base_file) does not exist.")

    def test_matches_ignore_prefix_collision_symlink_targets(self) -> None:
        repo_path = os.path.realpath(self.component.full_path)
        outside_path = f"{repo_path}_outside"
        os.makedirs(outside_path)
        self.addCleanup(remove_tree, outside_path, True)

        pathlib.Path(os.path.join(outside_path, "cs.po")).write_text(
            'msgid "prefix-collision"\nmsgstr ""\n', encoding="utf-8"
        )

        os.symlink(
            outside_path, os.path.join(self.component.full_path, "prefix-collision")
        )

        self.assertNotIn("prefix-collision/cs.po", self.discovery.matched_files)

    def test_matches_prune_prefix_collision_symlink_directories(self) -> None:
        repo_path = os.path.realpath(self.component.full_path)
        outside_path = f"{repo_path}_outside"
        os.makedirs(outside_path)
        self.addCleanup(remove_tree, outside_path, True)

        os.symlink(
            outside_path, os.path.join(self.component.full_path, "prefix-collision")
        )

        walk_calls: list[str] = []

        def fake_walk(path: str, *, followlinks: bool):
            self.assertEqual(path, self.discovery.path)
            self.assertTrue(followlinks)

            dirnames = ["prefix-collision"]
            walk_calls.append(path)
            yield path, dirnames, []

            if "prefix-collision" in dirnames:
                nested = os.path.join(path, "prefix-collision")
                walk_calls.append(nested)
                yield nested, [], ["cs.po"]

        with patch("weblate.trans.discovery.os.walk", side_effect=fake_walk):
            self.assertEqual(self.discovery.matches, [])

        self.assertEqual(walk_calls, [self.discovery.path])

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


class DetectedDiscoveryPresetTest(SimpleTestCase):
    @staticmethod
    def make_discovery_result(
        *,
        name: str = "",
        filemask: str = "",
        template: str = "",
        file_format: str = "",
        intermediate: str = "",
        new_base: str = "",
    ) -> DiscoveryResult:
        data: ResultDict = {}
        if name:
            data["name"] = name
        if filemask:
            data["filemask"] = filemask
        if template:
            data["template"] = template
        if file_format:
            data["file_format"] = file_format
        if intermediate:
            data["intermediate"] = intermediate
        if new_base:
            data["new_base"] = new_base

        result = DiscoveryResult(data)
        result.meta = {"priority": 1000, "origin": None}
        return result

    def test_detected_presets_deduplicate_discovery_results(self) -> None:
        first = self.make_discovery_result(
            file_format="aresource",
            filemask="android/values-*/strings.xml",
            template="android/values/strings.xml",
        )
        second = self.make_discovery_result(
            file_format="aresource",
            filemask="android-not-synced/values-*/strings.xml",
            template="android-not-synced/values/strings.xml",
        )

        presets = get_detected_discovery_presets_from_results(
            [first, first.copy(), second, second.copy()]
        )

        self.assertEqual(len(presets), 1)
        self.assertEqual(
            presets[0]["values"]["match"],
            r"(?P<component>[^/]*)/values\-(?P<language>[^/.]*)/strings\.xml",
        )
        self.assertEqual(
            presets[0]["values"]["base_file_template"],
            "{{ component }}/values/strings.xml",
        )

    def test_detected_presets_keep_filename_suffix_from_translation_finder_cases(
        self,
    ) -> None:
        first = self.make_discovery_result(
            file_format="po",
            filemask="translations/manual/*/regexp.po",
            new_base="translations/manual/regexp.pot",
        )
        second = self.make_discovery_result(
            file_format="po",
            filemask="translations/manual/*/regexp_quick_reference.po",
            new_base="translations/manual/regexp_quick_reference.pot",
        )

        presets = get_detected_discovery_presets_from_results([first, second])

        self.assertEqual(len(presets), 1)
        self.assertEqual(
            presets[0]["values"]["match"],
            r"translations/manual/(?P<language>[^/.]*)/(?P<component>[^/]*)\.po",
        )
        self.assertEqual(
            presets[0]["values"]["new_base_template"],
            "translations/manual/{{ component }}.pot",
        )

    def test_detected_presets_cover_docs_filename_language_example(self) -> None:
        first = self.make_discovery_result(
            file_format="markdown",
            filemask="docs/news_*.md",
        )
        second = self.make_discovery_result(
            file_format="markdown",
            filemask="docs/guide_*.md",
        )

        presets = get_detected_discovery_presets_from_results([first, second])

        self.assertEqual(len(presets), 1)
        self.assertEqual(
            presets[0]["values"]["match"],
            r"docs/(?P<component>[^/]*)_(?P<language>[^/.]*)\.md",
        )
        self.assertEqual(
            presets[0]["values"]["name_template"],
            "{{ component }}",
        )

    def test_detected_presets_cover_translation_finder_locales_examples(self) -> None:
        first = self.make_discovery_result(
            file_format="po",
            filemask="locales/*/messages.po",
            new_base="locales/messages.pot",
        )
        second = self.make_discovery_result(
            file_format="po",
            filemask="locales/*/other.po",
            new_base="locales/other.pot",
        )

        presets = get_detected_discovery_presets_from_results([first, second])

        self.assertEqual(len(presets), 1)
        self.assertEqual(
            presets[0]["values"]["match"],
            r"locales/(?P<language>[^/.]*)/(?P<component>[^/]*)\.po",
        )
        self.assertEqual(
            presets[0]["values"]["new_base_template"],
            "locales/{{ component }}.pot",
        )

    def test_detected_presets_skip_ambiguous_generic_and_variant_pairs(self) -> None:
        first = self.make_discovery_result(
            file_format="csv",
            filemask="weblate/trans/tests/data/*.csv",
        )
        second = self.make_discovery_result(
            file_format="csv",
            filemask="weblate/trans/tests/data/*-mono.csv",
        )

        preset = build_detected_discovery_preset(first, second)

        self.assertIsNone(preset)

    def test_detected_presets_trim_common_word_fragments_to_separators(self) -> None:
        first = self.make_discovery_result(
            file_format="po",
            filemask="weblate/trans/tests/data/*-simple.po",
            new_base="weblate/trans/tests/data/hello-charset.pot",
        )
        second = self.make_discovery_result(
            file_format="po",
            filemask="weblate/trans/tests/data/*-three.po",
            new_base="weblate/trans/tests/data/hello-charset.pot",
        )

        preset = build_detected_discovery_preset(first, second)

        self.assertIsNotNone(preset)
        if preset is None:
            self.fail("Expected a detected preset")
        self.assertEqual(
            preset["values"]["match"],
            r"weblate/trans/tests/data/(?P<language>[^/.]*)\-(?P<component>[^/]*)\.po",
        )

    def test_detected_presets_skip_dot_suffix_variants_in_same_segment(self) -> None:
        first = self.make_discovery_result(
            file_format="ini",
            filemask="weblate/trans/tests/data/*.ini",
        )
        second = self.make_discovery_result(
            file_format="ini",
            filemask="weblate/trans/tests/data/*.joomla.ini",
        )

        preset = build_detected_discovery_preset(first, second)

        self.assertIsNone(preset)

    def test_component_detected_presets_fallback_to_eager_scan(self) -> None:
        component = self.make_mock_component()
        discovered = [
            self.make_discovery_result(
                file_format="aresource",
                filemask="android/values-*/strings.xml",
                template="android/values/strings.xml",
            ),
            self.make_discovery_result(
                file_format="aresource",
                filemask="android-not-synced/values-*/strings.xml",
                template="android-not-synced/values/strings.xml",
            ),
        ]

        with patch(
            "weblate.trans.discovery.discover",
            side_effect=[[], discovered],
        ) as mocked:
            presets = get_component_detected_discovery_presets(component)

        self.assertEqual(len(presets), 1)
        self.assertEqual(presets[0]["values"]["file_format"], "aresource")
        self.assertEqual(
            mocked.call_args_list,
            [
                call(
                    component.full_path,
                    source_language=component.source_language.code,
                    hint=component.filemask,
                ),
                call(
                    component.full_path,
                    source_language=component.source_language.code,
                    eager=True,
                    hint=component.filemask,
                ),
            ],
        )

    def test_detected_preset_key_matches_builtin_equivalent_po_layout(self) -> None:
        first = self.make_discovery_result(
            file_format="po",
            filemask="*/application.po",
        )
        second = self.make_discovery_result(
            file_format="po",
            filemask="*/other.po",
        )

        presets = get_detected_discovery_presets_from_results([first, second])

        self.assertEqual(len(presets), 1)
        self.assertEqual(
            get_detected_discovery_preset_values_key(presets[0]["values"]),
            (
                r"(?P<language>[^/.]*)/(?P<component>[^/]*)\.po",
                "po",
                "{{ component }}",
                "",
                "",
                "",
                "^[^.]+$",
            ),
        )

    @staticmethod
    def make_mock_component():
        class MockSourceLanguage:
            code = "en"

        class MockProject:
            pass

        class MockComponent:
            full_path = "mock-component"
            filemask = "po/*.po"
            source_language = MockSourceLanguage()
            project = MockProject()

        return MockComponent()
