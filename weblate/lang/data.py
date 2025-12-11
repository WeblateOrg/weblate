# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.utils.translation import pgettext_lazy
from weblate_language_data import languages
from weblate_language_data.aliases import ALIASES
from weblate_language_data.ambiguous import AMBIGUOUS

NO_CODE_LANGUAGES = {lang[0] for lang in languages.LANGUAGES}

NO_SPACE_LANGUAGES = {
    "zh",
    "ja",
    "th",
    "km",
    "lo",
    "my",
    "ko",
}

UNDERSCORE_EXCEPTIONS = {
    "nb_NO",
    "zh_Hant",
    "zh_Hans",
    "be_Latn",
    "ro_MD",
    "pt_BR",
    "pa_PK",
    "hi_Latn",
}
AT_EXCEPTIONS = {"ca@valencia"}


def is_default_variant(code):
    language = code.partition("_")[0]
    if language not in NO_CODE_LANGUAGES and language in ALIASES:
        return code == ALIASES[language]
    return False


def is_basic(code):
    if code in AMBIGUOUS:
        return False
    if "_" in code:
        return code in UNDERSCORE_EXCEPTIONS or is_default_variant(code)
    return "@" not in code or code in AT_EXCEPTIONS


BASIC_LANGUAGES = {lang for lang in NO_CODE_LANGUAGES if is_basic(lang)}

# Following variables are used to map Gettext plural formulas
# to one/few/may/other like rules

ONE_OTHER_PLURALS = (
    "n==1 || n%10==1 ? 0 : 1",
    "n != 1",
    "(n != 1)",
    "n > 1",
    "(n > 1)",
    "n >= 2 && (n < 11 || n > 99)",
    "n % 10 != 1 || n % 100 == 11",
    "(n % 10 == 1 && n % 100 != 11) ? 0 : 1",
    "n != 1 && n != 2 && n != 3 && (n % 10 == 4 || n % 10 == 6 || n % 10 == 9)",
    "(n==0 || n==1)",
    "(n%10==1 && n%100!=11 ? 0 : 1)",
)

TWO_OTHER_PLURALS = ("(n==2) ? 1 : 0",)

ONE_FEW_MANY_PLURALS = (
    "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2",
    "n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    "(n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)",
    "n%10==1 && n%100!=11 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : 2",
    "(n % 10 == 1 && (n % 100 < 11 || n % 100 > 19)) ? 0 : ((n % 10 >= 2 && n % 10 <= 9 && (n % 100 < 11 || n % 100 > 19)) ? 1 : 2)",
    "(n%10==1 && n%100!=11 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : 2)",
    "(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)",
    "((n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2)",
)
ONE_FEW_OTHER_PLURALS = (
    "n==1 ? 0 : (n==0 || (n%100 > 0 && n%100 < 20)) ? 1 : 2",
    "(n == 1) ? 0 : ((n == 0 || n != 1 && n % 100 >= 1 && n % 100 <= 19) ? 1 : 2)",
    "(n == 0 || n == 1) ? 0 : ((n >= 2 && n <= 10) ? 1 : 2)",
    "(n == 1) ? 0 : ((n == 0 || n % 100 >= 2 && n % 100 <= 19) ? 1 : 2)",
    "(n==1 ? 0 : (n==0 || (n%100 > 0 && n%100 < 20)) ? 1 : 2)",
)
ZERO_ONE_FEW_OTHER_PLURALS = (
    "n == 0 ? 0 : n == 1 ? 1 : ((n >= 2 && n <= 10) ? 2 : 3)",
    "n==0 ? 0 : n==1 ? 1 : (n==0 || (n%100 > 0 && n%100 < 20)) ? 2 : 3",
    "n==0 ? 0 : (n == 1) ? 1 : ((n == 0 || n % 100 >= 2 && n % 100 <= 19) ? 2 : 3)",
    "n==0 ? 0 : n==1 ? 1 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 2 : 3",
    "n==0 ? 0 : (n==1) ? 1 : (n>=2 && n<=4) ? 2 : 3",
    "n==0 ? 0 : n%10==1 && n%100!=11 ? 1 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 2 : 3",
    "n==0 ? 0 : (n % 10 == 1 && (n % 100 < 11 || n % 100 > 19)) ? 1 : ((n % 10 >= 2 && n % 10 <= 9 && (n % 100 < 11 || n % 100 > 19)) ? 2 : 3)",
)

