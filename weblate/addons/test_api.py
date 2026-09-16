# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from io import BytesIO
from threading import Barrier
from types import ModuleType
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.urls import include, path, resolve, reverse
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.test import APIClient

from weblate.addons.api import (
    BoundedJSONParser,
    InstalledAddonAPIView,
    api_patterns,
    api_providers,
)
from weblate.addons.base import BaseAddon
from weblate.addons.models import ADDONS, Addon
from weblate.api.serializers import AddonSerializer
from weblate.auth.models import User
from weblate.trans.models import Category, Component
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import RepoTestMixin

if TYPE_CHECKING:
    from django.urls.resolvers import URLPattern
    from rest_framework.request import Request


class ExampleView(InstalledAddonAPIView):
    addon_name = "test.api-provider"

    def get(self, request: Request, **kwargs: str) -> Response:
        return Response({"value": kwargs["value"]})


class ExampleProvider(BaseAddon):
    name = "test.api-provider"
    api_name = "example"
    needs_component = True

    @classmethod
    def get_api_urls(cls) -> tuple[URLPattern, ...]:
        return (path("values/<int:value>/", ExampleView.as_view(), name="value"),)


class OtherProvider(ExampleProvider):
    name = "test.other-provider"


@override_settings(WEBLATE_ADDONS=["weblate.addons.test_api.ExampleProvider"])
class ConcurrentInstallationTest(RepoTestMixin, TransactionTestCase):
    def test_duplicate_installation(self) -> None:
        component = self.create_po()
        barrier = Barrier(2)

        def install() -> str:
            try:
                barrier.wait(timeout=10)
                ExampleProvider.create(component=component, run=False)
            except ValidationError:
                return "duplicate"
            finally:
                connections.close_all()
            return "created"

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(install) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]
        self.assertCountEqual(results, ["created", "duplicate"])
        self.assertEqual(Addon.objects.filter(component=component).count(), 1)


