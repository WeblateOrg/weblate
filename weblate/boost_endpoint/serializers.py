# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from rest_framework import serializers


class AddOrUpdateRequestSerializer(serializers.Serializer):
    """Serializer for add_or_update endpoint request."""

    organization = serializers.CharField(
        required=True,
        help_text="GitHub organization name (e.g., 'CppDigest')"
    )
    submodules = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        help_text="List of submodule names (e.g., ['json', 'unordered'])"
    )
    lang_code = serializers.CharField(
        required=True,
        help_text="Language code (e.g., 'zh_Hans')"
    )
    version = serializers.CharField(
        required=True,
        help_text="Boost version (e.g., 'boost-1.90.0')"
    )
    extensions = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        allow_null=True,
        default=None,
        help_text=(
            "Optional list of file extensions to include (e.g. ['.adoc', '.md']). "
            "Only Weblate-supported extensions in this list are scanned. "
            "If None or empty, all Weblate-supported extensions are used."
        ),
    )
