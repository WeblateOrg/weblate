# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


"""Compatibility of independent alternatives with scalar and plural consumers."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.test import SimpleTestCase

from weblate.checks.base import MissingExtraDict, merge_diagnostics
from weblate.checks.consistency import SamePluralsCheck
from weblate.checks.format import CFormatCheck
from weblate.checks.glossary import GlossaryCheck
from weblate.checks.icu import ICUSourceCheck
from weblate.checks.markup import AsciiDocMarkupCheck, RSTReferencesCheck
from weblate.checks.placeholders import PlaceholderCheck
from weblate.checks.source import EllipsisCheck
from weblate.glossary.models import get_glossary_tuples, iter_glossary_alternatives
from weblate.lang.models import PluralMapper
from weblate.machinery.microsoft import MicrosoftCognitiveTranslation
from weblate.machinery.openai import OpenAITranslation
from weblate.trans.tests.factories import make_unit
from weblate.trans.util import join_plural


class MultivalueTest(SimpleTestCase):
    def test_markup_diagnostics_cover_all_alternatives(self) -> None:
        for check, sources, target in (
            (RSTReferencesCheck(), [":ref:`first`", ":ref:`second`"], ":ref:`other`"),
            (
                AsciiDocMarkupCheck(),
                ["image:first.png[First]", "image:second.png[Second]"],
                "image:other.png[Other]",
            ),
        ):
            with self.subTest(check=check.check_id):
                unit = make_unit(source=sources, target=target)
                unit.translation.component.file_format = "csv-multi"
                results = list(check.check_target_generator(sources, [target], unit))
                self.assertEqual(
                    results,
                    list(check.check_target_generator(sources[::-1], [target], unit)),
                )
                result = results[0]
                assert isinstance(result, dict)
                self.assertEqual(len(result["missing"]), 2)
                self.assertEqual(len(result["extra"]), 1)
                self.assertEqual(
                    list(check.check_target_generator(sources, [sources[0]], unit)),
                    [False],
                )

    def test_diagnostics_preserve_counts_and_errors(self) -> None:
        failures: list[MissingExtraDict] = [
            {"missing": ["markup", "markup"], "errors": ["first"]},
            {"missing": ["markup"], "errors": ["second"]},
        ]
        self.assertEqual(
            merge_diagnostics(failures),
            {"missing": ["markup", "markup"], "errors": ["first", "second"]},
        )
        self.assertEqual(
            merge_diagnostics(failures), merge_diagnostics(reversed(failures))
        )

    def test_format_diagnostics_do_not_depend_on_source_order(self) -> None:
        for sources in (["%s", "%d"], ["%d", "%s"]):
            with self.subTest(sources=sources):
                unit = make_unit(
                    source=sources, target="%f", flags="c-format,placeholders:%s:%d:%f"
                )
                unit.translation.component.file_format = "csv-multi"
                self.assertEqual(
                    list(CFormatCheck().check_generator(sources, ["%f"], unit)),
                    [{"missing": ["d", "s"], "extra": ["f"]}],
                )
                self.assertEqual(
                    PlaceholderCheck().check_target_unit(sources, ["%f"], unit),
                    {"missing": {"%s", "%d"}, "extra": {"%f"}},
                )
                self.assertEqual(
                    list(CFormatCheck().check_generator(sources, ["%s"], unit)), [False]
                )
                self.assertFalse(
                    PlaceholderCheck().check_target_unit(sources, ["%s"], unit)
                )

    def test_llm_omits_plural_context_for_alternatives(self) -> None:
        unit = make_unit(
            source=["application", "app", "program"], target=["aplikace", "program"]
        )
        unit.translation.component.file_format = "csv-multi"
        unit.plural_map = unit.get_source_plurals()
        machine = OpenAITranslation(
            {"key": "x", "model": "auto", "persona": "", "style": ""}
        )
        for text in unit.plural_map:
            self.assertIsNone(machine._get_plural_context(text, unit, "en"))  # ruff: ignore[private-member-access]
        unit.source = "application"
        unit.target = "aplikace"
        self.assertIsNone(machine._get_plural_context("program", unit, "en"))  # ruff: ignore[private-member-access]

    def test_readonly_glossary_aliases_are_interchangeable(self) -> None:
        sources = ["Weblate", "Weblate.org"]
        term = make_unit(source=sources, target="", flags="read-only")
        term.translation.component.file_format = "csv-multi"
        unit = make_unit(source=sources)
        unit.translation.component.file_format = "csv-multi"
        for matched in (None, ("weblate",), ("weblate", "weblate.org")):
            with self.subTest(matched=matched):
                term.matched_sources = matched
                with patch(
                    "weblate.glossary.models.get_glossary_terms", return_value=[term]
                ):
                    check = GlossaryCheck()
                    for target in sources:
                        self.assertFalse(check.check_single(unit.source, target, unit))
                    self.assertTrue(check.check_single(unit.source, "missing", unit))

    def test_source_checks_inspect_every_alternative(self) -> None:
        for check, invalid, flags in (
            (EllipsisCheck(), "Wait...", ""),
            (ICUSourceCheck(), "{invalid", "icu-message-format"),
        ):
            for sources in (["Valid", invalid], [invalid, "Valid"]):
                with self.subTest(check=check.check_id, sources=sources):
                    unit = make_unit(source=sources, flags=flags)
                    unit.translation.component.file_format = "csv-multi"
                    self.assertTrue(check.check_source(sources, unit))
                    self.assertTrue(
                        check.check_source_with_flags(sources, unit, unit.all_flags)
                    )
                    unit.all_flags.merge(check.ignore_string)
                    self.assertFalse(check.check_source(sources, unit))
                    self.assertFalse(
                        check.check_source_with_flags(sources, unit, unit.all_flags)
                    )

    def test_llm_omits_unpaired_existing_translation(self) -> None:
        machine = OpenAITranslation(
            {"key": "x", "model": "auto", "persona": "", "style": ""}
        )
        for sources, targets, expected in (
            (["application", "app"], ["aplikace", "program"], False),
            (["application"], ["aplikace", "program"], False),
            (["application"], ["aplikace"], True),
        ):
            with self.subTest(sources=sources, targets=targets):
                unit = make_unit(source=sources, target=targets)
                unit.translation.component.file_format = "csv-multi"
                unit.glossary_terms = []
                with patch.object(
                    machine,
                    "_build_string_payload",
                    side_effect=lambda text, *_args: {"source": text},
                ):
                    message = json.loads(
                        machine._get_message(  # ruff: ignore[private-member-access]
                            "en", "cs", [(text, unit) for text in sources]
                        )
                    )
                for payload in message["strings"]:
                    self.assertEqual("translation" in payload, expected)

    def test_same_plurals_excludes_independent_alternatives(self) -> None:
        for file_format in ("csv-multi", "po"):
            with self.subTest(file_format=file_format):
                sources = ["application", "app"]
                targets = ["aplikace", "aplikace"]
                unit = make_unit(source=sources, target=targets)
                unit.translation.component.file_format = file_format
                self.assertEqual(
                    SamePluralsCheck().check_target_unit(sources, targets, unit),
                    file_format == "po",
                )

    def test_microsoft_rebases_alternative_glossary_positions(self) -> None:
        for file_format in ("csv-multi",):
            with self.subTest(file_format=file_format):
                edited = make_unit(source=["application", "app and app", "apple"])
                edited.translation.component.file_format = file_format
                term = make_unit(source="app", target="aplikace")
                offset = len(join_plural(["application", ""]))
                term.glossary_positions = (
                    (offset, offset + 3),
                    (offset + 8, offset + 11),
                )
                machine = MicrosoftCognitiveTranslation(
                    {"region": "", "endpoint_url": "example.com"}
                )
                with patch(
                    "weblate.machinery.microsoft.get_glossary_terms",
                    return_value=[term],
                ):
                    highlights = list(machine.get_highlights("app and app", edited))
                    self.assertEqual(
                        [(start, end) for start, end, _, _ in highlights],
                        [(0, 3), (8, 11)],
                    )
                    self.assertFalse(list(machine.get_highlights("apple", edited)))

    def test_unit_multivalue_detection(self) -> None:
        for file_format in ("po", "csv-multi"):
            with self.subTest(file_format=file_format):
                unit = make_unit(source="application", target="aplikace")
                unit.translation.component.file_format = file_format
                self.assertFalse(unit.is_multivalue)
                expected = file_format != "po"
                self.assertEqual(
                    unit.has_multiple_values(["application", "app"], ["aplikace"]),
                    expected,
                )
                self.assertEqual(
                    unit.has_multiple_values(["application"], ["aplikace", "program"]),
                    expected,
                )
                unit.target = join_plural(["aplikace", "program"])
                self.assertEqual(unit.is_multivalue, expected)
                self.assertFalse(
                    unit.has_multiple_values(["application"], ["aplikace"])
                )
                unit.target = "aplikace"
                unit.source = join_plural(["application", "app"])
                self.assertEqual(unit.is_multivalue, expected)
                unit.source = "application"
                self.assertFalse(unit.is_multivalue)

    def test_format_checks_match_independent_alternatives(self) -> None:
        for file_format in ("csv-multi",):
            for check, flags in (
                (CFormatCheck(), "c-format"),
                (PlaceholderCheck(), "placeholders:%s:%d"),
            ):
                for sources in (
                    ["%s application", "application"],
                    ["application", "%s application"],
                ):
                    for targets, expected in (
                        (["aplikace"], False),
                        (["aplikace", "%s program", "nastroj", "%s aplikace"], False),
                        (["aplikace", "%d program"], True),
                    ):
                        with self.subTest(
                            file_format=file_format,
                            check=check.check_id,
                            sources=sources,
                            targets=targets,
                        ):
                            unit = make_unit(
                                source=sources, target=targets, flags=flags
                            )
                            unit.translation.component.file_format = file_format
                            self.assertEqual(
                                bool(check.check_target(sources, targets, unit)),
                                expected,
                            )

    def test_multivalue_format_checks_preserve_missing_details(self) -> None:
        sources = ["%s application", "%s app"]
        targets = ["%s aplikace", "program"]
        unit = make_unit(
            source=sources, target=targets, flags="c-format,placeholders:%s"
        )
        unit.translation.component.file_format = "csv-multi"
        results = list(CFormatCheck().check_generator(sources, targets, unit))
        self.assertFalse(results[0])
        self.assertEqual(results[1], {"missing": ["s"], "extra": []})
        self.assertEqual(
            PlaceholderCheck().check_target_unit(sources, targets, unit),
            {"missing": {"%s"}, "extra": set()},
        )

    def test_scalar_consumers_preserve_grammatical_plurals(self) -> None:
        unit = make_unit(source=["car", "cars"], target=["auto", "auta", "aut"])
        self.assertEqual(
            [(item.source, item.target) for item in iter_glossary_alternatives([unit])],
            [("car", "auto"), ("cars", "auta"), ("cars", "aut")],
        )
        self.assertEqual(
            list(get_glossary_tuples([unit])), [("car", "auto"), ("cars", "auta")]
        )
        unit.matched_sources = ("cars",)
        self.assertEqual(list(get_glossary_tuples([unit])), [("cars", "auta")])

    def test_single_term_machinery_in_multivalue_formats(self) -> None:
        for file_format in ("csv-multi",):
            for code in ("cs", "ko"):
                for target in ("", "existing"):
                    with self.subTest(
                        file_format=file_format, code=code, target=target
                    ):
                        unit = make_unit(source="application", target=target, code=code)
                        unit.translation.component.file_format = file_format
                        multiple_targets = make_unit(
                            source="application", target=["one", "two"], code=code
                        )
                        multiple_sources = make_unit(
                            source=["application", "app"], code=code
                        )
                        for other in (multiple_targets, multiple_sources):
                            other.translation = unit.translation
                        machine = MicrosoftCognitiveTranslation(
                            {"region": "", "endpoint_url": "example.com"}
                        )
                        result = [[{"text": "translated", "quality": 100}]]
                        with (
                            patch.object(machine, "account_usage"),
                            patch.object(
                                machine, "get_languages", return_value=("en", code)
                            ),
                            patch.object(
                                machine, "_translate_sources", return_value=result
                            ) as translate,
                        ):
                            self.assertEqual(machine.translate(unit), result)
                            machine.batch_translate(
                                [multiple_targets, unit, multiple_sources]
                            )
                        self.assertEqual(translate.call_count, 2)
                        for call in translate.call_args_list:
                            self.assertEqual(call.args[2], [("application", unit)])
                        self.assertEqual(unit.machinery["translation"], ["translated"])
                        self.assertFalse(multiple_targets.machinery)
                        self.assertFalse(multiple_sources.machinery)

    def test_multivalue_machinery_maps_alternatives_independently(self) -> None:
        for file_format in ("csv-multi",):
            for code in ("cs", "ko"):
                with self.subTest(file_format=file_format, code=code):
                    unit = make_unit(source=["application", "app"], code=code)
                    unit.translation.component.file_format = file_format
                    mapper = PluralMapper(
                        unit.translation.component.source_language.plural,
                        unit.translation.plural,
                    )
                    self.assertEqual(mapper.map(unit), ["application", "app"])
                    other = make_unit(target=["program", "tool", "utility"])
                    self.assertEqual(
                        mapper.map(unit, other), ["program", "tool", "utility"]
                    )
