# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import logging
import os
import re
import traceback
from typing import TYPE_CHECKING, Protocol

import sentry_sdk

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

LOGGER = logging.getLogger(__name__)

UNKNOWN = "unknown"
MAX_INPUT_ATTACHMENT_BYTES = 1024 * 1024

_STATE = {"initialized": False}
_ATTACHMENT_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class AttachmentScope(Protocol):
    def add_attachment(self, **kwargs: object) -> None: ...


def _run_url(environ: Mapping[str, str]) -> str:
    repository = environ.get("GITHUB_REPOSITORY", "")
    run_id = environ.get("GITHUB_RUN_ID", "")
    if not repository or not run_id:
        return ""
    server_url = environ.get("GITHUB_SERVER_URL", "https://github.com")
    return f"{server_url}/{repository}/actions/runs/{run_id}"


def _environment(environ: Mapping[str, str]) -> str:
    return (
        environ.get("SENTRY_ENVIRONMENT")
        or f"fuzzing-{environ.get('CFLITE_MODE', 'batch')}"
    )


def init_sentry(environ: Mapping[str, str] | None = None) -> bool:
    environ = os.environ if environ is None else environ
    if _STATE["initialized"]:
        return True

    dsn = environ.get("SENTRY_DSN")
    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        release=environ.get("GITHUB_SHA") or None,
        environment=_environment(environ),
        default_integrations=False,
        auto_enabling_integrations=False,
        send_default_pii=False,
        attach_stacktrace=True,
        include_local_variables=False,
    )
    _STATE["initialized"] = True
    return True


def _top_frame(error: Exception) -> str:
    frames = traceback.extract_tb(error.__traceback__)
    if not frames:
        return UNKNOWN

    frame = frames[-1]
    return f"{frame.filename}:{frame.lineno}:{frame.name}"


def _exception_type(error: Exception) -> str:
    error_type = type(error)
    return f"{error_type.__module__}.{error_type.__name__}"


def _input_context(target_name: str, data: bytes) -> dict[str, object]:
    attachment_data = data[:MAX_INPUT_ATTACHMENT_BYTES]
    return {
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "attachment_filename": _attachment_filename(target_name),
        "attachment_size": len(attachment_data),
        "attachment_sha256": hashlib.sha256(attachment_data).hexdigest(),
        "attachment_truncated": len(attachment_data) != len(data),
        "attachment_limit": MAX_INPUT_ATTACHMENT_BYTES,
    }


def _attachment_filename(target_name: str) -> str:
    normalized_target = _ATTACHMENT_FILENAME_RE.sub("-", target_name).strip("-.")
    if not normalized_target:
        normalized_target = UNKNOWN
    return f"fuzz-input-{normalized_target}.bin"


def _attach_fuzz_input(scope: AttachmentScope, target_name: str, data: bytes) -> None:
    scope.add_attachment(
        bytes=data[:MAX_INPUT_ATTACHMENT_BYTES],
        filename=_attachment_filename(target_name),
        content_type="application/octet-stream",
    )


def _github_context(environ: Mapping[str, str]) -> dict[str, str]:
    return {
        "repository": environ.get("GITHUB_REPOSITORY", ""),
        "workflow": environ.get("GITHUB_WORKFLOW", ""),
        "run_id": environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": environ.get("GITHUB_RUN_ATTEMPT", ""),
        "sha": environ.get("GITHUB_SHA", ""),
        "run_url": _run_url(environ),
    }


def _clusterfuzzlite_context(
    target_name: str, error: Exception, environ: Mapping[str, str]
) -> dict[str, str]:
    return {
        "source": "direct",
        "mode": environ.get("CFLITE_MODE", "batch"),
        "sanitizer": environ.get("SANITIZER", "address"),
        "target": target_name,
        "exception_type": _exception_type(error),
        "top_frame": _top_frame(error),
    }


def capture_fuzz_exception(
    target_name: str,
    data: bytes,
    error: Exception,
    environ: Mapping[str, str] | None = None,
) -> None:
    environ = os.environ if environ is None else environ
    if not init_sentry(environ):
        return

    sanitizer = environ.get("SANITIZER", "address")
    exception_type = _exception_type(error)
    top_frame = _top_frame(error)

    with sentry_sdk.new_scope() as scope:
        _attach_fuzz_input(scope, target_name, data)
        sentry_sdk.capture_exception(
            error,
            fingerprint=[
                "clusterfuzzlite",
                sanitizer,
                target_name,
                exception_type,
                top_frame,
            ],
            tags={
                "source": "clusterfuzzlite",
                "mode": environ.get("CFLITE_MODE", "batch"),
                "sanitizer": sanitizer,
                "target": target_name,
                "workflow": environ.get("GITHUB_WORKFLOW", ""),
                "run_id": environ.get("GITHUB_RUN_ID", ""),
                "run_attempt": environ.get("GITHUB_RUN_ATTEMPT", ""),
                "sha": environ.get("GITHUB_SHA", ""),
            },
            contexts={
                "clusterfuzzlite": _clusterfuzzlite_context(
                    target_name, error, environ
                ),
                "fuzz_input": _input_context(target_name, data),
                "github_actions": _github_context(environ),
            },
        )
    sentry_sdk.flush(timeout=10)


def wrap_target(
    target_name: str, callback: Callable[[bytes], None]
) -> Callable[[bytes], None]:
    def wrapped(data: bytes) -> None:
        try:
            callback(data)
        except Exception as error:
            try:
                capture_fuzz_exception(target_name, data, error)
            except Exception as reporting_error:
                LOGGER.warning(
                    "Could not report fuzz exception to Sentry: %s", reporting_error
                )
            raise

    return wrapped