ONE_ZERO_FEW_OTHER_PLURALS = (
    "(n==1 ? 0 : (n==0 || (n%100>=1 && n%100<=10)) ? 1 : (n%100>=11 && n%100<=19) ? 2 : 3)",
)

ZERO_ONE_OTHER_PLURALS = (
    "n==0 ? 0 : n==1 ? 1 : 2",
    "(n == 0) ? 0 : ((n == 1) ? 1 : 2)",
    "(n % 10 == 0 || n % 100 >= 11 && n % 100 <= 19) ? 0 : ((n % 10 == 1 && n % 100 != 11) ? 1 : 2)",
    "n==0 ? 0 : n>1 ? 1 : 2",
    "n==0 ? 0 : n!=1 ? 1 : 2",
    "n == 0 ? 0 : n==1 || n%10==1 ? 1 : 2",
    "n==0 ? 0 : n != 1 && n != 2 && n != 3 && (n % 10 == 4 || n % 10 == 6 || n % 10 == 9) ? 1: 2",
    "n==0 ? 0 : n % 10 != 1 || n % 100 == 11 ? 1 :2",
    "n==0 ? 0 : n >= 2 && (n < 11 || n > 99) ? 1 : 2",
    "n==0 ? 0 : n%10==1 && n%100!=11 ? 1 : 2",
    "(n==1 ? 0 : (n%10==4 || n%10==6 || n%10== 9) ? 1 : 2)",
)

ONE_TWO_OTHER_PLURALS = (
    "n==1 ? 0 : n==2 ? 1 : 2",
    "(n == 1) ? 0 : ((n == 2) ? 1 : 2)",
    "n%100==1 ? 0 : n%100==2 ? 1 : 2",
    "(n==1 ? 0 : n==2 ? 1 : 2)",
    "(n%100==1 ? 0 : n%100==2 ? 1 : 2)",
)
ZERO_ONE_TWO_OTHER_PLURALS = (
    "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : 3",
    "n==0 ? 0 : (n == 1) ? 1 : ((n == 2) ? 2 : 3)",
)

ONE_OTHER_TWO_PLURALS = ("n==1 ? 0 : n==2 ? 2 : 1",)

ONE_TWO_THREE_OTHER_PLURALS = ("(n==1) ? 0 : (n==2) ? 1 : (n == 3) ? 2 : 3",)

