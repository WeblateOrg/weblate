# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import sys
from types import ModuleType
from typing import Any, NamedTuple

import django

_BOOTSTRAP_STATE = {"done": False}


class _StubManager:
    def filter(self, *args, **kwargs) -> list[object]:
        return []

    def all(self) -> list[object]:
        return []

    def create(self, *args, **kwargs) -> object:
        return object()

    def first(self) -> None:
        return None


class _StubView:
    @classmethod
    def as_view(cls, *_args, **_kwargs):
        def view(*_args, **_kwargs):
            return None

        return view


class _FontDimensions(NamedTuple):
    width: int
    height: int


def _install_font_utils_stub() -> None:
    """Provide lightweight font shims for fuzz startup."""
    if "weblate.fonts.utils" in sys.modules:
        return

    module: Any = ModuleType("weblate.fonts.utils")
    font_weights = {
        "normal": 400,
        "light": 300,
        "bold": 700,
        "": None,
    }

    def configure_fontconfig() -> None:
        return

    def get_font_weight(weight: str) -> int | None:
        return font_weights[weight]

    def render_size(
        text: str,
        *,
        font: str = "Kurinto Sans",
        weight: int | None = 400,
        size: int = 11,
        spacing: int = 0,
        width: int = 1000,
        lines: int = 1,
        cache_key: str | None = None,
        surface_height: int | None = None,
        surface_width: int | None = None,
        use_cache: bool = True,
    ) -> tuple[_FontDimensions, int]:
        del font, weight, spacing, cache_key, surface_height, surface_width, use_cache
        line_count = max(1, min(lines, text.count("\n") + 1))
        estimated_width = min(width, max(1, len(text) * max(size // 2, 1)))
        return _FontDimensions(
            width=estimated_width, height=size * line_count
        ), line_count

    def check_render_size(**kwargs) -> bool:
        rendered_size, actual_lines = render_size(**kwargs)
        return (
            rendered_size.width <= kwargs["width"] and actual_lines <= kwargs["lines"]
        )

    def get_font_name(*_args, **_kwargs) -> tuple[str, str]:
        return ("Kurinto Sans", "Regular")

    module.Dimensions = _FontDimensions
    module.FONT_WEIGHTS = font_weights
    module.configure_fontconfig = configure_fontconfig
    module.get_font_weight = get_font_weight
    module.render_size = render_size
    module.check_render_size = check_render_size
    module.get_font_name = get_font_name

    sys.modules["weblate.fonts.utils"] = module


def _install_webauthn_stubs() -> None:
    """Provide lightweight WebAuthn shims for fuzz startup."""
    if "django_otp_webauthn" in sys.modules:
        return

    package: Any = ModuleType("django_otp_webauthn")
    package.__path__ = []

    models: Any = ModuleType("django_otp_webauthn.models")
    helpers: Any = ModuleType("django_otp_webauthn.helpers")
    exceptions: Any = ModuleType("django_otp_webauthn.exceptions")
    views: Any = ModuleType("django_otp_webauthn.views")

    class WebAuthnCredential:
        objects = _StubManager()

    class WebAuthnHelper:
        pass

    class OTPWebAuthnApiError(Exception):
        pass

    class BeginCredentialAuthenticationView(_StubView):
        pass

    class CompleteCredentialAuthenticationView(_StubView):
        pass

    class BeginCredentialRegistrationView(_StubView):
        pass

    class CompleteCredentialRegistrationView(_StubView):
        pass

    models.WebAuthnCredential = WebAuthnCredential
    helpers.WebAuthnHelper = WebAuthnHelper
    exceptions.OTPWebAuthnApiError = OTPWebAuthnApiError
    views.BeginCredentialAuthenticationView = BeginCredentialAuthenticationView
    views.CompleteCredentialAuthenticationView = CompleteCredentialAuthenticationView
    views.BeginCredentialRegistrationView = BeginCredentialRegistrationView
    views.CompleteCredentialRegistrationView = CompleteCredentialRegistrationView

    package.models = models
    package.helpers = helpers
    package.exceptions = exceptions
    package.views = views

    sys.modules["django_otp_webauthn"] = package
    sys.modules["django_otp_webauthn.models"] = models
    sys.modules["django_otp_webauthn.helpers"] = helpers
    sys.modules["django_otp_webauthn.exceptions"] = exceptions
    sys.modules["django_otp_webauthn.views"] = views


def bootstrap_django() -> None:
    """Initialize Django once for fuzz targets."""
    if _BOOTSTRAP_STATE["done"]:
        return

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "weblate.settings_fuzz")
    os.environ.setdefault("CI_DB_HOST", "127.0.0.1")
    os.environ.setdefault("CI_DB_NAME", "weblate")
    os.environ.setdefault("CI_DB_USER", "weblate")
    os.environ.setdefault("CI_DB_PASSWORD", "weblate")
    os.environ.setdefault("CI_DB_PORT", "5432")

    _install_font_utils_stub()
    _install_webauthn_stubs()
    django.setup()
    _BOOTSTRAP_STATE["done"] = True
