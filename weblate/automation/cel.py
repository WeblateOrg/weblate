# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Resource-limited CEL helper. Executed directly, without initializing Django."""

from __future__ import annotations

import json
import resource
import sys


def main() -> None:
    # macOS can already exceed this address-space limit at interpreter startup.
    if sys.platform != "darwin":
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        response = evaluate_request()
    except Exception as error:
        response = {"error": str(error)[:4096]}
    sys.stdout.write(json.dumps(response))


def evaluate_request() -> dict:
    # Import the native runtime only after main has applied resource limits.
    # The upstream wheel provides stubs but no py.typed marker.
    from cel_expr_python import cel  # type: ignore[import-untyped]  # ruff: ignore[import-outside-top-level]

    request = json.loads(sys.stdin.buffer.read(1024 * 1024 + 1))
    environment = cel.NewEnv(
        variables=dict.fromkeys(
            ("component", "language", "unit", "change", "actor", "trigger", "results"),
            cel.Type.DYN,
        )
    )
    results = []
    for source in request["expressions"]:
        expression = environment.compile(source)
        if expression.return_type().name() not in {"BOOL", "DYN"}:
            msg = "A condition must return a boolean."
            raise ValueError(msg)
        if request.get("context") is not None:
            value = expression.eval(data=request["context"])
            if value.type() != cel.Type.BOOL:
                msg = "A condition must return a boolean."
                raise ValueError(msg)
            results.append(value.value())
    return {"results": results}


if __name__ == "__main__":
    main()