ONE_TWO_FEW_OTHER_PLURALS = (
    "(n==1 || n==11) ? 0 : (n==2 || n==12) ? 1 : (n > 2 && n < 20) ? 2 : 3",
    "n%100==1 ? 0 : n%100==2 ? 1 : n%100==3 || n%100==4 ? 2 : 3",
    "(n % 10 == 1) ? 0 : ((n % 10 == 2) ? 1 : ((n % 100 == 0 || n % 100 == 20 || n % 100 == 40 || n % 100 == 60 || n % 100 == 80) ? 2 : 3))",
    "(n % 100 == 1) ? 0 : ((n % 100 == 2) ? 1 : ((n % 100 == 3 || n % 100 == 4) ? 2 : 3))",
    "(n == 1) ? 0 : ((n == 2) ? 1 : ((n > 10 && n % 10 == 0) ? 2 : 3))",
    "(n == 1) ? 0 : ((n == 2) ? 1 : ((n == 10) ? 2 : 3))",
    "(n==1) ? 0 : (n==2) ? 1 : (n != 8 && n != 11) ? 2 : 3",
    "(n%100==1 ? 0 : n%100==2 ? 1 : n%100==3 || n%100==4 ? 2 : 3)",
)
ZERO_ONE_TWO_FEW_OTHER_PLURALS = (
    "n==0 ? 0 : (n==1 || n==11) ? 1 : (n==2 || n==12) ? 2 : (n > 2 && n < 20) ? 3 : 4",
    "n==0 ? 0 : (n == 1) ? 1 : ((n == 2) ? 2 : ((n > 10 && n % 10 == 0) ? 3 : 4))",
    "n==0 ? 0 : (n % 100 == 1) ? 1 : ((n % 100 == 2) ? 2 : ((n % 100 == 3 || n % 100 == 4) ? 3 : 4))",
    "n==0 ? 0 : n%100==1 ? 1 : n%100==2 ? 2 : n%100==3 || n%100==4 ? 3 : 4",
    "n==0 ? 0 : (n % 10 == 1) ? 1 : ((n % 10 == 2) ? 2 : ((n % 100 == 0 || n % 100 == 20 || n % 100 == 40 || n % 100 == 60 || n % 100 == 80) ? 3 : 4))",
)

OTHER_ONE_TWO_FEW_PLURALS = (
    "(n%100==1 ? 1 : n%100==2 ? 2 : n%100==3 || n%100==4 ? 3 : 0)",
)

ONE_TWO_FEW_MANY_OTHER_PLURALS = (
    "n==1 ? 0 : n==2 ? 1 : n<7 ? 2 : n<11 ? 3 : 4",
    "n==1 ? 0 : n==2 ? 1 : (n>2 && n<7) ? 2 :(n>6 && n<11) ? 3 : 4",
    "(n % 10 == 1 && n % 100 != 11 && n % 100 != 71 && n % 100 != 91) ? 0 : ((n % 10 == 2 && n % 100 != 12 && n % 100 != 72 && n % 100 != 92) ? 1 : ((((n % 10 == 3 || n % 10 == 4) || n % 10 == 9) && (n % 100 < 10 || n % 100 > 19) && (n % 100 < 70 || n % 100 > 79) && (n % 100 < 90 || n % 100 > 99)) ? 2 : ((n != 0 && n % 1000000 == 0) ? 3 : 4)))",
    "(n == 1) ? 0 : ((n == 2) ? 1 : ((n == 0 || n % 100 >= 3 && n % 100 <= 10) ? 2 : ((n % 100 >= 11 && n % 100 <= 19) ? 3 : 4)))",
)

ONE_FEW_MANY_OTHER_PLURALS = (
    "n==1 ? 0 : n==0 || ( n%100>1 && n%100<11) ? 1 : (n%100>10 && n%100<20 ) ? 2 : 3",
    "n==1 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : n%10==0 || (n%100>10 && n%100<20) ? 2 : 3",
    "n==1 ? 3 : n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    "(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<12 || n%100>14) ? 1 : n%10==0 || (n%10>=5 && n%10<=9) || (n%100>=11 && n%100<=14)? 2 : 3)",
    "(n==1 ? 0 : (n%10>=2 && n%10<=4) && (n%100<12 || n%100>14) ? 1 : n!=1 && (n%10>=0 && n%10<=1) || (n%10>=5 && n%10<=9) || (n%100>=12 && n%100<=14) ? 2 : 3)",
    "(n % 1 == 0 && n % 10 == 1 && n % 100 != 11 ? 0 : n % 1 == 0 && n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? 1 : n % 1 == 0 && (n % 10 ==0 || (n % 10 >=5 && n % 10 <=9) || (n % 100 >=11 && n % 100 <=14 )) ? 2: 3)",
)
ZERO_ONE_FEW_MANY_OTHER_PLURALS = (
    "n==0 ? 0 : n==1 ? 1 : ( n%100>1 && n%100<11) ? 2 : (n%100>10 && n%100<20 ) ? 3 : 4",
    "(n==0 ? 0 : n==1 ? 1 : (n>=2 && n<=5) ? 2 : n==6 ? 3 : 4)",
)

