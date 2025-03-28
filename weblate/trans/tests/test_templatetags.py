# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Testing of template tags."""

from __future__ import annotations

import datetime

from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from django.utils.html import format_html

from weblate.auth.models import User
from weblate.checks.flags import Flags
from weblate.checks.tests.test_checks import MockLanguage, MockUnit
from weblate.lang.models import Language
from weblate.trans.models import Component, Project, Translation, Unit
from weblate.trans.templatetags.translations import (
    format_translation,
    get_location_links,
    naturaltime,
)
from weblate.trans.tests.test_views import FixtureTestCase

TEST_DATA = (
    (0, "now"),
    (1, "a second from now"),
    (-1, "a second ago"),
    (2, "2 seconds from now"),
    (-2, "2 seconds ago"),
    (60, "a minute from now"),
    (-60, "a minute ago"),
    (120, "2 minutes from now"),
    (-120, "2 minutes ago"),
    (3600, "an hour from now"),
    (-3600, "an hour ago"),
    (3600 * 2, "2 hours from now"),
    (-3600 * 2, "2 hours ago"),
    (3600 * 24, "tomorrow"),
    (-3600 * 24, "yesterday"),
    (3600 * 24 * 2, "2 days from now"),
    (-3600 * 24 * 2, "2 days ago"),
    (3600 * 24 * 7, "a week from now"),
    (-3600 * 24 * 7, "a week ago"),
    (3600 * 24 * 14, "2 weeks from now"),
    (-3600 * 24 * 14, "2 weeks ago"),
    (3600 * 24 * 30, "a month from now"),
    (-3600 * 24 * 30, "a month ago"),
    (3600 * 24 * 60, "2 months from now"),
    (-3600 * 24 * 60, "2 months ago"),
    (3600 * 24 * 365, "a year from now"),
    (-3600 * 24 * 365, "a year ago"),
    (3600 * 24 * 365 * 2, "2 years from now"),
    (-3600 * 24 * 365 * 2, "2 years ago"),
)


class NaturalTimeTest(SimpleTestCase):
    """Testing of natural time conversion."""

    def test_natural(self) -> None:
        now = timezone.now()
        for diff, expected in TEST_DATA:
            testdate = now + datetime.timedelta(seconds=diff)
            result = naturaltime(testdate, now=now)
            expected = format_html(
                '<span title="{}">{}</span>',
                testdate.replace(microsecond=0).isoformat(),
                expected,
            )
            self.assertEqual(
                expected,
                result,
                f"naturaltime({testdate}) {result!r} != {expected!r}",
            )


