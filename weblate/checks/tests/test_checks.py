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

"""Helper for quality checks tests."""

import random

from django.test import SimpleTestCase

from weblate.checks.flags import Flags
from weblate.lang.models import Language, Plural


class MockLanguage(Language):
    """Mock language object."""

    class Meta:
        proxy = True

    def __init__(self, code="cs"):
        super().__init__(code=code)
        self.plural = Plural(language=self)


class MockProject:
    """Mock project object."""

    def __init__(self):
        self.id = 1
        self.use_shared_tm = True
        self.name = "MockProject"


class MockComponent:
    """Mock component object."""

    def __init__(self):
        self.id = 1
        self.source_language = MockLanguage("en")
        self.project = MockProject()
        self.name = "MockComponent"
        self.file_format = "auto"


class MockTranslation:
    """Mock translation object."""

    def __init__(self, code="cs"):
        self.language = MockLanguage(code)
        self.component = MockComponent()
        self.is_template = False
        self.is_source = False


class MockUnit:
    """Mock unit object."""

    def __init__(self, id_hash=None, flags="", code="cs", source="", note=""):
        if id_hash is None:
            id_hash = random.randint(0, 65536)
        self.id_hash = id_hash
        self.flags = Flags(flags)
        self.translation = MockTranslation(code)
        self.source = source
        self.fuzzy = False
        self.translated = True
        self.readonly = False
        self.state = 20
        self.note = note
        self.check_cache = {}
        self.machinery = {"best": -1}

    @property
    def all_flags(self):
        return self.flags

    def get_source_plurals(self):
        return [self.source]

    @property
    def source_string(self):
        return self.source


class CheckTestCase(SimpleTestCase):
    """Generic test, also serves for testing base class."""

    check = None
    default_lang = "cs"

    def setUp(self):
        self.test_empty = ("", "", "")
        self.test_good_matching = ("string", "string", "")
        self.test_good_none = ("string", "string", "")
        self.test_good_ignore = ()
        self.test_good_flag = ()
        self.test_failure_1 = ()
        self.test_failure_2 = ()
        self.test_failure_3 = ()
        self.test_ignore_check = (
            "x",
            "x",
            self.check.ignore_string if self.check else "",
        )
        self.test_highlight = ()

    def do_test(self, expected, data, lang=None):
        """Perform single check if we have data to test."""
        if lang is None:
            lang = self.default_lang
        if not data or self.check is None:
            return
        result = self.check.check_single(
            data[0], data[1], MockUnit(None, data[2], lang, source=data[0])
        )
        if expected:
            self.assertTrue(
                result, 'Check did not fire for "{}"/"{}" ({})'.format(*data)
            )
        else:
            self.assertFalse(result, 'Check did fire for "{}"/"{}" ({})'.format(*data))

    def test_single_good_matching(self):
        self.do_test(False, self.test_good_matching)

    def test_single_good_none(self):
        self.do_test(False, self.test_good_none)

    def test_single_good_ignore(self):
        self.do_test(False, self.test_good_ignore)

    def test_single_empty(self):
        self.do_test(False, self.test_empty)

    def test_single_failure_1(self):
        self.do_test(True, self.test_failure_1)

    def test_single_failure_2(self):
        self.do_test(True, self.test_failure_2)

    def test_single_failure_3(self):
        self.do_test(True, self.test_failure_3)

    def test_check_good_flag(self):
        if self.check is None or not self.test_good_flag:
            return
        self.assertFalse(
            self.check.check_target(
                [self.test_good_flag[0]],
                [self.test_good_flag[1]],
                MockUnit(
                    None,
                    self.test_good_flag[2],
                    self.default_lang,
                    source=self.test_good_flag[0],
                ),
            )
        )

    def test_check_good_matching_singular(self):
        if self.check is None:
            return
        self.assertFalse(
            self.check.check_target(
                [self.test_good_matching[0]],
                [self.test_good_matching[1]],
                MockUnit(
                    None,
                    self.test_good_matching[2],
                    self.default_lang,
                    source=self.test_good_matching[0],
                ),
            )
        )

    def test_check_good_none_singular(self):
        if self.check is None:
            return
        self.assertFalse(
            self.check.check_target(
                [self.test_good_none[0]],
                [self.test_good_none[1]],
                MockUnit(
                    None,
                    self.test_good_none[2],
                    self.default_lang,
                    source=self.test_good_none[0],
                ),
            )
        )

    def test_check_good_ignore_singular(self):
        if self.check is None or not self.test_good_ignore:
            return
        self.assertFalse(
            self.check.check_target(
                [self.test_good_ignore[0]],
                [self.test_good_ignore[1]],
                MockUnit(
                    None,
                    self.test_good_ignore[2],
                    self.default_lang,
                    source=self.test_good_ignore[0],
                ),
            )
        )

    def test_check_good_matching_plural(self):
        if self.check is None:
            return
        self.assertFalse(
            self.check.check_target(
                [self.test_good_matching[0]] * 2,
                [self.test_good_matching[1]] * 3,
                MockUnit(
                    None,
                    self.test_good_matching[2],
                    self.default_lang,
                    source=self.test_good_matching[0],
                ),
            )
        )

    def test_check_failure_1_singular(self):
        if not self.test_failure_1 or self.check is None:
            return
        self.assertTrue(
            self.check.check_target(
                [self.test_failure_1[0]],
                [self.test_failure_1[1]],
                MockUnit(
                    None,
                    self.test_failure_1[2],
                    self.default_lang,
                    source=self.test_failure_1[0],
                ),
            )
        )

    def test_check_failure_1_plural(self):
        if not self.test_failure_1 or self.check is None:
            return
        self.assertTrue(
            self.check.check_target(
                [self.test_failure_1[0]] * 2,
                [self.test_failure_1[1]] * 3,
                MockUnit(
                    None,
                    self.test_failure_1[2],
                    self.default_lang,
                    source=self.test_failure_1[0],
                ),
            )
        )

    def test_check_failure_2_singular(self):
        if not self.test_failure_2 or self.check is None:
            return
        self.assertTrue(
            self.check.check_target(
                [self.test_failure_2[0]],
                [self.test_failure_2[1]],
                MockUnit(
                    None,
                    self.test_failure_2[2],
                    self.default_lang,
                    source=self.test_failure_2[0],
                ),
            )
        )

    def test_check_failure_3_singular(self):
        if not self.test_failure_3 or self.check is None:
            return
        self.assertTrue(
            self.check.check_target(
                [self.test_failure_3[0]],
                [self.test_failure_3[1]],
                MockUnit(
                    None,
                    self.test_failure_3[2],
                    self.default_lang,
                    source=self.test_failure_3[0],
                ),
            )
        )

    def test_check_ignore_check(self):
        if self.check is None:
            return
        self.assertFalse(
            self.check.check_target(
                [self.test_ignore_check[0]] * 2,
                [self.test_ignore_check[1]] * 3,
                MockUnit(
                    None,
                    self.test_ignore_check[2],
                    self.default_lang,
                    source=self.test_ignore_check[0],
                ),
            )
        )

    def test_check_highlight(self):
        if self.check is None or not self.test_highlight:
            return
        unit = MockUnit(
            None,
            self.test_highlight[0],
            self.default_lang,
            source=self.test_highlight[1],
        )
        self.assertEqual(
            self.check.check_highlight(self.test_highlight[1], unit),
            self.test_highlight[2],
        )
