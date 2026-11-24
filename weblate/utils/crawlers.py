# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Curated crawler identities; no request-time network discovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from ipaddress import IPv4Network, IPv6Network, ip_network
from pathlib import Path
from typing import Literal

Network = IPv4Network | IPv6Network
SNAPSHOT = Path(__file__).with_name("crawler-ranges.json")
MAX_DOWNLOAD = 1024 * 1024
# Endpoint checks alone miss private/special subnets inside a public-looking supernet.
NONPUBLIC_V4 = tuple(
    ip_network(value)
    for value in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
    )
)


@dataclass(frozen=True)
class Crawler:
    """A reviewed identity with either an official feed or bundled addresses."""

    agent: str
    source: str
    format: Literal["json", "text", "bundled"] = "json"
    ranges: tuple[str, ...] = ()


# Based on data/crawlers/_allow-good.yaml and its imported IP-based rules.
# Anubis is MIT licensed; regexes and network selections are reviewed, not loaded remotely.
ANUBIS_REVISION = "f9801e225c9e7904b74d97cc7109739fe78ef4f3"
CRAWLERS = {
    "googlebot": Crawler(
        r"\+http\://www\.google\.com/bot\.html",
        "https://developers.google.com/crawling/ipranges/common-crawlers.json",
    ),
    "bingbot": Crawler(
        r"\+http\://www\.bing\.com/bingbot\.htm",
        "https://www.bing.com/toolbox/bingbot.json",
    ),
    "applebot": Crawler(
        r"Applebot", "https://search.developer.apple.com/applebot.json"
    ),
    "duckduckbot": Crawler(
        r"DuckDuckBot/[^;\s]+; \(\+http\://duckduckgo\.com/duckduckbot\.html\)",
        "https://duckduckgo.com/duckduckbot.json",
    ),
    "qwantbot": Crawler(
        r"\+https\://help\.qwant\.com/bot/", "https://help.qwant.com/qwantbot.json"
    ),
    "mojeekbot": Crawler(
        r"\+https\://www\.mojeek\.com/bot\.html",
        "https://www.mojeek.com/mojeekbot.json",
    ),
    "marginalia": Crawler(
        r"search\.marginalia\.nu",
        "https://search.marginalia.nu/crawler-ips.txt",
        "text",
    ),
    "commoncrawl": Crawler(r"CCBot", "https://index.commoncrawl.org/ccbot.json"),
    # Archive services deliberately accept browser-like User-Agents.
    "arquivo-pt": Crawler(r".*", "https://arquivo.pt/crawlerips.json"),
    "seznambot": Crawler(
        r"\bSeznamBot/", "https://search.seznam.cz/ipranges/seznambot.json"
    ),
    "kagibot": Crawler(
        r"\+https\://kagi\.com/bot",
        "https://kagi.com/bot",
        "bundled",
        (
            "216.18.205.234/32",
            "35.212.27.76/32",
            "104.254.65.50/32",
            "209.151.156.194/32",
        ),
    ),
    "internet-archive": Crawler(
        r".*",
        "https://github.com/TecharoHQ/anubis/blob/"
        + ANUBIS_REVISION
        + "/data/crawlers/internet-archive.yaml",
        "bundled",
        ("207.241.224.0/20", "208.70.24.0/21", "2620:0:9c0::/48"),
    ),
    "wikimedia-citoid": Crawler(
        r"Citoid/WMF|ZoteroTranslationServer/WMF",
        "https://wikitech.wikimedia.org/wiki/IP_and_AS_allocations",
        "bundled",
        ("208.80.152.0/22", "2620:0:860::/46"),
    ),
}


def public_network(value: str) -> Network:
    """Reject non-public and excessively broad provider ranges."""
    if not isinstance(value, str):
        msg = "Crawler network must be a string"
        raise TypeError(msg)
    network = ip_network(value)
    if (
        not network.is_global
        or network.is_multicast
        or network.prefixlen < (8 if network.version == 4 else 16)
        or (
            network.version == 4
            and any(network.overlaps(block) for block in NONPUBLIC_V4)
        )
    ):
        msg = "Crawler ranges must be public, bounded networks"
        raise ValueError(msg)
    return network


def parse_feed(raw: bytes, crawler: Crawler) -> list[str]:
    """Parse only the supported official formats, without trusting publication dates."""
    if len(raw) > MAX_DOWNLOAD:
        msg = "Crawler snapshot is too large"
        raise ValueError(msg)
    if crawler.format == "text":
        values = [
            line.strip() for line in raw.decode("utf-8").splitlines() if line.strip()
        ]
    else:
        data = json.loads(raw)
        values = [
            item.get("ipv4Prefix") or item["ipv6Prefix"] for item in data["prefixes"]
        ]
    networks = sorted({str(public_network(value)) for value in values})
    if not networks:
        msg = "Empty crawler snapshot"
        raise ValueError(msg)
    return networks
