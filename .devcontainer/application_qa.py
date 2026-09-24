# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exercise real HTTP requests, workers, repositories, and SMTP in the app profile."""

from __future__ import annotations

import json
import time
from io import BytesIO
from typing import TYPE_CHECKING
from uuid import uuid4
from zipfile import ZipFile

if TYPE_CHECKING:
    from collections.abc import Callable


def wait_for[T](description: str, probe: Callable[[], T], timeout: float = 180) -> T:
    deadline = time.monotonic() + timeout
    while True:
        result = probe()
        if result:
            print(f"PASS: {description}", flush=True)
            return result
        if time.monotonic() >= deadline:
            msg = f"Timed out after {timeout}s: {description}"
            raise TimeoutError(msg)
        time.sleep(0.2)


def fixture_archive() -> bytes:
    result = BytesIO()
    with ZipFile(result, "w") as archive:
        archive.writestr(
            "cs.po",
            'msgid ""\nmsgstr ""\n'
            '"Content-Type: text/plain; charset=UTF-8\\n"\n'
            '"Language: cs\\n"\n'
            '"Plural-Forms: nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;\\n"\n'
            '\nmsgid "Hello Celery"\nmsgstr ""\n',
        )
    return result.getvalue()


def verify_export(content: bytes, target: str) -> None:
    with ZipFile(BytesIO(content)) as archive:
        if not any(
            target in archive.read(name).decode()
            for name in archive.namelist()
            if name.endswith("cs.po")
        ):
            msg = "Export does not contain the saved translation"
            raise RuntimeError(msg)
    print("PASS: exported archive contains translation", flush=True)


def translated_in_page(content: bytes) -> bool:
    from lxml.html import fromstring  # ruff: ignore[import-outside-top-level]

    cells = fromstring(content).xpath("//tr[th[normalize-space()='Translated']]/td[2]")
    return bool(cells and cells[0].text_content().strip() == "1")


