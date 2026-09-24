# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from threading import Barrier
from typing import TYPE_CHECKING
from unittest.mock import patch
from weakref import ref

from arsc_writer import Text
from django.db import DatabaseError, connections, transaction
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from jsonschema.exceptions import ValidationError as SchemaValidationError
from rest_framework.test import APIClient, APIRequestFactory
from translate.storage.base import ParseError as TranslateParseError

from weblate.formats.ttkit import AndroidFormat
from weblate.kotlin_sdk.addons import (
    KotlinSDKAddon,
    KotlinSDKForm,
)
from weblate.kotlin_sdk.api import BuildMetadataSerializer
from weblate.kotlin_sdk.models import KotlinSDKBuild, KotlinSDKCleanup
from weblate.kotlin_sdk.publication import Publication
from weblate.kotlin_sdk.retention import select_retired_builds
from weblate.kotlin_sdk.translations import LocaleSnapshot, LocaleValues
from weblate.trans.exceptions import FileParseError
from weblate.trans.models import Category, Component, Translation, Unit
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import RepoTestMixin
from weblate.utils.site import get_site_url
from weblate.utils.state import STATE_READONLY, STATE_TRANSLATED
from weblate.utils.unittest import tempdir_setting

if TYPE_CHECKING:
    from collections.abc import Iterable
    from weakref import ReferenceType

    type TranslationSnapshot = dict[
        str, tuple[str, dict[tuple[str, str], Text | dict[str, Text]]]
    ]
    from arsc_writer import ResourceTable

    from weblate.kotlin_sdk.preparation import BuildInput


def metadata(version: int = 1) -> dict:
    return {
        "packageName": "org.weblate.sample",
        "versionCode": version,
        "strings": {"hello": "0x7f090003"},
        "plurals": {"count": "0x7f080004"},
    }


def locales(snapshot: TranslationSnapshot) -> list[LocaleSnapshot]:
    return [
        LocaleSnapshot(language, LocaleValues(locale, entries.items()))
        for language, (locale, entries) in snapshot.items()
    ]


class MetadataTest(SimpleTestCase):
    def test_manifest_schema(self) -> None:
        from weblate.kotlin_sdk.preparation import (  # ruff: ignore[import-outside-top-level]
            BuildInput,
            PreparedPublication,
        )

        build = BuildInput(1, "0" * 64, "org.weblate.sample", 1)
        manifest = PreparedPublication().manifest(build)
        self.assertEqual(manifest["locales"], {})
        with self.assertRaises(SchemaValidationError):
            PreparedPublication(
                locales={
                    "fr": {
                        "url": "../wrong.arsc",
                        "sha256": "a" * 64,
                        "size": 1,
                    }
                }
            ).manifest(build)

    def test_compilation_limit_closes_resource_stream(self) -> None:
        from tempfile import TemporaryDirectory  # ruff: ignore[import-outside-top-level]

        from weblate.kotlin_sdk.preparation import prepare  # ruff: ignore[import-outside-top-level]

        closed = []

        def records() -> Iterable[tuple[tuple[str, str], Text]]:
            try:
                yield ("strings", "hello"), Text("Bonjour")
            finally:
                closed.append(True)

        with (
            TemporaryDirectory() as directory,
            self.assertRaisesMessage(ValueError, "compilation estimate"),
        ):
            prepare(
                metadata(),
                Path(directory),
                lambda _keys: [LocaleSnapshot("fr", LocaleValues("fr", records()))],
                1,
                1024,
            )
        self.assertEqual(closed, [True])

    def test_retention_selection(self) -> None:
        now = timezone.now()
        for published, reserve, expected in (
            ((False, True, True), 0, [1]),
            ((False, False, True), 0, [2]),
            ((False, False, True), 1, [3, 2]),
            ((True, False, True), 0, [2, 1]),
            ((False, False, False), 0, [1]),
            ((False, False, False), 1, [2, 1]),
        ):
            with self.subTest(published=published, reserve=reserve):
                builds = [
                    KotlinSDKBuild(
                        pk=3 - index,
                        created=now - timedelta(hours=index),
                        published=now if value else None,
                    )
                    for index, value in enumerate(published)
                ]
                retired = select_retired_builds(
                    builds, maximum=1, cutoff=now - timedelta(days=1), reserve=reserve
                )
                self.assertEqual([build.pk for build in retired], expected)
                self.assertTrue(all(build.retired is None for build in builds))
        self.assertEqual(select_retired_builds(builds, maximum=100, cutoff=now), builds)

    def test_lifecycle_limits(self) -> None:
        values = {"maximum_versions": 20, "maximum_age": 365}
        addon = KotlinSDKAddon(KotlinSDKAddon.create_object())
        self.assertTrue(KotlinSDKForm(None, addon, data=values).is_valid())
        for field, limit in (
            ("maximum_versions", 100),
            ("maximum_age", 730),
        ):
            for value in (0, limit + 1):
                with self.subTest(field=field, value=value):
                    form = KotlinSDKForm(None, addon, data=values | {field: value})
                    self.assertFalse(form.is_valid())
                    self.assertIn(field, form.errors)

    def test_mapping_types(self) -> None:
        for kind in ("strings", "plurals"):
            data = metadata()
            data.pop(kind)
            serializer = BuildMetadataSerializer(data=data)
            self.assertTrue(serializer.is_valid(), serializer.errors)
            self.assertEqual(serializer.validated_data[kind], {})

    def test_invalid(self) -> None:
        changes: dict
        for changes in (
            {"schemaVersion": 2},
            {"strings": {}, "plurals": {}},
            {"plurals": {"hello": "0x7f090003"}},
            {"packageName": "../bad"},
            {"packageName": "org.example.app\n"},
            {"packageName": " org.example.app"},
            {"packageName": "org.example.app\t"},
            {"versionCode": 0},
            {"strings": {"../bad": "0x7f090003"}},
        ):
            serializer = BuildMetadataSerializer(data=metadata() | changes)
            self.assertFalse(serializer.is_valid(), changes)

    def test_same_name_different_type(self) -> None:
        serializer = BuildMetadataSerializer(
            data=metadata() | {"plurals": {"hello": "0x7f080003"}}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)


