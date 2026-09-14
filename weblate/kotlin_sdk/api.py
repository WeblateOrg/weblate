# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Kotlin SDK build registration and versioned CDN publication."""

# Kotlin SDK metadata uses camelCase field names.

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any, cast

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.reverse import reverse

from weblate.addons.api import InstalledAddonAPIView
from weblate.kotlin_sdk.publication import Publication

if TYPE_CHECKING:
    from django.urls.resolvers import URLPattern
    from rest_framework.request import Request

    from weblate.addons.models import Addon
    from weblate.kotlin_sdk.addons import KotlinSDKAddon
    from weblate.kotlin_sdk.models import KotlinSDKBuild

MAX_BUILD_RECORDS = 1000

API_DESCRIPTION = (
    "The Kotlin SDK API is in beta. No compatibility is guaranteed until the "
    "final Kotlin SDK is released. Endpoints, build metadata, CDN manifests, and "
    "generated resource formats may change without backward compatibility."
)


class BuildMetadataSerializer(serializers.Serializer):
    schemaVersion = serializers.IntegerField(  # ruff: ignore[mixed-case-variable-in-class-scope]
        default=1,
        min_value=1,
        max_value=1,
        help_text="Metadata format version. Only version 1 is supported.",
    )
    packageName = serializers.RegexField(  # ruff: ignore[mixed-case-variable-in-class-scope]
        r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+\Z",
        max_length=127,
        trim_whitespace=False,
        help_text="Android application package name from the final installed build. Leading or trailing whitespace is rejected.",
    )
    versionCode = serializers.IntegerField(  # ruff: ignore[mixed-case-variable-in-class-scope]
        min_value=1,
        max_value=2100000000,
        help_text="Android version code. Together with packageName, identifies an immutable resource mapping.",
    )
    strings = serializers.DictField(
        child=serializers.RegexField(r"^0x[0-9a-fA-F]{8}$"),
        default=dict,
        help_text='String resource names mapped to final resource IDs, for example {"welcome": "0x7f090003"}. Defaults to an empty object. Translated values come from Weblate.',
    )
    plurals = serializers.DictField(
        child=serializers.RegexField(r"^0x[0-9a-fA-F]{8}$"),
        default=dict,
        help_text='Plural resource names mapped to final resource IDs, for example {"count": "0x7f080004"}. Defaults to an empty object. Quantities and translated values come from Weblate, not this mapping.',
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if self.initial_data.keys() - self.fields.keys():
            msg = "Unknown metadata fields."
            raise serializers.ValidationError(msg)
        total = len(attrs["strings"]) + len(attrs["plurals"])
        if not 0 < total <= 100000:
            msg = "Expected between 1 and 100000 resources."
            raise serializers.ValidationError(msg)
        ids = set()
        package_ids = set()
        types = []
        for kind in ("strings", "plurals"):
            type_ids = set()
            for name, value in attrs[kind].items():
                if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.]*", name):
                    msg = "Invalid Android resource name."
                    raise serializers.ValidationError(msg)
                resource_id = int(value, 16)
                if resource_id in ids or resource_id >> 16 & 0xFF == 0:
                    msg = "Duplicate or invalid resource ID."
                    raise serializers.ValidationError(msg)
                ids.add(resource_id)
                package_ids.add(resource_id >> 24)
                type_ids.add(resource_id >> 16 & 0xFF)
                attrs[kind][name] = f"0x{resource_id:08x}"
            if len(type_ids) > 1:
                msg = "A resource kind must have one type ID."
                raise serializers.ValidationError(msg)
            types.append(type_ids)
        if package_ids != {0x7F} or types[0] & types[1]:
            msg = "Expected app package IDs and distinct string/plural types."
            raise serializers.ValidationError(msg)
        return attrs


class BuildConflictSerializer(serializers.Serializer):
    detail = serializers.CharField(
        help_text="The package and version have a different resource mapping, or the add-on has reached its limit of 1000 registration records. Retry new registrations after retired records are cleaned up. Identical retries remain accepted."
    )


class BuildStatusSerializer(serializers.Serializer):
    packageName = serializers.CharField(  # ruff: ignore[mixed-case-variable-in-class-scope]
        help_text="Registered Android application package name."
    )
    versionCode = serializers.IntegerField(help_text="Registered Android version code.")  # ruff: ignore[mixed-case-variable-in-class-scope]
    status = serializers.CharField(
        help_text="Publication state: pending, published, failed, or retired. A failed replacement can still have a previous successful manifest. Retired versions do not reactivate on repeat uploads."
    )
    error = serializers.CharField(
        help_text="Publication error details, or an empty string when there is no error."
    )
    manifest_url = serializers.URLField(
        help_text="Public CDN manifest URL. Publication is asynchronous, so this URL may initially return 404. Retired manifests are removed. The JSON manifest contains schemaVersion (1), packageName, versionCode, and locales keyed by Weblate language code. Each locale contains url (relative to this manifest URL), sha256, and size (bytes) for an immutable ARSC artifact. Revalidate manifests, verify artifact size and hash, and preserve bundled resources on download failure."
    )
    status_url = serializers.URLField(
        help_text="Authenticated GET endpoint for polling this registration's publication state."
    )