def run() -> None:
    # Imports follow django.setup() in main so polling/fixture tests need no database.
    from django.conf import settings  # ruff: ignore[import-outside-top-level]
    from django.db import transaction  # ruff: ignore[import-outside-top-level]
    from requests import Session  # ruff: ignore[import-outside-top-level]

    from weblate.accounts.models import Subscription  # ruff: ignore[import-outside-top-level]
    from weblate.accounts.notifications import (  # ruff: ignore[import-outside-top-level]
        NotificationFrequency,
        NotificationScope,
    )
    from weblate.auth.models import User  # ruff: ignore[import-outside-top-level]
    from weblate.lang.models import Language  # ruff: ignore[import-outside-top-level]
    from weblate.memory.models import Memory  # ruff: ignore[import-outside-top-level]
    from weblate.trans.models import Component, Project  # ruff: ignore[import-outside-top-level]
    from weblate.trans.tasks import update_enforced_checks  # ruff: ignore[import-outside-top-level]
    from weblate.utils.celery import app  # ruff: ignore[import-outside-top-level]

    if settings.CELERY_TASK_ALWAYS_EAGER or not app.conf.broker_url.startswith(
        "redis://"
    ):
        msg = "Application QA requires non-eager Celery and the real Valkey broker"
        raise RuntimeError(msg)
    if settings.EMAIL_HOST != "maildev":
        msg = "Application QA requires Maildev"
        raise RuntimeError(msg)

    slug = f"celery-qa-{uuid4().hex[:12]}"
    target = f"Ahoj Celery {slug}"
    recipient = f"{slug}@example.com"
    print(f"QA fixture: {slug}", flush=True)
    tasks = []
    session = Session()
    # Use the application profile's existing development administrator.
    session.headers["Authorization"] = (
        f"Token {User.objects.get(username='admin').auth_token.key}"
    )
    mailbox = Session()
    session.headers["Host"] = settings.SITE_DOMAIN
    session.headers["Accept-Language"] = "en"

    def request(method: str, path: str, status: int = 200, **kwargs):
        # Generated API URLs carry the published host port; requests originate
        # inside the app container, so use the internal listener instead.
        from urllib.parse import urlsplit  # ruff: ignore[import-outside-top-level]

        parsed = urlsplit(path)
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        response = session.request(
            method, f"http://127.0.0.1:8080{path}", timeout=30, **kwargs
        )
        if response.status_code != status:
            msg = f"{method} {path}: {response.status_code}: {response.text[:2000]}"
            raise RuntimeError(msg)
        return response

    def task_result(task_id: str, expected: str = "SUCCESS") -> bool:
        task = app.AsyncResult(task_id)
        if task.state in {"FAILURE", "REVOKED"}:
            msg = (
                f"Worker task {task_id}: {task.state}: {task.result}\n{task.traceback}"
            )
            raise RuntimeError(msg)
        return task.state == expected

    def finish(task_url: str) -> None:
        task_id = task_url.rstrip("/").rsplit("/", 1)[-1]
        tasks.append(task_id)
        wait_for(f"worker task {task_id}", lambda: task_result(task_id))
        result = request("GET", task_url).json()
        if not result["completed"]:
            msg = f"Task completion not visible over HTTP: {result}"
            raise RuntimeError(msg)

    try:
        request(
            "POST",
            "/api/projects/",
            201,
            json={"name": slug, "slug": slug, "web": "https://example.com/"},
        )
        imported = request(
            "POST",
            f"/api/projects/{slug}/components/",
            201,
            data={
                "name": "Messages",
                "slug": "messages",
                "filemask": "*.po",
                "file_format": "po",
                "new_lang": "none",
            },
            files={"zipfile": ("messages.zip", fixture_archive(), "application/zip")},
        ).json()
        component = Component.objects.get(project__slug=slug, slug="messages")
        # A fast worker can finish before the response serializer runs, in which
        # case task_url is null. The component cache still records the task ID.
        task_url = imported["task_url"] or (
            f"/api/tasks/{component.background_task_id}/"
            if component.background_task_id
            else None
        )
        if not task_url:
            msg = "Component import did not schedule a worker task"
            raise RuntimeError(msg)
        finish(task_url)
        translation_url = f"/api/translations/{slug}/messages/cs/"
        translation = wait_for(
            "imported strings visible through HTTP",
            lambda: (
                data
                if (data := request("GET", translation_url).json())["total"] == 1
                else {}
            ),
        )
        component = Component.objects.get(project__slug=slug, slug="messages")
        watcher = User.objects.create_user(username=slug, email=recipient)
        watcher.profile.languages.add(Language.objects.get(code="cs"))
        Subscription.objects.create(
            user=watcher,
            component=component,
            notification="TranslatedStringNotificaton",
            scope=NotificationScope.SCOPE_COMPONENT,
            frequency=NotificationFrequency.FREQ_INSTANT,
        )
        unit = request("GET", translation["units_list_url"]).json()["results"][0]
        request("PATCH", unit["url"], json={"target": [target], "state": 20})
        wait_for(
            "translated count visible through HTTP",
            lambda: request("GET", translation_url).json()["translated"] == 1,
        )
        wait_for(
            "translated count visible on application page",
            lambda: translated_in_page(request("GET", translation["web_url"]).content),
        )
        queued = request(
            "POST",
            imported["repository_url"],
            202,
            json={"operation": "commit", "background": True},
        ).json()
        finish(queued["task_url"])
        # Inspect the committed Git object, not just a dirty working-tree file.
        committed = component.repository.get_file("cs.po", "HEAD")
        if target not in committed:
            msg = f"Translation is absent from committed repository: {committed}"
            raise RuntimeError(msg)
        print("PASS: translation committed to Git", flush=True)
        exported = request("GET", f"/api/components/{slug}/messages/file/?format=zip")
        verify_export(exported.content, target)
        wait_for(
            "translation memory worker stored translation",
            lambda: Memory.objects.filter(
                source="Hello Celery", target=target
            ).exists(),
        )

        def delivered() -> bool:
            response = mailbox.get("http://maildev:1080/email", timeout=10)
            response.raise_for_status()
            for message in response.json():
                if any(address["address"] == recipient for address in message["to"]):
                    detail = mailbox.get(
                        f"http://maildev:1080/email/{message['id']}", timeout=10
                    )
                    detail.raise_for_status()
                    if target in detail.json().get("text", ""):
                        return True
            return False

        wait_for("translation notification delivered to Maildev", delivered)

        # Deliberately enqueue a real task before its fixture row is committed.
        # This tests retry/redelivery after a visibility race, without changing
        # worker settings or registering a synthetic worker task.
        with transaction.atomic():
            retry_component = Component(
                project=Project.objects.get(slug=slug),
                name="Retry visibility",
                slug="retry",
                repo="local:",
                vcs="local",
                filemask="*.po",
                file_format="po",
                source_language=Language.objects.get(code="en"),
            )
            # Only the row is needed by update_enforced_checks. Avoid scheduling
            # an unrelated repository import for this transaction-only fixture.
            Component.objects.bulk_create([retry_component])
            retry = update_enforced_checks.delay(retry_component.pk)
            tasks.append(retry.id)
            wait_for(
                "worker retries an uncommitted row",
                lambda: task_result(retry.id, "RETRY"),
            )
        wait_for(
            "retried task succeeds after commit",
            lambda: task_result(retry.id),
            timeout=300,
        )
        print(f"PASS: application QA journeys ({slug})", flush=True)
    finally:
        for task_id in tasks:
            task = app.AsyncResult(task_id)
            print(
                json.dumps(
                    {
                        "task": task_id,
                        "state": task.state,
                        "result": str(task.result),
                        "traceback": task.traceback,
                    }
                ),
                flush=True,
            )
        session.close()
        mailbox.close()


def main() -> None:
    import django  # ruff: ignore[import-outside-top-level]

    django.setup()
    run()


if __name__ == "__main__":
    main()
