# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Private staging and background execution of translation uploads."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager, suppress
from html import unescape
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from celery import current_task
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.html import strip_tags
from django.utils.translation import gettext, override

from weblate.auth.models import AuthenticatedHttpRequest, User
from weblate.formats.helpers import NamedBytesIO
from weblate.trans.exceptions import FileParseError, PluralFormsMismatchError
from weblate.trans.models import Translation
from weblate.trans.models.translation import read_translation_upload
from weblate.trans.util import check_upload_method_permissions, get_upload_error_message
from weblate.utils.celery import app, delete_task_metadata, store_task_metadata
from weblate.utils.change_origin import acting_user_context
from weblate.utils.data import data_path
from weblate.utils.errors import report_error
from weblate.utils.files import get_upload_message, remove_tree
from weblate.utils.lock import WeblateLock

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import BinaryIO

    from celery.result import AsyncResult

UPLOAD_EXPIRY = 6 * 3600
UPLOAD_CLEANUP_AGE = 24 * 3600


class UploadRequest(AuthenticatedHttpRequest):
    """In-memory request context for shared upload validation and messages."""

    def __init__(self, user: User) -> None:
        super().__init__()
        self.user = user
        self.session = SessionStore()
        self._messages = FallbackStorage(self)


def upload_directory(upload_id: str) -> Path:
    """Resolve only generated identifiers inside the private staging directory."""
    if str(UUID(upload_id)) != upload_id:
        msg = "Invalid upload identifier"
        raise ValueError(msg)
    return data_path("translation-uploads") / upload_id