ONE_OTHER_ZERO_PLURALS = (
    "n%10==1 && n%100!=11 ? 0 : n != 0 ? 1 : 2",
    "(n%10==1 && n%100!=11 ? 0 : n != 0 ? 1 : 2)",
)

ZERO_ONE_TWO_FEW_MANY_OTHER_PLURALS = (
    "(n==0) ? 0 : (n==1) ? 1 : (n==2) ? 2 : (n==3) ? 3 :(n==6) ? 4 : 5",
    "(n == 0) ? 0 : ((n == 1) ? 1 : ((n == 2) ? 2 : ((n % 100 >= 3 && n % 100 <= 10) ? 3 : ((n % 100 >= 11 && n % 100 <= 99) ? 4 : 5))))",
    "(n == 0) ? 0 : ((n == 1) ? 1 : (((n % 100 == 2 || n % 100 == 22 || n % 100 == 42 || n % 100 == 62 || n % 100 == 82) || n % 1000 == 0 && (n % 100000 >= 1000 && n % 100000 <= 20000 || n % 100000 == 40000 || n % 100000 == 60000 || n % 100000 == 80000) || n != 0 && n % 1000000 == 100000) ? 2 : ((n % 100 == 3 || n % 100 == 23 || n % 100 == 43 || n % 100 == 63 || n % 100 == 83) ? 3 : ((n != 1 && (n % 100 == 1 || n % 100 == 21 || n % 100 == 41 || n % 100 == 61 || n % 100 == 81)) ? 4 : 5))))",
    "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : (n>2 && n<7) ? 3 :(n>6 && n<11) ? 4 : 5",
    "n==0 ? 0 : (n % 10 == 1 && n % 100 != 11 && n % 100 != 71 && n % 100 != 91) ? 1 : ((n % 10 == 2 && n % 100 != 12 && n % 100 != 72 && n % 100 != 92) ? 2 : ((((n % 10 == 3 || n % 10 == 4) || n % 10 == 9) && (n % 100 < 10 || n % 100 > 19) && (n % 100 < 70 || n % 100 > 79) && (n % 100 < 90 || n % 100 > 99)) ? 3 : ((n != 0 && n % 1000000 == 0) ? 4 : 5)))",
    "(n == 0) ? 0 : (n == 1) ? 1 : ((n == 2) ? 2 : ((n == 0 || n % 100 >= 3 && n % 100 <= 10) ? 3 : ((n % 100 >= 11 && n % 100 <= 19) ? 4 : 5)))",
    "(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : (n%100>=3 && n%100<=10) ? 3 : n%100>=11 ? 4 : 5)",
    "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5",
)
ONE_MANY_OTHER_PLURALS = (
    "(n == 1) ? 0 : ((n != 0 && n % 1000000 == 0) ? 1 : 2)",
    "(n == 0 || n == 1) ? 0 : ((n != 0 && n % 1000000 == 0) ? 1 : 2)",
)
ZERO_ONE_MANY_OTHER_PLURALS = (
    "(n == 0) ? 0 : (n == 1) ? 1 : ((n != 0 && n % 1000000 == 0) ? 2 : 3)",
)

ZERO_OTHER_PLURALS = ("n==0 ? 0 : 1",)