@override_settings(WEBLATE_ADDONS=["weblate.addons.test_api.ExampleProvider"])
class ProviderTest(SimpleTestCase):
    def test_bounded_json_parser(self) -> None:
        parser = BoundedJSONParser()
        parser.max_body_size = 16
        self.assertEqual(parser.parse(BytesIO(b'{"value": 42}')), {"value": 42})
        for body in (b"x" * 17, b"{", b'"\xff"', b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(body=body), self.assertRaises(ParseError):
                parser.parse(BytesIO(body))

    def test_names(self) -> None:
        names: tuple[object, ...] = (
            "",
            42,
            False,
            [],
            "foo.bar",
            "foo/bar",
            "foo bar",
            "foo\n",
            "x" * 65,
        )
        for name in names:
            with (
                self.subTest(name=name),
                patch.object(ExampleProvider, "api_name", name),
                self.assertRaises(ImproperlyConfigured),
            ):
                api_providers()
        with patch.object(ExampleProvider, "api_name", "Example_API" + "x" * 53):
            self.assertIn(ExampleProvider.api_name, api_providers())

    def test_duplicate_provider(self) -> None:
        with (
            patch.dict(ADDONS.data, {OtherProvider.name: OtherProvider}),
            self.assertRaisesMessage(ImproperlyConfigured, "Duplicate add-on API name"),
        ):
            api_providers()

    def test_scope(self) -> None:
        for attribute, value in (
            ("repo_scope", True),
            ("needs_component", False),
            ("multiple", True),
        ):
            with (
                self.subTest(attribute=attribute),
                patch.object(ExampleProvider, attribute, value),
                self.assertRaisesMessage(
                    ImproperlyConfigured, "single-installation component"
                ),
            ):
                api_providers()

    def test_patterns_without_installations(self) -> None:
        module = ModuleType("addon_test_urls")
        module.__dict__["urlpatterns"] = api_patterns()
        with patch.dict(sys.modules, {module.__name__: module}):
            match = resolve(
                "/components/project/component/addons/example/values/42/",
                urlconf=module.__name__,
            )
        self.assertEqual(match.kwargs["value"], 42)
        self.assertEqual(match.func.view_class.addon_name, ExampleProvider.name)  # type: ignore[attr-defined]
        with override_settings(WEBLATE_ADDONS=[]):
            self.assertEqual(api_patterns(), [])
        self.assertTrue(api_patterns())


class InstallationTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        # Load the normal routes before replacing the provider registry.
        original_patterns = import_module(settings.ROOT_URLCONF).urlpatterns
        self.enterContext(
            override_settings(
                WEBLATE_ADDONS=["weblate.addons.test_api.ExampleProvider"]
            )
        )
        module = ModuleType("addon_installation_urls")
        module.__dict__["urlpatterns"] = [
            path("api/", include(api_patterns())),
            *original_patterns,
        ]
        self.enterContext(patch.dict(sys.modules, {module.__name__: module}))
        self.enterContext(override_settings(ROOT_URLCONF=module.__name__))

    def install(self) -> ExampleProvider:
        return ExampleProvider.create(
            component=self.component, configuration={}, run=False
        )

    def test_permissions_and_installation(self) -> None:
        client = APIClient()
        client.force_authenticate(self.user)
        url = f"/api/components/{self.project.slug}/{self.component.slug}/addons/example/values/42/"
        self.assertEqual(client.get(url).status_code, 404)
        self.install()
        self.assertEqual(client.get(url).status_code, 403)
        self.make_manager()
        client.force_authenticate(User.objects.get(pk=self.user.pk))
        self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(client.post(url).status_code, 405)
        with patch.object(ExampleProvider, "can_process", return_value=False):
            self.assertEqual(client.get(url).status_code, 404)
        with override_settings(WEBLATE_ADDONS=[]):
            self.assertEqual(client.get(url).status_code, 404)

    def test_state_only_save(self) -> None:
        addon = self.install()
        for number, fields in enumerate(
            (["state"], ("state",), {"state"}, iter(["state"])), 1
        ):
            with self.subTest(fields=fields), self.assertNumQueries(3):
                addon.instance.state["test"] = number
                addon.instance.save(update_fields=fields)
        addon.instance.refresh_from_db()
        self.assertEqual(addon.instance.state["test"], 4)
        self.assertEqual(addon.instance.api_name, "example")

    def test_api_discovery(self) -> None:
        addon = self.install()
        serializer = AddonSerializer(addon.instance, context={"request": None})
        self.assertEqual(serializer.data["api_name"], "example")
        self.assertEqual(
            serializer.data["api_url"],
            f"/api/components/{self.project.slug}/{self.component.slug}/addons/example/",
        )

    def test_duplicate_installation(self) -> None:
        self.install()
        with self.assertRaisesMessage(ValidationError, "already installed"):
            self.install()
        self.assertEqual(self.component.addon_set.count(), 1)

    def test_duplicate_installation_api(self) -> None:
        self.make_manager()
        self.install()
        client = APIClient()
        client.force_authenticate(User.objects.get(pk=self.user.pk))
        # Simulate another request inserting after validation has passed.
        with patch.object(AddonSerializer, "check_addon"):
            response = client.post(
                f"/api/components/{self.project.slug}/{self.component.slug}/addons/",
                {
                    "name": ExampleProvider.name,
                    "component": f"http://testserver/api/components/{self.project.slug}/{self.component.slug}/",
                    "configuration": {},
                },
                format="json",
            )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertContains(response, "already installed", status_code=400)

    def test_discovery_tracks_provider(self) -> None:
        addon = self.install().instance
        self.assertEqual(addon.api_name, "example")
        self.assertIsNotNone(addon.api_url)
        with override_settings(WEBLATE_ADDONS=[]):
            data = AddonSerializer(addon, context={"request": None}).data
            self.assertIsNone(data["api_name"])
            self.assertIsNone(data["api_url"])
        with patch.object(ExampleProvider, "can_process", return_value=False):
            self.assertIsNone(addon.api_url)
        with patch.object(ExampleProvider, "api_name", "renamed"):
            self.assertTrue((addon.api_url or "").endswith("/addons/renamed/"))

    def test_duplicate_installation_ui(self) -> None:
        self.make_manager()

        def install_before_insert(_component: Component) -> bool:
            self.install()
            return True

        with patch.object(
            ExampleProvider, "api_available", side_effect=install_before_insert
        ):
            response = self.client.post(
                reverse("addons", kwargs=self.kw_component),
                {"name": ExampleProvider.name, "form": "1"},
                follow=True,
            )
        self.assertContains(response, "already installed")
        self.assertEqual(self.component.addon_set.count(), 1)

    def test_duplicate_installation_command(self) -> None:
        def install_before_insert(_component: Component) -> bool:
            self.install()
            return True

        with (
            patch.object(
                ExampleProvider, "api_available", side_effect=install_before_insert
            ),
            self.assertRaisesMessage(CommandError, "already installed"),
        ):
            call_command(
                "install_addon", self.component.full_slug, addon=ExampleProvider.name
            )
        self.assertEqual(self.component.addon_set.count(), 1)

    def test_categorized_component(self) -> None:
        self.make_manager()
        parent = self.create_category(self.project)
        child = Category.objects.create(
            name="Nested", slug="nested", project=self.project, category=parent
        )
        Component.objects.filter(pk=self.component.pk).update(category=child)
        self.component.refresh_from_db()
        addon = self.install().instance
        client = APIClient()
        client.force_authenticate(User.objects.get(pk=self.user.pk))
        expected = f"{parent.slug}%252Fnested%252F{self.component.slug}"
        self.assertIn(expected, addon.api_url or "")
        response = client.get(f"{addon.api_url}values/42/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            client.get(
                f"/api/components/{self.project.slug}/{self.component.slug}/addons/example/values/42/"
            ).status_code,
            404,
        )
        # A root component with the same slug must not make either lookup ambiguous.
        duplicate = Component.objects.get(pk=self.component.pk)
        duplicate.pk = None
        duplicate.category = None
        Component.objects.bulk_create([duplicate])
        ExampleProvider.create(component=duplicate, run=False)
        self.assertEqual(client.get(f"{addon.api_url}values/42/").status_code, 200)
        self.assertEqual(
            client.get(
                f"/api/components/{self.project.slug}/{duplicate.slug}/addons/example/values/42/"
            ).status_code,
            200,
        )
