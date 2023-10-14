# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for language manipulations."""

import gettext
from io import StringIO
from itertools import chain
from unittest import SkipTest

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import activate
from weblate_language_data.languages import LANGUAGES
from weblate_language_data.plurals import CLDRPLURALS, EXTRAPLURALS

from weblate.lang import data
from weblate.lang.models import Language, Plural, PluralMapper, get_plural_type
from weblate.trans.models import Unit
from weblate.trans.tests.test_models import BaseTestCase
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.util import join_plural
from weblate.utils.db import using_postgresql

TEST_LANGUAGES = (
    ("cs_CZ", "cs", "ltr", "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2", "Czech", False),
    ("cze_CZ", "cs", "ltr", "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2", "Czech", False),
    ("ces_CZ", "cs", "ltr", "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2", "Czech", False),
    (
        "cs_latn",
        "cs_Latn",
        "ltr",
        "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2",
        "Czech (cs_Latn)",
        True,
    ),
    ("cs (2)", "cs", "ltr", "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2", "Czech", False),
    ("cscz", "cs", "ltr", "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2", "Czech", False),
    ("czech", "cs", "ltr", "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2", "Czech", False),
    (
        "cs_CZ@hantec",
        "cs_CZ@hantec",
        "ltr",
        "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2",
        "Czech (cs_CZ@hantec)",
        True,
    ),
    ("de-DE", "de", "ltr", "n != 1", "German", False),
    ("de_AT", "de_AT", "ltr", "n != 1", "German (Austria)", False),
    ("de_CZ", "de_CZ", "ltr", "n != 1", "German (de_CZ)", True),
    ("portuguese_portugal", "pt_PT", "ltr", "n > 1", "Portuguese (Portugal)", False),
    ("pt-rBR", "pt_BR", "ltr", "n > 1", "Portuguese (Brazil)", False),
    ("ptbr", "pt_BR", "ltr", "n > 1", "Portuguese (Brazil)", False),
    (
        "sr+latn",
        "sr_Latn",
        "ltr",
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && "
        "(n%100<10 || n%100>=20) ? 1 : 2",
        "Serbian (latin)",
        False,
    ),
    (
        "sr_RS@latin",
        "sr_Latn",
        "ltr",
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && "
        "(n%100<10 || n%100>=20) ? 1 : 2",
        "Serbian (latin)",
        False,
    ),
    (
        "sr-RS@latin",
        "sr_Latn",
        "ltr",
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && "
        "(n%100<10 || n%100>=20) ? 1 : 2",
        "Serbian (latin)",
        False,
    ),
    (
        "sr_RS_latin",
        "sr_Latn",
        "ltr",
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && "
        "(n%100<10 || n%100>=20) ? 1 : 2",
        "Serbian (latin)",
        False,
    ),
    (
        "en_CA_MyVariant",
        "en_CA@myvariant",
        "ltr",
        "n != 1",
        "English (Canada) (en_CA@myvariant)",
        True,
    ),
    ("en_CZ", "en_CZ", "ltr", "n != 1", "English (en_CZ)", True),
    ("zh_CN", "zh_Hans", "ltr", "0", "Chinese (Simplified)", False),
    ("zh-CN", "zh_Hans", "ltr", "0", "Chinese (Simplified)", False),
    ("zh_HANT", "zh_Hant", "ltr", "0", "Chinese (Traditional)", False),
    ("zh-HANT", "zh_Hant", "ltr", "0", "Chinese (Traditional)", False),
    ("zh-CN@test", "zh_CN@test", "ltr", "0", "Chinese (Simplified) (zh_CN@test)", True),
    ("zh-rCN", "zh_Hans", "ltr", "0", "Chinese (Simplified)", False),
    ("zh_rCN", "zh_Hans", "ltr", "0", "Chinese (Simplified)", False),
    ("zh_HK", "zh_Hant_HK", "ltr", "0", "Chinese (Traditional, Hong Kong)", False),
    (
        "zh_Hant-rHK",
        "zh_Hant_HK",
        "ltr",
        "0",
        "Chinese (Traditional, Hong Kong)",
        False,
    ),
    (
        "ar",
        "ar",
        "rtl",
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 "
        ": n%100>=11 ? 4 : 5",
        "Arabic",
        False,
    ),
    (
        "ar_AA",
        "ar",
        "rtl",
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 "
        ": n%100>=11 ? 4 : 5",
        "Arabic",
        False,
    ),
    (
        "ar_XX",
        "ar_XX",
        "rtl",
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 "
        ": n%100>=11 ? 4 : 5",
        "Arabic (ar_XX)",
        True,
    ),
    ("xx", "xx", "ltr", "n != 1", "xx (generated) (xx)", True),
    ("nb_NO", "nb_NO", "ltr", "n != 1", "Norwegian Bokmål", False),
    ("nb-NO", "nb_NO", "ltr", "n != 1", "Norwegian Bokmål", False),
    ("nb", "nb_NO", "ltr", "n != 1", "Norwegian Bokmål", False),
    ("nono", "nb_NO", "ltr", "n != 1", "Norwegian Bokmål", False),
    (
        "b+zh+Hant+HK",
        "zh_Hant_HK",
        "ltr",
        "0",
        "Chinese (Traditional, Hong Kong)",
        False,
    ),
    (
        "plPL",
        "pl",
        "ltr",
        "n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
        "Polish",
        False,
    ),
)