@contextmanager
def upload_lock(upload_id: str) -> Generator[None, None, None]:
    # File locks have no lease expiry and are released if a worker dies. All
    # workers already need the shared staging filesystem to read the payload.
    # NFS requires a writable descriptor for exclusive locks. Open the existing
    # payload without truncating it or recreating a cleaned-up upload.
    with (upload_directory(upload_id) / "file").open("r+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def browser_upload_key(user_id: int) -> str:
    return f"browser-translation-upload-{user_id}"


def browser_upload_lock(user_id: int) -> WeblateLock:
    return WeblateLock(
        scope="browser-upload", key=user_id, slug=str(user_id), timeout=10
    )


def release_browser_upload(user_id: int, upload_id: str) -> None:
    with browser_upload_lock(user_id):
        key = browser_upload_key(user_id)
        if cache.get(key) == upload_id:
            cache.delete(key)


def reserve_browser_upload(user_id: int, upload_id: str) -> None:
    with browser_upload_lock(user_id):
        key = browser_upload_key(user_id)
        if cache.get(key):
            raise ValidationError(
                gettext("A translation upload is already in progress.")
            )
        cache.set(key, upload_id, timeout=None)


def stage_upload(
    temporary: Path,
    directory: Path,
    translation: Translation,
    user: User,
    fileobj: BinaryIO,
    options: dict[str, Any],
    *,
    browser: bool,
) -> None:
    content = read_translation_upload(fileobj)
    with (temporary / "file").open("xb") as handle:
        os.chmod(handle.name, 0o600)
        handle.write(content)
    metadata = {
        "user_id": user.pk,
        "translation_id": translation.pk,
        "filename": Path(fileobj.name).name,
        "options": options,
        "browser": browser,
    }
    (temporary / "metadata.json").write_text(json.dumps(metadata))
    temporary.rename(directory)


def queue_translation_upload(
    translation: Translation,
    user: User,
    fileobj: BinaryIO,
    options: dict[str, Any],
    *,
    browser: bool = False,
) -> AsyncResult:
    """Stage bounded input and publish a task without serializing file contents."""
    upload_id = str(uuid4())
    directory = upload_directory(upload_id)
    directory.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Install the complete directory atomically; abandoned temporary directories
    # are covered by the same age-based cleanup as published jobs.
    temporary = Path(tempfile.mkdtemp(prefix=".staging-", dir=directory.parent))
    try:
        stage_upload(
            temporary, directory, translation, user, fileobj, options, browser=browser
        )
        if browser:
            reserve_browser_upload(user.pk, upload_id)
        store_task_metadata(
            upload_id,
            user_id=user.pk,
            task_kind="translation-upload",
            cancellable=False,
        )
        with acting_user_context(user):
            return translation_upload.apply_async(
                kwargs={"upload_id": upload_id},
                task_id=upload_id,
                expires=UPLOAD_EXPIRY,
            )
    except BaseException:
        if browser:
            release_browser_upload(user.pk, upload_id)
        delete_task_metadata(upload_id)
        remove_tree(directory)
        raise
    finally:
        fileobj.close()
        remove_tree(temporary)


def upload_progress(progress: int) -> None:
    if current_task and current_task.request.id:
        current_task.update_state(state="PROGRESS", meta={"progress": progress})


def upload_merge_progress(done: int, total: int) -> None:
    upload_progress(10 + (85 * done // total if total else 85))


@app.task(trail=False, store_eager_result=True)
def translation_upload(*, upload_id: str) -> dict[str, Any]:
    """Execute once with fresh permissions and the original initiating actor."""
    directory = upload_directory(upload_id)
    if not directory.exists():
        return expired_upload_result()
    with upload_lock(upload_id):
        # A duplicate delivery after cleanup must never repeat a repository edit.
        if not directory.exists():
            return expired_upload_result()
        metadata = json.loads((directory / "metadata.json").read_text())
        try:
            store_task_metadata(
                upload_id,
                user_id=metadata["user_id"],
                task_kind="translation-upload",
                cancellable=False,
            )
            user = User.objects.get(pk=metadata["user_id"])
            with override(user.profile.language), acting_user_context(user):
                return perform_translation_upload(directory, metadata, user)
        finally:
            try:
                if metadata["browser"]:
                    release_browser_upload(metadata["user_id"], upload_id)
            finally:
                remove_tree(directory)


def expired_upload_result() -> dict[str, Any]:
    message = gettext("The uploaded file has expired or was already processed.")
    return {
        "detail": message,
        "completion_message": {"text": message, "level": "error"},
    }


def get_upload_translation(
    directory: Path, metadata: dict[str, Any], user: User
) -> Translation:
    if time.time() - directory.stat().st_mtime > UPLOAD_EXPIRY:
        raise ValidationError(gettext("The uploaded file has expired."))
    translation = Translation.objects.filter_access(user).get(
        pk=metadata["translation_id"]
    )
    options = metadata["options"]
    if (
        not user.is_authenticated
        or not user.is_active
        or translation.component.locked
        or not user.has_perm("upload.perform", translation)
        or not check_upload_method_permissions(user, translation, options["method"])
    ):
        raise PermissionDenied
    if options["conflicts"] and not user.has_perm("upload.overwrite", translation):
        raise PermissionDenied
    if options["conflicts"] == "replace-approved" and not user.has_perm(
        "unit.review", translation
    ):
        raise PermissionDenied
    if (
        options.get("author_name") or options.get("author_email")
    ) and not user.has_perm("upload.authorship", translation):
        raise PermissionDenied
    return translation


def perform_translation_upload(
    directory: Path, metadata: dict[str, Any], user: User
) -> dict[str, Any]:
    translation = None
    # ruff: ignore[too-many-statements-in-try-clause]
    try:
        upload_progress(0)
        translation = get_upload_translation(directory, metadata, user)
        request = UploadRequest(user)
        upload_progress(10)
        result = translation.handle_upload(
            request,
            NamedBytesIO(metadata["filename"], (directory / "file").read_bytes()),
            progress=upload_merge_progress,
            **metadata["options"],
        )
        not_found, skipped, accepted, total = result
        message = get_upload_message(*result)
        warnings = [unescape(strip_tags(str(entry))) for entry in get_messages(request)]
        upload_progress(100)
        return {
            "not_found": not_found,
            "skipped": skipped,
            "accepted": accepted,
            "total": total,
            "result": accepted > 0,
            "count": total,
            "upload_warnings": warnings,
            "completion_message": {
                "text": " ".join([*warnings, str(message)]),
                "level": "success" if accepted else "warning",
            },
        }
    except Exception as error:
        if isinstance(error, PermissionDenied | Translation.DoesNotExist):
            message = gettext("The upload target or permissions changed.")
        elif isinstance(error, PluralFormsMismatchError):
            message = gettext(
                "Plural forms in the uploaded file do not match current translation."
            )
        elif isinstance(error, ValidationError):
            message = "; ".join(error.messages)
        else:
            if translation is not None:
                message = get_upload_error_message(
                    error,
                    repo_urls=(translation.component.repo, translation.component.push),
                    extra_paths=(translation.component.full_path, directory),
                )
            else:
                message = gettext("File upload has failed. Please try again later.")
            if not isinstance(error, ValidationError | FileParseError):
                report_error(
                    "Upload error",
                    project=translation.component.project if translation else None,
                )
        return {
            "detail": str(message),
            "completion_message": {"text": str(message), "level": "error"},
        }


@app.task(trail=False)
def cleanup_translation_uploads() -> None:
    """Remove expired jobs and interrupted staging without touching active work."""
    root = data_path("translation-uploads")
    if not root.exists():
        return
    cutoff = time.time() - UPLOAD_CLEANUP_AGE
    for directory in root.iterdir():
        if not directory.is_dir() or directory.stat().st_mtime >= cutoff:
            continue
        if directory.name.startswith(".staging-"):
            remove_tree(directory)
            continue
        with suppress(BlockingIOError, FileNotFoundError), upload_lock(directory.name):
            metadata = json.loads((directory / "metadata.json").read_text())
            try:
                if metadata["browser"]:
                    release_browser_upload(metadata["user_id"], directory.name)
            finally:
                remove_tree(directory)
