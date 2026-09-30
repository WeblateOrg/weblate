# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.files.base import ContentFile
from django.http import QueryDict
from rest_framework.parsers import DataAndFiles, MultiPartParser

if TYPE_CHECKING:
    from typing import BinaryIO

# Latin-1 maps every byte to a single code point, so decoding is lossless.
LOSSLESS_ENCODING = "latin-1"


class TranslationFileMultiPartParser(MultiPartParser):
    """
    Keep raw bytes of a ``file`` field submitted without a filename.

    Django decodes such parts as text and replaces undecodable bytes, which
    corrupts translation files that are not UTF-8.
    """

    def parse(
        self,
        stream: BinaryIO,
        media_type: str | None = None,
        parser_context: dict[str, Any] | None = None,
    ) -> DataAndFiles:
        parser_context = parser_context or {}
        encoding = parser_context.get("encoding", settings.DEFAULT_CHARSET)
        result = super().parse(
            stream, media_type, {**parser_context, "encoding": LOSSLESS_ENCODING}
        )

        def recode(value: str) -> str:
            return value.encode(LOSSLESS_ENCODING).decode(encoding, errors="replace")

        data = QueryDict(mutable=True, encoding=encoding)
        files = result.files
        for key, values in result.data.lists():
            if key == "file":
                files.setlist(
                    key,
                    [
                        # use name without extension so format is only derived from component, not filename
                        ContentFile(value.encode(LOSSLESS_ENCODING), name="upload")
                        for value in values
                    ],
                )
            else:
                data.setlist(recode(key), [recode(value) for value in values])
        for upload in files.values():
            if upload.name:
                upload.name = recode(upload.name)
        return DataAndFiles(data, files)
