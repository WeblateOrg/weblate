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

"""Tests for ICU MessageFormat checks."""

from weblate.checks.icu import ICUMessageFormatCheck, ICUSourceCheck
from weblate.checks.tests.test_checks import CheckTestCase, MockUnit


class ICUMessageFormatCheckTest(CheckTestCase):
    check = ICUMessageFormatCheck()

    id_hash = "icu_message_format"
    flag = "icu-message-format"
    flags = None

    def get_mock(self, source=None, flags=None):
        if not flags and self.flags:
            flags = self.flags
        elif flags and self.flags:
            flags = f"{self.flags}:{flags}"

        if flags:
            flags = f"{self.flag}, icu-flags:{flags}"
        else:
            flags = self.flag

        return MockUnit(
            self.id_hash, flags=flags, source=source, is_source=source is not None
        )

    def test_plain(self):
        self.assertFalse(
            self.check.check_format("string", "string", False, self.get_mock())
        )

    def test_plain_source(self):
        self.assertFalse(
            self.check.check_format("string", "string", False, self.get_mock("string"))
        )

    def test_malformed(self):
        result = self.check.check_format(
            "Hello, {name}!", "Hello, {name!", False, self.get_mock()
        )

        self.assertTrue(result)
        self.assertIn("syntax", result)
        syntax = result["syntax"]
        self.assertTrue(isinstance(syntax, list) and len(syntax) == 1)
        self.assertIn("Expected , or }", syntax[0].msg)

    def test_malformed_source(self):
        # When dealing with a translation and not the source,
        # any source issue is silently discarded.
        self.assertFalse(
            self.check.check_format(
                "Hello, {name!", "Hello, {name}!", False, self.get_mock()
            )
        )

        # However, if the unit is_source, we return syntax errors.
        result = self.check.check_format(
            "Hello, {name!", "Hello, {name}!", False, self.get_mock("Hello, {name!")
        )

        self.assertTrue(result)
        self.assertIn("syntax", result)
        syntax = result["syntax"]
        self.assertTrue(isinstance(syntax, list) and len(syntax) == 1)
        self.assertIn("Expected , or }", syntax[0].msg)

    def test_source(self):
        check = ICUSourceCheck()
        self.assertFalse(check.check_source_unit([""], self.get_mock()))
        self.assertFalse(check.check_source_unit(["Hello, {name}!"], self.get_mock()))

    def test_source_non_icu(self):
        check = ICUSourceCheck()
        source = "icon in the top bar: {{ img-queue | strip }}"
        self.assertFalse(check.check_source([source], MockUnit("x", source=source)))

    def test_bad_source(self):
        check = ICUSourceCheck()
        self.assertTrue(check.check_source_unit(["Hello, {name!"], self.get_mock()))

    def test_no_formats(self):
        self.assertFalse(
            self.check.check_format(
                "Hello, {name}!", "Hallo, {name}!", False, self.get_mock()
            )
        )

    def test_whitespace(self):
        self.assertFalse(
            self.check.check_format(
                "Hello, {  \t name\n  \n}!", "Hallo, {name}!", False, self.get_mock()
            )
        )

    def test_missing_placeholder(self):
        result = self.check.check_format(
            "Hello, {name}!", "Hallo, Fred!", False, self.get_mock()
        )

        self.assertDictEqual(result, {"missing": ["name"]})

    def test_extra_placeholder(self):
        result = self.check.check_format(
            "Hello, {firstName}!",
            "Hallo, {firstName} {lastName}!",
            False,
            self.get_mock(),
        )

        self.assertDictEqual(result, {"extra": ["lastName"]})

    def test_types(self):
        self.assertFalse(
            self.check.check_format(
                "Cost: {value, number, ::currency/USD}",
                "Kosten: {value, number, ::currency/USD}",
                False,
                self.get_mock(),
            )
        )

    def test_wrong_types(self):
        result = self.check.check_format(
            "Cost: {value, number, ::currency/USD}",
            "Kosten: {value}",
            False,
            self.get_mock(),
        )

        self.assertDictEqual(result, {"wrong_type": ["value"]})

    def test_flag_wrong_types(self):
        self.assertFalse(
            self.check.check_format(
                "{value, number}", "{value}", False, self.get_mock(None, "-types")
            )
        )

    def test_more_wrong_types(self):
        result = self.check.check_format(
            "Cost: {value, foo}", "Kosten: {value, bar}", False, self.get_mock()
        )

        self.assertDictEqual(result, {"wrong_type": ["value"]})

    def test_plural_types(self):
        self.assertFalse(
            self.check.check_format(
                "You have {count, plural, one {# message} other {# messages}}. "
                "Yes. {count, number}.",
                "Sie haben {count, plural, one {# Nachricht} other "
                "{# Nachrichten}}. Ja. {count, number}.",
                False,
                self.get_mock(),
            )
        )

    def test_no_other(self):
        result = self.check.check_format(
            "{count, number}", "{count, plural, one {typo}}", False, self.get_mock()
        )

        self.assertDictEqual(result, {"no_other": ["count"]})

    def test_flag_no_other(self):
        inp = "{count, plural, one {#}}"
        self.assertFalse(
            self.check.check_format(
                inp, inp, False, self.get_mock(inp, "-require_other")
            )
        )

    def test_random_submessage(self):
        inp = "{count, test, one {yes} other {no}}"
        self.assertFalse(self.check.check_format(inp, inp, False, self.get_mock()))

    def test_bad_select(self):
        result = self.check.check_format(
            "{pronoun,select,hehim{}sheher{}other{}}",
            "{pronoun,select,he{}sheeher{}other{}}",
            False,
            self.get_mock(),
        )

        self.assertDictEqual(
            result, {"bad_submessage": [["pronoun", {"he", "sheeher"}]]}
        )

    def test_flag_bad_select(self):
        # This also checks multiple flags.
        self.assertFalse(
            self.check.check_format(
                "{n,select,one{}two{}}",
                "{n,select,three{}four{}}",
                False,
                self.get_mock(None, "-require_other:-submessage_selectors"),
            )
        )

    def test_bad_plural(self):
        result = self.check.check_format(
            "{count, number}",
            "{count, plural, bad {typo} other {okay}}",
            False,
            self.get_mock(),
        )

        self.assertDictEqual(result, {"bad_plural": [["count", {"bad"}]]})

    def test_flag_bad_plural(self):
        self.assertFalse(
            self.check.check_format(
                "{n,number}",
                "{n,plural,bad{}other{}}",
                False,
                self.get_mock(None, "-plural_selectors"),
            )
        )

    def test_good_plural(self):
        self.assertFalse(
            self.check.check_format(
                "{count, number}",
                "{count, plural, zero{#} one{#} two{#} few{#} many{#} "
                "other{#} =0{#} =-12{#} =391.5{#}}",
                False,
                self.get_mock(),
            )
        )

    def test_check_highlight(self):
        highlights = list(
            self.check.check_highlight(
                "Hello, <link> {na<>me} </link>. You have {count, plural, one "
                "{# message} other {# messages}}.",
                self.get_mock(),
            )
        )

        self.assertListEqual(
            highlights,
            [
                (14, 22, "{na<>me}"),
            ],
        )

    def test_check_error_highlight(self):
        highlights = list(
            self.check.check_highlight(
                "Hello, {name}! You have {count,number", self.get_mock()
            )
        )

        self.assertListEqual(highlights, [])

    def test_check_flag_highlight(self):
        highlights = list(
            self.check.check_highlight(
                "Hello, {name}! You have {count,number",
                self.get_mock(None, "-highlight"),
            )
        )

        self.assertListEqual(highlights, [])

    def test_check_no_highlight(self):
        highlights = list(
            self.check.check_highlight(
                "Hello, {name}!", MockUnit("java_format", flags="java-format")
            )
        )

        self.assertListEqual(highlights, [])