class TestSequenceMeta(type):
    def __new__(mcs, name, bases, dict):  # noqa: N804
        def gen_test(original, expected, direction, plural, name, create):
            def test(self):
                self.run_create(original, expected, direction, plural, name, create)

            return test

        for params in TEST_LANGUAGES:
            test_name = "test_create_%s" % params[0].replace("@", "___").replace(
                "+", "_"
            ).replace("-", "__")
            if test_name in dict:
                raise ValueError(f"Duplicate test: {params[0]}, mapped to {test_name}")
            dict[test_name] = gen_test(*params)

        return type.__new__(mcs, name, bases, dict)


class LanguagesTest(BaseTestCase, metaclass=TestSequenceMeta):
    def setUp(self):
        # Ensure we're using English
        activate("en")

    def run_create(self, original, expected, direction, plural, name, create):
        """Test that auto create correctly handles languages."""
        # Lookup language
        lang = Language.objects.auto_get_or_create(original, create=False)
        self.assertEqual(
            create,
            not bool(lang.pk),
            f"Could not assert creation for {original}: {create}",
        )
        # Create language
        lang = Language.objects.auto_get_or_create(original)
        # Check language code
        self.assertEqual(
            lang.code, expected, f"Invalid code for {original}: {lang.code}"
        )
        # Check direction
        self.assertEqual(lang.direction, direction, f"Invalid direction for {original}")
        # Check plurals
        plural_obj = lang.plural_set.get(source=Plural.SOURCE_DEFAULT)
        self.assertEqual(
            plural_obj.formula,
            plural,
            f"Invalid plural for {original} "
            f"(expected {plural}, got {plural_obj.formula})",
        )
        # Check whether html contains both language code and direction
        self.assertIn(direction, lang.get_html())
        self.assertIn(expected, lang.get_html())
        # Check name
        self.assertEqual(str(lang), name)

    def test_private_use(self, code="de-x-a123", expected="de-x-a123"):
        lang = Language.objects.auto_get_or_create(code, create=False)
        self.assertEqual(lang.code, expected)
        Language.objects.create(name="Test", code=code)
        lang = Language.objects.auto_get_or_create(code, create=False)
        self.assertEqual(lang.code, code)

    def test_private_country(self):
        self.test_private_use("en-US-x-twain", "en_US-x-twain")

    def test_private_fuzzy_get(self):
        Language.objects.auto_get_or_create("cs_FOO")
        self.run_create(
            "czech", "cs", "ltr", "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2", "Czech", False
        )

    def test_chinese_fuzzy_get(self):
        """Test handling of manually created zh_CN language."""
        language = Language.objects.create(code="zh_CN", name="Chinese")
        language.plural_set.create(
            number=0,
            formula="0",
            source=Plural.SOURCE_DEFAULT,
        )
        self.run_create("zh-rCN", "zh_CN", "ltr", "0", "Chinese (zh_CN)", False)

    def test_case_sensitive_fuzzy_get(self):
        """Test handling of manually created zh-TW, zh-TW and zh_TW languages."""
        if not using_postgresql():
            raise SkipTest("Not supported on MySQL")

        language = Language.objects.create(code="zh_TW", name="Chinese (Taiwan)")
        language.plural_set.create(
            number=0,
            formula="0",
            source=Plural.SOURCE_DEFAULT,
        )
        self.run_create("zh_TW", "zh_TW", "ltr", "0", "Chinese (Taiwan) (zh_TW)", False)
        language = Language.objects.create(code="zh-TW", name="Chinese Taiwan")
        language.plural_set.create(
            number=0,
            formula="0",
            source=Plural.SOURCE_DEFAULT,
        )
        self.run_create("zh-TW", "zh-TW", "ltr", "0", "Chinese Taiwan (zh-TW)", False)
        language = Language.objects.create(code="zh-tw", name="Traditional Chinese")
        language.plural_set.create(
            number=0,
            formula="0",
            source=Plural.SOURCE_DEFAULT,
        )
        self.run_create(
            "zh-tw", "zh-tw", "ltr", "0", "Traditional Chinese (zh-tw)", False
        )


