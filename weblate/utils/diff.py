# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from diff_match_patch import diff_match_patch
from django.utils.html import format_html

from weblate.utils.unicodechars import COMPOSITING_CHARS

MAX_DIFF_PAIRS = 1_000_000
MAX_DIFF_LENGTH = 10_000
DIFF_TIMEOUT = 0.05


class Differ:
    DIFF_DELETE = diff_match_patch.DIFF_DELETE
    DIFF_INSERT = diff_match_patch.DIFF_INSERT
    DIFF_EQUAL = diff_match_patch.DIFF_EQUAL

    def __init__(self) -> None:
        self.dmp = diff_match_patch()
        self.dmp.Diff_Timeout = DIFF_TIMEOUT

    def compare(self, new: str, old: str) -> list[tuple[str, str]] | None:
        """Return None when the changed content is too large to diff safely."""
        dmp = self.dmp
        prefix = dmp.diff_commonPrefix(old, new)
        suffix = dmp.diff_commonSuffix(old[prefix:], new[prefix:])
        old_length = len(old) - prefix - suffix
        new_length = len(new) - prefix - suffix
        if (
            max(old_length, new_length) > MAX_DIFF_LENGTH
            or old_length * new_length > MAX_DIFF_PAIRS
        ):
            return None
        diffs = dmp.diff_main(old, new)
        dmp.diff_cleanupSemantic(diffs)
        dmp.diff_cleanupEfficiency(diffs)
        self.cleanup_unicode(diffs)
        return diffs

    def cleanup_unicode(self, diffs: list[tuple[str, str]]) -> None:
        """Merge Unicode characters."""
        pointer = 0
        while pointer < len(diffs):
            if (
                diffs[pointer][0] != self.DIFF_EQUAL
                and diffs[pointer][1]
                and diffs[pointer][1][0] in COMPOSITING_CHARS
                and pointer > 0
                and diffs[pointer - 1][0] == self.DIFF_EQUAL
            ):
                # Merge previous characters up to anything else than non spacing mark to current diff
                previous_block = diffs[pointer - 1][1]
                merged = 1
                while (
                    merged < len(previous_block)
                    and previous_block[-merged] in COMPOSITING_CHARS
                ):
                    merged += 1

                previous_chars = previous_block[-merged:]

                current_operation = diffs[pointer][0]
                diffs[pointer] = (
                    current_operation,
                    f"{previous_chars}{diffs[pointer][1]}",
                )
                new_operation = (
                    self.DIFF_DELETE
                    if current_operation == self.DIFF_INSERT
                    else self.DIFF_INSERT
                )
                if len(previous_block) == merged:
                    diffs[pointer - 1] = (new_operation, previous_chars)
                else:
                    # Remove extracted char
                    diffs[pointer - 1] = (
                        diffs[pointer - 1][0],
                        previous_block[:-merged],
                    )
                    # Build new diff entry
                    new_diff = (new_operation, previous_chars)
                    # Extend diff list
                    diffs.insert(pointer, new_diff)
                    pointer += 1
            pointer += 1

    def highlight(self, new: str, old: str) -> str:
        diff = self.compare(new, old)
        if diff is None:
            return str(format_html("{}", new))
        output = []
        for op, data in diff:
            if op == self.DIFF_DELETE:
                template = "<del>{}</del>"
            elif op == self.DIFF_INSERT:
                template = "<ins>{}</ins>"
            elif op == self.DIFF_EQUAL:
                template = "{}"
            else:
                msg = f"Unsuppoorted operation: {op}"
                raise ValueError(msg)
            output.append(format_html(template, data))
        return "".join(output)
