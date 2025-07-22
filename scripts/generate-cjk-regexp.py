#!/usr/bin/env python

# Copyright © yhëhtozr <conlang2012@outlook.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Generate optimized regexp pattern to match CJK characters.

Character ranges should be made as contiguous as possible for maximum performance.

Used in weblate/trans/util.py
"""

import tinyunicodeblock

CJK_BLOCKS = {
    "CJK Unified Ideographs",
    "CJK Unified Ideographs Extension A",
    # 'CJK Unified Ideographs Extension B', # commented out in favor of catch-all Planes 2-3 match
    # 'CJK Unified Ideographs Extension C', # commented out in favor of catch-all Planes 2-3 match
    # 'CJK Unified Ideographs Extension D', # commented out in favor of catch-all Planes 2-3 match
    # 'CJK Unified Ideographs Extension E', # commented out in favor of catch-all Planes 2-3 match
    # 'CJK Unified Ideographs Extension F', # commented out in favor of catch-all Planes 2-3 match
    # 'CJK Unified Ideographs Extension G', # commented out in favor of catch-all Planes 2-3 match
    # 'CJK Unified Ideographs Extension H', # commented out in favor of catch-all Planes 2-3 match
    # 'CJK Unified Ideographs Extension I', # commented out in favor of catch-all Planes 2-3 match
    "CJK Compatibility",
    "CJK Compatibility Forms",
    "CJK Compatibility Ideographs",
    # 'CJK Compatibility Ideographs Supplement', # commented out in favor of catch-all Planes 2-3 match
    "CJK Radicals Supplement",
    "CJK Strokes",
    "CJK Symbols and Punctuation",
    "Hiragana",
    "Katakana",
    "Katakana Phonetic Extensions",
    "Kana Extended-A",
    "Kana Extended-B",
    "Kana Supplement",
    "Small Kana Extension",
    "Hangul Jamo",
    "Hangul Compatibility Jamo",
    "Hangul Jamo Extended-A",
    "Hangul Jamo Extended-B",
    "Hangul Syllables",
    "Halfwidth and Fullwidth Forms",
    "Enclosed CJK Letters and Months",
    "Enclosed Ideographic Supplement",
    "Kangxi Radicals",
    "Ideographic Description Characters",
    "Kanbun",
    "Yijing Hexagram Symbols",  # not strictly necessary but for the sake of range continuity
    "Bopomofo",
    "Bopomofo Extended",
}

cjkranges = [(b[0], b[1]) for b in tinyunicodeblock.BLOCKS if b[2] in CJK_BLOCKS]
cjkranges.sort(key=lambda r: ord(r[0]))
cjkmerged = []
prev = None
for r in cjkranges:
    if prev is None:
        prev = r
    elif ord(prev[1]) == ord(r[0]) - 1:
        prev = (prev[0], r[1])
    else:
        cjkmerged.append(prev)
        prev = r
cjkmerged.append(prev)


def hexchar(char):
    val = ord(char)
    if val > 0xFFFF:
        return rf"\U{val:08x}"
    return rf"\u{val:04x}"


print(
    rf'CJK_PATTERN = re.compile(r"([{"".join([f"{hexchar(r[0])}-{hexchar(r[1])}" for r in cjkmerged])}\U00020000-\U0003FFFF]+)")'
)
