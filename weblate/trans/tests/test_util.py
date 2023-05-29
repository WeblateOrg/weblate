# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import SimpleTestCase
from translate.misc.multistring import multistring

from weblate.trans.util import (
    cleanup_path,
    cleanup_repo_url,
    get_string,
    translation_percent,
)


class HideCredentialsTest(SimpleTestCase):
    def test_http(self):
        self.assertEqual(
            cleanup_repo_url("http://foo:bar@example.com"), "http://example.com"
        )

    def test_http_user(self):
        self.assertEqual(
            cleanup_repo_url("http://foo@example.com"), "http://example.com"
        )

    def test_git(self):
        self.assertEqual(
            cleanup_repo_url("git://git.weblate.org/weblate.git"),
            "git://git.weblate.org/weblate.git",
        )

    def test_github(self):
        self.assertEqual(
            cleanup_repo_url("git@github.com:WeblateOrg/weblate.git"),
            "git@github.com:WeblateOrg/weblate.git",
        )

    def test_git_hg(self):
        self.assertEqual(
            cleanup_repo_url("hg::https://bitbucket.org/sumwars/sumwars-code"),
            "hg::https://bitbucket.org/sumwars/sumwars-code",
        )


class TranslationPercentTest(SimpleTestCase):
    def test_common(self):
        self.assertAlmostEqual(translation_percent(2, 4), 50.0)

    def test_empty(self):
        self.assertAlmostEqual(translation_percent(0, 0), 100.0)

    def test_none(self):
        self.assertAlmostEqual(translation_percent(0, None), 0.0)

    def test_untranslated_file(self):
        self.assertAlmostEqual(translation_percent(0, 100), 0.0)

    def test_almost_untranslated_file(self):
        self.assertAlmostEqual(translation_percent(1, 10000000000), 0.1)

    def test_translated_file(self):
        self.assertAlmostEqual(translation_percent(100, 100), 100.0)

    def test_almost_translated_file(self):
        self.assertAlmostEqual(translation_percent(99999999, 100000000), 99.9)


class CleanupPathTest(SimpleTestCase):
    def test_relative(self):
        self.assertEqual(cleanup_path("../*.po"), "*.po")

    def test_current(self):
        self.assertEqual(cleanup_path("./*.po"), "*.po")

    def test_mixed(self):
        self.assertEqual(cleanup_path("./../*.po"), "*.po")

    def test_slash(self):
        self.assertEqual(cleanup_path("/*.po"), "*.po")

    def test_double_slash(self):
        self.assertEqual(cleanup_path("foo//*.po"), "foo/*.po")


class TextConversionTest(SimpleTestCase):
    def test_multistring(self):
        self.assertEqual(get_string(multistring(["foo", "bar"])), "foo\x1e\x1ebar")

    def test_surrogates(self):
        self.assertEqual(
            get_string("\ud83d\udc68\u200d\ud83d\udcbbАгенты"), "👨‍💻Агенты"
        )

    def test_none(self):
        self.assertEqual(get_string(None), "")

    def test_int(self):
        self.assertEqual(get_string(42), "42")
