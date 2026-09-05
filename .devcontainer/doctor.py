# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check the container's test environment without resetting any state."""

# This standalone diagnostic intentionally executes tools from the container PATH.

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryFile
from threading import Thread

import django
from django.conf import settings
from django.db import connection
from redis import Redis
from redis.exceptions import RedisError

import weblate
from weblate.trans.tests.browser import create_browser


def wait_for_services(cache: Redis) -> None:
    connection.settings_dict.setdefault("OPTIONS", {})["connect_timeout"] = 2
    deadline = time.monotonic() + 60
    while True:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            cache.ping()
            break
        except (django.db.DatabaseError, RedisError):
            connection.close()
            if time.monotonic() >= deadline:
                sys.exit(
                    "PostgreSQL or Valkey is unavailable after 60 seconds; inspect Compose logs."
                )
            time.sleep(1)


class BrowserPage(BaseHTTPRequestHandler):
    """Serve only a fixed diagnostic page, without exposing checkout files."""

    def do_GET(self) -> None:
        body = (
            b"<!doctype html><title>Weblate browser check</title>"
            b'<p id="result">Loading</p><script>'
            b'document.getElementById("result").textContent = "Ready";</script>'
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        pass


def check_browser() -> None:
    with ThreadingHTTPServer(("127.0.0.1", 0), BrowserPage) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with create_browser() as browser:
                browser.set_page_load_timeout(30)
                browser.set_script_timeout(30)
                browser.get(f"http://127.0.0.1:{server.server_port}/")
                if (
                    browser.title != "Weblate browser check"
                    or browser.execute_script(
                        'return document.getElementById("result").textContent'
                    )
                    != "Ready"
                ):
                    msg = "Browser failed to load the page and execute JavaScript"
                    raise RuntimeError(msg)
                capabilities = browser.capabilities
                print(
                    f"Browser: {capabilities['browserVersion']}; "
                    f"driver: {capabilities['chrome']['chromedriverVersion']}"
                )
        finally:
            server.shutdown()
            thread.join()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--services-only", action="store_true")
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    django.setup()
    cache = Redis(
        host=os.environ["CI_REDIS_HOST"],
        port=int(os.environ["CI_REDIS_PORT"]),
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    wait_for_services(cache)
    print(
        f"PostgreSQL: {settings.DATABASES['default']['HOST']} / {connection.settings_dict['NAME']}"
    )
    print(
        f"Valkey: {os.environ['CI_REDIS_HOST']}:{os.environ['CI_REDIS_PORT']} reachable"
    )
    if args.services_only:
        return
    root = Path(__file__).resolve().parent.parent
    imported = Path(weblate.__file__).resolve().parent
    if imported != root / "weblate":
        sys.exit(f"Wrong Weblate import: {imported}; expected {root / 'weblate'}")
    print(f"Checkout: {root}\nPython: {sys.executable}\nWeblate: {imported}")
    for flag in ("HEAD", "--git-common-dir"):
        subprocess.run(["git", "rev-parse", flag], cwd=root, check=True)
    for directory in (
        settings.DATA_DIR,
        settings.STATIC_ROOT,
        os.environ["UV_PROJECT_ENVIRONMENT"],
    ):
        path = Path(directory)
        if not path.is_dir():
            sys.exit(f"Missing directory: {path}; rerun bootstrap")
        with TemporaryFile(dir=path):
            pass
        print(f"Writable: {path}")
    if not any(Path(settings.STATIC_ROOT).iterdir()):
        sys.exit("Static assets are missing; rerun bootstrap")
    if not any((root / "weblate/locale").glob("*/LC_MESSAGES/django.mo")):
        sys.exit("Compiled translations are missing; rerun bootstrap")
    subprocess.run(["uv", "pip", "check"], check=True)
    if args.browser:
        check_browser()
    print("Ready for pytest and lint. Test database migrations are applied by pytest.")


if __name__ == "__main__":
    main()