# Plural types definition
PLURAL_NONE = 0
PLURAL_ONE_OTHER = 1
PLURAL_ONE_FEW_OTHER = 2
PLURAL_ARABIC = 3
PLURAL_ONE_TWO_OTHER = 4
PLURAL_ONE_TWO_THREE_OTHER = 5
PLURAL_ONE_TWO_FEW_OTHER = 6
PLURAL_ONE_OTHER_ZERO = 7
PLURAL_ONE_FEW_MANY_OTHER = 8
PLURAL_TWO_OTHER = 9
PLURAL_ONE_TWO_FEW_MANY_OTHER = 10
PLURAL_ZERO_ONE_OTHER = 11
PLURAL_ZERO_ONE_TWO_FEW_MANY_OTHER = 12
PLURAL_OTHER_ONE_TWO_FEW = 13
PLURAL_ONE_OTHER_TWO = 14
PLURAL_ZERO_OTHER = 15
PLURAL_ZERO_ONE_FEW_OTHER = 16
PLURAL_ZERO_ONE_TWO_FEW_OTHER = 17
PLURAL_ZERO_ONE_TWO_OTHER = 18
PLURAL_ZERO_ONE_FEW_MANY_OTHER = 19
PLURAL_ONE_MANY_OTHER = 20
PLURAL_ZERO_ONE_MANY_OTHER = 21
PLURAL_ONE_FEW_MANY = 22
PLURAL_ONE_ZERO_FEW_OTHER = 23
PLURAL_UNKNOWN = 666

# Extra zero plural handling for stringsdict
ZERO_PLURAL_TYPES = {
    PLURAL_ARABIC,
    PLURAL_ZERO_ONE_OTHER,
    PLURAL_ZERO_ONE_TWO_FEW_MANY_OTHER,
}