class LocationLinksTest(TestCase):
    def setUp(self) -> None:
        self.unit = Unit(
            translation=Translation(
                component=Component(
                    project=Project(slug="p", name="p"),
                    source_language=Language(),
                    slug="c",
                    name="c",
                    pk=-1,
                ),
                language=Language(),
            ),
            pk=-1,
        )
        self.unit.source_unit = self.unit
        self.user = User.objects.create(username="location-test")

    def test_empty(self) -> None:
        self.assertEqual(get_location_links(self.user, self.unit), "")

    def test_numeric(self) -> None:
        self.unit.location = "123"
        self.assertEqual(get_location_links(self.user, self.unit), "string ID 123")

    def test_filename(self) -> None:
        self.unit.location = "f&oo.bar:123"
        self.assertEqual(get_location_links(self.user, self.unit), "f&amp;oo.bar:123")

    def test_filenames(self) -> None:
        self.unit.location = "foo.bar:123,bar.foo:321"
        self.assertEqual(
            get_location_links(self.user, self.unit),
            'foo.bar:123\n<span class="divisor">•</span>\nbar.foo:321',
        )
        self.assertEqual(
            get_location_links(None, self.unit),
            'foo.bar:123\n<span class="divisor">•</span>\nbar.foo:321',
        )

    def test_repowebs(self) -> None:
        self.unit.translation.component.repoweb = (
            "http://example.net/{{filename}}#L{{line}}"
        )
        self.unit.location = "foo.bar:123,bar.foo:321"
        self.assertHTMLEqual(
            get_location_links(self.user, self.unit),
            """
            <a class="wrap-text"
                href="http://example.net/foo.bar#L123" tabindex="-1" target="_blank"
                dir="ltr" rel="noopener noreferrer">
            foo.bar:123
            </a>
            <span class="divisor">•</span>
            <a class="wrap-text"
                href="http://example.net/bar.foo#L321" tabindex="-1" target="_blank"
                dir="ltr" rel="noopener noreferrer">
            bar.foo:321
            </a>
            """,
        )

    def test_repoweb(self) -> None:
        self.unit.translation.component.repoweb = (
            "http://example.net/{{filename}}#L{{line}}"
        )
        self.unit.location = "foo.bar:123"
        self.assertHTMLEqual(
            get_location_links(self.user, self.unit),
            """
            <a class="wrap-text"
                href="http://example.net/foo.bar#L123" tabindex="-1" target="_blank"
                dir="ltr" rel="noopener noreferrer">
            foo.bar:123
            </a>
            """,
        )

    def test_user_url(self) -> None:
        self.unit.translation.component.repoweb = (
            "http://example.net/{{filename}}#L{{line}}"
        )
        self.user.profile.editor_link = "editor://open/?file={{filename}}&line={{line}}"
        self.unit.location = "foo.bar:123"
        self.assertHTMLEqual(
            get_location_links(self.user, self.unit),
            """
            <a class="wrap-text"
                href="editor://open/?file=foo.bar&amp;line=123" tabindex="-1" target="_blank"
                dir="ltr" rel="noopener noreferrer">
            foo.bar:123
            </a>
            """,
        )

    def test_filename_quote(self) -> None:
        self.unit.translation.component.repoweb = (
            "http://example.net/{{filename}}#L{{line}}"
        )
        self.unit.location = "foo+bar:321"
        self.assertHTMLEqual(
            get_location_links(self.user, self.unit),
            """
            <a class="wrap-text"
                href="http://example.net/foo%2Bbar#L321" tabindex="-1" target="_blank"
                dir="ltr" rel="noopener noreferrer">
            foo+bar:321
            </a>
            """,
        )

    def test_absolute_url(self) -> None:
        self.unit.translation.component.repoweb = (
            "http://example.net/{{filename}}#L{{line}}"
        )
        self.unit.location = (
            "foo.bar:123,bar.foo:321,https://example.com/foo,http://example.org/bar"
        )
        self.assertHTMLEqual(
            get_location_links(self.user, self.unit),
            """
            <a class="wrap-text"
                href="http://example.net/foo.bar#L123" tabindex="-1" target="_blank"
                dir="ltr" rel="noopener noreferrer">
            foo.bar:123
            </a>
            <span class="divisor">•</span>
            <a class="wrap-text"
                href="http://example.net/bar.foo#L321" tabindex="-1" target="_blank"
                dir="ltr" rel="noopener noreferrer">
            bar.foo:321
            </a>
            <span class="divisor">•</span>
            <a class="wrap-text"
                href="https://example.com/foo" tabindex="-1" target="_blank"
                dir="ltr" rel="noopener noreferrer">
            https://example.com/foo
            </a>
            <span class="divisor">•</span>
            <a class="wrap-text"
                href="http://example.org/bar" tabindex="-1" target="_blank"
                dir="ltr" rel="noopener noreferrer">
            http://example.org/bar
            </a>
            """,
        )


