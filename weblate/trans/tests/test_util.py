# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import SimpleTestCase, override_settings
from translate.misc.multistring import multistring

from weblate.lang.models import Language
from weblate.trans.util import (
    cleanup_path,
    cleanup_repo_url,
    count_words,
    get_string,
    join_plural,
    sanitize_backend_error_message,
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


class BackendErrorSanitizationTest(SimpleTestCase):
    def test_sanitize_backend_error_message(self) -> None:
        sanitized = sanitize_backend_error_message(
            (
                "fatal: unable to access "
                "'ssh://git@internal.example.net/private/repo.git': "
                "Could not resolve host: internal.example.net\n"
                "/srv/weblate/data/vcs/test/.git/index.lock"
            ),
            repo_urls=("ssh://git@internal.example.net/private/repo.git",),
            extra_paths=("/srv/weblate/data/vcs/test",),
        )

        self.assertIn("Could not resolve host: ...", sanitized)
        self.assertNotIn("internal.example.net", sanitized)
        self.assertNotIn("ssh://", sanitized)
        self.assertNotIn("/srv/weblate/data/vcs/test", sanitized)
        self.assertIn(".../.git/index.lock", sanitized)

    def test_strip_descendant_internal_path(self) -> None:
        sanitized = sanitize_backend_error_message(
            "Commit failed in /srv/weblate/data/vcs/test/test/secret",
            extra_paths=("/srv/weblate/data/vcs/test/test",),
        )

        self.assertEqual(sanitized, "Commit failed in .../secret")

    def test_strip_internal_path_before_period(self) -> None:
        sanitized = sanitize_backend_error_message(
            "Commit failed in /srv/weblate/data/vcs/test/test.",
            extra_paths=("/srv/weblate/data/vcs/test/test",),
        )

        self.assertEqual(sanitized, "Commit failed in ....")

    @override_settings(DATA_DIR="/srv/weblate/data", CACHE_DIR="/srv/weblate/cache")
    def test_strip_descendant_internal_path_before_cleanup(self) -> None:
        sanitized = sanitize_backend_error_message(
            "Commit failed in /srv/weblate/data/vcs/test/test/secret",
            extra_paths=("/srv/weblate/data/vcs/test/test",),
        )

        self.assertEqual(sanitized, "Commit failed in .../secret")

    def test_preserve_file_line_diagnostics(self) -> None:
        sanitized = sanitize_backend_error_message(
            "messages.po:123: unknown keyword",
        )

        self.assertEqual(sanitized, "messages.po:123: unknown keyword")

    def test_preserve_repo_relative_refs(self) -> None:
        sanitized = sanitize_backend_error_message(
            "fatal: couldn't find remote ref refs/heads/main",
        )

        self.assertEqual(sanitized, "fatal: couldn't find remote ref refs/heads/main")

    def test_preserve_newlines(self) -> None:
        sanitized = sanitize_backend_error_message(
            (
                "fatal: unable to access "
                "'ssh://git@internal.example.net/private/repo.git':\n"
                "Could not resolve host: internal.example.net\n"
                "Could not resolve host: internal.example.net\n"
                "/srv/weblate/data/vcs/test/.git/index.lock"
            ),
            repo_urls=("ssh://git@internal.example.net/private/repo.git",),
            extra_paths=("/srv/weblate/data/vcs/test",),
        )

        self.assertEqual(
            sanitized,
            "fatal: unable to access 'repository URL':\n"
            "Could not resolve host: ...\n"
            ".../.git/index.lock",
        )


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