FORMULA_WITH_ZERO = {
    "0": "n==0 ? 0 : 1",
    "n > 1": "n==0 ? 0 : n==1 ? 1 : 2",
    "n != 1": "n==0 ? 0 : n==1 ? 1 : 2",
    "(n == 0 || n == 1) ? 0 : ((n >= 2 && n <= 10) ? 1 : 2)": "n == 0 ? 0 : n == 1 ? 1 : ((n >= 2 && n <= 10) ? 2 : 3)",
    "n == 1 ? 0 : n == 2 ? 1 : 2": "n == 0 ? 0 : n == 1 ? 1 : n == 2 ? 2 : 3",
    "n==1 || n%10==1 ? 0 : 1": "n == 0 ? 0 : n==1 || n%10==1 ? 1 : 2",
    "n==1 ? 0 : n==2 ? 1 : 2": "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : 3",
    "(n==1 || n==11) ? 0 : (n==2 || n==12) ? 1 : (n > 2 && n < 20) ? 2 : 3": "n==0 ? 0 : (n==1 || n==11) ? 1 : (n==2 || n==12) ? 2 : (n > 2 && n < 20) ? 3 : 4",
    "n != 1 && n != 2 && n != 3 && (n % 10 == 4 || n % 10 == 6 || n % 10 == 9)": "n==0 ? 0 : n != 1 && n != 2 && n != 3 && (n % 10 == 4 || n % 10 == 6 || n % 10 == 9) ? 1: 2",
    "n==1 ? 0 : (n==0 || (n%100 > 0 && n%100 < 20)) ? 1 : 2": "n==0 ? 0 : n==1 ? 1 : (n==0 || (n%100 > 0 && n%100 < 20)) ? 2 : 3",
    "(n == 1) ? 0 : ((n == 0 || n % 100 >= 2 && n % 100 <= 19) ? 1 : 2)": "n==0 ? 0 : (n == 1) ? 1 : ((n == 0 || n % 100 >= 2 && n % 100 <= 19) ? 2 : 3)",
    "n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2": "n==0 ? 0 : n==1 ? 1 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 2 : 3",
    "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2": "n==0 ? 0 : (n==1) ? 1 : (n>=2 && n<=4) ? 2 : 3",
    "(n == 1) ? 0 : ((n == 2) ? 1 : 2)": "n==0 ? 0 : (n == 1) ? 1 : ((n == 2) ? 2 : 3)",
    "n==1 ? 0 : n==0 || ( n%100>1 && n%100<11) ? 1 : (n%100>10 && n%100<20 ) ? 2 : 3": "n==0 ? 0 : n==1 ? 1 : ( n%100>1 && n%100<11) ? 2 : (n%100>10 && n%100<20 ) ? 3 : 4",
    "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2": "n==0 ? 0 : n%10==1 && n%100!=11 ? 1 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 2 : 3",
    "(n == 1) ? 0 : ((n == 2) ? 1 : ((n > 10 && n % 10 == 0) ? 2 : 3))": "n==0 ? 0 : (n == 1) ? 1 : ((n == 2) ? 2 : ((n > 10 && n % 10 == 0) ? 3 : 4))",
    "n==1 ? 0 : n==2 ? 1 : (n>2 && n<7) ? 2 :(n>6 && n<11) ? 3 : 4": "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : (n>2 && n<7) ? 3 :(n>6 && n<11) ? 4 : 5",
    "(n % 100 == 1) ? 0 : ((n % 100 == 2) ? 1 : ((n % 100 == 3 || n % 100 == 4) ? 2 : 3))": "n==0 ? 0 : (n % 100 == 1) ? 1 : ((n % 100 == 2) ? 2 : ((n % 100 == 3 || n % 100 == 4) ? 3 : 4))",
    "n%100==1 ? 0 : n%100==2 ? 1 : n%100==3 || n%100==4 ? 2 : 3": "n==0 ? 0 : n%100==1 ? 1 : n%100==2 ? 2 : n%100==3 || n%100==4 ? 3 : 4",
    "n % 10 != 1 || n % 100 == 11": "n==0 ? 0 : n % 10 != 1 || n % 100 == 11 ? 1 :2",
    "(n % 10 == 1 && (n % 100 < 11 || n % 100 > 19)) ? 0 : ((n % 10 >= 2 && n % 10 <= 9 && (n % 100 < 11 || n % 100 > 19)) ? 1 : 2)": "n==0 ? 0 : (n % 10 == 1 && (n % 100 < 11 || n % 100 > 19)) ? 1 : ((n % 10 >= 2 && n % 10 <= 9 && (n % 100 < 11 || n % 100 > 19)) ? 2 : 3)",
    "n >= 2 && (n < 11 || n > 99)": "n==0 ? 0 : n >= 2 && (n < 11 || n > 99) ? 1 : 2",
    "(n % 10 == 1) ? 0 : ((n % 10 == 2) ? 1 : ((n % 100 == 0 || n % 100 == 20 || n % 100 == 40 || n % 100 == 60 || n % 100 == 80) ? 2 : 3))": "n==0 ? 0 : (n % 10 == 1) ? 1 : ((n % 10 == 2) ? 2 : ((n % 100 == 0 || n % 100 == 20 || n % 100 == 40 || n % 100 == 60 || n % 100 == 80) ? 3 : 4))",
    "(n % 10 == 1 && n % 100 != 11 && n % 100 != 71 && n % 100 != 91) ? 0 : ((n % 10 == 2 && n % 100 != 12 && n % 100 != 72 && n % 100 != 92) ? 1 : ((((n % 10 == 3 || n % 10 == 4) || n % 10 == 9) && (n % 100 < 10 || n % 100 > 19) && (n % 100 < 70 || n % 100 > 79) && (n % 100 < 90 || n % 100 > 99)) ? 2 : ((n != 0 && n % 1000000 == 0) ? 3 : 4)))": "n==0 ? 0 : (n % 10 == 1 && n % 100 != 11 && n % 100 != 71 && n % 100 != 91) ? 1 : ((n % 10 == 2 && n % 100 != 12 && n % 100 != 72 && n % 100 != 92) ? 2 : ((((n % 10 == 3 || n % 10 == 4) || n % 10 == 9) && (n % 100 < 10 || n % 100 > 19) && (n % 100 < 70 || n % 100 > 79) && (n % 100 < 90 || n % 100 > 99)) ? 3 : ((n != 0 && n % 1000000 == 0) ? 4 : 5)))",
    "n%10==1 && n%100!=11 ? 0 : n != 0 ? 1 : 2": "n==0 ? 0 : n%10==1 && n%100!=11 ? 1 : 2",
    "(n == 1) ? 0 : ((n != 0 && n % 1000000 == 0) ? 1 : 2)": "(n == 0) ? 0 : (n == 1) ? 1 : ((n != 0 && n % 1000000 == 0) ? 2 : 3)",
    "(n == 0 || n == 1) ? 0 : ((n != 0 && n % 1000000 == 0) ? 1 : 2)": "(n == 0) ? 0 : (n == 1) ? 1 : ((n != 0 && n % 1000000 == 0) ? 2 : 3)",
    "(n == 1) ? 0 : ((n == 2) ? 1 : ((n == 0 || n % 100 >= 3 && n % 100 <= 10) ? 2 : ((n % 100 >= 11 && n % 100 <= 19) ? 3 : 4)))": "(n == 0) ? 0 : (n == 1) ? 1 : ((n == 2) ? 2 : ((n == 0 || n % 100 >= 3 && n % 100 <= 10) ? 3 : ((n % 100 >= 11 && n % 100 <= 19) ? 4 : 5)))",
}