# This is a sub-class of our existing test set because this format is an extension
# of the other format and it should handle all existing syntax properly.
class ICUXMLFormatCheckTest(ICUMessageFormatCheckTest):

    flags = "xml"

    def test_tags(self):
        self.assertFalse(
            self.check.check_format(
                "Hello <user/>! <link>Click here!</link>",
                "Hallo <user />! <link>Klicke hier!</link>",
                False,
                None,
            )
        )

    def test_empty_tags(self):
        self.assertFalse(
            self.check.check_format(
                "<empty />", "<empty/><empty></empty>", False, self.get_mock()
            )
        )

    def test_incorrectly_full_tags(self):
        result = self.check.check_format(
            "<empty /><full>tag</full>",
            "<full /><empty>tag</empty>",
            False,
            self.get_mock(),
        )

        self.assertDictEqual(
            result, {"tag_not_empty": ["empty"], "tag_empty": ["full"]}
        )

    def test_tag_vs_placeholder(self):
        result = self.check.check_format(
            "Hello, <bold>{firstName}</bold>.",
            "Hello {bold} <firstName />.",
            False,
            self.get_mock(),
        )

        self.assertDictEqual(
            result,
            {
                "should_be_tag": ["bold"],
                "not_tag": ["firstName"],
            },
        )

    def test_flag_tags(self):
        self.assertFalse(
            self.check.check_format(
                "Hello, <bold>{firstName}</bold>.",
                "Hello {bold} <firstName />.",
                False,
                self.get_mock(None, "-tags"),
            )
        )

    def test_check_highlight(self):
        highlights = list(
            self.check.check_highlight(
                "Hello, <link> {na<>me} </link>. You have {count, plural, "
                "one {# message} other {# messages}}.",
                self.get_mock(),
            )
        )

        self.assertListEqual(
            highlights,
            [
                (14, 22, "{na<>me}"),
            ],
        )

    def test_not_a_tag(self):
        self.assertFalse(
            self.check.check_format(
                "I <3 Software", "I <3 Open Source", False, self.get_mock()
            )
        )

    def test_tag_prefix(self):
        self.assertFalse(
            self.check.check_format(
                "<bold>test",
                "<italic>test",
                False,
                self.get_mock(None, 'xml, icu-tag-prefix:"x:"'),
            )
        )


class ICUXMLStrictFormatCheckTest(ICUXMLFormatCheckTest):

    flags = "strict-xml"

    def test_tag_prefix(self):
        # Tag Prefix is ignored with strict tags.
        pass

    def test_not_a_tag(self):
        result = self.check.check_format(
            "I <3 Software", "I <3 Open Source", False, self.get_mock()
        )

        self.assertTrue(result)
        self.assertIn("syntax", result)
        syntax = result["syntax"]
        self.assertTrue(isinstance(syntax, list) and len(syntax) == 1)
        self.assertIn("Expected > or />", syntax[0].msg)
