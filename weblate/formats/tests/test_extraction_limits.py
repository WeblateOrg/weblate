# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Resource limits for compressed format conversion."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from translate.storage.base import ParseError
from translate.storage.extraction_limits import ExtractionBudget

from weblate.formats.convert import IDMLFormat, OpenDocumentFormat
from weblate.trans.tests.utils import get_test_file


def test_odf_conversion_rejects_many_paragraphs() -> None:
    start = (
        "<office:document-content "
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        "<office:body><office:text>"
    )
    paragraphs = "".join(f"<text:p>Unique sentence {i}</text:p>" for i in range(50_001))
    xml = (
        start + paragraphs + "</office:text></office:body></office:document-content>"
    ).encode()
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.writestr("content.xml", xml)
    archive.seek(0)

    with pytest.raises(ParseError, match="element extraction limit"):
        object.__new__(OpenDocumentFormat).convertfile(archive, None)


def test_idml_conversion_uses_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "weblate.formats.convert.make_extraction_budget",
        lambda: ExtractionBudget(max_xml_bytes=1),
    )
    content = Path(get_test_file("en.idml")).read_bytes()
    with pytest.raises(ParseError, match="byte extraction limit"):
        object.__new__(IDMLFormat).convertfile(BytesIO(content), None)
