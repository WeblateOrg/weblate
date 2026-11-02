#!/usr/bin/env python3
# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
HTTP benchmark against a disposable HTTPS Weblate instance with PoW enabled.

Cookie files contain a raw Cookie header copied from a browser (keep private).
Pass all server worker PIDs to measure combined CPU and resident memory on Linux.
Run against a representative public page, with proxy caching disabled.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def resources(pids: list[int]) -> tuple[float, int]:
    cpu = 0.0
    rss = 0
    for pid in pids:
        # Skip the parenthesized process name, which can contain whitespace.
        fields = (
            Path(f"/proc/{pid}/stat")
            .read_text(encoding="utf-8")
            .rsplit(")", 1)[1]
            .split()
        )
        cpu += (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")
        rss += int(fields[21]) * os.sysconf("SC_PAGE_SIZE")
    return cpu, rss


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--authenticated-cookie-file", type=Path, required=True)
    parser.add_argument("--clearance-cookie-file", type=Path, required=True)
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--server-pid", type=int, action="append", default=[])
    args = parser.parse_args()
    if urlsplit(args.url).scheme != "https":
        parser.error("Use an HTTPS test deployment")
    cases = {
        "authenticated": args.authenticated_cookie_file.read_text(
            encoding="utf-8"
        ).strip(),
        "clearance": args.clearance_cookie_file.read_text(encoding="utf-8").strip(),
        "new-anonymous": "",
        "repeated-unsolved": "",
    }
    for concurrency in (1, 32, 128):
        for name, cookie in cases.items():

            def fetch(
                index: int, cookie: str = cookie, name: str = name
            ) -> tuple[float, int]:
                headers = {"Accept": "text/html", "Cookie": cookie}
                # Separate client state; no application sessions are created.
                if name == "new-anonymous":
                    headers["Cookie"] = f"benchmark_client={index}"
                started = time.perf_counter()
                try:
                    with urlopen(  # ruff: ignore[suspicious-url-open-usage]
                        Request(args.url, headers=headers),  # ruff: ignore[suspicious-url-open-usage]
                        timeout=30,
                    ) as response:
                        response.read()
                        status = response.status
                except HTTPError as error:
                    error.read()
                    status = error.code
                return time.perf_counter() - started, status

            cpu_before, _rss = resources(args.server_pid)
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                results = list(pool.map(fetch, range(args.requests)))
            elapsed = time.perf_counter() - started
            cpu_after, rss = resources(args.server_pid)
            latencies = sorted(item[0] for item in results)
            print(
                json.dumps(
                    {
                        "case": name,
                        "concurrency": concurrency,
                        "rps": args.requests / elapsed,
                        "cpu_seconds": cpu_after - cpu_before,
                        "rss_bytes": rss,
                        "latency_ms": {
                            str(p): latencies[
                                min(len(latencies) - 1, int(len(latencies) * p / 100))
                            ]
                            * 1000
                            for p in (50, 95, 99)
                        },
                        "statuses": {
                            str(status): sum(item[1] == status for item in results)
                            for status in {item[1] for item in results}
                        },
                    }
                )
            )


if __name__ == "__main__":
    main()
