# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import SimpleTestCase
from translate.misc.multistring import multistring

from weblate.lang.models import Language
from weblate.trans.util import (
    cleanup_path,
    cleanup_repo_url,
    count_words,
    get_string,
    join_plural,
    translation_percent,
)


class HideCredentialsTest(SimpleTestCase):
    def test_http(self) -> None:
        self.assertEqual(
            cleanup_repo_url("http://foo:bar@example.com"), "http://example.com"
        )

    def test_http_user(self) -> None:
        self.assertEqual(
            cleanup_repo_url("http://foo@example.com"), "http://example.com"
        )

    def test_git(self) -> None:
        self.assertEqual(
            cleanup_repo_url("git://git.weblate.org/weblate.git"),
            "git://git.weblate.org/weblate.git",
        )

    def test_github(self) -> None:
        self.assertEqual(
            cleanup_repo_url("git@github.com:WeblateOrg/weblate.git"),
            "git@github.com:WeblateOrg/weblate.git",
        )

    def test_git_hg(self) -> None:
        self.assertEqual(
            cleanup_repo_url("hg::https://bitbucket.org/sumwars/sumwars-code"),
            "hg::https://bitbucket.org/sumwars/sumwars-code",
        )


class TranslationPercentTest(SimpleTestCase):
    def test_common(self) -> None:
        self.assertAlmostEqual(translation_percent(2, 4), 50.0)

    def test_empty(self) -> None:
        self.assertAlmostEqual(translation_percent(0, 0), 100.0)

    def test_none(self) -> None:
        self.assertAlmostEqual(translation_percent(0, None), 0.0)

    def test_untranslated_file(self) -> None:
        self.assertAlmostEqual(translation_percent(0, 100), 0.0)

    def test_almost_untranslated_file(self) -> None:
        self.assertAlmostEqual(translation_percent(1, 10000000000), 0.1)

    def test_translated_file(self) -> None:
        self.assertAlmostEqual(translation_percent(100, 100), 100.0)

    def test_almost_translated_file(self) -> None:
        self.assertAlmostEqual(translation_percent(99999999, 100000000), 99.9)


class CleanupPathTest(SimpleTestCase):
    def test_relative(self) -> None:
        self.assertEqual(cleanup_path("../*.po"), "*.po")

    def test_current(self) -> None:
        self.assertEqual(cleanup_path("./*.po"), "*.po")

    def test_mixed(self) -> None:
        self.assertEqual(cleanup_path("./../*.po"), "*.po")

    def test_slash(self) -> None:
        self.assertEqual(cleanup_path("/*.po"), "*.po")

    def test_double_slash(self) -> None:
        self.assertEqual(cleanup_path("foo//*.po"), "foo/*.po")


class TextConversionTest(SimpleTestCase):
    def test_multistring(self) -> None:
        self.assertEqual(get_string(multistring(["foo", "bar"])), "foo\x1e\x1ebar")

    def test_surrogates(self) -> None:
        self.assertEqual(
            get_string("\ud83d\udc68\u200d\ud83d\udcbbАгенты"), "👨‍💻Агенты"
        )

    def test_none(self) -> None:
        self.assertEqual(get_string(None), "")

    def test_int(self) -> None:
        self.assertEqual(get_string(42), "42")


class WordCountTestCase(SimpleTestCase):
    def test_words(self) -> None:
        self.assertEqual(count_words("count words"), 2)

    def test_plural(self) -> None:
        self.assertEqual(count_words(join_plural(["count word", "count words"])), 4)

    def test_unused(self) -> None:
        self.assertEqual(
            count_words(join_plural(["<unused singular 1>", "count words"])), 2
        )

    def test_sentence(self) -> None:
        self.assertEqual(count_words("You need to count a word!"), 6)

    def test_numbers(self) -> None:
        self.assertEqual(count_words("There are 123 words"), 4)

    def test_complex(self) -> None:
        self.assertEqual(
            count_words("I've just realized that they have 5 %(color)s cats."), 9
        )
        self.assertEqual(
            count_words(
                "I've just realized that they have 5 %(color)s cats.",
                Language(code="en"),
            ),
            9,
        )

    def test_cjk(self) -> None:
        self.assertEqual(
            count_words(
                "小娜在2014年4月2日举行的微软Build开发者大会上正式展示并发布。2014年中旬，微软发布了“小娜”这一名字，作为Cortana在中国大陆使用的中文名。与这一中文名一起发布的是小娜在中国大陆的另一个形象。“小娜”一名源自微软旗下知名FPS游戏《光环》中的同名女角色。",
                Language(code="zh"),
            ),
            118,
        )
        self.assertEqual(
            count_words(
                "小娜在2014年4月2日举行的微软Build开发者大会上正式展示并发布。2014年中旬，微软发布了“小娜”这一名字，作为Cortana在中国大陆使用的中文名。与这一中文名一起发布的是小娜在中国大陆的另一个形象。“小娜”一名源自微软旗下知名FPS游戏《光环》中的同名女角色。",
                Language(code="zh_Hant"),
            ),
            118,
        )
