# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify persistent inventory refreshes and offline Sphinx builds."""

from __future__ import annotations

import json
import zlib
from io import StringIO
from pathlib import Path
from unittest.mock import Mock

import intersphinx_cache
import pytest
from requests.exceptions import HTTPError, Timeout
from sphinx.testing.util import SphinxTestApp

TARGET = "https://example.com/stable/"
URL = TARGET + "objects.inv"


def inventory(version: str = "1") -> bytes:
    return (
        f"# Sphinx inventory version 2\n# Project: Example\n# Version: {version}\n"
        "# The remainder of this file is compressed using zlib.\n"
    ).encode() + zlib.compress(b"example py:function 1 api.html#example -\n")


@pytest.fixture
def upstream(monkeypatch: pytest.MonkeyPatch) -> Mock:
    monkeypatch.setattr(
        intersphinx_cache,
        "remote_mapping",
        lambda _language: {"example": (TARGET, None)},
    )
    response = Mock(content=inventory(), url=URL)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    get = Mock(return_value=response)
    monkeypatch.setattr(intersphinx_cache.requests, "get", get)
    return get


@pytest.mark.parametrize(
    ("language", "normalized", "python", "django", "sphinx"),
    [
        ("no", "nb", "3/", "en/stable/", "en/master/"),
        ("zh-cn", "zh_CN", "zh-cn/3/", "zh-hans/stable/", "zh_CN/master/"),
        ("pt-br", "pt_BR", "pt-br/3/", "pt-br/stable/", "pt_BR/master/"),
        ("ta", "ta", "3/", "en/stable/", "ta/latest/"),
    ],
)
def test_language_mapping(
    language: str, normalized: str, python: str, django: str, sphinx: str
) -> None:
    assert intersphinx_cache.normalize_language(language) == normalized
    mapping = intersphinx_cache.remote_mapping(language)
    assert mapping["python"] == (f"https://docs.python.org/{python}", None)
    django_target = f"https://docs.djangoproject.com/{django}"
    assert mapping["django"] == (django_target, django_target + "_objects/")
    assert mapping["sphinx"] == (f"https://www.sphinx-doc.org/{sphinx}", None)


def test_refresh_and_offline_build(tmp_path: Path, upstream: Mock) -> None:
    cache = tmp_path / "cache"
    upstream.return_value.url = "https://example.com/2.0/objects.inv"
    assert intersphinx_cache.refresh_inventories(["en", "fr", "zh-cn"], cache) == []
    upstream.assert_called_once_with(URL, timeout=30)
    mapping = intersphinx_cache.cached_mapping("en", cache)
    assert mapping["example"][0] == "https://example.com/2.0"
    upstream.side_effect = AssertionError("Offline builds must not fetch inventories")
    (tmp_path / "conf.py").write_text(
        "extensions = ['sphinx.ext.intersphinx']\n"
        f"intersphinx_mapping = {mapping!r}\n"
        "nitpicky = True\n",
        encoding="utf-8",
    )
    (tmp_path / "index.rst").write_text(
        "Example\n=======\n\n:external+example:py:func:`example`\n",
        encoding="utf-8",
    )
    # Independent fresh environments must both read the persistent cache.
    for _ in range(2):
        warnings = StringIO()
        app = SphinxTestApp(srcdir=tmp_path, warning=warnings, freshenv=True)
        try:
            app.build()
            assert not warnings.getvalue()
            html = (app.outdir / "index.html").read_text(encoding="utf-8")
            assert 'href="https://example.com/2.0/api.html#example"' in html
        finally:
            app.cleanup()


@pytest.mark.parametrize(
    "failure",
    [
        Timeout("timeout"),
        HTTPError("503"),
        b"invalid",
        b"# Sphinx inventory version 2\n# Project: X\n# Version: 1\n# zlib\nbroken",
    ],
)
def test_failed_refresh_retains_copy(
    tmp_path: Path, upstream: Mock, failure: Exception | bytes
) -> None:
    assert intersphinx_cache.refresh_inventories([], tmp_path) == []
    original = intersphinx_cache.cached_mapping("en", tmp_path)
    if isinstance(failure, bytes):
        upstream.return_value.content = failure
    else:
        upstream.side_effect = failure
    assert len(intersphinx_cache.refresh_inventories([], tmp_path)) == 1
    assert intersphinx_cache.cached_mapping("en", tmp_path) == original
    path = original["example"][1]
    assert path is not None
    assert Path(path).read_bytes() == inventory()


def test_missing_and_incomplete_cache(tmp_path: Path, upstream: Mock) -> None:
    assert intersphinx_cache.cached_mapping("en", tmp_path) == {
        "example": (TARGET, None)
    }
    directory = intersphinx_cache.cache_directory(tmp_path, URL)
    directory.mkdir()
    (directory / "metadata.json").write_text(
        json.dumps({"digest": "a" * 64, "target": TARGET}), encoding="utf-8"
    )
    assert intersphinx_cache.cached_mapping("en", tmp_path) == {
        "example": (TARGET, None)
    }
    upstream.assert_not_called()


def test_interrupted_publication(
    tmp_path: Path, upstream: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert intersphinx_cache.refresh_inventories([], tmp_path) == []
    original = intersphinx_cache.cached_mapping("en", tmp_path)
    upstream.return_value.content = inventory("2")
    write = intersphinx_cache.atomic_write

    def interrupted_write(path: Path, content: bytes) -> None:
        if path.name == "metadata.json":
            msg = "Interrupted before publishing metadata"
            raise OSError(msg)
        write(path, content)

    monkeypatch.setattr(intersphinx_cache, "atomic_write", interrupted_write)
    assert len(intersphinx_cache.refresh_inventories([], tmp_path)) == 1
    assert intersphinx_cache.cached_mapping("en", tmp_path) == original


def test_refresh_continues_after_failure(
    tmp_path: Path, upstream: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        intersphinx_cache,
        "remote_mapping",
        lambda _language: {
            "broken": ("https://broken.example.com/", None),
            "example": (TARGET, None),
        },
    )
    upstream.side_effect = [Timeout("timeout"), upstream.return_value]
    assert len(intersphinx_cache.refresh_inventories([], tmp_path)) == 1
    assert upstream.call_count == 2
    mapping = intersphinx_cache.cached_mapping("en", tmp_path)
    assert mapping["broken"] == ("https://broken.example.com/", None)
    assert mapping["example"][1] is not None


def test_django_redirect_preserves_target(
    tmp_path: Path, upstream: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    target, url = intersphinx_cache.remote_mapping("en")["example"]
    url = target + "_objects/"
    monkeypatch.setattr(
        intersphinx_cache, "remote_mapping", lambda _language: {"django": (target, url)}
    )
    upstream.return_value.url = "https://example.com/2.0/_objects/"
    assert intersphinx_cache.refresh_inventories([], tmp_path) == []
    upstream.assert_called_once_with(url, timeout=30)
    assert intersphinx_cache.cached_mapping("en", tmp_path)["django"][0] == target


def test_cli_summary_and_exit_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr("sys.argv", ["intersphinx_cache", "--languages", '["fr"]'])
    refresh = Mock(return_value=["https://example.com/objects.inv: timeout"])
    monkeypatch.setattr(intersphinx_cache, "refresh_inventories", refresh)
    assert intersphinx_cache.main() == 1
    refresh.assert_called_once_with(["fr"])
    assert "timeout" in summary.read_text(encoding="utf-8")
    refresh.return_value = []
    assert intersphinx_cache.main() == 0
    assert "All inventories refreshed successfully" in summary.read_text(
        encoding="utf-8"
    )
