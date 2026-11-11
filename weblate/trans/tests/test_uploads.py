# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Regression coverage for bounded and background translation uploads."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest.mock import Mock, PropertyMock, patch

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from weblate.auth.models import Group, Permission, Role, User, get_anonymous
from weblate.auth.permissions import check_permission
from weblate.formats.helpers import NamedBytesIO
from weblate.formats.ttkit import PoFormat
from weblate.trans.actions import ActionEvents
from weblate.trans.exceptions import FileParseError
from weblate.trans.models import Change, Component, Translation
from weblate.trans.models.translation import UploadNotFoundLog
from weblate.trans.tests.test_files import TEST_PO, ImportBaseTest
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.uploads import (
    UPLOAD_CLEANUP_AGE,
    UPLOAD_EXPIRY,
    browser_upload_key,
    cleanup_translation_uploads,
    queue_translation_upload,
    translation_upload,
    upload_directory,
    upload_lock,
)
from weblate.utils.celery import get_task_metadata
from weblate.utils.change_origin import change_origin_context


class UploadNotFoundLogTest(SimpleTestCase):
    def test_counts_all_strings_and_retains_eight_examples(self) -> None:
        log = UploadNotFoundLog()
        for index in range(30):
            log.append(str(index))
        self.assertEqual(len(log), 30)
        self.assertEqual(log.strings, [str(index) for index in range(8)])