class CommandTest(BaseTestCase):
    """Test for management commands."""

    def test_setuplang(self):
        call_command("setuplang")
        self.assertTrue(Language.objects.exists())

    def test_setuplang_noupdate(self):
        call_command("setuplang", update=False)
        self.assertTrue(Language.objects.exists())

    def check_list(self, **kwargs):
        output = StringIO()
        call_command("list_languages", "cs", stdout=output, **kwargs)
        self.assertIn("Czech", output.getvalue())

    def test_list_languages(self):
        self.check_list()

    def test_list_languages_lower(self):
        self.check_list(lower=True)

    def test_move_language(self):
        Language.objects.auto_create("cs_CZ")
        call_command("move_language", "cs_CZ", "cs")


class VerifyPluralsTest(TestCase):
    """In database plural form verification."""

    @staticmethod
    def all_data():
        return chain(LANGUAGES, EXTRAPLURALS, CLDRPLURALS)

    def test_valid(self):
        """Validate that we can name all plural formulas."""
        for code, _name, _nplurals, plural_formula in self.all_data():
            self.assertNotEqual(
                get_plural_type(code.replace("_", "-").split("-")[0], plural_formula),
                data.PLURAL_UNKNOWN,
                f"Can not guess plural type for {code}: {plural_formula}",
            )

    def test_with_zero(self):
        for _code, _name, _nplurals, plural_formula in CLDRPLURALS:
            self.assertIn(plural_formula, data.FORMULA_WITH_ZERO)
            with_zero = data.FORMULA_WITH_ZERO[plural_formula]
            gettext.c2py(with_zero)

    def test_formula(self):
        """Validate that all formulas can be parsed by gettext."""
        # Verify we get an error on invalid syntax
        with self.assertRaises((SyntaxError, ValueError)):
            gettext.c2py("n==0 ? 1 2")
        for code, _name, nplurals, plural_formula in self.all_data():
            # Validate plurals can be parsed
            plural = gettext.c2py(plural_formula)
            # Get maximal plural
            calculated = max(plural(x) for x in range(200)) + 1
            # Check it matches ours
            self.assertEqual(
                calculated,
                nplurals,
                "Invalid nplurals for {}: calculated={} (number={}, formula={})".format(
                    code, calculated, nplurals, plural_formula
                ),
            )


