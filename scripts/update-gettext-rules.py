#!/usr/bin/env python3
# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Refresh bundled ITS rule pairs from the releases pinned below."""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path
from typing import NamedTuple

from lxml import etree

# renovate-its: datasource=github-tags depName=polkit-org/polkit
POLKIT_VERSION = "126"
# renovate-its: datasource=github-tags depName=ximion/appstream
APPSTREAM_VERSION = "v1.0.5"
# renovate-its: datasource=github-tags depName=GNOME/glib
GLIB_VERSION = "2.84.4"
# renovate-its: datasource=github-tags depName=GNOME/gtk
GTK_VERSION = "3.24.49"
# renovate-its: datasource=gitlab-tags depName=xdg/shared-mime-info registryUrl=https://gitlab.freedesktop.org
SHARED_MIME_INFO_VERSION = "2.4"

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "weblate/addons/extractors/gettext"
START_MARKER = "<!-- BEGIN GENERATED ITS SOURCES -->"
END_MARKER = "<!-- END GENERATED ITS SOURCES -->"


class RuleSource(NamedTuple):
    name: str
    version: str
    repository: str
    directory: str

    @property
    def source_url(self) -> str:
        separator = (
            "tree" if self.repository.startswith("https://github.com/") else "-/tree"
        )
        return f"{self.repository}/{separator}/{self.version}/{self.directory}"

    def download_url(self, suffix: str) -> str:
        if self.repository.startswith("https://github.com/"):
            base = self.repository.replace(
                "https://github.com/", "https://raw.githubusercontent.com/"
            )
            return f"{base}/{self.version}/{self.directory}/{self.name}.{suffix}"
        return f"{self.repository}/-/raw/{self.version}/{self.directory}/{self.name}.{suffix}"


SOURCES = (
    RuleSource(
        "polkit", POLKIT_VERSION, "https://github.com/polkit-org/polkit", "gettext/its"
    ),
    RuleSource(
        "metainfo", APPSTREAM_VERSION, "https://github.com/ximion/appstream", "data/its"
    ),
    RuleSource("gschema", GLIB_VERSION, "https://github.com/GNOME/glib", "gio"),
    RuleSource("gtkbuilder", GTK_VERSION, "https://github.com/GNOME/gtk", "gtk"),
    RuleSource(
        "shared-mime-info",
        SHARED_MIME_INFO_VERSION,
        "https://gitlab.freedesktop.org/xdg/shared-mime-info",
        "data/its",
    ),
)


def fetch_rule(url: str) -> bytes:
    # URLs are constructed exclusively from the pinned upstream sources above.
    with urllib.request.urlopen(url, timeout=30) as response:  # ruff: ignore[suspicious-url-open-usage]
        return response.read()


def validate_pair(name: str, rules: dict[str, bytes]) -> None:
    for suffix in ("its", "loc"):
        parser = etree.XMLParser(
            resolve_entities=False, load_dtd=False, no_network=True
        )
        root = etree.fromstring(rules[f"{name}.{suffix}"], parser)
        if root.getroottree().docinfo.doctype:
            msg = f"Unexpected DTD in {name}.{suffix}"
            raise ValueError(msg)
        expected = (
            "{http://www.w3.org/2005/11/its}rules"
            if suffix == "its"
            else "locatingRules"
        )
        if root.tag != expected:
            msg = f"Unexpected root in {name}.{suffix}: {root.tag!r}"
            raise ValueError(msg)
        if suffix == "loc":
            targets = {
                node.attrib["target"] for node in root.iter() if "target" in node.attrib
            }
            if targets != {f"{name}.its"}:
                msg = f"Unexpected ITS targets in {name}.loc: {targets}"
                raise ValueError(msg)


def generate_files(output_dir: Path) -> dict[Path, bytes]:
    """Download and validate all pairs before modifying the bundle."""
    result = {}
    table = [
        START_MARKER,
        "",
        "| Files | Upstream version | Source |",
        "| --- | --- | --- |",
    ]
    for source in SOURCES:
        rules = {
            f"{source.name}.{suffix}": fetch_rule(source.download_url(suffix))
            for suffix in ("its", "loc")
        }
        validate_pair(source.name, rules)
        result.update({output_dir / "its" / name: data for name, data in rules.items()})
        table.append(f"| {source.name}.* | {source.version} | <{source.source_url}> |")
    table.extend(["", END_MARKER])
    readme = output_dir / "README.md"
    content = readme.read_text(encoding="utf-8")
    before, remainder = content.split(START_MARKER, 1)
    _, after = remainder.split(END_MARKER, 1)
    result[readme] = (before + "\n".join(table) + after).encode("utf-8")
    return result


def update_rules(output_dir: Path, *, check: bool = False) -> bool:
    generated = generate_files(output_dir)
    obsolete = sorted(
        path
        for path in (output_dir / "its").glob("*")
        if path.suffix in {".its", ".loc"}
        and (path.is_file() or path.is_symlink())
        and path not in generated
    )
    changed = {
        path: data
        for path, data in generated.items()
        if not path.exists() or path.read_bytes() != data
    }
    for path, data in changed.items():
        print(f"{'Outdated' if check else 'Updating'} {path.relative_to(output_dir)}")
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    for path in obsolete:
        print(f"{'Obsolete' if check else 'Removing'} {path.relative_to(output_dir)}")
        if not check:
            path.unlink()
    return bool(changed or obsolete)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the bundle differs from the pinned upstream files.",
    )
    args = parser.parse_args()
    changed = update_rules(OUTPUT_DIR, check=args.check)
    if args.check and changed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
