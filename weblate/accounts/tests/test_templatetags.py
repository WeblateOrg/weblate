# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.management import call_command
from django.template import Context, Template
from django.test import SimpleTestCase, override_settings
from social_core.backends.utils import load_backends

from weblate.accounts.templatetags.authnames import (
    auth_name,
    get_auth_name,
    get_auth_params,
)
from weblate.accounts.templatetags.urlformat import urlformat
from weblate.utils.static import WeblateManifestStaticFilesStorage


class TemplateTagsTestCase(SimpleTestCase):
    def test_add_site_url_filter(self) -> None:
        template = Template("""
                {% load site_url %}
                <html><body>
                {% filter add_site_url %}
                <p>
                    text:
                    <a href="/foo"><span>Foo</span></a>
                </p>
                {% endfilter %}
                <p>
                {% filter add_site_url %}
                    other&amp;
                {% endfilter %}
                </p>
                </body>
                </html>
            """)
        self.assertHTMLEqual(
            """
            <html>
            <body>
                <p>
                    text:
                    <a href="http://example.com/foo">
                        <span>
                            Foo
                        </span>
                    </a>
                </p>
                <p>other&amp;</p>
            </body>
            </html>
            """,
            template.render(Context()),
        )

    def test_urlformat(self) -> None:
        self.assertEqual(urlformat("https://weblate.org/"), "weblate.org")
        self.assertEqual(urlformat("https://weblate.org/user/"), "weblate.org/user")
        self.assertEqual(
            urlformat("https://weblate.org/user/xxxxxxxxxxxxxxxxxxxxxxxxx"),
            "weblate.org",
        )

    @override_settings(
        AUTHENTICATION_BACKENDS=[
            "social_core.backends.azuread.AzureADOAuth2",
            "social_core.backends.azuread_tenant.AzureADTenantOAuth2",
        ]
    )
    def test_microsoft_entra_defaults(self) -> None:
        load_backends([], force_load=True)
        self.addCleanup(load_backends, [], force_load=True)
        self.assertEqual(get_auth_name("azuread-oauth2"), "Microsoft")
        self.assertEqual(
            get_auth_params("azuread-tenant-oauth2")["image"],
            "social_auth/icons/microsoft.svg",
        )