class BackgroundUploadTest(ImportBaseTest):
    def setUp(self) -> None:
        super().setUp()
        directory = self.enterContext(TemporaryDirectory())  # pylint: disable=consider-using-with
        self.upload_root = Path(directory)
        self.enterContext(
            patch(
                "weblate.trans.uploads.data_path",
                side_effect=lambda component: self.upload_root / component,
            )
        )
        self.options = {
            "method": "suggest",
            "conflicts": "",
            "fuzzy": "",
            "ignore_language": False,
        }

    def stage(self, *, browser: bool = False, user: User | None = None) -> str:
        with patch.object(translation_upload, "apply_async") as publish:
            queue_translation_upload(
                self.translation,
                user if user is not None else self.user,
                NamedBytesIO("test.po", Path(TEST_PO).read_bytes()),
                self.options,
                browser=browser,
            )
        return publish.call_args.kwargs["task_id"]

    def test_private_staging_and_metadata(self) -> None:
        upload_id = self.stage()
        directory = upload_directory(upload_id)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual((directory / "file").stat().st_mode & 0o777, 0o600)
        self.assertEqual((directory / "file").read_bytes(), Path(TEST_PO).read_bytes())
        metadata = get_task_metadata(upload_id) or {}
        self.assertEqual(metadata["user_id"], self.user.pk)
        self.assertFalse(metadata["cancellable"])
        self.assertIsNone(metadata.get("translation_id"))

    def test_browser_reservation_does_not_restrict_api(self) -> None:
        upload_id = self.stage(browser=True)
        with self.assertRaisesMessage(ValidationError, "already in progress"):
            self.stage(browser=True)
        self.assertEqual(cache.get(browser_upload_key(self.user.pk)), upload_id)
        api_id = self.stage()
        self.assertNotEqual(api_id, upload_id)
        self.assertEqual(len(list(upload_directory(api_id).parent.iterdir())), 2)

    def test_publication_failure_removes_file_and_reservation(self) -> None:
        with (
            patch.object(translation_upload, "apply_async", side_effect=RuntimeError),
            self.assertRaises(RuntimeError),
        ):
            queue_translation_upload(
                self.translation,
                self.user,
                NamedBytesIO("test.po", b"data"),
                self.options,
                browser=True,
            )
        self.assertIsNone(cache.get(browser_upload_key(self.user.pk)))
        self.assertEqual(list((self.upload_root / "translation-uploads").iterdir()), [])

    def test_worker_preserves_actor_and_origin(self) -> None:
        upload_id = self.stage(browser=True)
        with change_origin_context({"scope": "api"}):
            result = translation_upload.run(upload_id=upload_id)
        self.assertGreater(result["accepted"], 0)
        change = Change.objects.get(
            translation=self.translation, action=ActionEvents.FILE_UPLOAD
        )
        self.assertEqual(change.user, self.user)
        self.assertEqual(change.author, self.user)
        self.assertEqual(change.details["change_origin"], {"scope": "api"})
        self.assertFalse(upload_directory(upload_id).exists())
        self.assertIsNone(cache.get(browser_upload_key(self.user.pk)))
        with patch.object(Translation, "handle_upload") as handle:
            translation_upload.run(upload_id=upload_id)
        handle.assert_not_called()

    def test_worker_keeps_initiator_separate_from_author(self) -> None:
        author = User.objects.create_user(
            "upload-author", "upload-author@example.org", full_name="Upload Author"
        )
        self.options.update(author_name=author.full_name, author_email=author.email)
        upload_id = self.stage()
        result = translation_upload.run(upload_id=upload_id)
        self.assertGreater(result["accepted"], 0)
        change = Change.objects.get(
            translation=self.translation, action=ActionEvents.FILE_UPLOAD
        )
        self.assertEqual(change.user, self.user)
        self.assertEqual(change.author, author)

    def test_deleted_target_does_not_process(self) -> None:
        upload_id = self.stage()
        self.translation.delete()
        with patch.object(Translation, "handle_upload") as handle:
            result = translation_upload.run(upload_id=upload_id)
        self.assertEqual(result["completion_message"]["level"], "error")
        handle.assert_not_called()
        self.assertFalse(upload_directory(upload_id).exists())

    def test_worker_dispatches_every_method_and_options(self) -> None:
        for method in (
            "suggest",
            "translate",
            "fuzzy",
            "approve",
            "add",
            "replace",
            "source",
        ):
            with self.subTest(method=method):
                self.options["method"] = method
                upload_id = self.stage()
                with (
                    patch(
                        "weblate.trans.uploads.check_upload_method_permissions",
                        return_value=True,
                    ),
                    patch.object(
                        Translation, "handle_upload", return_value=(0, 0, 1, 1)
                    ) as handle,
                ):
                    result = translation_upload.run(upload_id=upload_id)
                self.assertEqual(result["accepted"], 1)
                options = dict(handle.call_args.kwargs)
                self.assertTrue(callable(options.pop("progress")))
                self.assertEqual(options, self.options)

    def test_revoked_permissions_and_changed_locks(self) -> None:
        for permission_revoked in (True, False):
            with self.subTest(permission_revoked=permission_revoked):
                upload_id = self.stage()
                if permission_revoked:
                    self.user.is_active = False
                    self.user.save()
                else:
                    self.component.locked = True
                    self.component.save()
                with patch.object(Translation, "handle_upload") as handle:
                    result = translation_upload.run(upload_id=upload_id)
                self.assertEqual(result["completion_message"]["level"], "error")
                handle.assert_not_called()
                self.assertFalse(upload_directory(upload_id).exists())
                self.user.is_active = True
                self.user.save()

    def test_expired_job_does_not_process(self) -> None:
        upload_id = self.stage(browser=True)
        directory = upload_directory(upload_id)
        old = time.time() - UPLOAD_EXPIRY - 1
        os.utime(directory, (old, old))
        with patch.object(Translation, "handle_upload") as handle:
            result = translation_upload.run(upload_id=upload_id)
        self.assertIn("expired", result["detail"])
        handle.assert_not_called()
        self.assertFalse(directory.exists())
        self.assertIsNone(cache.get(browser_upload_key(self.user.pk)))

    def test_cleanup_skips_active_upload_and_releases_stale_reservation(self) -> None:
        upload_id = self.stage(browser=True)
        directory = upload_directory(upload_id)
        old = time.time() - UPLOAD_CLEANUP_AGE - 1
        os.utime(directory, (old, old))
        with upload_lock(upload_id):
            cleanup_translation_uploads()
        self.assertTrue(directory.exists())
        cleanup_translation_uploads()
        self.assertFalse(directory.exists())
        self.assertIsNone(cache.get(browser_upload_key(self.user.pk)))

    def test_worker_failure_cleans_staging_and_hides_paths(self) -> None:
        upload_id = self.stage(browser=True)
        directory = upload_directory(upload_id)
        with patch.object(
            Translation, "handle_upload", side_effect=FileParseError(str(directory))
        ):
            result = translation_upload.run(upload_id=upload_id)
        self.assertNotIn(str(directory), result["detail"])
        self.assertFalse(directory.exists())
        self.assertIsNone(cache.get(browser_upload_key(self.user.pk)))

    def test_suggestion_limit_rejects_before_changes(self) -> None:
        changes = Change.objects.count()
        suggested = self.user.profile.suggested
        with (
            patch("weblate.trans.models.translation.MAX_SUGGESTION_UPLOAD_UNITS", 1),
            self.assertRaisesMessage(FileParseError, "limited to 1 strings"),
        ):
            self.translation.handle_upload(
                self.get_request(),
                NamedBytesIO("test.po", Path(TEST_PO).read_bytes()),
                "",
                method="suggest",
            )
        self.assertEqual(Change.objects.count(), changes)
        self.assertFalse(
            self.translation.unit_set.filter(suggestion__isnull=False).exists()
        )
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.suggested, suggested)

    def test_suggestion_limit_accepts_boundary(self) -> None:
        with patch("weblate.trans.models.translation.MAX_SUGGESTION_UPLOAD_UNITS", 4):
            result = self.translation.handle_upload(
                self.get_request(),
                NamedBytesIO("test.po", Path(TEST_PO).read_bytes()),
                "",
                method="suggest",
            )
        self.assertGreater(result[2], 0)
        self.assertEqual(result[3], 4)

    def test_suggestion_limit_excludes_po_headers_and_obsolete_entries(self) -> None:
        content = (
            b'msgid ""\nmsgstr "Content-Type: text/plain; charset=UTF-8\\n"\n\n'
            b'#~ msgid "Obsolete string"\n#~ msgstr "Obsolete translation"\n\n'
            b'msgid "Hello, world!\\n"\nmsgstr "Suggested translation"\n'
        )
        with patch("weblate.trans.models.translation.MAX_SUGGESTION_UPLOAD_UNITS", 1):
            result = self.translation.handle_upload(
                self.get_request(),
                NamedBytesIO("test.po", content),
                "",
                method="suggest",
            )
        self.assertEqual(result[2:], (1, 1))

    def test_merge_progress_does_not_rescan_content_per_update(self) -> None:
        content_getter = cast("property", PoFormat.content_units).fget
        assert content_getter is not None
        for method in ("suggest", "translate"):
            read_counts = []
            for count in (101, 301):
                with self.subTest(method=method, count=count):
                    content = "\n".join(
                        f'msgid "Unknown string {index}"\nmsgstr "Translation"\n'
                        for index in range(count)
                    ).encode()
                    store = PoFormat(NamedBytesIO("test.po", content))
                    progress = Mock()
                    with patch.object(
                        PoFormat,
                        "content_units",
                        new_callable=PropertyMock,
                        side_effect=lambda store=store: content_getter(store),
                    ) as content_units:
                        if method == "suggest":
                            result = self.translation.merge_suggestions(
                                self.get_request(),
                                self.user,
                                store,
                                "",
                                progress=progress,
                            )
                        else:
                            result = self.translation.merge_translations(
                                self.get_request(),
                                self.user,
                                store,
                                "",
                                "translate",
                                "",
                                progress=progress,
                            )
                    read_counts.append(content_units.call_count)
                    self.assertEqual(result, (count, 0, 0, count))
                    self.assertEqual(
                        [call.args for call in progress.call_args_list],
                        [(index, count) for index in range(0, count, 100)],
                    )
            self.assertEqual(read_counts[0], read_counts[1])

    def test_worker_rejects_anonymous_actor(self) -> None:
        upload_id = self.stage(user=get_anonymous())
        with patch.object(Translation, "handle_upload") as handle:
            result = translation_upload.run(upload_id=upload_id)
        self.assertEqual(result["completion_message"]["level"], "error")
        handle.assert_not_called()
        self.assertFalse(upload_directory(upload_id).exists())

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_browser_queues_and_shows_progress(self) -> None:
        with patch.object(
            translation_upload, "apply_async", return_value=Mock(id="upload-task")
        ):
            response = self.do_import(follow=True)
        self.assertContains(response, "Translation upload in progress.")
        self.assertContains(response, 'data-task="/api/tasks/upload-task/"')

    def test_browser_rate_limit_prevents_staging(self) -> None:
        with (
            patch("weblate.trans.views.files.check_rate_limit", return_value=False),
            patch("weblate.trans.views.files.queue_translation_upload") as queue,
        ):
            response = self.do_import(follow=True)
        self.assertContains(response, "Too many uploads")
        queue.assert_not_called()