class LanguagesViewTest(FixtureTestCase):
    def test_languages(self):
        response = self.client.get(reverse("languages"))
        self.assertContains(response, "Czech")

    def test_language(self):
        response = self.client.get(reverse("show_language", kwargs={"lang": "cs"}))
        self.assertContains(response, "Czech")
        self.assertContains(response, "test/test")

    def test_language_br(self):
        response = self.client.get(reverse("show_language", kwargs={"lang": "br"}))
        self.assertContains(response, "Breton")
        # Example is listed
        self.assertContains(response, "1000000")

    def test_project_language(self):
        response = self.client.get(
            reverse(
                "project-language-redirect", kwargs={"lang": "cs", "project": "test"}
            ),
            follow=True,
        )
        self.assertRedirects(
            response,
            reverse("show", kwargs={"path": ["test", "-", "cs"]}),
            status_code=301,
        )
        self.assertContains(response, "Czech")
        self.assertContains(response, "/projects/test/test/cs/")

    def test_language_redirect(self):
        response = self.client.get(reverse("show_language", kwargs={"lang": "cs_CZ"}))
        self.assertRedirects(response, reverse("show_language", kwargs={"lang": "cs"}))

    def test_language_nonexisting(self):
        response = self.client.get(
            reverse("show_language", kwargs={"lang": "nonexisting"})
        )
        self.assertEqual(response.status_code, 404)

    def test_add(self):
        response = self.client.get(reverse("create-language"))
        self.assertEqual(response.status_code, 302)
        self.user.is_superuser = True
        self.user.save()
        response = self.client.get(reverse("create-language"))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("create-language"), {"code": "x"})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("create-language"),
            {
                "code": "xx",
                "name": "XX",
                "direction": "ltr",
                "number": "2",
                "formula": "n != 1",
                "population": 10,
            },
        )
        self.assertRedirects(response, reverse("show_language", kwargs={"lang": "xx"}))

    def test_delete(self):
        response = self.client.post(reverse("show_language", kwargs={"lang": "br"}))
        self.assertEqual(response.status_code, 200)
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(reverse("show_language", kwargs={"lang": "cs"}))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("show_language", kwargs={"lang": "br"}))
        self.assertRedirects(response, reverse("languages"))

    def test_edit(self):
        language = Language.objects.get(code="cs")
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("edit-language", kwargs={"pk": language.pk}),
            {
                "code": "xx",
                "name": "XX",
                "direction": "ltr",
                "population": 10,
                "workflow-suggestion_autoaccept": 0,
            },
        )
        self.assertRedirects(response, reverse("show_language", kwargs={"lang": "xx"}))

    def test_edit_workflow(self):
        language = Language.objects.get(code="cs")
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("edit-language", kwargs={"pk": language.pk}),
            {
                "code": "xx",
                "name": "XX",
                "direction": "ltr",
                "population": 10,
                "workflow-enable": 1,
                "workflow-translation_review": 1,
                "workflow-suggestion_autoaccept": 0,
            },
        )
        self.assertRedirects(response, reverse("show_language", kwargs={"lang": "xx"}))
        self.assertTrue(language.workflowsetting_set.exists())
        response = self.client.post(
            reverse("edit-language", kwargs={"pk": language.pk}),
            {
                "code": "xx",
                "name": "XX",
                "direction": "ltr",
                "population": 10,
                "workflow-translation_review": 1,
                "workflow-suggestion_autoaccept": 0,
            },
        )
        self.assertRedirects(response, reverse("show_language", kwargs={"lang": "xx"}))
        self.assertFalse(language.workflowsetting_set.exists())

    def test_edit_plural(self):
        language = Language.objects.get(code="cs")
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("edit-plural", kwargs={"pk": language.plural.pk}),
            {"number": "2", "formula": "n != 1"},
        )
        self.assertRedirects(
            response, reverse("show_language", kwargs={"lang": "cs"}) + "#information"
        )


class PluralsCompareTest(TestCase):
    def test_match(self):
        plural = Plural.objects.get(language__code="cs", source=Plural.SOURCE_DEFAULT)
        self.assertTrue(plural.same_plural(plural.number, plural.formula))

    def test_formula(self):
        plural = Plural.objects.get(language__code="pt", source=Plural.SOURCE_DEFAULT)
        self.assertFalse(plural.same_plural(2, "(n != 1)"))

    def test_different_formula(self):
        plural = Plural.objects.get(language__code="pt", source=Plural.SOURCE_DEFAULT)
        self.assertTrue(plural.same_plural(2, "(n > 1)"))

    def test_different_count(self):
        plural = Plural.objects.get(language__code="lt", source=Plural.SOURCE_DEFAULT)
        self.assertFalse(
            plural.same_plural(
                4,
                "(n%10==1 ? 0 : n%10==1 && n%100!=11 ?"
                " 1 : n %10>=2 && (n%100<10 || n%100>=20) ? 2 : 3)",
            )
        )

    def test_invalid(self):
        plural = Plural.objects.get(language__code="lt", source=Plural.SOURCE_DEFAULT)
        self.assertFalse(plural.same_plural(1, "bogus"))


