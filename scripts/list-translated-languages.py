#!/usr/bin/env python3

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from importlib.util import module_from_spec, spec_from_file_location

import requests
from icu import Locale

URL = "https://hosted.weblate.org/api/components/weblate/application/statistics/?format=json-flat"
THRESHOLD = 40


def print_language(lang, fmt="{0} ({1})") -> None:
    """Print language code with its name."""
    locale = Locale(lang)
    print(fmt.format(lang, locale.getDisplayName(locale).capitalize()))


def main() -> None:
    # load and parse data
    data = requests.get(URL, timeout=5).json()

    # select languages
    languages_list = []
    for lang in data:
        if lang["translated_percent"] > THRESHOLD:
            code = lang["code"].replace("_", "-").lower()
            if code == "nb-no":
                code = "nb"
            languages_list.append(code)
    languages_list.sort()
    print("Expected setup:")
    for lang in languages_list:
        print_language(lang, fmt="    ('{0}', '{1}'),")

    # prepare for checking
    languages = set(languages_list)
    # we always want english language
    languages.add("en")
    # load settings
    extra = set()
    spec = spec_from_file_location("settings", "./weblate/settings_example.py")
    if spec is None or spec.loader is None:
        raise ValueError
    settings = module_from_spec(spec)
    if settings is None:
        raise ValueError
    spec.loader.exec_module(settings)
    for lang in settings.LANGUAGES:
        if lang[0] in languages:
            languages.remove(lang[0])
        else:
            extra.add(lang[0])
    # Print results
    if len(extra) > 0:
        print("Extra languages:")
        for lang in extra:
            print_language(lang)
    if len(languages) > 0:
        print("Missing languages:")
        for lang in languages:
            print_language(lang)


if __name__ == "__main__":
    main()
