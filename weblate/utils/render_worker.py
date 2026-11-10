# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Render untrusted templates without application settings or model instances."""

from __future__ import annotations

import json
import sys

SOURCE_LIMIT = 64 * 1024
LOOP_LIMIT = 10_000
OUTPUT_LIMIT = 1024 * 1024
CONTEXT_LIMIT = 8 * 1024 * 1024
DEPTH_LIMIT = 32
RENDER_TIMEOUT = 5
MEMORY_LIMIT = 512 * 1024 * 1024
ERROR_LIMIT = 4096


def main() -> None:
    import resource  # ruff: ignore[import-outside-top-level]

    if sys.platform != "darwin":
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (RENDER_TIMEOUT,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        response = render_request()
    except Exception as error:
        response = {"error": str(error)[:ERROR_LIMIT] or type(error).__name__}
    sys.stdout.write(json.dumps(response, ensure_ascii=False))


def render_request() -> dict[str, str]:
    from django.conf import settings  # ruff: ignore[import-outside-top-level]

    request = json.loads(sys.stdin.buffer.read(CONTEXT_LIMIT + SOURCE_LIMIT * 6 + 1))
    settings.configure(
        USE_I18N=False,
        LANGUAGE_CODE="en",
        USE_TZ=request["use_tz"],
        TIME_ZONE=request["time_zone"],
        USE_THOUSAND_SEPARATOR=request["thousands"],
    )
    # Import only after process limits and minimal Django settings are installed.
    from weblate.utils.render_engine import (  # ruff: ignore[import-outside-top-level]
        decode_value,
        render_bounded,
    )

    return {
        "text": render_bounded(request["template"], decode_value(request["context"]))
    }


if __name__ == "__main__":
    main()