@override_settings(
    AUTHENTICATION_BACKENDS=[
        "social_core.backends.github.GithubOAuth2",
        "social_core.backends.openinfra.OpenInfraOpenId",
        "social_core.backends.twitter_oauth2.TwitterOAuth2",
    ]
)
class AuthMetadataTest(SimpleTestCase):
    def setUp(self) -> None:
        load_backends([], force_load=True)
        self.addCleanup(load_backends, [], force_load=True)

    def test_shared_metadata(self) -> None:
        self.assertEqual(get_auth_name("github"), "GitHub")
        self.assertEqual(get_auth_name("twitter-oauth2"), "X")
        self.assertEqual(
            get_auth_params("github")["image"], "social_auth/icons/github.svg"
        )
        self.assertEqual(get_auth_params("openinfra")["image"], "password.svg")

    def test_local_and_unknown_labels(self) -> None:
        self.assertEqual(str(get_auth_name("password")), "Password")
        self.assertEqual(str(get_auth_name("email")), "E-mail")
        self.assertEqual(get_auth_name("unknown-provider"), "Unknown-Provider")

    @override_settings(
        SOCIAL_AUTH_GITHUB_TITLE="Company <account>",
        SOCIAL_AUTH_GITHUB_IMAGE="company.svg",
    )
    def test_overrides_and_escaping(self) -> None:
        with (
            patch(
                "weblate.accounts.templatetags.authnames.finders.find",
                return_value=None,
            ),
            patch(
                "weblate.accounts.templatetags.authnames.staticfiles_storage.url",
                return_value="/static/auth/company.svg",
            ) as url,
        ):
            result = auth_name("github")
        url.assert_called_once_with("auth/company.svg")
        self.assertIn("Company &lt;account&gt;", result)
        self.assertIn('alt="" aria-hidden="true"', result)

    @override_settings(SOCIAL_AUTH_GITHUB_IMAGE="github.svg")
    def test_legacy_bundled_image(self) -> None:
        with (
            patch(
                "weblate.accounts.templatetags.authnames.finders.find",
                side_effect=[None, "/core/github.svg"],
            ),
            patch(
                "weblate.accounts.templatetags.authnames.staticfiles_storage.url",
                return_value="/static/shared.svg",
            ) as url,
        ):
            auth_name("github")
        url.assert_called_once_with("social_auth/icons/github.svg")

    @override_settings(SOCIAL_AUTH_GITHUB_IMAGE="github.svg")
    def test_legacy_local_image_precedence(self) -> None:
        with (
            patch(
                "weblate.accounts.templatetags.authnames.finders.find",
                return_value="/local/github.svg",
            ),
            patch(
                "weblate.accounts.templatetags.authnames.staticfiles_storage.url",
                return_value="/static/local.svg",
            ) as url,
        ):
            auth_name("github")
        url.assert_called_once_with("auth/github.svg")

    def test_external_images(self) -> None:
        for image in (
            "https://example.com/icon.svg",
            "data:image/svg+xml;base64,PHN2Zz4=",
        ):
            with (
                self.subTest(image=image),
                override_settings(SOCIAL_AUTH_GITHUB_IMAGE=image),
                patch(
                    "weblate.accounts.templatetags.authnames.staticfiles_storage.url"
                ) as url,
            ):
                self.assertEqual(auth_name("github", only="image"), image)
                url.assert_not_called()

    @override_settings(
        STORAGES={
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        }
    )
    def test_shared_and_local_icon_rendering(self) -> None:
        shared = auth_name("github")
        self.assertIn("social_auth/icons/github.svg", shared)
        self.assertIn("GitHub", shared)
        for backend in ("password", "openinfra", "unknown-provider"):
            with self.subTest(backend=backend):
                self.assertIn("auth/password.svg", auth_name(backend))
        self.assertIn("auth/email.svg", auth_name("email"))

    def test_shared_icons_with_weblate_manifest_storage(self) -> None:
        with TemporaryDirectory() as source_dir, TemporaryDirectory() as static_root:
            source = Path(source_dir)
            source.joinpath("auth").mkdir()
            local_icons = Path(__file__).parents[2] / "static" / "auth"
            for filename in ("password.svg", "email.svg"):
                source.joinpath("auth", filename).write_bytes(
                    local_icons.joinpath(filename).read_bytes()
                )
            source.joinpath("auth", "github.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"></svg>',
                encoding="utf-8",
            )

            with override_settings(
                DEBUG=False,
                STATIC_ROOT=static_root,
                STATICFILES_DIRS=(source_dir,),
                STATICFILES_FINDERS=(
                    "django.contrib.staticfiles.finders.FileSystemFinder",
                    "social_django.finders.SocialAuthIconFinder",
                ),
                STORAGES={
                    "staticfiles": {
                        "BACKEND": "weblate.utils.static.WeblateManifestStaticFilesStorage"
                    },
                },
            ):
                call_command("collectstatic", interactive=False, verbosity=0)
                assert isinstance(
                    staticfiles_storage, WeblateManifestStaticFilesStorage
                )
                icons = files("social_core").joinpath("static", "social_auth", "icons")
                for asset in icons.iterdir():
                    with self.subTest(icon=asset.name):
                        path = f"social_auth/icons/{asset.name}"
                        url = staticfiles_storage.url(path)
                        self.assertRegex(url, r"\.[0-9a-f]{12}\.svg$")
                        hashed_path = url.removeprefix(staticfiles_storage.base_url)
                        self.assertEqual(
                            Path(static_root, hashed_path).read_bytes(),
                            asset.read_bytes(),
                        )

                for backend, path in (
                    ("github", "social_auth/icons/github.svg"),
                    ("twitter-oauth2", "social_auth/icons/x.svg"),
                    ("password", "auth/password.svg"),
                    ("email", "auth/email.svg"),
                    ("openinfra", "auth/password.svg"),
                ):
                    with self.subTest(backend=backend):
                        self.assertIn(staticfiles_storage.url(path), auth_name(backend))

                with override_settings(SOCIAL_AUTH_GITHUB_IMAGE="github.svg"):
                    self.assertIn(
                        staticfiles_storage.url("auth/github.svg"), auth_name("github")
                    )
                with override_settings(SOCIAL_AUTH_GITHUB_IMAGE="x.svg"):
                    self.assertIn(
                        staticfiles_storage.url("social_auth/icons/x.svg"),
                        auth_name("github"),
                    )
                self.assertTrue(Path(static_root, "staticfiles.json").is_file())
