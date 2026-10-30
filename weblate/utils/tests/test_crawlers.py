# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Crawler identity, refresh isolation, and snapshot lifecycle tests."""

from __future__ import annotations

import io
import json
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, SimpleTestCase, override_settings

from weblate.utils.bot_protection import CrawlerRanges
from weblate.utils.crawlers import (
    CRAWLERS,
    MAX_DOWNLOAD,
    SNAPSHOT,
    parse_feed,
    public_network,
)
from weblate.utils.management.commands.update_crawler_ranges import refresh

if TYPE_CHECKING:
    from collections.abc import Generator

AGENTS = {
    "googlebot": "Googlebot (+http://www.google.com/bot.html)",
    "bingbot": "bingbot (+http://www.bing.com/bingbot.htm)",
    "applebot": "Applebot/0.1",
    "duckduckbot": "DuckDuckBot/1.1; (+http://duckduckgo.com/duckduckbot.html)",
    "qwantbot": "Qwantbot-news/2.0; +https://help.qwant.com/bot/",
    "mojeekbot": "MojeekBot +https://www.mojeek.com/bot.html",
    "marginalia": "search.marginalia.nu",
    "commoncrawl": "CCBot/2.0",
    "arquivo-pt": "Mozilla/5.0",
    "seznambot": "SeznamBot/4.0",
    "kagibot": "Kagibot/1.0; +https://kagi.com/bot",
    "internet-archive": "Mozilla/5.0",
    "wikimedia-citoid": "Citoid/WMF",
}


@contextmanager
def crawler_snapshot_path() -> Generator[Path, None, None]:
    """Keep the temporary snapshot directory alive for the complete test."""
    with tempfile.TemporaryDirectory() as directory:
        yield Path(directory) / "ranges.json"


