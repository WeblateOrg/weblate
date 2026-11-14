# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for sitemaps."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from weblate.trans.models import Change, ComponentLink, Project
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.stats import ProjectLanguage
from weblate.utils.xml import parse_xml


class PagesSitemapTest(TestCase):
    @override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
    )
    def test_sitemap_without_changes(self) -> None:
        self.assertFalse(Change.objects.exists())
        response = self.client.get(reverse("sitemap", kwargs={"section": "pages"}))
        self.assertEqual(response.status_code, 200)
        tree = parse_xml(response.content)
        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        self.assertEqual(tree.tag, f"{namespace}urlset")
        urls = tree.findall(f"{namespace}url")
        self.assertTrue(urls)
        self.assertTrue(all(url.findtext(f"{namespace}loc") for url in urls))
        self.assertFalse(tree.findall(f"{namespace}url/{namespace}lastmod"))


class SitemapTest(FixtureTestCase):
    def assert_sitemap_entry(
        self, section: str, location: str, *, present: bool
    ) -> None:
        response = self.client.get(reverse("sitemap", kwargs={"section": section}))
        assertion = self.assertContains if present else self.assertNotContains
        assertion(response, location)

    def set_project_access(
        self, access_control: int, *, public_sharing: bool = False
    ) -> None:
        self.project.access_control = access_control
        self.project.public_sharing = public_sharing
        self.project.save(update_fields=["access_control", "public_sharing"])
        cache.clear()

    def test_sitemaps(self) -> None:
        # Get root sitemap
        response = self.client.get("/sitemap.xml")
        self.assertContains(response, "<sitemapindex")

        # Parse it
        tree = parse_xml(response.content)
        sitemaps = tree.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap")
        for sitemap in sitemaps:
            location = sitemap.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
            if location is None or location.text is None:
                self.fail("Sitemap index entry has no location")
            response = self.client.get(location.text)
            self.assertContains(response, "<urlset")
            # Try if it's a valid XML
            parse_xml(response.content)

    @override_settings(REQUIRE_LOGIN=True, PUBLIC_ENGAGE=True)
    def test_public_engage_sitemap_index(self) -> None:
        response = self.client.get("/sitemap.xml")

        for section in ("engage", "engagelang"):
            self.assertContains(
                response, reverse("sitemap", kwargs={"section": section})
            )
        for section in ("project", "component", "translation", "pages"):
            self.assertNotContains(
                response, reverse("sitemap", kwargs={"section": section})
            )

    def test_public_and_protected_project_sitemaps(self) -> None:
        self.client.logout()
        locations = {
            "project": self.project.get_absolute_url(),
            "component": self.component.get_absolute_url(),
            "translation": self.translation.get_absolute_url(),
            "engage": reverse("engage", kwargs={"path": self.project.get_url_path()}),
            "engagelang": reverse(
                "engage",
                kwargs={
                    "path": ProjectLanguage(
                        self.project, self.translation.language
                    ).get_url_path()
                },
            ),
        }

        for access_control in (Project.ACCESS_PUBLIC, Project.ACCESS_PROTECTED):
            for public_sharing in (False, True):
                with self.subTest(
                    access_control=access_control, public_sharing=public_sharing
                ):
                    self.set_project_access(
                        access_control, public_sharing=public_sharing
                    )
                    for section, location in locations.items():
                        self.assert_sitemap_entry(section, location, present=True)

    def test_private_project_public_sharing_sitemaps(self) -> None:
        self.client.logout()
        direct_locations = {
            "project": self.project.get_absolute_url(),
            "component": self.component.get_absolute_url(),
            "translation": self.translation.get_absolute_url(),
        }
        sharing_locations = {
            "engage": reverse("engage", kwargs={"path": self.project.get_url_path()}),
            "engagelang": reverse(
                "engage",
                kwargs={
                    "path": ProjectLanguage(
                        self.project, self.translation.language
                    ).get_url_path()
                },
            ),
        }

        for access_control in (Project.ACCESS_PRIVATE, Project.ACCESS_CUSTOM):
            with self.subTest(access_control=access_control, public_sharing=False):
                self.set_project_access(access_control)
                for section, location in (direct_locations | sharing_locations).items():
                    self.assert_sitemap_entry(section, location, present=False)

            with self.subTest(access_control=access_control, public_sharing=True):
                self.set_project_access(access_control, public_sharing=True)
                for section, location in direct_locations.items():
                    self.assert_sitemap_entry(section, location, present=False)
                for section, location in sharing_locations.items():
                    self.assert_sitemap_entry(section, location, present=True)

    def test_restricted_component_sitemaps(self) -> None:
        self.set_project_access(Project.ACCESS_PUBLIC)
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        self.client.logout()

        self.assertEqual(
            self.client.get(self.component.get_absolute_url()).status_code, 404
        )
        self.assert_sitemap_entry(
            "component", self.component.get_absolute_url(), present=False
        )
        self.assert_sitemap_entry(
            "translation", self.translation.get_absolute_url(), present=False
        )
        self.assert_sitemap_entry(
            "project", self.project.get_absolute_url(), present=True
        )
        self.assert_sitemap_entry(
            "engage",
            reverse("engage", kwargs={"path": self.project.get_url_path()}),
            present=True,
        )

    def test_shared_component_language_in_engage_sitemap(self) -> None:
        shared_project = Project.objects.create(
            name="Shared project",
            slug="shared-project",
            access_control=Project.ACCESS_PRIVATE,
            public_sharing=True,
        )
        ComponentLink.objects.create(component=self.component, project=shared_project)
        cache.clear()
        self.client.logout()

        self.assert_sitemap_entry(
            "engagelang",
            reverse(
                "engage",
                kwargs={
                    "path": ProjectLanguage(
                        shared_project, self.translation.language
                    ).get_url_path()
                },
            ),
            present=True,
        )