class TranslationFormatTestCase(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.translation = self.get_translation()

    def build_glossary(self, source: str, target: str, positions=list[tuple[int, int]]):
        unit = Unit(source=source, target=target, translation=self.translation)
        unit.glossary_positions = positions
        return unit

    def test_basic(self) -> None:
        self.assertEqual(
            format_translation(
                ["Hello world"],
                self.component.source_language,
            )["items"][0]["content"],
            "Hello world",
        )

    def test_diff(self) -> None:
        self.assertEqual(
            format_translation(
                ["Hello world"],
                self.component.source_language,
                diff="Hello, world!",
            )["items"][0]["content"],
            "Hello<del>,</del> world<del>!</del>",
        )
        self.assertHTMLEqual(
            format_translation(
                ["Hello world"],
                self.component.source_language,
                diff="Hello  world",
            )["items"][0]["content"],
            """
            Hello
            <del>
                <span class="hlspace">
                    <span class="space-space"> </span>
                </span>
            </del>
            world
            """,
        )

    def test_diff_github_9821(self) -> None:
        unit = Unit(translation=self.translation)
        unit.all_flags = Flags("python-brace-format")
        self.assertHTMLEqual(
            format_translation(
                ["由 {username} 邀请至 {project} 项目。"],
                self.component.source_language,
                diff="由 {username} 邀请至 {site_title}。",
                unit=unit,
            )["items"][0]["content"],
            """
            由
            <span class="hlcheck" data-value="{username}"><span class="highlight-number"></span>{username}</span>
             邀请至
             {<del>site_title}</del><ins>project} 项目</ins>。
            """,
        )

    def test_diff_whitespace(self) -> None:
        self.assertHTMLEqual(
            format_translation(
                ["Helloworld"],
                self.component.source_language,
                diff="Hello world",
            )["items"][0]["content"],
            """Hello
            <del>
                <span class="hlspace">
                    <span class="space-space"> </span>
                </span>
            </del>
            world
            """,
        )
        self.assertHTMLEqual(
            format_translation(
                ["Hello world"],
                self.component.source_language,
                diff="Helloworld",
            )["items"][0]["content"],
            """Hello
            <ins>
                <span class="hlspace">
                    <span class="space-space"> </span>
                </span>
            </ins>
            world
            """,
        )

    def test_diff_whitespace_changed(self) -> None:
        self.assertHTMLEqual(
            format_translation(
                ["Hello  world"],
                self.component.source_language,
                diff="Hello world",
            )["items"][0]["content"],
            """Hello
            <span class="hlspace">
                <span class="space-space">
                </span>
            </span>
            <ins>
                <span class="hlspace">
                    <span class="space-space">
                    </span>
                </span>
            </ins>
            world
            """,
        )

    def test_diff_newline(self) -> None:
        self.assertHTMLEqual(
            format_translation(
                ["Hello world"],
                self.component.source_language,
                diff="Hello\nworld",
            )["items"][0]["content"],
            """Hello
            <del>
                <span class="hlspace">
                    <span class="space-nl"></span>
                </span><br />
            </del>
            <ins>
                <span class="hlspace">
                    <span class="space-space"> </span>
                </span>
            </ins>
            world
            """,
        )

    def test_diff_changed_whitespace(self) -> None:
        self.assertHTMLEqual(
            format_translation(
                ["     ${APP_NAME} is great"],
                self.component.source_language,
                diff="    App is great",
            )["items"][0]["content"],
            """
            <span class="hlspace">
                <span class="space-space"> </span>
                <span class="space-space"> </span>
                <span class="space-space"> </span>
                <span class="space-space"> </span>
            </span>
            <del>App</del>
            <ins>
                <span class="hlspace">
                    <span class="space-space"> </span>
                </span>
                ${APP_NAME}
            </ins>
            is great
            """,
        )

    def test_diff_whitespace_leading_added(self) -> None:
        self.assertHTMLEqual(
            format_translation(
                ["新增 :http:get:"],
                self.component.source_language,
                diff="新增：http:get:",
            )["items"][0]["content"],
            """新增
            <del>：</del>
            <ins><span class="hlspace"><span class="space-space"> </span></span>:</ins>
            http:get:
            """,
        )

    def test_glossary(self) -> None:
        self.assertHTMLEqual(
            format_translation(
                ["Hello world"],
                self.component.source_language,
                glossary=[self.build_glossary("hello", "ahoj", [(0, 5)])],
            )["items"][0]["content"],
            """
            <span class="glossary-term"
                title="Glossary term:
ahoj [hello]">Hello</span>
            world
            """,
        )

    def test_glossary_newline(self) -> None:
        self.assertHTMLEqual(
            format_translation(
                ["Hello\nworld"],
                self.component.source_language,
                glossary=[self.build_glossary("world", "svět", [(6, 11)])],
            )["items"][0]["content"],
            """
            Hello
            <span class="hlspace">
                <span class="space-nl">
                </span>
            </span><br>
            <span class="glossary-term"
                title="Glossary term:
svět [world]">
                world
            </span>
            """,
        )

    def test_glossary_overlap(self) -> None:
        self.maxDiff = None
        self.assertHTMLEqual(
            format_translation(
                ["Hello world"],
                self.component.source_language,
                glossary=[
                    self.build_glossary("hello world", "ahoj svete", [(0, 11)]),
                    self.build_glossary("hello", "ahoj", [(0, 5)]),
                ],
            )["items"][0]["content"],
            """
            <span class="glossary-term" title="Glossary terms:
ahoj svete [hello world]
ahoj [hello]">
                Hello
            </span>
            <span class="glossary-term" title="Glossary term:
ahoj svete [hello world]">
                world
            </span>
            """,
        )

    def test_glossary_brackets(self) -> None:
        self.assertHTMLEqual(
            format_translation(
                ["[Hello] world"],
                self.component.source_language,
                glossary=[self.build_glossary("[hello]", "ahoj", [(0, 7)])],
            )["items"][0]["content"],
            """
            <span class="glossary-term"
                title="Glossary term:
ahoj [[hello]]">[Hello]</span>
            world
            """,
        )

    def test_glossary_space(self) -> None:
        self.assertHTMLEqual(
            format_translation(
                ["text  Hello world"],
                self.component.source_language,
                glossary=[self.build_glossary("hello", "ahoj", [(6, 11)])],
            )["items"][0]["content"],
            """
            text
            <span class="hlspace">
                <span class="space-space">
                </span>
                <span class="space-space">
                </span>
            </span>
            <span class="glossary-term"
                title="Glossary term:
ahoj [hello]">Hello</span>
            world
            """,
        )

    def test_glossary_escape(self) -> None:
        self.assertHTMLEqual(
            format_translation(
                ["Hello world"],
                self.component.source_language,
                glossary=[self.build_glossary("hello", '<b>ahoj"', [(0, 5)])],
            )["items"][0]["content"],
            """
            <span class="glossary-term"
                title="Glossary term:
&lt;b&gt;ahoj&quot; [hello]">Hello</span>
            world
            """,
        )

    def test_glossary_multi(self) -> None:
        self.assertHTMLEqual(
            format_translation(
                ["Hello glossary"],
                self.component.source_language,
                glossary=[
                    self.build_glossary("hello", "ahoj", [(0, 5)]),
                    self.build_glossary("glossary", "glosář", [(6, 14)]),
                ],
            )["items"][0]["content"],
            """
            <span class="glossary-term"
                title="Glossary term:
ahoj [hello]">Hello</span>
            <span class="glossary-term"
                title="Glossary term:
glosář [glossary]">glossary</span>
            """,
        )

    def test_glossary_format(self) -> None:
        unit = Unit(translation=self.translation)
        unit.all_flags = Flags("php-format")
        self.assertHTMLEqual(
            format_translation(
                ["%3$sHow"],
                self.component.source_language,
                glossary=[
                    self.build_glossary("show", "zobrazit", [(3, 7)]),
                ],
                unit=unit,
            )["items"][0]["content"],
            """
            <span class="hlcheck" data-value="%3$s">
            <span class="highlight-number"></span>
            %3$s
            </span>
            How
            """,
        )

    def test_highlight(self) -> None:
        unit = self.translation.unit_set.get(id_hash=2097404709965985808)
        self.assertHTMLEqual(
            format_translation(
                unit.get_source_plurals(),
                unit.translation.language,
                unit=unit,
            )["items"][0]["content"],
            """
            Orangutan has
            <span class="hlcheck" data-value="%d">
                <span class="highlight-number"></span>%d
            </span>
            banana.<span class="hlspace"><span class="space-nl">
            </span>
            </span>
            <br/>
            """,
        )

    def test_search(self) -> None:
        self.assertHTMLEqual(
            format_translation(
                ["Hello world"],
                self.component.source_language,
                search_match="world",
            )["items"][0]["content"],
            """Hello <span class="hlmatch">world</span>""",
        )

    def test_whitespace(self) -> None:
        self.assertHTMLEqual(
            format_translation(
                [" Hello world"],
                self.component.source_language,
            )["items"][0]["content"],
            """
            <span class="hlspace">
                <span class="space-space">
                </span>
            </span>
            Hello
            world
            """,
        )
        self.assertHTMLEqual(
            format_translation(
                ["  Hello world"],
                self.component.source_language,
            )["items"][0]["content"],
            """
            <span class="hlspace">
                <span class="space-space">
                </span>
                <span class="space-space">
                </span>
            </span>
            Hello
            world
            """,
        )
        self.assertHTMLEqual(
            format_translation(
                ["Hello   world"],
                self.component.source_language,
            )["items"][0]["content"],
            """
            Hello
            <span class="hlspace">
                <span class="space-space">
                </span>
                <span class="space-space">
                </span>
                <span class="space-space">
                </span>
            </span>
            world
            """,
        )
        self.assertHTMLEqual(
            format_translation(
                ["Hello world "],
                self.component.source_language,
            )["items"][0]["content"],
            """
            Hello
            world
            <span class="hlspace"><span class="space-space">
            </span>
            </span>
            """,
        )

    def test_whitespace_special(self) -> None:
        self.assertHTMLEqual(
            format_translation(
                ["Hello\u00a0world"],
                self.component.source_language,
            )["items"][0]["content"],
            """
            Hello
            <span class="hlspace">
                <span class="space-space" title="NO-BREAK SPACE">
                    \u00a0
                </span>
            </span>
            world
            """,
        )

    def test_whitespace_newline(self) -> None:
        self.assertHTMLEqual(
            format_translation(
                ["Hello\n world"],
                self.component.source_language,
            )["items"][0]["content"],
            """
            Hello
            <span class="hlspace">
                <span class="space-nl">
                </span>
            </span><br>
            <span class="hlspace">
                <span class="space-space">
                </span>
            </span>
            world
            """,
        )


class DiffTestCase(SimpleTestCase):
    """Testing of HTML diff function."""

    def html_diff(self, diff, source):
        unit = MockUnit(source=source)
        return format_translation(
            unit.get_source_plurals(),
            unit.translation.component.source_language,
            diff=diff,
        )["items"][0]["content"]

    def test_same(self) -> None:
        self.assertEqual(self.html_diff("first text", "first text"), "first text")

    def test_add(self) -> None:
        self.assertHTMLEqual(
            self.html_diff("first text", "first new text"),
            """
            first
            <ins>
            new
            <span class="hlspace">
            <span class="space-space">
            </span>
            </span>
            </ins>
            text
            """,
        )

    def test_unicode(self) -> None:
        self.assertHTMLEqual(
            self.html_diff("zkouška text", "zkouška nový text"),
            """
            zkouška
            <ins>nový
            <span class="hlspace">
            <span class="space-space">
            </span>
            </span>
            </ins>
            text
            """,
        )

    def test_remove(self) -> None:
        self.assertHTMLEqual(
            self.html_diff("first old text", "first text"),
            """
            first
            <del>old
             <span class="hlspace">
             <span class="space-space">
             </span>
             </span>
            </del>
            text""",
        )

    def test_replace(self) -> None:
        self.assertEqual(
            self.html_diff("first old text", "first new text"),
            "first <del>old</del><ins>new</ins> text",
        )

    def test_format_diff(self) -> None:
        unit = MockUnit(source="Hello word!")
        self.assertEqual(
            format_translation(
                unit.get_source_plurals(),
                unit.translation.component.source_language,
                diff="Hello world!",
            )["items"][0]["content"],
            "Hello wor<del>l</del>d!",
        )

    def test_format_diff_whitespace(self) -> None:
        unit = MockUnit(source="Hello world!")
        self.assertHTMLEqual(
            format_translation(
                unit.get_source_plurals(),
                unit.translation.component.source_language,
                diff="Hello world! ",
            )["items"][0]["content"],
            'Hello world!<del><span class="hlspace"><span class="space-space">'
            " </span></span></del>",
        )

    def test_format_diff_add_space(self) -> None:
        unit = MockUnit(source="Hello.  World.")
        self.assertHTMLEqual(
            format_translation(
                unit.get_source_plurals(),
                unit.translation.component.source_language,
                diff="Hello. World.",
            )["items"][0]["content"],
            """
            Hello.
            <ins>
                <span class="hlspace">
                    <span class="space-space"></span>
                </span>
            </ins>
            <span class="hlspace">
                <span class="space-space"></span>
            </span>
            World.
            """,
        )

    def test_format_entities(self) -> None:
        unit = MockUnit(source="'word'")
        self.assertEqual(
            format_translation(
                unit.get_source_plurals(),
                unit.translation.component.source_language,
                diff='"word"',
            )["items"][0]["content"],
            "<del>&quot;</del><ins>&#x27;</ins>word<del>&quot;</del><ins>&#x27;</ins>",
        )

    def test_fmtsearchmatch(self) -> None:
        self.assertEqual(
            format_translation(
                ["Hello world!"], MockLanguage("en"), search_match="hello"
            )["items"][0]["content"],
            '<span class="hlmatch">Hello</span> world!',
        )
