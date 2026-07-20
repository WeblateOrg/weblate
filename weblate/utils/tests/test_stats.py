# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest.mock import patch

from django.test import SimpleTestCase

from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_READONLY,
    STATE_TRANSLATED,
)
from weblate.utils.stats import (
    STATS_PREFETCH_CHUNK_SIZE,
    BaseStats,
    TranslationStats,
    prefetch_stats,
)


class StubStats(BaseStats):
    def __init__(self, identifier: int) -> None:
        super().__init__(None)
        self.identifier = identifier

    @property
    def cache_key(self) -> str:
        return f"stub-stats-{self.identifier}"

    def _calculate_basic(self) -> None:
        raise AssertionError


class StubObject:
    def __init__(self, identifier: int) -> None:
        self.identifier = identifier
        self.stats = StubStats(identifier)


class StatsPrefetchTest(SimpleTestCase):
    def test_prefetch_is_bounded_and_preserves_order(self) -> None:
        count = 2 * STATS_PREFETCH_CHUNK_SIZE + 1
        objects = [StubObject(identifier) for identifier in range(count)]

        with patch("weblate.utils.stats.cache.get_many", return_value={}) as get_many:
            result = prefetch_stats(item for item in objects)

        self.assertEqual(
            [item.identifier for item in result],
            list(range(count)),
        )
        self.assertEqual(
            [len(call.args[0]) for call in get_many.call_args_list],
            [STATS_PREFETCH_CHUNK_SIZE, STATS_PREFETCH_CHUNK_SIZE, 1],
        )
        self.assertTrue(all(item.stats.is_loaded for item in objects))

    def test_update_dependencies_are_deduplicated_in_order(self) -> None:
        root = StubStats(0)
        dependencies: list[BaseStats] = [
            StubStats(1),
            StubStats(2),
            StubStats(1),
            StubStats(3),
        ]
        root._collected_update_objects = dependencies  # ruff: ignore[private-member-access]
        for stats in dependencies:
            stats.set_data({})

        self.assertEqual(
            [stats.cache_key for stats in root._iterate_update_objects()],  # ruff: ignore[private-member-access]
            ["stub-stats-1", "stub-stats-2", "stub-stats-3"],
        )

    def test_snapshot_buckets_cover_all_delta_keys(self) -> None:
        covered: set[str] = set()
        for state in (
            STATE_EMPTY,
            STATE_FUZZY,
            STATE_TRANSLATED,
            STATE_APPROVED,
            STATE_READONLY,
        ):
            for flags in range(32):
                covered.update(
                    TranslationStats.snapshot_to_bucket(
                        {
                            "state": state,
                            "num_words": 2,
                            "num_chars": 3,
                            "active_checks_count": flags & 1,
                            "dismissed_checks_count": flags & 2,
                            "suggestion_count": flags & 4,
                            "label_count": flags & 8,
                            "comment_count": flags & 16,
                        }
                    )
                )

        self.assertEqual(covered, TranslationStats.UNIT_DELTA_KEYS)
