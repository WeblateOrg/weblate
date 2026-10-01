# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Share and refresh persistent intersphinx inventories."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import posixpath
import tempfile
import zlib
from pathlib import Path
from typing import TYPE_CHECKING

from requests.exceptions import RequestException
from sphinx.util import requests
from sphinx.util.inventory import InventoryFile

if TYPE_CHECKING:
    from collections.abc import Iterable

CACHE_DIR = Path(__file__).resolve().parents[1] / "_build" / "intersphinx"
LOGGER = logging.getLogger(__name__)


def normalize_language(language: str) -> str:
    """Normalize Read the Docs language codes for Sphinx."""
    if language == "no":
        return "nb"
    if "-" in language:
        name, country = language.split("-", 1)
        return f"{name}_{country.upper()}"
    return language


def remote_mapping(language: str) -> dict[str, tuple[str, str | None]]:
    """Return the upstream mappings without importing Sphinx configuration."""
    language = normalize_language(language)
    python_doc_url = "https://docs.python.org/3/"
    if language == "pt_BR":
        python_doc_url = "https://docs.python.org/pt-br/3/"
    elif language in {"es", "fr", "ja", "ko", "tr"}:
        python_doc_url = f"https://docs.python.org/{language}/3/"
    elif language == "zh_CN":
        python_doc_url = "https://docs.python.org/zh-cn/3/"
    elif language == "zh_TW":
        python_doc_url = "https://docs.python.org/zh-tw/3/"

    django_doc_url = "https://docs.djangoproject.com/en/stable/"
    if language in {"el", "es", "fr", "id", "ja", "ko", "pl"}:
        django_doc_url = f"https://docs.djangoproject.com/{language}/stable/"
    elif language == "pt_BR":
        django_doc_url = "https://docs.djangoproject.com/pt-br/stable/"
    elif language == "zh_CN":
        django_doc_url = "https://docs.djangoproject.com/zh-hans/stable/"

    sphinx_doc_url = "https://www.sphinx-doc.org/en/master/"
    if language in {
        "ar",
        "ca",
        "de",
        "ru",
        "es",
        "fr",
        "it",
        "ja",
        "ko",
        "pl",
        "pt_BR",
        "sr",
        "zh_CN",
    }:
        sphinx_doc_url = f"https://www.sphinx-doc.org/{language}/master/"
    elif language in {"zh_TW", "ta"}:
        sphinx_doc_url = f"https://www.sphinx-doc.org/{language}/latest/"

    return {
        "python": (python_doc_url, None),
        "django": (django_doc_url, f"{django_doc_url}_objects/"),
        "psa": ("https://python-social-auth.readthedocs.io/en/latest/", None),
        "tt": (
            "https://docs.translatehouse.org/projects/translate-toolkit/en/latest/",
            None,
        ),
        "amagama": (
            "https://docs.translatehouse.org/projects/amagama/en/latest/",
            None,
        ),
        "ldap": ("https://django-auth-ldap.readthedocs.io/en/latest/", None),
        "celery": ("https://docs.celeryq.dev/en/stable/", None),
        "sphinx": (sphinx_doc_url, None),
        "rtd": ("https://docs.readthedocs.com/platform/latest/", None),
        "borg": ("https://borgbackup.readthedocs.io/en/stable/", None),
        "drf-standardized-error": (
            "https://drf-standardized-errors.readthedocs.io/en/latest/",
            None,
        ),
    }


def inventory_url(target: str, inventory: str | None) -> str:
    return inventory or posixpath.join(target, "objects.inv")


def cache_directory(cache_dir: Path, url: str) -> Path:
    return cache_dir / hashlib.sha256(url.encode()).hexdigest()


def cached_mapping(
    language: str, cache_dir: Path = CACHE_DIR
) -> dict[str, tuple[str, str | None]]:
    """Prefer cached inventories, leaving cache misses to Sphinx."""
    mapping = remote_mapping(language)
    for name, (target, inventory) in mapping.items():
        directory = cache_directory(cache_dir, inventory_url(target, inventory))
        try:
            cached = read_cached_inventory(directory)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if cached is not None:
            mapping[name] = cached
    return mapping


def read_cached_inventory(directory: Path) -> tuple[str, str] | None:
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    # A digest names the immutable inventory associated with this metadata.
    digest = metadata["digest"]
    if not isinstance(digest, str) or len(digest) != 64:
        return None
    if any(char not in "0123456789abcdef" for char in digest):
        return None
    path = directory / f"{digest}.inv"
    base = metadata["target"]
    if path.is_file() and isinstance(base, str):
        return base, str(path.resolve())
    return None


def atomic_write(path: Path, content: bytes) -> None:
    """Publish a complete file without exposing partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def refresh_inventory(url: str, target: str, cache_dir: Path) -> None:
    """Validate and publish one inventory with its effective link target."""
    with requests.get(url, timeout=30) as response:
        response.raise_for_status()
        content = response.content
        # Match Sphinx's base-URL adjustment for redirected inventories.
        if response.url != url and target in {
            url,
            posixpath.dirname(url),
            posixpath.dirname(url) + "/",
        }:
            target = posixpath.dirname(response.url)
    InventoryFile.loads(content, uri=target)
    directory = cache_directory(cache_dir, url)
    digest = hashlib.sha256(content).hexdigest()
    atomic_write(directory / f"{digest}.inv", content)
    atomic_write(
        directory / "metadata.json",
        json.dumps({"digest": digest, "target": target}).encode(),
    )
    for previous in directory.glob("*.inv"):
        if previous.name != f"{digest}.inv":
            previous.unlink()


def refresh_inventories(
    languages: Iterable[str], cache_dir: Path = CACHE_DIR
) -> list[str]:
    """Refresh distinct inventories and retain old copies on failure."""
    inventories = {
        inventory_url(target, inventory): target
        for language in {"en", *languages}
        for target, inventory in remote_mapping(language).values()
    }
    failures = []
    for url, target in sorted(inventories.items()):
        try:
            refresh_inventory(url, target, cache_dir)
        except (RequestException, OSError, ValueError, zlib.error) as error:
            failures.append(f"{url}: {error}")
            LOGGER.exception("Failed %s", url)
        else:
            LOGGER.info("Updated %s", url)
    return failures


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", required=True, help="JSON list of languages")
    args = parser.parse_args()
    failures = refresh_inventories(json.loads(args.languages))
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write("## Intersphinx inventory refresh\n\n")
            if failures:
                handle.write("Failed inventories (previous copies retained):\n\n")
                handle.writelines(f"- {failure}\n" for failure in failures)
            else:
                handle.write("All inventories refreshed successfully.\n")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
