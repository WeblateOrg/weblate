# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Properties cleanup addon.

This is reimplementation of
https://github.com/freeplane/freeplane/blob/1.4.x/freeplane_ant/
src/main/java/org/freeplane/ant/FormatTranslation.java
"""


import re

from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_PRE_COMMIT

SPLITTER = re.compile(r"\s*=\s*")
UNICODE = re.compile(r"\\[uU][0-9a-fA-F]{4}")


def sort_key(line):
    """Sort key for properties."""
    prefix = SPLITTER.split(line, 1)[0]
    return prefix.lower()


def unicode_format(match):
    """Callback for re.sub for formatting unicode chars."""
    return f"\\u{match.group(0)[2:].upper()}"


def fix_newlines(lines):
    """Convert newlines to unix."""
    for i, line in enumerate(lines):
        if line.endswith("\r\n"):
            lines[i] = line[:-2] + "\n"
        elif line.endswith("\r"):
            lines[i] = line[:-1] + "\n"


def format_unicode(lines):
    """Standard formatting for unicode chars."""
    for i, line in enumerate(lines):
        if UNICODE.findall(line) is None:
            continue
        lines[i] = UNICODE.sub(unicode_format, line)


def value_quality(value):
    """Calculate value quality."""
    if not value:
        return 0
    if "[translate me]" in value:
        return 1
    if "[auto]" in value:
        return 2
    return 3


def filter_lines(lines):
    """Filter comments, empty lines and duplicate strings."""
    result = []
    lastkey = None
    lastvalue = None

    for line in lines:
        # Skip comments and blank lines
        if line[0] == "#" or not line.strip():
            continue
        parts = SPLITTER.split(line, 1)

        # Missing = or empty key
        if len(parts) != 2 or not parts[0]:
            continue

        key, value = parts
        # Strip trailing \n in value
        value = value[:-1]

        # Empty translation
        if value in ("", "[auto]", "[translate me]"):
            continue

        # Check for duplicate key
        if key == lastkey:
            # Skip duplicate
            if value == lastvalue:
                continue

            quality = value_quality(value)
            lastquality = value_quality(lastvalue)

            if quality > lastquality:
                # Replace lower quality with new one
                result.pop()
            elif lastquality > quality or quality < 4:
                # Drop lower quality one
                continue

        result.append(line)
        lastkey = key
        lastvalue = value

    return result


def format_file(filename):
    """Format single properties file."""
    with open(filename) as handle:
        lines = handle.readlines()

    result = sorted(lines, key=sort_key)

    fix_newlines(result)
    format_unicode(result)
    result = filter_lines(result)

    if lines != result:
        with open(filename, "w") as handle:
            handle.writelines(result)


class PropertiesSortAddon(BaseAddon):
    events = (EVENT_PRE_COMMIT,)
    name = "weblate.properties.sort"
    verbose = gettext_lazy("Format the Java properties file")
    description = gettext_lazy("Formats and sorts the Java properties file.")
    compat = {"file_format": {"properties-utf8", "properties", "gwt"}}
    icon = "sort-alphabetical.svg"

    def pre_commit(self, translation, author):
        format_file(translation.get_filename())
