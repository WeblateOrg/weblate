# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build documentation to verify rubric permalinks and navigation."""

from __future__ import annotations

import runpy
import sys
from io import StringIO
from pathlib import Path

import pytest
from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo
from bs4 import BeautifulSoup
from docutils import nodes
from sphinx.testing.util import SphinxTestApp

SOURCE = """\
Weblate 2026.10
===============

.. rubric:: New features
   :name: weblate-2026-10-features

* See `details <https://example.com/details>`_.

.. rubric:: Bug fixes

.. rubric:: Bug fixes

.. rubric:: Reserved anchor
   :name: weblate-2026-10-bug-fixes-2

Weblate 2026.9
==============

.. rubric:: Bug fixes
"""


@pytest.mark.parametrize("permalinks", [True, False])
@pytest.mark.parametrize("language", ["en", "cs"])
def test_rubric_permalinks(
    tmp_path: Path,
    permalinks: bool,
    language: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    extension_dir = Path(__file__).parent
    (tmp_path / "conf.py").write_text(
        f"""\
import sys
sys.path.insert(0, {str(extension_dir)!r})
extensions = ['rubric_permalinks']
root_doc = 'index'
html_theme = 'furo'
html_static_path = [{str(extension_dir / "static")!r}]
locale_dirs = ['locales']
language = {language!r}
html_permalinks = {permalinks!r}
html_permalinks_icon = 'LINK'
""",
        encoding="utf-8",
    )
    (tmp_path / "index.rst").write_text(
        "Documentation\n=============\n\n.. toctree::\n\n   changes\n   other\n",
        encoding="utf-8",
    )
    (tmp_path / "changes.rst").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "other.rst").write_text(
        "Other\n=====\n\n.. rubric:: Bug fixes\n   :name: other-fixes\n",
        encoding="utf-8",
    )
    catalog = Catalog(locale="cs")
    catalog.add("Bug fixes", "Opravy chyb")
    catalog.add("Weblate 2026.10", "Vydání Weblate 2026.10")
    translations = tmp_path / "locales" / "cs" / "LC_MESSAGES"
    translations.mkdir(parents=True)
    with (translations / "changes.mo").open("wb") as handle:
        write_mo(handle, catalog)

    warnings = StringIO()
    app = SphinxTestApp(srcdir=tmp_path, warning=warnings, freshenv=True)
    try:
        app.build()
        assert not warnings.getvalue()
        soup = BeautifulSoup(
            (app.outdir / "changes.html").read_text(encoding="utf-8"), "html.parser"
        )
        rubrics = soup.select(".changelog-rubric")
        anchors = [rubric["id"] for rubric in rubrics]
        assert anchors == [
            "weblate-2026-10-features",
            "weblate-2026-10-bug-fixes",
            "weblate-2026-10-bug-fixes-3",
            "weblate-2026-10-bug-fixes-2",
            "weblate-2026-9-bug-fixes",
        ]
        assert all(rubric.name == "p" for rubric in rubrics)
        if language == "cs":
            assert "Opravy chyb" in rubrics[1].get_text()
            assert "Vydání Weblate 2026.10" in soup.get_text()
        for rubric in rubrics:
            links = rubric.select("a.headerlink")
            assert len(links) == int(permalinks)
            if permalinks:
                assert links[0]["href"] == f"#{rubric['id']}"
                assert links[0].get_text() == "LINK"
                assert links[0]["title"]
        toc = app.env.tocs["changes"]
        assert all(
            reference.get("anchorname") not in {f"#{anchor}" for anchor in anchors}
            for reference in toc.findall(nodes.reference)
        )
        other = BeautifulSoup(
            (app.outdir / "other.html").read_text(encoding="utf-8"), "html.parser"
        )
        assert not other.select(".rubric .headerlink, .changelog-rubric")
        assert (app.outdir / "_static" / "rubric-permalinks.css").is_file()
        release_input = tmp_path / "docs" / "_build" / "html"
        release_input.mkdir(parents=True)
        (release_input / "changes.html").write_bytes(
            (app.outdir / "changes.html").read_bytes()
        )
        extractor = extension_dir.parent.parent / "scripts" / "extract-release-notes.py"
        monkeypatch.chdir(tmp_path)
        for version, expected_rubrics in (([], rubrics[:4]), (["2026.9"], rubrics[4:])):
            monkeypatch.setattr(sys, "argv", [str(extractor), *version])
            runpy.run_path(str(extractor), run_name="__main__")
            notes = BeautifulSoup(capsys.readouterr().out, "html.parser")
            assert [heading.get_text() for heading in notes.select("h3")] == [
                rubric.contents[0] for rubric in expected_rubrics
            ]
            assert not notes.select(".headerlink, .rubric")
            if not version:
                assert notes.select_one('a[href="https://example.com/details"]')
    finally:
        app.cleanup()