def nospace_set(source):
    return {item.replace(" ", "") for item in source}


# Plural formula - type mappings
PLURAL_MAPPINGS = (
    (nospace_set(ONE_OTHER_PLURALS), PLURAL_ONE_OTHER),
    (nospace_set(ONE_FEW_OTHER_PLURALS), PLURAL_ONE_FEW_OTHER),
    (nospace_set(ZERO_ONE_FEW_OTHER_PLURALS), PLURAL_ZERO_ONE_FEW_OTHER),
    (nospace_set(ONE_ZERO_FEW_OTHER_PLURALS), PLURAL_ONE_ZERO_FEW_OTHER),
    (nospace_set(ONE_TWO_OTHER_PLURALS), PLURAL_ONE_TWO_OTHER),
    (nospace_set(ZERO_ONE_TWO_OTHER_PLURALS), PLURAL_ZERO_ONE_TWO_OTHER),
    (nospace_set(ONE_OTHER_TWO_PLURALS), PLURAL_ONE_OTHER_TWO),
    (nospace_set(ZERO_ONE_OTHER_PLURALS), PLURAL_ZERO_ONE_OTHER),
    (nospace_set(ONE_TWO_FEW_OTHER_PLURALS), PLURAL_ONE_TWO_FEW_OTHER),
    (nospace_set(ZERO_ONE_TWO_FEW_OTHER_PLURALS), PLURAL_ZERO_ONE_TWO_FEW_OTHER),
    (nospace_set(OTHER_ONE_TWO_FEW_PLURALS), PLURAL_OTHER_ONE_TWO_FEW),
    (nospace_set(ONE_TWO_THREE_OTHER_PLURALS), PLURAL_ONE_TWO_THREE_OTHER),
    (nospace_set(ONE_OTHER_ZERO_PLURALS), PLURAL_ONE_OTHER_ZERO),
    (nospace_set(ONE_FEW_MANY_OTHER_PLURALS), PLURAL_ONE_FEW_MANY_OTHER),
    (nospace_set(ZERO_ONE_FEW_MANY_OTHER_PLURALS), PLURAL_ZERO_ONE_FEW_MANY_OTHER),
    (nospace_set(TWO_OTHER_PLURALS), PLURAL_TWO_OTHER),
    (nospace_set(ONE_TWO_FEW_MANY_OTHER_PLURALS), PLURAL_ONE_TWO_FEW_MANY_OTHER),
    (
        nospace_set(ZERO_ONE_TWO_FEW_MANY_OTHER_PLURALS),
        PLURAL_ZERO_ONE_TWO_FEW_MANY_OTHER,
    ),
    (nospace_set(ZERO_OTHER_PLURALS), PLURAL_ZERO_OTHER),
    (nospace_set(ONE_MANY_OTHER_PLURALS), PLURAL_ONE_MANY_OTHER),
    (nospace_set(ZERO_ONE_MANY_OTHER_PLURALS), PLURAL_ZERO_ONE_MANY_OTHER),
    (nospace_set(ONE_FEW_MANY_PLURALS), PLURAL_ONE_FEW_MANY),
)