def build_status(
    addon: Addon, request: Request, build: KotlinSDKBuild
) -> dict[str, Any]:
    component = addon.component
    if component is None:
        msg = "Kotlin SDK add-on requires a component"
        raise ValueError(msg)
    return {
        "packageName": build.package_name,
        "versionCode": build.version_code,
        "status": build.status,
        "error": build.error,
        "manifest_url": cast("KotlinSDKAddon", addon.addon).cdn_url(
            f"{build.package_name}/{build.version_code}/manifest.json"
        ),
        "status_url": reverse(
            "api:kotlin-sdk:build-status",
            kwargs={
                "project__slug": component.project.slug,
                "slug": component.slug,
                "package": build.package_name,
                "version": build.version_code,
            },
            request=request,
        ),
    }


def register_build(addon: Addon, request: Request, data: dict[str, Any]) -> Response:
    from weblate.addons.models import Addon  # ruff: ignore[import-outside-top-level]
    from weblate.kotlin_sdk.models import KotlinSDKBuild  # ruff: ignore[import-outside-top-level]

    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    with transaction.atomic():
        addon = Addon.objects.select_for_update().get(pk=addon.pk)
        publisher = Publication(addon)
        publisher.expire_builds()
        build = addon.sdk_builds.filter(
            package_name=data["packageName"], version_code=data["versionCode"]
        ).first()
        created = build is None
        if build is None:
            if addon.sdk_builds.count() >= MAX_BUILD_RECORDS:
                return Response(
                    {
                        "detail": "Kotlin SDK registration storage limit reached. Retry after retired registrations are cleaned up."
                    },
                    status=409,
                )
            publisher.expire_builds(reserve=1)
            build = KotlinSDKBuild.objects.create(
                addon=addon,
                package_name=data["packageName"],
                version_code=data["versionCode"],
                metadata=data,
                digest=digest,
            )
        if build.digest != digest:
            return Response(
                {
                    "detail": "This package/version already has a different resource mapping."
                },
                status=409,
            )
        if build.retired is None:
            cast("KotlinSDKAddon", addon.addon).schedule()
        return Response(
            build_status(addon, request, build), status=202 if created else 200
        )


def get_build(
    addon: Addon, request: Request, data: None, package: str, version: int
) -> Response:
    if not 1 <= version <= 2100000000 or not re.fullmatch(r"[A-Za-z0-9_.]+", package):
        from rest_framework.exceptions import NotFound  # ruff: ignore[import-outside-top-level]

        raise NotFound
    build = get_object_or_404(
        addon.sdk_builds, package_name=package, version_code=version
    )
    return Response(build_status(addon, request, build))


AVAILABILITY = "\n\nRequires the Kotlin SDK CDN add-on (`weblate.cdn.kotlin`) installed directly on the component and `component.edit` permission."


