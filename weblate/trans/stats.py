# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


def get_project_stats(project):
    """Return stats for project."""
    return [
        {
            "language": str(tup.language),
            "code": tup.language.code,
            "total": tup.all,
            "translated": tup.translated,
            "translated_percent": tup.translated_percent,
            "total_words": tup.all_words,
            "translated_words": tup.translated_words,
            "translated_words_percent": tup.translated_words_percent,
            "total_chars": tup.all_chars,
            "translated_chars": tup.translated_chars,
            "translated_chars_percent": tup.translated_chars_percent,
        }
        for tup in project.stats.get_language_stats()
    ]
