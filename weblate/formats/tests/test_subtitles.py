# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Subtitle translation persistence."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from weblate.formats.ttkit import (
    AdvSubStationAlphaFormat,
    MicroDVDFormat,
    SubRipFormat,
    SubStationAlphaFormat,
)
from weblate.trans.models.translation import Translation, read_stored_content


class SubRipFormatTest(SimpleTestCase):
    format_class = SubRipFormat
    SAMPLE = "1\n00:00:01,000 --> 00:00:03,000\nSource cue\n\n"
    SECOND_CUE = "2\n00:00:04,000 --> 00:00:06,000\nSecond cue\n\n"

    def setUp(self) -> None:
        super().setUp()
        directory = TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(directory.cleanup)
        self.filename = Path(directory.name, f"cs.{self.format_class.format_id}")
        template_filename = self.filename.with_stem("en")
        template_filename.write_text(self.SAMPLE + self.SECOND_CUE, encoding="utf-8")
        self.filename.write_text(
            self.SAMPLE.replace("Source cue", "Translated cue"), encoding="utf-8"
        )
        self.template = self.format_class(template_filename, is_template=True)
        self.storage = self.format_class(self.filename, template_store=self.template)
        self.unit, self.missing_unit = self.storage.content_units

    def reload(self) -> SubRipFormat:
        return self.format_class(self.filename, template_store=self.template)

    def test_load(self) -> None:
        self.assertEqual(self.unit.source, "Source cue")
        self.assertEqual(self.unit.target, "Translated cue")
        self.assertEqual(self.missing_unit.source, "Second cue")
        self.assertEqual(self.missing_unit.target, "")
        self.assertFalse(self.missing_unit.has_unit())

    def test_edit(self) -> None:
        original = {1: (self.unit, read_stored_content(self.unit))}
        locations = self.unit.locations
        self.unit.set_target("Edited translation")
        self.assertEqual(self.unit.target, "Edited translation")
        self.assertTrue(Translation.has_stored_content_changed(original))
        self.storage.save()

        unit = self.reload().content_units[0]
        self.assertEqual(unit.target, "Edited translation")
        self.assertEqual(unit.source, "Source cue")
        self.assertEqual(", ".join(unit.unit.getlocations()), locations)

    def test_unchanged_target(self) -> None:
        original = {1: (self.unit, read_stored_content(self.unit))}
        self.unit.set_target(self.unit.target)
        self.assertFalse(Translation.has_stored_content_changed(original))

    def test_empty_target(self) -> None:
        self.assertEqual(self.unit.target, "Translated cue")
        self.unit.set_target("")
        self.assertEqual(self.unit.target, "")
        self.unit.invalidate_all_caches()
        self.assertEqual(self.unit.target, "")

    def test_add_missing_translation(self) -> None:
        self.assertEqual(self.missing_unit.target, "")
        locations = self.missing_unit.locations
        unit, add = self.storage.find_unit(
            self.missing_unit.context, self.missing_unit.source
        )
        self.assertTrue(add)
        self.assertEqual(unit.target, "Second cue")
        self.storage.add_unit(unit)
        unit.set_target("Added translation")
        self.assertEqual(unit.target, "Added translation")
        self.storage.save()

        unit = self.reload().content_units[1]
        self.assertEqual(unit.target, "Added translation")
        self.assertEqual(unit.source, "Second cue")
        self.assertEqual(", ".join(unit.unit.getlocations()), locations)


class MicroDVDFormatTest(SubRipFormatTest):
    format_class = MicroDVDFormat
    SAMPLE = "{25}{75}Source cue\n"
    SECOND_CUE = "{100}{150}Second cue\n"


class AdvSubStationAlphaFormatTest(SubRipFormatTest):
    format_class = AdvSubStationAlphaFormat
    SAMPLE = """[Script Info]
ScriptType: v4.00+

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0000,0000,0000,,Source cue
"""
    SECOND_CUE = (
        "Dialogue: 0,0:00:04.00,0:00:06.00,Default,,0000,0000,0000,,Second cue\n"
    )


class SubStationAlphaFormatTest(SubRipFormatTest):
    format_class = SubStationAlphaFormat
    SAMPLE = """[Script Info]
ScriptType: v4.00

[Events]
Format: Marked, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: Marked=0,0:00:01.00,0:00:03.00,Default,,0000,0000,0000,,Source cue
"""
    SECOND_CUE = (
        "Dialogue: Marked=0,0:00:04.00,0:00:06.00,Default,,0000,0000,0000,,Second cue\n"
    )