@override_settings(LOCALIZE_CDN_URL="https://cdn.example.com/")
class RegistrationConcurrencyTest(RepoTestMixin, TransactionTestCase):
    def setUp(self) -> None:
        self.clone_test_repos()
        super().setUp()

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_worker_renews_publication_lock(self) -> None:
        from arsc_writer import generate  # ruff: ignore[import-outside-top-level]

        from weblate.kotlin_sdk.tasks import publish_kotlin_sdk  # ruff: ignore[import-outside-top-level]
        from weblate.utils.lock import WeblateLock  # ruff: ignore[import-outside-top-level]

        addon = KotlinSDKAddon.create(
            component=self.create_android(), configuration={}, run=False
        )
        build = KotlinSDKBuild.objects.create(
            addon=addon.instance,
            package_name="org.weblate.sample",
            version_code=1,
            metadata=metadata(),
            digest="0" * 64,
        )
        snapshot: TranslationSnapshot = {
            locale: (locale, {("strings", "hello"): Text("Hello")})
            for locale in ("de", "fr")
        }
        renewed: list[WeblateLock] = []
        compiled: list[int] = []
        original_reacquire = WeblateLock.reacquire

        def renew(lock: WeblateLock) -> None:
            self.assertTrue(lock.is_locked)
            original_reacquire(lock)
            renewed.append(lock)

        def compile_locale(
            resources: ResourceTable, *, package: str, locale: str
        ) -> bytes:
            self.assertGreater(len(renewed), compiled[-1] if compiled else 0)
            compiled.append(len(renewed))
            return generate(resources, package=package, locale=locale)

        with (
            patch.object(WeblateLock, "reacquire", autospec=True, side_effect=renew),
            patch.object(Publication, "translations", return_value=locales(snapshot)),
            patch(
                "weblate.kotlin_sdk.preparation.generate", side_effect=compile_locale
            ),
        ):
            publish_kotlin_sdk.run(addon.instance.pk)
        self.assertEqual(len(compiled), 2)
        self.assertGreater(len(renewed), compiled[-1])
        self.assertTrue(all(lock is renewed[0] for lock in renewed))
        self.assertFalse(renewed[0].is_locked)
        build.refresh_from_db()
        self.assertEqual(build.status, "published")

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_overlapping_workers_retry(self) -> None:
        from celery.exceptions import Retry  # ruff: ignore[import-outside-top-level]

        from weblate.kotlin_sdk.tasks import publish_kotlin_sdk  # ruff: ignore[import-outside-top-level]
        from weblate.utils.lock import WeblateLock  # ruff: ignore[import-outside-top-level]

        addon = KotlinSDKAddon.create(
            component=self.create_android(), configuration={}, run=False
        )

        def worker() -> None:
            try:
                publish_kotlin_sdk.run(addon.instance.pk)
            finally:
                connections.close_all()

        with (
            WeblateLock(scope="kotlin-sdk", key=addon.instance.pk, slug="test"),
            patch.object(publish_kotlin_sdk, "retry", side_effect=Retry) as retry,
            patch.object(Publication, "publish") as publish,
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            future = executor.submit(worker)
            with self.assertRaises(Retry):
                future.result(timeout=10)
            retry.assert_called_once()
            publish.assert_not_called()
        with patch.object(Publication, "publish", return_value=None) as publish:
            publish_kotlin_sdk.run(addon.instance.pk)
            publish.assert_called_once()

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_lifecycle_changes_during_compilation(self) -> None:
        from arsc_writer import generate  # ruff: ignore[import-outside-top-level]

        from weblate.addons.models import Addon  # ruff: ignore[import-outside-top-level]
        from weblate.kotlin_sdk.api import register_build  # ruff: ignore[import-outside-top-level]
        from weblate.kotlin_sdk.tasks import publish_kotlin_sdk  # ruff: ignore[import-outside-top-level]

        component = self.create_android()
        for action in ("register", "retire", "uninstall", "reinstall", "expire"):
            with self.subTest(action=action):
                adapter = KotlinSDKAddon.create(
                    component=component, configuration={}, run=False
                )
                addon_id = adapter.instance.pk
                build = KotlinSDKBuild.objects.create(
                    addon=adapter.instance,
                    package_name="org.weblate.sample",
                    version_code=1,
                    metadata=metadata(),
                    digest="0" * 64,
                )
                root = Path(adapter.cdn_path(""))
                barrier = Barrier(2)

                def compile_locale(
                    resources: ResourceTable,
                    *,
                    package: str,
                    locale: str,
                    barrier: Barrier = barrier,
                ) -> bytes:
                    self.assertFalse(connections["default"].in_atomic_block)
                    barrier.wait(timeout=10)
                    barrier.wait(timeout=10)
                    return generate(resources, package=package, locale=locale)

                def worker(addon_id: int = addon_id) -> None:
                    try:
                        publish_kotlin_sdk.run(addon_id)
                    finally:
                        connections.close_all()

                with (
                    patch.object(
                        Publication,
                        "translations",
                        return_value=locales(
                            {"fr": ("fr", {("strings", "hello"): Text("Bonjour")})}
                        ),
                    ),
                    patch(
                        "weblate.kotlin_sdk.preparation.generate",
                        side_effect=compile_locale,
                    ),
                    patch(
                        "weblate.kotlin_sdk.tasks.publish_kotlin_sdk.delay_on_commit"
                    ),
                    ThreadPoolExecutor(max_workers=1) as executor,
                ):
                    future = executor.submit(worker)
                    barrier.wait(timeout=10)
                    try:
                        # Neither the repository nor the add-on row is locked by compilation.
                        with component.repository.lock, transaction.atomic():
                            with connections["default"].cursor() as cursor:
                                cursor.execute("SET LOCAL lock_timeout = '2s'")
                            current = Addon.objects.select_for_update().get(pk=addon_id)
                            if action == "register":
                                serializer = BuildMetadataSerializer(data=metadata(2))
                                serializer.is_valid(raise_exception=True)
                                self.assertEqual(
                                    register_build(
                                        current,
                                        APIRequestFactory().post("/"),
                                        serializer.validated_data,
                                    ).status_code,
                                    202,
                                )
                            elif action == "retire":
                                KotlinSDKBuild.objects.filter(pk=build.pk).update(
                                    retired=timezone.now(),
                                    status="retired",
                                    metadata={},
                                )
                            elif action == "expire":
                                KotlinSDKBuild.objects.filter(pk=build.pk).update(
                                    created=timezone.now() - timedelta(days=2)
                                )
                                current.configuration = {"maximum_age": 1}
                                current.save()
                            else:
                                current.delete()
                                if action == "reinstall":
                                    KotlinSDKAddon.create(
                                        component=component, configuration={}, run=False
                                    )
                    finally:
                        barrier.wait(timeout=10)
                    future.result(timeout=15)
                manifest = root / "org.weblate.sample/1/manifest.json"
                self.assertEqual(manifest.exists(), action == "register")
                component.addon_set.all().delete()

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_concurrent_capacity(self) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.addons.models import Addon
        from weblate.kotlin_sdk.api import register_build  # ruff: ignore[import-outside-top-level]

        component = self.create_android()
        addon = Publication(
            KotlinSDKAddon.create(
                component=component, configuration={}, run=False
            ).instance
        )
        barrier = Barrier(2)

        def register(version: int) -> int:
            try:
                instance = Addon.objects.get(pk=addon.instance.pk)
                serializer = BuildMetadataSerializer(data=metadata(version))
                serializer.is_valid(raise_exception=True)
                barrier.wait(timeout=10)
                return register_build(
                    instance, APIRequestFactory().post("/"), serializer.validated_data
                ).status_code
            finally:
                connections.close_all()

        with (
            patch("weblate.kotlin_sdk.api.MAX_BUILD_RECORDS", 1),
            patch("weblate.kotlin_sdk.api.build_status", return_value={}),
            patch("weblate.kotlin_sdk.tasks.publish_kotlin_sdk.delay_on_commit"),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            self.assertEqual(sorted(executor.map(register, (1, 2))), [202, 409])
        self.assertEqual(addon.instance.sdk_builds.count(), 1)

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_worker_commit_boundaries(self) -> None:
        from weblate.addons.events import AddonActivityLogStatus  # ruff: ignore[import-outside-top-level]
        from weblate.addons.models import AddonActivityLog  # ruff: ignore[import-outside-top-level]
        from weblate.kotlin_sdk.tasks import publish_kotlin_sdk  # ruff: ignore[import-outside-top-level]

        component = self.create_android()
        addon = Publication(
            KotlinSDKAddon.create(
                component=component, configuration={}, run=False
            ).instance
        )
        build = KotlinSDKBuild.objects.create(
            addon=addon.instance,
            package_name="org.weblate.sample",
            version_code=1,
            metadata=metadata(),
            digest="0" * 64,
        )
        original = Publication.finalize_manifest
        finalized = []

        def finalize(publisher: Publication, build_id: int) -> str | None:
            self.assertFalse(connections["default"].in_atomic_block)
            current = KotlinSDKBuild.objects.get(pk=build_id)
            if current.pending_manifest:
                self.assertTrue(current.artifacts.exists())
                finalized.append(build_id)
                # A new trigger between phases must not be swallowed by coalescing.
                with patch(
                    "weblate.kotlin_sdk.tasks.publish_kotlin_sdk.delay_on_commit"
                ) as enqueue:
                    publisher.schedule()
                enqueue.assert_called_once_with(addon.instance.pk)
            return original(publisher, build_id)

        snapshot: TranslationSnapshot = {
            "fr": ("fr", {("strings", "hello"): Text("Bonjour")})
        }
        with (
            patch.object(Publication, "translations", return_value=locales(snapshot)),
            patch.object(
                Publication, "finalize_manifest", autospec=True, side_effect=finalize
            ),
        ):
            publish_kotlin_sdk.run(addon.instance.pk)
        build.refresh_from_db()
        addon.instance.refresh_from_db()
        self.assertEqual(finalized, [build.pk])
        self.assertEqual(build.status, "published")
        self.assertIn("kotlin_pending", addon.instance.state)
        self.assertEqual(
            AddonActivityLog.objects.filter(addon=addon.instance).latest("pk").status,
            AddonActivityLogStatus.SUCCESS,
        )
        with (
            patch.object(Publication, "translations", return_value=locales(snapshot)),
            patch.object(
                KotlinSDKAddon, "write_cdn_text", side_effect=OSError("manifest failed")
            ),
        ):
            publish_kotlin_sdk.run(addon.instance.pk)
        build.refresh_from_db()
        self.assertEqual(build.status, "failed")
        self.assertTrue(build.pending_manifest)
        self.assertEqual(
            AddonActivityLog.objects.filter(addon=addon.instance).latest("pk").status,
            AddonActivityLogStatus.ERROR,
        )


@override_settings(LOCALIZE_CDN_URL="https://cdn.example.com/")
class KotlinSDKTest(ViewTestCase):
    def stage_build(
        self,
        addon: Publication,
        build: KotlinSDKBuild,
        translations: Iterable[LocaleSnapshot],
    ) -> None:
        """Prepare and commit a single mapping using the same job pipeline."""
        from tempfile import TemporaryDirectory  # ruff: ignore[import-outside-top-level]

        from weblate.kotlin_sdk import publication  # ruff: ignore[import-outside-top-level]
        from weblate.kotlin_sdk.preparation import (  # ruff: ignore[import-outside-top-level]
            BuildInput,
            prepare,
            resource_mapping,
        )

        with addon.locked_addon() as current:
            if current is None:
                return
            addon.staging_path.mkdir(mode=0o700, parents=True, exist_ok=True)
            temporary = TemporaryDirectory(dir=addon.staging_path)
        with temporary as directory:
            result = prepare(
                resource_mapping(build),
                Path(directory),
                lambda _keys: translations,
                publication.MAX_COMPILATION_BYTES,
                publication.MAX_PREPARATION_BYTES,
            )
            addon.commit(BuildInput.capture(build), result)

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_inventory_refresh_after_cleanup(self) -> None:
        addon = self.install()
        build = self.register(addon)
        snapshot: TranslationSnapshot = {
            "fr": ("fr", {("strings", "hello"): Text("Bonjour")})
        }
        with patch.object(addon, "translations", return_value=locales(snapshot)):
            self.publish(addon)
        orphan = Path(addon.cdn.cdn_path("artifacts/orphan.arsc"))
        orphan.write_bytes(b"x" * 8192)
        addon.refresh_inventory()
        orphan.unlink()
        with (
            patch("weblate.kotlin_sdk.publication.MAX_ARTIFACT_BYTES", 2048),
            patch.object(
                addon, "refresh_inventory", wraps=addon.refresh_inventory
            ) as refresh,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.stage_build(addon, build, locales(snapshot))
        refresh.assert_called_once()
        build.refresh_from_db()
        self.assertEqual(build.status, "published")

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_shared_preparation(self) -> None:
        from arsc_writer import generate  # ruff: ignore[import-outside-top-level]

        addon = self.install()
        builds = [self.register(addon, version) for version in range(1, 5)]
        builds[2].package_name = "org.weblate.other"
        builds[2].save(update_fields=["package_name"])
        builds[3].metadata["strings"]["hello"] = "0x7f090005"
        builds[3].save(update_fields=["metadata"])
        snapshot: TranslationSnapshot = {
            "fr": ("fr", {("strings", "hello"): Text("Bonjour")}),
            "de": ("de", {("strings", "hello"): Text("Hallo")}),
        }

        def extract_group(_keys: set[tuple[str, str]]) -> list[LocaleSnapshot]:
            self.assertFalse(list(addon.staging_path.rglob("*.arsc")))
            return locales(snapshot)

        with (
            patch.object(addon, "translations", side_effect=extract_group) as extract,
            patch(
                "weblate.kotlin_sdk.preparation.generate", wraps=generate
            ) as compile_locale,
            patch.object(
                addon, "refresh_inventory", wraps=addon.refresh_inventory
            ) as inventory,
        ):
            self.publish(addon)
        self.assertEqual(extract.call_count, 3)
        extract.assert_called_with({("strings", "hello"), ("plurals", "count")})
        self.assertEqual(compile_locale.call_count, 6)
        inventory.assert_called_once()
        for build in builds:
            build.refresh_from_db()
            self.assertEqual(build.status, "published", build.error)
        self.assertEqual(
            set(builds[0].artifacts.values_list("pk", flat=True)),
            set(builds[1].artifacts.values_list("pk", flat=True)),
        )

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_retired_mapping_representative(self) -> None:
        addon = self.install()
        first = self.register(addon)
        second = self.register(addon, 2)
        publish_group = addon.publish_group

        def retire_representative(digest: str, builds: list[BuildInput]) -> None:
            with addon.locked_addon():
                representative = KotlinSDKBuild.objects.get(pk=builds[0].pk)
                addon.retire(representative, timezone.now())
            publish_group(digest, builds)

        with (
            patch.object(addon, "publish_group", side_effect=retire_representative),
            patch.object(
                addon,
                "translations",
                return_value=locales(
                    {"fr": ("fr", {("strings", "hello"): Text("Bonjour")})}
                ),
            ),
        ):
            self.publish(addon)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertCountEqual([first.status, second.status], ["retired", "published"])

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_resource_failure_isolation(self) -> None:
        addon = self.install()
        bad = self.register(addon)
        good = self.register(addon, 2)
        good.metadata["strings"] = {"valid": "0x7f090003"}
        good.save(update_fields=["metadata"])

        def extract(keys: set[tuple[str, str]]) -> list[LocaleSnapshot]:
            if ("strings", "hello") in keys:
                msg = "Unsupported Android span"
                raise ValueError(msg)
            return locales({"fr": ("fr", {("strings", "valid"): Text("Bonjour")})})

        with patch.object(addon, "translations", side_effect=extract):
            self.publish(addon)
        bad.refresh_from_db()
        good.refresh_from_db()
        self.assertEqual(bad.status, "failed")
        self.assertEqual(good.status, "published", good.error)

    def publish(self, addon: Publication) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            addon.publish()

    def create_component(self) -> Component:
        return self.create_android()

    def install(self) -> Publication:
        return Publication(
            KotlinSDKAddon.create(
                component=self.component, configuration={}, run=False
            ).instance
        )

    def register(self, addon: Publication, version: int = 1) -> KotlinSDKBuild:
        serializer = BuildMetadataSerializer(data=metadata(version))
        serializer.is_valid(raise_exception=True)
        return KotlinSDKBuild.objects.create(
            addon=addon.instance,
            package_name="org.weblate.sample",
            version_code=version,
            metadata=serializer.validated_data,
            digest=str(version).zfill(64),
        )

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_publication_waits_for_commit(self) -> None:
        addon = self.install()
        build = self.register(addon)
        with (
            self.captureOnCommitCallbacks(execute=True),
            transaction.atomic(),
            patch.object(addon, "translations", return_value=()),
        ):
            addon.publish()
            build.refresh_from_db()
            self.assertTrue(build.pending_manifest)
            self.assertFalse(
                Path(addon.cdn.cdn_path("org.weblate.sample/1/manifest.json")).exists()
            )
        build.refresh_from_db()
        self.assertEqual(build.status, "published")

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_publication_rollback_discards_callback(self) -> None:
        addon = self.install()
        self.register(addon)
        with (
            self.captureOnCommitCallbacks(execute=True) as callbacks,
            self.assertRaisesMessage(ValueError, "rollback"),
            transaction.atomic(),
        ):
            with patch.object(addon, "translations", return_value=()):
                addon.publish()
            msg = "rollback"
            raise ValueError(msg)
        self.assertEqual(callbacks, [])
        self.assertFalse(
            Path(addon.cdn.cdn_path("org.weblate.sample/1/manifest.json")).exists()
        )

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_registration_api(self) -> None:
        self.make_manager()
        addon = self.install()
        client = APIClient()
        client.force_authenticate(self.user)
        url = f"/api/components/{self.component.project.slug}/{self.component.slug}/addons/kotlin-sdk/builds/"
        with patch("weblate.kotlin_sdk.tasks.publish_kotlin_sdk.delay_on_commit"):
            response = client.post(url, metadata(), format="json")
            self.assertEqual(response.status_code, 202, response.content)
            self.assertEqual(
                client.post(url, metadata(), format="json").status_code, 200
            )
            changed = metadata() | {"strings": {"hello": "0x7f090005"}}
            self.assertEqual(client.post(url, changed, format="json").status_code, 409)
        self.assertEqual(addon.instance.sdk_builds.count(), 1)
        self.assertEqual(client.get(response.data["status_url"]).status_code, 200)
        self.assertEqual(client.put(url, metadata(), format="json").status_code, 405)
        self.assertEqual(
            client.get(url.replace("kotlin-sdk", "missing")).status_code, 404
        )
        client.force_authenticate(None)
        self.assertIn(client.get(response.data["status_url"]).status_code, (401, 403))
        self.assertIn(
            client.post(url, metadata(), format="json").status_code, (401, 403)
        )

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_api_links(self) -> None:
        self.make_manager()
        addon = self.install()
        response = self.client.get(addon.instance.get_absolute_url())
        api_url = reverse("addon-api", kwargs={"pk": addon.instance.pk})
        self.assertContains(response, api_url)
        self.assertNotContains(response, "Add-on API base URL:")
        self.assertContains(response, f"serverUrl = &quot;{get_site_url()}&quot;")
        self.assertContains(response, f"cdnUrl = &quot;{addon.cdn.cdn_base_url}&quot;")
        self.assertContains(response, f"project = &quot;{self.project.slug}&quot;")
        self.assertContains(response, f"component = &quot;{self.component.slug}&quot;")
        self.assertContains(response, "authToken = &quot;INSERT_TOKEN_HERE&quot;")
        self.assertContains(response, 'data-clipboard-value="weblate {')
        self.assertContains(
            response,
            reverse("manage-access", kwargs={"project": self.project.slug}) + "#api",
        )
        self.assertContains(response, addon.cdn.cdn_base_url)

        response = self.client.get(api_url)
        self.assertTemplateUsed(response, "addons/addon_api.html")
        self.assertEqual(response.context["addon_page"], "api")
        self.assertContains(
            response,
            f'data-clipboard-value="{addon.instance.api_url}"',
        )
        self.assertNotContains(response, f'href="{addon.instance.api_url}"')
        self.assertContains(response, '<a href="/api/">API root</a>', html=True)
        self.assertContains(response, '/admin/addons.html#addon-weblate-cdn-kotlin"')
        self.assertEqual(self.client.get("/api/").status_code, 200)

        self.client.logout()
        self.assertEqual(self.client.get(api_url).status_code, 403)

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_integration_in_nested_category(self) -> None:
        self.make_manager()
        parent = Category.objects.create(
            name="Parent", slug="parent", project=self.project
        )
        child = Category.objects.create(
            name="Child", slug="child", category=parent, project=self.project
        )
        self.component.category = child
        self.component.save()
        addon = self.install()

        response = self.client.get(addon.instance.get_absolute_url())
        self.assertContains(
            response,
            f"component = &quot;parent%2Fchild%2F{self.component.slug}&quot;",
        )

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_registration_uses_locked_configuration(self) -> None:
        from weblate.addons.models import Addon  # ruff: ignore[import-outside-top-level]
        from weblate.kotlin_sdk.api import register_build  # ruff: ignore[import-outside-top-level]

        addon = self.install()
        addon.instance.configuration = {"maximum_versions": 1}
        addon.instance.save()
        first = self.register(addon)
        self.register(addon, 2)
        Addon.objects.filter(pk=addon.instance.pk).update(
            configuration={"maximum_versions": 3}
        )
        serializer = BuildMetadataSerializer(data=metadata(3))
        serializer.is_valid(raise_exception=True)
        with (
            patch("weblate.kotlin_sdk.api.build_status", return_value={}),
            patch("weblate.kotlin_sdk.tasks.publish_kotlin_sdk.delay_on_commit"),
        ):
            result = register_build(
                addon.instance, APIRequestFactory().post("/"), serializer.validated_data
            )
        self.assertEqual(result.status_code, 202)
        self.assertEqual(
            addon.instance.sdk_builds.filter(retired__isnull=True).count(), 3
        )
        first.refresh_from_db()
        self.assertTrue(first.metadata)

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_registration_limits(self) -> None:
        self.make_manager()
        addon = self.install()
        addon.instance.configuration = {
            "maximum_versions": 1,
            "maximum_age": 1,
        }
        addon.instance.save()
        client = APIClient()
        client.force_authenticate(self.user)
        url = f"/api/components/{self.project.slug}/{self.component.slug}/addons/kotlin-sdk/builds/"
        with patch("weblate.kotlin_sdk.tasks.publish_kotlin_sdk.delay_on_commit"):
            first = client.post(url, metadata(), format="json")
            self.assertEqual(first.status_code, 202)
            original = addon.instance.sdk_builds.get()
            second = metadata(2) | {"packageName": "org.example.other"}
            self.assertEqual(client.post(url, second, format="json").status_code, 202)
            with patch.object(addon, "translations", return_value=()):
                self.publish(addon)
            original.refresh_from_db()
            self.assertEqual(original.status, "retired")
            self.assertEqual(original.metadata, {})
            self.assertEqual(
                client.post(url, metadata(), format="json").status_code, 200
            )
            self.assertEqual(
                addon.instance.sdk_builds.filter(retired__isnull=True).count(), 1
            )
            with patch("weblate.kotlin_sdk.api.MAX_BUILD_RECORDS", 2):
                self.assertEqual(
                    client.post(url, metadata(3), format="json").status_code, 409
                )
                self.assertEqual(
                    client.post(url, second, format="json").status_code, 200
                )
            addon.instance.sdk_builds.filter(pk=original.pk).update(
                retired=timezone.now() - timedelta(days=2)
            )
            self.assertEqual(
                client.post(url, metadata(), format="json").status_code, 202
            )
            self.assertFalse(addon.instance.sdk_builds.filter(pk=original.pk).exists())

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_registration_does_not_reserialize_metadata(self) -> None:
        from weblate.kotlin_sdk.api import register_build  # ruff: ignore[import-outside-top-level]

        addon = self.install()
        original = self.register(addon)
        serializer = BuildMetadataSerializer(data=metadata(2))
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        request = APIRequestFactory().post("/")
        with (
            patch("weblate.kotlin_sdk.api.build_status", return_value={}),
            patch("weblate.kotlin_sdk.tasks.publish_kotlin_sdk.delay_on_commit"),
            patch("weblate.kotlin_sdk.api.json.dumps", wraps=json.dumps) as dumps,
        ):
            self.assertEqual(
                register_build(addon.instance, request, data).status_code, 202
            )
            self.assertNotIn(
                original.metadata, [call.args[0] for call in dumps.call_args_list]
            )

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_absolute_expiry(self) -> None:
        addon = self.install()
        build = self.register(addon)
        now = timezone.now()
        addon.instance.sdk_builds.update(created=now - timedelta(days=730))
        addon.instance.configuration = {"maximum_age": 10000}
        with patch("weblate.kotlin_sdk.publication.timezone.now", return_value=now):
            addon.expire_builds()
        build.refresh_from_db()
        self.assertEqual(build.status, "retired")

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_uninstall_cleanup(self) -> None:
        addon = self.install()
        root = Path(addon.cdn.cdn_path(""))
        addon.cdn.write_cdn_bytes("artifacts/test.arsc", b"test")
        sibling = root.parent / "other-addon"
        sibling.mkdir()
        with self.assertRaisesMessage(ValueError, "rollback"), transaction.atomic():
            addon.instance.delete()
            msg = "rollback"
            raise ValueError(msg)
        self.assertTrue(root.exists())
        self.assertFalse(KotlinSDKCleanup.objects.exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.component.addon_set.filter(name=addon.cdn.name).delete()
        self.assertFalse(root.exists())
        self.assertTrue(sibling.exists())

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_uninstall_cleanup_retry(self) -> None:
        from weblate.kotlin_sdk.tasks import cleanup_publications  # ruff: ignore[import-outside-top-level]

        addon = self.install()
        addon.cdn.write_cdn_bytes("artifacts/test.arsc", b"test")
        root = Path(addon.cdn.cdn_path(""))
        completed = []
        with (
            patch(
                "weblate.kotlin_sdk.tasks.shutil.rmtree",
                side_effect=PermissionError("read-only CDN"),
            ),
            self.assertLogs("weblate.kotlin_sdk.tasks", level="ERROR"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            addon.instance.delete()
            transaction.on_commit(lambda: completed.append(True))
        self.assertEqual(completed, [True])
        self.assertTrue(root.exists())
        self.assertEqual(KotlinSDKCleanup.objects.get().path, str(root))
        cleanup_publications.run()
        self.assertFalse(root.exists())
        self.assertFalse(KotlinSDKCleanup.objects.exists())
        cleanup_publications.run()

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_retired_cleanup_blocks_path_reuse(self) -> None:
        from weblate.kotlin_sdk.tasks import cleanup_publication, cleanup_publications  # ruff: ignore[import-outside-top-level]

        addon = self.install()
        build = self.register(addon)
        snapshot: TranslationSnapshot = {
            "fr": ("fr", {("strings", "hello"): Text("Bonjour")})
        }
        with patch.object(addon, "translations", return_value=locales(snapshot)):
            self.publish(addon)
        manifest = Path(addon.cdn.cdn_path("org.weblate.sample/1/manifest.json"))
        artifact = build.artifacts.get()
        addon.instance.sdk_builds.update(created=timezone.now() - timedelta(days=731))
        with (
            patch.object(Path, "unlink", side_effect=PermissionError("read-only CDN")),
            self.assertLogs("weblate.kotlin_sdk.tasks", level="ERROR"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            addon.expire_builds()
        intent = KotlinSDKCleanup.objects.get(build=build)
        addon.instance.sdk_builds.update(retired=timezone.now() - timedelta(hours=25))
        addon.expire_builds()
        self.assertTrue(addon.instance.sdk_builds.filter(pk=build.pk).exists())
        self.assertTrue(build.artifacts.exists())
        self.assertTrue(manifest.exists())
        cleanup_publications.run()
        self.assertFalse(manifest.exists())
        artifact.refresh_from_db()
        self.assertIsNotNone(artifact.unreferenced)
        addon.expire_builds()
        self.assertFalse(addon.instance.sdk_builds.filter(pk=build.pk).exists())
        replacement = self.register(addon)
        with patch.object(addon, "translations", return_value=locales(snapshot)):
            self.publish(addon)
        cleanup_publication(intent.pk)
        replacement.refresh_from_db()
        self.assertEqual(replacement.status, "published")
        self.assertTrue(manifest.exists())

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_replacement_capacity_preserves_published_build(self) -> None:
        self.make_manager()
        addon = self.install()
        addon.instance.configuration = {"maximum_versions": 1}
        addon.instance.save()
        old = self.register(addon)
        snapshot: TranslationSnapshot = {
            "fr": ("fr", {("strings", "hello"): Text("Bonjour")})
        }
        with patch.object(addon, "translations", return_value=locales(snapshot)):
            self.publish(addon)
        manifest = Path(addon.cdn.cdn_path("org.weblate.sample/1/manifest.json"))
        original = manifest.read_bytes()
        client = APIClient()
        client.force_authenticate(self.user)
        url = f"/api/components/{self.project.slug}/{self.component.slug}/addons/kotlin-sdk/builds/"
        replacement = metadata(2) | {"strings": {"hello": "0x7f090004"}}
        with (
            patch("weblate.kotlin_sdk.tasks.publish_kotlin_sdk.delay_on_commit"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.assertEqual(
                client.post(url, replacement, format="json").status_code, 202
            )
        with (
            patch.object(addon, "translations", return_value=locales(snapshot)),
            patch("weblate.kotlin_sdk.publication.MAX_ARTIFACT_FILES", 1),
        ):
            self.publish(addon)
        old.refresh_from_db()
        new = addon.instance.sdk_builds.get(version_code=2)
        self.assertEqual(old.status, "published")
        self.assertEqual(new.status, "failed")
        self.assertEqual(manifest.read_bytes(), original)
        self.assertTrue(old.metadata)
        with patch.object(addon, "translations", return_value=locales(snapshot)):
            self.publish(addon)
        old.refresh_from_db()
        new.refresh_from_db()
        self.assertEqual(old.status, "retired")
        self.assertEqual(new.status, "published")
        self.assertFalse(manifest.exists())

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_component_deletion_cleanup(self) -> None:
        addon = self.install()
        addon.cdn.write_cdn_bytes("artifacts/test.arsc", b"test")
        root = Path(addon.cdn.cdn_path(""))
        with self.captureOnCommitCallbacks(execute=True):
            self.component.delete()
        self.assertFalse(root.exists())

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_worker_and_coalescing(self) -> None:
        from weblate.kotlin_sdk.tasks import publish_kotlin_sdk  # ruff: ignore[import-outside-top-level]

        addon = self.install()
        build = self.register(addon)
        with patch(
            "weblate.kotlin_sdk.tasks.publish_kotlin_sdk.delay_on_commit"
        ) as enqueue:
            addon.schedule()
            addon.schedule()
            enqueue.assert_called_once_with(addon.instance.pk)
        with (
            patch.object(
                Publication,
                "translations",
                return_value=locales(
                    {"fr": ("fr", {("strings", "hello"): Text("Bonjour")})}
                ),
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            publish_kotlin_sdk.run(addon.instance.pk)
        build.refresh_from_db()
        addon.instance.refresh_from_db()
        self.assertEqual(build.status, "published")
        self.assertNotIn("kotlin_pending", addon.instance.state)

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_payload_limit_and_invalid_json(self) -> None:
        self.make_manager()
        self.install()
        client = APIClient()
        client.force_authenticate(self.user)
        url = f"/api/components/{self.component.project.slug}/{self.component.slug}/addons/kotlin-sdk/builds/"
        for content in (
            b"{",
            b"",
            b"[" * 2000 + b"]" * 2000,
            b" " * (5 * 1024 * 1024 + 1),
        ):
            response = client.post(url, content, content_type="application/json")
            self.assertEqual(response.status_code, 400, response.content)

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_artifact_grace_and_sharing(self) -> None:
        addon = self.install()
        first = self.register(addon)
        second = self.register(addon, 2)
        snapshot: TranslationSnapshot = {
            "fr": ("fr", {("strings", "hello"): Text("Bonjour")})
        }
        with patch.object(addon, "translations", return_value=locales(snapshot)):
            self.publish(addon)
        artifact = first.artifacts.get()
        self.assertEqual(second.artifacts.get().pk, artifact.pk)
        with self.assertNumQueries(1):
            first.set_artifacts([artifact])
        first.set_artifacts([])
        artifact.refresh_from_db()
        self.assertIsNone(artifact.unreferenced)
        first.set_artifacts([artifact])
        old_path = Path(addon.cdn.cdn_path(f"artifacts/{artifact.digest}.arsc"))
        with patch.object(addon, "translations", return_value={}):
            self.publish(addon)
        artifact.refresh_from_db()
        self.assertIsNotNone(artifact.unreferenced)
        self.assertTrue(old_path.exists())
        now = timezone.now()
        addon.instance.sdk_artifacts.filter(pk=artifact.pk).update(
            unreferenced=now - timedelta(hours=23)
        )
        addon.cleanup_artifacts()
        self.assertTrue(old_path.exists())
        addon.instance.sdk_artifacts.filter(pk=artifact.pk).update(
            unreferenced=now - timedelta(hours=24)
        )
        with patch.object(addon, "translations", return_value={}):
            self.publish(addon)
        self.assertFalse(old_path.exists())
        self.assertFalse(addon.instance.sdk_artifacts.exists())

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_artifact_capacity(self) -> None:
        addon = self.install()
        build = self.register(addon)
        snapshot: TranslationSnapshot = {
            "fr": ("fr", {("strings", "hello"): Text("Bonjour")})
        }
        with patch.object(addon, "translations", return_value=locales(snapshot)):
            self.publish(addon)
        root = Path(addon.cdn.cdn_path("artifacts"))
        original_files = {path.name: path.read_bytes() for path in root.iterdir()}
        size = sum(map(len, original_files.values()))
        manifest = Path(addon.cdn.cdn_path("org.weblate.sample/1/manifest.json"))
        original_manifest = manifest.read_bytes()
        # Reusing the same immutable artifact consumes no additional quota.
        with (
            patch("weblate.kotlin_sdk.publication.MAX_ARTIFACT_BYTES", size),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.stage_build(addon, build, locales(snapshot))
        changed: TranslationSnapshot = {
            "fr": ("fr", {("strings", "hello"): Text("Salut")})
        }
        for limit, value in (
            ("MAX_ARTIFACT_BYTES", size),
            ("MAX_ARTIFACT_FILES", 1),
            ("MAX_PREPARATION_BYTES", 1),
        ):
            with (
                self.subTest(limit=limit),
                patch(f"weblate.kotlin_sdk.publication.{limit}", value),
                patch.object(addon, "translations", return_value=locales(changed)),
            ):
                self.publish(addon)
                build.refresh_from_db()
                self.assertEqual(build.status, "failed")
                self.assertIn("storage limit", build.error)
                self.assertEqual(manifest.read_bytes(), original_manifest)
                self.assertFalse(list(addon.staging_path.rglob("*.arsc")))
                self.assertEqual(
                    {path.name: path.read_bytes() for path in root.iterdir()},
                    original_files,
                )
        # Superseded files and rollback leftovers both count against capacity.
        with patch.object(addon, "translations", return_value={}):
            self.publish(addon)
        with (
            patch("weblate.kotlin_sdk.publication.MAX_ARTIFACT_BYTES", size),
            self.assertRaisesRegex(ValueError, "storage limit"),
        ):
            self.stage_build(addon, build, locales(changed))
        orphan = root / "orphan.arsc"
        orphan.write_bytes(b"orphan")
        with (
            patch("weblate.kotlin_sdk.publication.MAX_ARTIFACT_BYTES", size),
            self.assertRaisesRegex(ValueError, "storage limit"),
        ):
            inventory = addon.refresh_inventory()
            addon.check_artifact_capacity(
                total=inventory.total, count=len(inventory.sizes)
            )
        addon.cleanup_artifacts()
        self.assertTrue(orphan.exists())
        old = (timezone.now() - timedelta(hours=25)).timestamp()
        os.utime(orphan, (old, old))
        addon.instance.sdk_artifacts.update(
            unreferenced=timezone.now() - timedelta(hours=25)
        )
        with (
            patch.object(addon, "translations", return_value=locales(changed)),
            patch("weblate.kotlin_sdk.publication.MAX_ARTIFACT_BYTES", size),
        ):
            self.publish(addon)
        build.refresh_from_db()
        self.assertEqual(build.status, "published")
        self.assertFalse(orphan.exists())

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_artifact_failed_write_accounting(self) -> None:
        addon = self.install()
        build = self.register(addon)
        snapshot: TranslationSnapshot = {
            "fr": ("fr", {("strings", "hello"): Text("Bonjour")})
        }
        with (
            patch.object(
                KotlinSDKAddon, "write_cdn_text", side_effect=OSError("failed manifest")
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.stage_build(addon, build, locales(snapshot))
            self.assertEqual(addon.finalize_manifest(build.pk), "failed manifest")
        build.refresh_from_db()
        self.assertEqual(build.status, "failed")
        self.assertTrue(build.pending_manifest)
        self.assertTrue(build.artifacts.exists())
        self.assertTrue(addon.instance.sdk_artifacts.exists())
        with (
            patch("weblate.kotlin_sdk.publication.MAX_ARTIFACT_BYTES", 1),
            self.assertRaisesRegex(ValueError, "storage limit"),
        ):
            inventory = addon.refresh_inventory()
            addon.check_artifact_capacity(
                total=inventory.total, count=len(inventory.sizes)
            )

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_invalid_pending_artifact_recovery(self) -> None:
        addon = self.install()
        snapshot: TranslationSnapshot = {
            "fr": ("fr", {("strings", "hello"): Text("Bonjour")})
        }
        for version, corruption in enumerate((None, b"broken"), start=1):
            with self.subTest(corruption=corruption):
                build = self.register(addon, version=version)
                with (
                    patch.object(
                        KotlinSDKAddon, "write_cdn_text", side_effect=OSError("failed")
                    ),
                    self.captureOnCommitCallbacks(execute=True),
                ):
                    self.stage_build(addon, build, locales(snapshot))
                artifact = build.artifacts.get()
                path = Path(addon.cdn.cdn_path(f"artifacts/{artifact.digest}.arsc"))
                expected = path.read_bytes()
                if corruption is None:
                    path.unlink()
                else:
                    path.write_bytes(corruption)
                self.assertIsNotNone(addon.finalize_manifest(build.pk))
                build.refresh_from_db()
                self.assertEqual(build.status, "failed")
                self.assertFalse(build.pending_manifest)
                with (
                    patch.object(addon, "translations", return_value=locales(snapshot)),
                    patch(
                        "weblate.kotlin_sdk.publication.MAX_ARTIFACT_BYTES",
                        len(expected),
                    ),
                    patch("weblate.kotlin_sdk.publication.MAX_ARTIFACT_FILES", 1),
                ):
                    self.publish(addon)
                build.refresh_from_db()
                self.assertEqual(build.status, "published")
                self.assertFalse(build.pending_manifest)
                self.assertEqual(path.read_bytes(), expected)

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_invalid_pending_manifest(self) -> None:
        addon = self.install()
        snapshot: TranslationSnapshot = {
            "fr": ("fr", {("strings", "hello"): Text("Bonjour")})
        }
        for version, corruption in enumerate(("size", "url"), start=1):
            with self.subTest(corruption=corruption):
                build = self.register(addon, version=version)
                with (
                    patch.object(
                        KotlinSDKAddon,
                        "write_cdn_text",
                        side_effect=OSError("failed"),
                    ),
                    self.captureOnCommitCallbacks(execute=True),
                ):
                    self.stage_build(addon, build, locales(snapshot))
                build.refresh_from_db()
                locale = build.pending_manifest["locales"]["fr"]
                if corruption == "size":
                    locale["size"] = 0
                else:
                    locale["url"] = f"../../artifacts/{'a' * 64}.arsc"
                build.save(update_fields=["pending_manifest"])
                self.assertIsNotNone(addon.finalize_manifest(build.pk))
                build.refresh_from_db()
                self.assertEqual(build.status, "failed")
                self.assertFalse(build.pending_manifest)
                self.assertFalse(
                    Path(
                        addon.cdn.cdn_path(
                            f"org.weblate.sample/{version}/manifest.json"
                        )
                    ).exists()
                )

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_incompatible_component_retirement(self) -> None:
        from weblate.kotlin_sdk.tasks import (  # ruff: ignore[import-outside-top-level]
            cleanup_publications,
            publish_kotlin_sdk,
        )

        addon = self.install()
        build = self.register(addon)
        snapshot: TranslationSnapshot = {
            "fr": ("fr", {("strings", "hello"): Text("Bonjour")})
        }
        with patch.object(addon, "translations", return_value=locales(snapshot)):
            self.publish(addon)
        artifact = build.artifacts.get()
        path = Path(addon.cdn.cdn_path(f"artifacts/{artifact.digest}.arsc"))
        manifest = Path(addon.cdn.cdn_path("org.weblate.sample/1/manifest.json"))
        Component.objects.filter(pk=self.component.pk).update(file_format="po")
        with patch.object(publish_kotlin_sdk, "delay_on_commit") as schedule:
            cleanup_publications()
        schedule.assert_called_once_with(addon.instance.pk)
        with (
            patch.object(Publication, "translations") as extract,
            self.captureOnCommitCallbacks(execute=True),
        ):
            publish_kotlin_sdk(addon.instance.pk)
        extract.assert_not_called()
        build.refresh_from_db()
        self.assertEqual(build.status, "retired")
        self.assertFalse(build.metadata)
        self.assertFalse(manifest.exists())
        self.assertTrue(path.exists())
        old = timezone.now() - timedelta(hours=25)
        build.artifacts.model.objects.filter(pk=artifact.pk).update(unreferenced=old)
        KotlinSDKBuild.objects.filter(pk=build.pk).update(retired=old)
        with self.captureOnCommitCallbacks(execute=True):
            publish_kotlin_sdk(addon.instance.pk)
        self.assertFalse(path.exists())
        self.assertFalse(KotlinSDKBuild.objects.filter(pk=build.pk).exists())

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_manifest_rollback_and_recovery(self) -> None:
        addon = self.install()
        build = self.register(addon)
        snapshot: TranslationSnapshot = {
            "fr": ("fr", {("strings", "hello"): Text("Bonjour")})
        }
        changed: TranslationSnapshot = {
            "fr": ("fr", {("strings", "hello"): Text("Updated")})
        }
        with patch.object(addon, "translations", return_value=locales(snapshot)):
            self.publish(addon)
        manifest_path = Path(addon.cdn.cdn_path("org.weblate.sample/1/manifest.json"))
        old_manifest = manifest_path.read_bytes()
        with (
            self.captureOnCommitCallbacks(execute=True),
            self.assertRaisesMessage(ValueError, "rollback"),
            transaction.atomic(),
        ):
            self.stage_build(addon, build, locales(changed))
            self.assertEqual(manifest_path.read_bytes(), old_manifest)
            msg = "rollback"
            raise ValueError(msg)
        self.assertEqual(manifest_path.read_bytes(), old_manifest)
        build.refresh_from_db()
        self.assertFalse(build.pending_manifest)
        self.assertEqual(build.artifacts.count(), 1)
        # Simulate a worker stopping between the staging and finalization phases.
        self.stage_build(addon, build, locales(changed))
        build.refresh_from_db()
        self.assertTrue(build.pending_manifest)
        self.assertEqual(build.artifacts.count(), 2)
        self.assertEqual(manifest_path.read_bytes(), old_manifest)
        with patch(
            "weblate.kotlin_sdk.publication.timezone.now",
            return_value=timezone.now() + timedelta(hours=25),
        ):
            addon.cleanup_artifacts()
        for artifact in build.artifacts.all():
            self.assertTrue(
                Path(addon.cdn.cdn_path(f"artifacts/{artifact.digest}.arsc")).exists()
            )
        # A failed commit after replacing the manifest retains both generations.
        with (
            patch.object(
                KotlinSDKBuild, "save", side_effect=DatabaseError("failed commit")
            ),
            self.assertRaises(DatabaseError),
        ):
            addon.finalize_manifest(build.pk)
        build.refresh_from_db()
        self.assertTrue(build.pending_manifest)
        self.assertEqual(build.artifacts.count(), 2)
        self.assertNotEqual(manifest_path.read_bytes(), old_manifest)
        addon.finalize_manifest(build.pk)
        build.refresh_from_db()
        self.assertFalse(build.pending_manifest)
        self.assertEqual(build.artifacts.count(), 1)
        self.assertEqual(build.status, "published")

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_artifact_staging_and_memory_bound(self) -> None:
        addon = self.install()
        build = self.register(addon)
        snapshot: TranslationSnapshot = {
            locale: (locale, {("strings", "hello"): Text("Hello")})
            for locale in ("de", "fr")
        }
        buffers: list[ReferenceType[memoryview]] = []

        def compile_locale(
            resources: ResourceTable, *, package: str, locale: str
        ) -> memoryview:
            self.assertTrue(all(buffer() is None for buffer in buffers))
            buffer = memoryview(locale.encode())
            buffers.append(ref(buffer))
            return buffer

        with (
            patch(
                "weblate.kotlin_sdk.preparation.generate", side_effect=compile_locale
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.stage_build(addon, build, locales(snapshot))
        self.assertTrue(all(buffer() is None for buffer in buffers))
        self.assertFalse(list(Path(addon.cdn.cdn_path("artifacts")).glob("staged-*")))
        with (
            patch("weblate.kotlin_sdk.publication.MAX_COMPILATION_BYTES", 1),
            patch("weblate.kotlin_sdk.preparation.generate") as generate,
            self.assertRaisesRegex(ValueError, "compilation estimate"),
        ):
            self.stage_build(addon, build, locales(snapshot))
        generate.assert_not_called()
        with (
            patch(
                "weblate.kotlin_sdk.preparation.generate",
                side_effect=[b"staged", ValueError("compile failed")],
            ),
            self.assertRaisesRegex(ValueError, "compile failed"),
        ):
            self.stage_build(addon, build, locales(snapshot))
        self.assertFalse(list(Path(addon.cdn.cdn_path("artifacts")).glob("staged-*")))

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_imported_references_and_literals(self) -> None:
        addon = self.install()
        translation = self.component.source_translation
        unit = translation.unit_set.earliest("pk")
        Unit.objects.filter(translation__component=self.component).update(
            state=STATE_READONLY
        )
        for prefix in ("@string/", "?attr/"):
            for plural in (False, True):
                for escaped in (False, True):
                    for edited in (False, True):
                        with self.subTest(
                            prefix=prefix, plural=plural, escaped=escaped, edited=edited
                        ):
                            value = prefix + "other"
                            raw = ("\\" if escaped else "") + value
                            xml = (
                                f'<plurals name="alias"><item quantity="one">{raw}</item>'
                                '<item quantity="other">Others</item></plurals>'
                                if plural
                                else f'<string name="alias">{raw}</string>'
                            )
                            template = AndroidFormat(
                                BytesIO(f"<resources>{xml}</resources>".encode()),
                                is_template=True,
                            )
                            store = AndroidFormat(
                                BytesIO(f"<resources>{xml}</resources>".encode()),
                                language_code="en",
                                template_store=template,
                            )
                            wrapper, _ = store.find_unit("alias", "alias")
                            self.assertIsNotNone(wrapper)
                            target = wrapper.target
                            if edited:
                                # A changed plural sibling must not hide the reference.
                                target = (
                                    target.replace("Others", "Updated")
                                    if plural
                                    else "Updated"
                                )
                            translation.unit_set.filter(pk=unit.pk).update(
                                context="alias",
                                source=wrapper.source,
                                target=target,
                                state=STATE_TRANSLATED,
                            )
                            with patch(
                                "weblate.trans.models.Translation.load_store",
                                return_value=store,
                            ):
                                entries = {
                                    language: dict(values.entries)
                                    for language, values in addon.translations()
                                }[translation.language.code]
                            key = ("plurals" if plural else "strings", "alias")
                            if not escaped and (plural or not edited):
                                self.assertNotIn(key, entries)
                            elif plural:
                                self.assertEqual(
                                    entries[key],
                                    {
                                        "one": Text(value),
                                        "other": Text(
                                            "Updated" if edited else "Others"
                                        ),
                                    },
                                )
                            else:
                                self.assertEqual(
                                    entries[key], Text("Updated" if edited else value)
                                )

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_snapshot(self) -> None:
        addon = self.install()
        snapshot = {
            language: (values.locale, dict(values.entries))
            for language, values in addon.translations()
        }
        self.assertTrue(snapshot)
        self.assertTrue(any(entries for _, entries in snapshot.values()))
        build = self.register(addon)
        keys = sorted({key for _, entries in snapshot.values() for key in entries})
        build.metadata["strings"] = {}
        build.metadata["plurals"] = {}
        for index, (kind, name) in enumerate(keys):
            type_id = 8 if kind == "plurals" else 9
            build.metadata[kind][name] = f"0x7f{type_id:02x}{index:04x}"
        build.save(update_fields=["metadata"])
        self.publish(addon)
        build.refresh_from_db()
        self.assertEqual(build.status, "published", build.error)
        self.assertTrue(build.artifacts.exists())

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_locale_streaming(self) -> None:
        addon = self.install()
        with patch.object(
            Translation, "load_store", autospec=True, side_effect=Translation.load_store
        ) as load:
            stream = addon.translations()
            load.assert_not_called()
            first = next(stream)
            list(first.values.entries)
            self.assertEqual(load.call_count, 1)
            second = next(stream)
            list(second.values.entries)
            self.assertEqual(load.call_count, 2)
            self.assertNotEqual(first[0], second[0])
            stream.close()

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_parse_failure_status(self) -> None:
        addon = self.install()
        builds = [self.register(addon, version) for version in (1, 2)]
        for error in (
            FileParseError("broken file"),
            TranslateParseError("broken file"),
        ):
            with (
                self.subTest(error=type(error)),
                patch.object(Translation, "load_store", side_effect=error),
            ):
                outcome = addon.publish()
                self.assertIsNotNone(outcome)
            for build in builds:
                build.refresh_from_db()
                self.assertEqual(build.status, "failed")
                self.assertIn("broken file", build.error)
                self.assertFalse(build.pending_manifest)

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_retirement_cleanup_failure(self) -> None:
        from weblate.kotlin_sdk.api import register_build  # ruff: ignore[import-outside-top-level]

        addon = self.install()
        addon.instance.configuration = {"maximum_versions": 1}
        addon.instance.save()
        self.register(addon)
        addon.instance.sdk_builds.update(created=timezone.now() - timedelta(days=731))
        serializer = BuildMetadataSerializer(data=metadata(2))
        serializer.is_valid(raise_exception=True)
        with (
            patch(
                "weblate.kotlin_sdk.tasks.cleanup_publication",
                side_effect=OSError("cleanup failed"),
            ),
            patch("weblate.kotlin_sdk.tasks.publish_kotlin_sdk.delay") as enqueue,
            self.assertLogs(level="ERROR"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = register_build(
                addon.instance, APIRequestFactory().post("/"), serializer.validated_data
            )
            self.assertEqual(response.status_code, 202)
        enqueue.assert_called_once_with(addon.instance.pk)

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_finalization_starts_artifact_grace(self) -> None:
        addon = self.install()
        build = self.register(addon)
        snapshot: TranslationSnapshot = {
            "fr": ("fr", {("strings", "hello"): Text("Bonjour")})
        }
        with self.captureOnCommitCallbacks(execute=True):
            self.stage_build(addon, build, locales(snapshot))
            addon.finalize_manifest(build.pk)
        artifact = build.artifacts.get()
        self.assertIsNone(artifact.unreferenced)
        now = timezone.now() + timedelta(days=2)
        with (
            patch("weblate.kotlin_sdk.publication.timezone.now", return_value=now),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.stage_build(addon, build, ())
            addon.finalize_manifest(build.pk)
        artifact.refresh_from_db()
        self.assertEqual(artifact.unreferenced, now)
        path = Path(addon.cdn.cdn_path(f"artifacts/{artifact.digest}.arsc"))
        with patch(
            "weblate.kotlin_sdk.publication.timezone.now",
            return_value=now + timedelta(hours=24),
        ):
            addon.cleanup_artifacts()
        self.assertFalse(path.exists())

    @tempdir_setting("LOCALIZE_CDN_PATH")
    def test_publish_retention_and_failure(self) -> None:
        addon = self.install()
        build = self.register(addon)
        snapshot: TranslationSnapshot = {
            "fr": (
                "fr",
                {
                    ("strings", "hello"): Text("Bonjour"),
                    ("plurals", "count"): {
                        "one": Text("Un"),
                        "other": Text("Plusieurs"),
                    },
                },
            )
        }
        manifest_path = Path(addon.cdn.cdn_path("org.weblate.sample/1/manifest.json"))
        with patch.object(addon, "translations", return_value=locales(snapshot)):
            self.publish(addon)
        old_manifest = manifest_path.read_bytes()
        manifest = json.loads(old_manifest)
        artifact_path = (
            manifest_path.parent / manifest["locales"]["fr"]["url"]
        ).resolve()
        self.assertTrue(artifact_path.exists())
        build.refresh_from_db()
        self.assertEqual(build.status, "published")
        with (
            patch.object(addon, "translations", return_value=locales(snapshot)),
            patch(
                "weblate.kotlin_sdk.preparation.generate",
                side_effect=ValueError("broken"),
            ),
        ):
            self.publish(addon)
        self.assertEqual(manifest_path.read_bytes(), old_manifest)
        self.assertTrue(artifact_path.exists())
        self.register(addon, 2)
        addon.instance.configuration = {
            "maximum_versions": 1,
            "maximum_age": 1,
        }
        addon.instance.save()
        KotlinSDKBuild.objects.filter(pk=build.pk).update(
            created=timezone.now() - timedelta(days=2)
        )
        with (
            self.captureOnCommitCallbacks(execute=True),
            patch.object(addon, "translations", return_value=locales(snapshot)),
        ):
            self.publish(addon)
        self.assertFalse(manifest_path.exists())
        self.assertFalse(manifest_path.parent.exists())
        self.assertTrue(artifact_path.exists())
        build.refresh_from_db()
        self.assertEqual(build.status, "retired")