class BuildRegistrationView(InstalledAddonAPIView):
    addon_name = "weblate.cdn.kotlin"
    serializer_class = BuildMetadataSerializer

    @extend_schema(
        operation_id="api_components_addons_kotlin_sdk_builds_create",
        responses={
            200: BuildStatusSerializer,
            202: BuildStatusSerializer,
            409: BuildConflictSerializer,
        },
        description=(
            API_DESCRIPTION
            + "\n\n"
            + (
                "Register resource IDs from a final Android build for the Kotlin SDK CDN add-on. "
                "Send application/json using an API token with component.edit permission. "
                "Keep the token in the build environment, never in the application.\n\n"
                "The request limit is 5 MiB and 100000 resources combined across strings and plurals, "
                "with at least one resource required. Names must match [a-zA-Z_][a-zA-Z0-9_.]*. "
                "IDs must belong to app package 0x7f, with one nonzero type ID per resource kind "
                "and distinct type IDs for strings and plurals. The same name may appear in both "
                "maps with different IDs. Duplicate IDs, invalid names, unknown fields, and "
                "unsupported schema versions are rejected with 400.\n\n"
                "Returns 202 for a new registration, 200 for identical existing metadata, "
                "or 409 for conflicting metadata or aggregate storage capacity. Publication is "
                "asynchronous: poll status_url; manifest_url need not exist yet. Repeat uploads "
                "do not extend retention or reactivate retained retired records.\n\n"
                "Add-on configuration maximum_versions defaults to 20 (range 1-100), and "
                "maximum_age defaults to 365 days (range 1-730), measured from first registration. "
                "Limits apply across all package names. One additional unpublished replacement is allowed. "
                "New registrations can retire older unpublished replacements, but published builds are "
                "retired for the version limit only after a replacement is published. Failed replacements "
                "preserve existing publications; maximum-age expiry still applies independently. "
                "Expiry is enforced on registration, publication, and daily cleanup. "
                "Retirement immediately clears metadata. Lightweight retired records are deleted "
                "on cleanup after 24 hours and successful manifest removal; their identifiers can then be "
                "registered again. Failed or interrupted manifest removals are retried hourly. Until removal "
                "succeeds, the retired record and its artifact references are retained to prevent path reuse. Mapping immutability "
                "is guaranteed only while a registration is retained. The add-on accepts at most "
                "1000 total registration records, including retired records. Metadata is bounded "
                "by the per-upload size limit and maximum retained version count plus one replacement, without a separate byte quota. "
                "Superseded artifacts are deleted on cleanup after a fixed 24-hour window. "
                "Serve manifests with Cache-Control: no-cache so clients revalidate before use. "
                "All artifact files, including superseded and incomplete publication output, count "
                "towards hard limits of 5 GiB and 10000 files per add-on. The larger artifact allowance "
                "accommodates translated text and multiple locales; it does not guarantee capacity for "
                "every locale or build combination. A publication exceeding "
                "either limit fails before writing new artifacts and preserves the previous manifest. "
                "Shared artifacts count only once. The window and storage limits are not configurable. "
                "Artifacts are compiled one locale at a time and staged on disk. Per-locale compilation "
                "rejects resources whose conservative encoded text and styling estimate exceeds 64 MiB. "
                "Preparation uses a separate fixed temporary-storage limit of 5 GiB per publication job, "
                "for staged ARSC output, shared by versions with identical resource mappings. "
                "Before enabling the add-on, configure the CDN origin to deny access to the "
                ".kotlin-sdk-staging directory under LOCALIZE_CDN_PATH; it contains unpublished preparation files. "
                "The manifest becomes visible only after its publication intent is committed. Failed "
                "or interrupted manifest writes are retried by subsequent publication jobs; artifacts "
                "for both old and pending manifests remain protected until replacement succeeds. "
                "Registration capacity errors reject new registrations without evicting active builds; identical "
                "retries remain accepted. Uninstalling attempts to remove origin files immediately; "
                "failed or interrupted removals are retried hourly. Files may remain publicly accessible "
                "until cleanup succeeds. Removal does not revoke copies already "
                "cached or downloaded by clients.\n\n"
                "Builds receive current component translations matched by resource name and type. "
                "Source text and formatting argument compatibility with older builds is the "
                "maintainer's responsibility. Strings, plurals, and Android styled text are supported; "
                "arrays and resource references are not generated. Untranslated, read-only, and "
                "incomplete plural entries are omitted so bundled resources remain available. "
                "Unsupported styling fails publication without replacing the previous manifest. "
                "CDN output is public, even for private components. Manifests expose packageName "
                "and versionCode; ARSC files expose published resource names and their submitted IDs "
                "alongside translated text. Do not treat the uploaded mapping as confidential. "
                "Access to registration and status endpoints remains permission-controlled."
            )
        )
        + AVAILABILITY,
        tags=["components"],
    )
    def post(self, request: Request, **kwargs: str) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return register_build(self.addon, request, serializer.validated_data)


class BuildStatusView(InstalledAddonAPIView):
    addon_name = "weblate.cdn.kotlin"
    serializer_class = BuildStatusSerializer

    @extend_schema(
        operation_id="api_components_addons_kotlin_sdk_builds_retrieve",
        description=(
            API_DESCRIPTION
            + "\n\n"
            + (
                "Get the publication state and CDN manifest URL for a registered package/version. "
                "Requires component.edit permission. Missing installations or registrations return "
                "404. States are pending, published, failed, and retired. A failed replacement "
                "may still have a previous successful manifest. Retired versions remain queryable "
                "but their manifests are removed; repeat uploads do not reactivate them. "
                "Maximum build age and retained version count are configured on the add-on. "
                "Retired metadata is cleared immediately and its lightweight registration record "
                "is deleted on cleanup after 24 hours and successful manifest removal. Failed removals are "
                "retried hourly; the registration and referenced artifacts are retained until removal succeeds. "
                "Superseded artifacts have a fixed 24-hour "
                "window, subject to the aggregate artifact storage limits documented on registration."
            )
        )
        + AVAILABILITY,
        tags=["components"],
    )
    def get(
        self, request: Request, package: str, version: int, **kwargs: str
    ) -> Response:
        return get_build(self.addon, request, None, package, version)


def get_api_urls() -> tuple[URLPattern, ...]:
    return (
        path("builds/", BuildRegistrationView.as_view(), name="build-register"),
        path(
            "builds/<str:package>/<int:version>/",
            BuildStatusView.as_view(),
            name="build-status",
        ),
    )
