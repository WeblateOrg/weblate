# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals

from numba import njit

from jellyfish import damerau_levenshtein_distance


@njit
def jit_damerau_levenshtein_distance(s1, s2):
    """Reimplemented from jellyfish to utilize jit

    - avoid type checking
    - avoid using defaultdict
    """
    len1 = len(s1)
    len2 = len(s2)
    infinite = len1 + len2
    # character array
    da = {}
    # distance matrix
    score = [[0] * (len2 + 2) for x in range(len1 + 2)]
    score[0][0] = infinite
    for i in range(0, len1 + 1):
        score[i + 1][0] = infinite
        score[i + 1][1] = i
    for i in range(0, len2 + 1):
        score[0][i + 1] = infinite
        score[1][i + 1] = i
    for i in range(1, len1 + 1):
        db = 0
        for j in range(1, len2 + 1):
            k = s2[j - 1]
            i1 = da.get(s2[j - 1], 0)
            j1 = db
            cost = 1
            if s1[i - 1] == s2[j - 1]:
                cost = 0
                db = j
            score[i + 1][j + 1] = min(
                score[i][j] + cost,
                score[i + 1][j] + 1,
                score[i][j + 1] + 1,
                score[i1][j1] + (i - i1 - 1) + 1 + (j - j1 - 1),
            )
        da[s1[i - 1]] = i
    return score[len1 + 1][len2 + 1]


class Comparer(object):
    """String comparer abstraction.

    The reason is to be able to change implementation."""

    def similarity(self, first, second):
        """Returns string similarity in range 0 - 100%."""
        try:
            # The C version (default) fails on unicode chars
            # see https://github.com/jamesturk/jellyfish/issues/55
            try:
                distance = damerau_levenshtein_distance(first, second)
            except ValueError:
                distance = jit_damerau_levenshtein_distance(first, second)
            return int(
                100 * (1.0 - (float(distance) / max(len(first), len(second), 1)))
            )
        except MemoryError:
            # Too long string, mark them as not much similar
            return 50