class PluralTest(BaseTestCase):
    def test_examples(self):
        plural = Plural(number=2, formula="n!=1")
        self.assertEqual(
            plural.examples,
            {0: ["1"], 1: ["0", "2", "3", "4", "5", "6", "7", "8", "9", "10", "…"]},
        )

    def test_plurals(self):
        """Test whether plural form is correctly calculated."""
        plural = Plural.objects.get(language__code="cs")
        self.assertEqual(
            plural.plural_form,
            "nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;",
        )

    def test_plural_names(self):
        plural = Plural.objects.get(language__code="cs")
        self.assertEqual(plural.get_plural_name(0), "One")
        self.assertEqual(plural.get_plural_name(1), "Few")
        self.assertEqual(plural.get_plural_name(2), "Many")

    def test_plural_names_invalid(self):
        plural = Plural.objects.get(language__code="cs")
        plural.type = -1
        self.assertEqual(plural.get_plural_name(0), "Singular")
        self.assertEqual(plural.get_plural_name(1), "Plural")
        self.assertEqual(plural.get_plural_name(2), "Plural form 2")

    def test_plural_labels(self):
        plural = Plural.objects.get(language__code="cs")
        label = plural.get_plural_label(0)
        self.assertIn("One", label)
        self.assertIn("1", label)
        label = plural.get_plural_label(1)
        self.assertIn("Few", label)
        self.assertIn("2, 3, 4", label)
        label = plural.get_plural_label(2)
        self.assertIn("Many", label)
        self.assertIn("5, 6, 7", label)

    def test_plural_type(self):
        language = Language.objects.get(code="cs")
        plural = Plural.objects.create(
            language=language,
            number=3,
            formula=(
                "(n%10==1 && n%100!=11 ? 0 : "
                "n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)"
            ),
            source=Plural.SOURCE_GETTEXT,
        )
        self.assertEqual(plural.type, data.PLURAL_ONE_FEW_MANY)

    def test_definitions(self):
        """Verify consistency of plural definitions."""
        plurals = [x[1] for x in data.PLURAL_MAPPINGS]
        choices = [x[0] for x in Plural.PLURAL_CHOICES]
        for plural in plurals:
            self.assertIn(plural, choices)
            self.assertIn(plural, data.PLURAL_NAMES)


class PluralMapperTestCase(FixtureTestCase):
    def test_english_czech(self):
        english = Language.objects.get(code="en")
        czech = Language.objects.get(code="cs")
        mapper = PluralMapper(english.plural, czech.plural)
        self.assertEqual(mapper._target_map, ((0, None), (None, None), (-1, None)))
        unit = Unit.objects.get(
            translation__language=english, id_hash=2097404709965985808
        )
        self.assertEqual(
            mapper.map(unit),
            ["Orangutan has %d banana.\n", "", "Orangutan has %d bananas.\n"],
        )

    def test_russian_english(self):
        russian = Language.objects.get(code="ru")
        english = Language.objects.get(code="en")
        mapper = PluralMapper(russian.plural, english.plural)
        self.assertEqual(mapper._target_map, ((0, "1"), (-1, None)))
        # Use English here to test incomplete plural set in the source string
        unit = Unit.objects.get(
            translation__language=english, id_hash=2097404709965985808
        )
        self.assertEqual(
            mapper.map(unit),
            ["Orangutan has %d banana.\n", "Orangutan has %d bananas.\n"],
        )

    def test_russian_english_interpolate(self):
        russian = Language.objects.get(code="ru")
        english = Language.objects.get(code="en")
        mapper = PluralMapper(russian.plural, english.plural)
        self.assertEqual(mapper._target_map, ((0, "1"), (-1, None)))
        # Use English here to test incomplete plural set in the source string
        unit = Unit.objects.get(
            translation__language=english, id_hash=2097404709965985808
        )
        unit.extra_flags = "python-brace-format"
        unit.source = unit.source.replace("%d", "{count}")
        self.assertEqual(
            mapper.map(unit),
            ["Orangutan has 1 banana.\n", "Orangutan has {count} bananas.\n"],
        )

    def test_russian_english_interpolate_double(self):
        russian = Language.objects.get(code="ru")
        english = Language.objects.get(code="en")
        mapper = PluralMapper(russian.plural, english.plural)
        self.assertEqual(mapper._target_map, ((0, "1"), (-1, None)))
        # Use English here to test incomplete plural set in the source string
        unit = Unit.objects.get(
            translation__language=english, id_hash=2097404709965985808
        )
        unit.extra_flags = "python-brace-format"
        unit.source = unit.source.replace("%d", "{count} {count}")
        self.assertEqual(
            mapper.map(unit),
            [
                "Orangutan has {count} {count} banana.\n",
                "Orangutan has {count} {count} bananas.\n",
            ],
        )

    def test_russian_english_interpolate_missing(self):
        russian = Language.objects.get(code="ru")
        english = Language.objects.get(code="en")
        mapper = PluralMapper(russian.plural, english.plural)
        self.assertEqual(mapper._target_map, ((0, "1"), (-1, None)))
        unit = Unit.objects.get(
            translation__language=english, id_hash=2097404709965985808
        )
        unit.extra_flags = "i18next-interpolation"
        unit.source = join_plural(["{{periodNumber}}-я четверть"] * 3)
        self.assertEqual(
            mapper.map(unit),
            ["{{periodNumber}}-я четверть", "{{periodNumber}}-я четверть"],
        )