# Plural names mapping
PLURAL_NAMES = {
    PLURAL_NONE: ("",),
    PLURAL_ONE_OTHER: (
        pgettext_lazy("Plural form description", "Singular"),
        pgettext_lazy("Plural form description", "Plural"),
    ),
    PLURAL_ONE_FEW_OTHER: (
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Few"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ZERO_ONE_FEW_OTHER: (
        pgettext_lazy("Plural form description", "Zero"),
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Few"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ONE_ZERO_FEW_OTHER: (
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Zero"),
        pgettext_lazy("Plural form description", "Few"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ARABIC: (
        pgettext_lazy("Plural form description", "Zero"),
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Two"),
        pgettext_lazy("Plural form description", "Few"),
        pgettext_lazy("Plural form description", "Many"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ZERO_ONE_OTHER: (
        pgettext_lazy("Plural form description", "Zero"),
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ONE_TWO_OTHER: (
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Two"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ZERO_ONE_TWO_OTHER: (
        pgettext_lazy("Plural form description", "Zero"),
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Two"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ONE_OTHER_TWO: (
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Other"),
        pgettext_lazy("Plural form description", "Two"),
    ),
    PLURAL_ONE_TWO_THREE_OTHER: (
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Two"),
        pgettext_lazy("Plural form description", "Three"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ONE_TWO_FEW_OTHER: (
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Two"),
        pgettext_lazy("Plural form description", "Few"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ZERO_ONE_TWO_FEW_OTHER: (
        pgettext_lazy("Plural form description", "Zero"),
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Two"),
        pgettext_lazy("Plural form description", "Few"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_OTHER_ONE_TWO_FEW: (
        pgettext_lazy("Plural form description", "Other"),
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Two"),
        pgettext_lazy("Plural form description", "Few"),
    ),
    PLURAL_ONE_OTHER_ZERO: (
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Other"),
        pgettext_lazy("Plural form description", "Zero"),
    ),
    PLURAL_ONE_FEW_MANY_OTHER: (
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Few"),
        pgettext_lazy("Plural form description", "Many"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ZERO_ONE_FEW_MANY_OTHER: (
        pgettext_lazy("Plural form description", "Zero"),
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Few"),
        pgettext_lazy("Plural form description", "Many"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ONE_TWO_FEW_MANY_OTHER: (
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Two"),
        pgettext_lazy("Plural form description", "Few"),
        pgettext_lazy("Plural form description", "Many"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_TWO_OTHER: (
        pgettext_lazy("Plural form description", "Two"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ZERO_ONE_TWO_FEW_MANY_OTHER: (
        pgettext_lazy("Plural form description", "Zero"),
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Two"),
        pgettext_lazy("Plural form description", "Few"),
        pgettext_lazy("Plural form description", "Many"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ZERO_OTHER: (
        pgettext_lazy("Plural form description", "Zero"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ONE_MANY_OTHER: (
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Many"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ZERO_ONE_MANY_OTHER: (
        pgettext_lazy("Plural form description", "Zero"),
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Many"),
        pgettext_lazy("Plural form description", "Other"),
    ),
    PLURAL_ONE_FEW_MANY: (
        pgettext_lazy("Plural form description", "One"),
        pgettext_lazy("Plural form description", "Few"),
        pgettext_lazy("Plural form description", "Many"),
    ),
}