class MonolingualSuggestionUploadTest(ImportBaseTest):
    def create_component(self) -> Component:
        return self.create_json_mono()

    def test_limit_counts_uploaded_entries_instead_of_template(self) -> None:
        unit = self.translation.unit_set.get(source="Hello, world!\n")
        content = json.dumps({unit.context: "Suggested translation\n"}).encode()
        template = self.component.template_store
        assert template is not None
        total = len(template.content_units)
        self.assertGreater(total, 1)
        with patch("weblate.trans.models.translation.MAX_SUGGESTION_UPLOAD_UNITS", 1):
            result = self.translation.handle_upload(
                self.get_request(),
                NamedBytesIO("test.json", content),
                "",
                method="suggest",
            )
        self.assertEqual(result[2:], (1, total))
        self.assertTrue(
            unit.suggestion_set.filter(target="Suggested translation\n").exists()
        )

    def test_limit_includes_unknown_and_untranslated_uploaded_entries(self) -> None:
        unit = self.translation.unit_set.get(source="Hello, world!\n")
        template = self.component.template_store
        assert template is not None
        limit = len(template.content_units)
        uploaded = {unit.context: "Suggested translation"}
        uploaded.update({f"unknown-{index}": "" for index in range(limit)})
        content = json.dumps(uploaded).encode()
        changes = Change.objects.count()
        with (
            patch(
                "weblate.trans.models.translation.MAX_SUGGESTION_UPLOAD_UNITS", limit
            ),
            self.assertRaisesMessage(FileParseError, f"limited to {limit} strings"),
        ):
            self.translation.handle_upload(
                self.get_request(),
                NamedBytesIO("test.json", content),
                "",
                method="suggest",
            )
        self.assertEqual(Change.objects.count(), changes)
        self.assertFalse(unit.suggestion_set.exists())


class UploadLoginTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        role = Role.objects.create(name="Guest uploads")
        role.permissions.add(Permission.objects.get(codename="upload.perform"))
        Group.objects.get(name="Guests").roles.add(role)
        self.anonymous = get_anonymous()
        self.anonymous.clear_permissions_cache()

    def test_guest_permissions_do_not_allow_uploads(self) -> None:
        self.assertTrue(
            check_permission(self.anonymous, "upload.perform", self.translation)
        )
        self.assertTrue(self.anonymous.has_perm("suggestion.add", self.translation))
        for obj in (self.project, self.component, self.translation):
            with self.subTest(obj=obj):
                self.assertFalse(self.anonymous.has_perm("upload.perform", obj))

    def test_anonymous_upload_redirects_to_login_without_staging(self) -> None:
        self.client.logout()
        url = reverse("upload", kwargs=self.kw_translation)
        with (
            patch("weblate.trans.views.files.queue_translation_upload") as queue,
            open(TEST_PO, "rb") as handle,
        ):
            response = self.client.post(url, {"file": handle, "method": "suggest"})
        self.assertRedirects(
            response, f"{settings.LOGIN_URL}?next={url}", fetch_redirect_response=False
        )
        queue.assert_not_called()

    def test_anonymous_upload_controls_are_hidden(self) -> None:
        self.client.logout()
        for obj in (self.project, self.component, self.translation):
            with self.subTest(obj=obj):
                response = self.client.get(obj.get_absolute_url())
                self.assertNotContains(response, "Upload translation")