class CrawlerTest(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.filename = self.enterContext(crawler_snapshot_path())
        self.settings_override = override_settings(
            BOT_PROTECTION_CRAWLER_FILE=str(self.filename),
            BOT_PROTECTION_CRAWLER_RULES={},
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        self.snapshot["refreshed_at"] = {
            name: time.time() for name in self.snapshot["ranges"]
        }
        self.save()

    def save(self) -> None:
        self.filename.write_text(json.dumps(self.snapshot), encoding="utf-8")

    def verified(self, ranges: CrawlerRanges, address: str, agent: str) -> bool:
        return ranges.verified(
            self.factory.get("/", REMOTE_ADDR=address, HTTP_USER_AGENT=agent)
        )

    def test_identities(self) -> None:
        ranges = CrawlerRanges()
        for name, crawler in CRAWLERS.items():
            networks = crawler.ranges or tuple(self.snapshot["ranges"][name])
            for value in networks:
                address = str(public_network(value).network_address)
                with self.subTest(provider=name, network=value):
                    self.assertTrue(self.verified(ranges, address, AGENTS[name]))
                    if name not in {"internet-archive", "arquivo-pt"}:
                        self.assertFalse(
                            self.verified(ranges, address, "ordinary-browser")
                        )
            self.assertFalse(self.verified(ranges, "1.1.1.1", AGENTS[name]))
        self.assertTrue(
            self.verified(ranges, "208.80.152.1", "ZoteroTranslationServer/WMF")
        )
        self.assertFalse(self.verified(ranges, "194.210.235.64", "Mozilla/5.0"))
        self.assertFalse(self.verified(ranges, "194.210.234.255", "Mozilla/5.0"))
        self.assertFalse(self.verified(ranges, "77.75.76.1", "SeznamBot/4.0"))
        self.assertTrue(self.verified(ranges, "77.75.72.26", "SeznamBot/4.0"))

    def test_staleness_and_custom_rules(self) -> None:
        self.snapshot["refreshed_at"]["googlebot"] -= 8 * 86400
        self.snapshot["ranges"]["custom"] = ["8.8.8.8/32"]
        self.snapshot["refreshed_at"]["custom"] = time.time()
        self.save()
        with override_settings(BOT_PROTECTION_CRAWLER_RULES={"custom": "ExampleBot"}):
            ranges = CrawlerRanges()
        self.assertTrue(self.verified(ranges, "66.249.64.1", AGENTS["googlebot"]))
        self.assertTrue(self.verified(ranges, "8.8.8.8", "ExampleBot"))
        self.assertTrue(self.verified(ranges, "157.55.39.1", AGENTS["bingbot"]))
        self.filename.write_text("{broken", encoding="utf-8")
        ranges = CrawlerRanges()
        self.assertTrue(self.verified(ranges, "207.241.224.1", "Mozilla/5.0"))
        self.assertFalse(self.verified(ranges, "157.55.39.1", AGENTS["bingbot"]))

    def test_malformed_provider_is_isolated(self) -> None:
        self.snapshot["ranges"]["googlebot"] = ["10.0.0.0/8"]
        self.snapshot["refreshed_at"]["applebot"] = time.time() + 3600
        self.snapshot["refreshed_at"]["duckduckbot"] = "invalid"
        self.save()
        ranges = CrawlerRanges()
        self.assertTrue(self.verified(ranges, "157.55.39.1", AGENTS["bingbot"]))
        self.assertNotIn("googlebot", ranges.ranges)
        self.assertIn("applebot", ranges.ranges)
        self.assertIn("duckduckbot", ranges.ranges)

    def test_no_request_io_and_startup_loading(self) -> None:
        ranges = CrawlerRanges()
        with (
            patch("socket.gethostbyaddr", side_effect=AssertionError),
            patch("urllib.request.urlopen", side_effect=AssertionError),
            patch.object(ranges, "load", side_effect=AssertionError),
            patch("pathlib.Path.open", side_effect=AssertionError),
            patch(
                "weblate.utils.bot_protection.json.loads", side_effect=AssertionError
            ),
            patch(
                "weblate.utils.bot_protection.public_network",
                side_effect=AssertionError,
            ),
        ):
            for _index in range(100):
                self.assertTrue(
                    self.verified(ranges, "77.75.72.26", AGENTS["seznambot"])
                )
        self.snapshot["ranges"]["seznambot"] = []
        self.save()
        self.assertTrue(self.verified(ranges, "77.75.72.26", AGENTS["seznambot"]))
        self.assertFalse(
            self.verified(CrawlerRanges(), "77.75.72.26", AGENTS["seznambot"])
        )

    def test_feed_validation(self) -> None:
        for value in (
            "10.0.0.0/8",
            "172.0.0.0/8",
            "127.0.0.1",
            "fc00::/7",
            "0.0.0.0/0",
            "224.0.0.0/4",
            "invalid",
            134744072,
        ):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                public_network(cast("str", value))
        for raw in (
            b"{}",
            b'{"prefixes": []}',
            b'{"prefixes": [{"ipv4Prefix": "10.0.0.0/8"}]}',
            b"x" * (MAX_DOWNLOAD + 1),
        ):
            with self.subTest(raw=raw[:50]), self.assertRaises((ValueError, KeyError)):
                parse_feed(raw, CRAWLERS["googlebot"])
        self.assertEqual(
            parse_feed(b"8.8.8.8\n8.8.8.8\n", CRAWLERS["marginalia"]), ["8.8.8.8/32"]
        )

    def test_partial_refresh_preserves_custom_and_failed(self) -> None:
        self.snapshot["ranges"]["custom"] = ["8.8.8.8/32"]
        self.snapshot["refreshed_at"]["custom"] = time.time()
        self.save()
        old_google = self.snapshot["refreshed_at"]["googlebot"]

        def response(url: str, **_kwargs: int) -> io.BytesIO:
            if url == CRAWLERS["googlebot"].source:
                msg = "unavailable"
                raise OSError(msg)
            if url == CRAWLERS["marginalia"].source:
                return io.BytesIO(b"9.9.9.9\n")
            return io.BytesIO(
                b'{"creationTime":"2000-01-01", "prefixes":[{"ipv4Prefix":"9.9.9.9/32"}]}'
            )

        with patch(
            "weblate.utils.management.commands.update_crawler_ranges.urlopen",
            side_effect=response,
        ):
            failures = refresh(str(self.filename))
            self.assertEqual(len(failures), 1)
            with self.assertRaisesMessage(CommandError, "googlebot"):
                call_command("update_crawler_ranges")
        updated = json.loads(self.filename.read_text(encoding="utf-8"))
        self.assertEqual(updated["refreshed_at"]["googlebot"], old_google)
        self.assertEqual(updated["ranges"]["custom"], ["8.8.8.8/32"])
        self.assertEqual(updated["ranges"]["bingbot"], ["9.9.9.9/32"])
        self.assertGreaterEqual(updated["refreshed_at"]["bingbot"], int(old_google))

    def test_atomic_replacement_failure(self) -> None:
        original = self.filename.read_bytes()
        with (
            patch(
                "weblate.utils.management.commands.update_crawler_ranges.download",
                return_value=["8.8.8.8/32"],
            ),
            patch(
                "weblate.utils.management.commands.update_crawler_ranges.os.replace",
                side_effect=OSError,
            ),
            self.assertRaises(OSError),
        ):
            refresh(str(self.filename))
        self.assertEqual(self.filename.read_bytes(), original)
        self.assertEqual(list(self.filename.parent.iterdir()), [self.filename])
