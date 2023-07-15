# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re

from django.utils.html import format_html
from django.utils.translation import gettext_lazy

from weblate.checks.base import TargetCheck
from weblate.checks.data import NON_WORD_CHARS
from weblate.checks.same import strip_format

# Regexp for non word chars
NON_WORD = re.compile("[{}\\]]+".format("".join(NON_WORD_CHARS)))

# Per language ignore list
IGNORES = {
    "fy": {"jo", "mei"},
    "fr": {"vous", "nous"},
    "hi": {"कर"},
    "tr": {"tek"},
    "sq": {"të"},
}


class DuplicateCheck(TargetCheck):
    """Check for duplicated tokens."""

    check_id = "duplicate"
    name = gettext_lazy("Consecutive duplicated words")
    description = gettext_lazy("Text contains the same word twice in a row:")

    def extract_groups(self, text: str, language_code: str):
        previous = None
        group = 1
        groups = []
        words = []
        ignored = IGNORES.get(language_code, set())
        for word in NON_WORD.split(text):
            if not word:
                continue
            if word not in ignored and len(word) >= 2 and previous == word:
                group += 1
            elif group > 1:
                groups.append(group)
                words.append(previous)
                group = 1
            previous = word
        if group > 1:
            groups.append(group)
            words.append(previous)
        return groups, words

    def check_single(self, source, target, unit):
        source_code = unit.translation.component.source_language.base_code
        lang_code = unit.translation.language.base_code

        source_groups, source_words = self.extract_groups(
            strip_format(source, unit.all_flags),
            source_code,
        )
        target_groups, target_words = self.extract_groups(
            strip_format(target, unit.all_flags),
            lang_code,
        )

        # The same groups in source and target
        if source_groups == target_groups:
            return {}

        return set(target_words) - set(source_words)

    def get_description(self, check_obj):
        duplicate = set()
        unit = check_obj.unit
        source = unit.source_string
        for target in unit.get_target_plurals():
            duplicate.update(self.check_single(source, target, unit))
        return format_html("{} {}", self.description, ", ".join(sorted(duplicate)))
