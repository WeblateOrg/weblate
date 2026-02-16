#!/usr/bin/env python3
"""
Generate Weblate project setup JSON files from a Boost libraries submodules list.

Reads each row from a file like boost-1.90.0_libraries_list_submodules.txt
(slug, repo_url, component_names, ref, paths, exclude_extensions) and writes
one setup_project_boost_<slug>.json per row, matching the structure of
setup_project_boost_json.json for use with setup_project.py.

Usage:
    python generate_boost_project_configs.py --list boost-1.90.0_libraries_list_submodules.txt
    python generate_boost_project_configs.py --list list.txt --output-dir project-configs
"""

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path


def parse_list_row(line: str) -> tuple[str, str, str, str, str, str] | None:
    """Parse a quoted CSV-like row; return (slug, repo_url, names, ref, paths, exts) or None."""
    line = line.strip()
    if not line:
        return None
    try:
        row = next(csv.reader([line], skipinitialspace=True))
    except csv.Error:
        return None
    if len(row) < 6:
        return None
    return (
        row[0].strip(),
        row[1].strip(),
        row[2].strip(),
        row[3].strip(),
        row[4].strip(),
        row[5].strip(),
    )


def https_to_git_ssh(url: str) -> str:
    """Convert https://github.com/owner/repo.git to git@github.com:owner/repo.git."""
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    if not m:
        return url
    return f"git@github.com:{m.group(1)}/{m.group(2).removesuffix('.git')}.git"


def slug_to_project_name(slug: str) -> str:
    """e.g. 'json' -> 'Json', 'date_time' -> 'Date Time'."""
    return slug.replace("_", " ").title()


def slug_to_project_slug(slug: str) -> str:
    """e.g. 'json' -> 'boost-json-documentation'."""
    return "boost-" + slug.replace("_", "-") + "-documentation"


def slug_to_doc_url_path(slug: str) -> str:
    """Path segment for boost.org doc URL (slug as-is)."""
    return slug


def paths_to_github_path(paths: str) -> str:
    """Convert paths column to github_path: root -> doc/; root|root/mem_fn -> doc/, mem_fn/doc/."""
    if not paths.strip():
        return "doc/"
    result = []
    for p in (x.strip() for x in paths.split("|")):
        if p == "root":
            result.append("doc/")
        elif p.startswith("root/"):
            result.append(p[5:] + "/doc/")
        else:
            result.append(p + "/doc/" if p else "doc/")
    return ", ".join(result)


# Extensions considered documentation (from _exts we keep only these).
DOC_EXTENSIONS = {
    ".adoc", ".html", ".htm", ".xml", ".qbk", ".rst", ".md", ".dox", ".txt", ".xsl",
}

EXTENSION_FULLNAMES = {
    ".adoc": "AsciiDoc",
    ".html": "HTML",
    ".htm": "HTML",
    ".xml": "XML",
    ".qbk": "Quickbook",
    ".rst": "reStructuredText",
    ".md": "Markdown",
    ".dox": "Doxygen",
    ".txt": "plain text",
    ".xsl": "XSL",
}


def exts_to_doc_extensions(exts_str: str) -> list[str]:
    """From pipe-separated _exts, return only doc extensions. e.g. .gif|.html|.xml -> [.html, .xml]."""
    if not exts_str or not exts_str.strip():
        return [".adoc"]
    result = []
    for p in (x.strip().lower() for x in exts_str.split("|") if x.strip()):
        if not p.startswith("."):
            p = "." + p
        if p in DOC_EXTENSIONS:
            result.append(p)
    return sorted(set(result)) if result else [".adoc"]


def extensions_to_fullname(ext_list: list[str]) -> str:
    """Human-readable name for instructions, e.g. [.html, .xml] -> 'HTML and XML'."""
    names = []
    seen = set()
    for e in ext_list:
        name = EXTENSION_FULLNAMES.get(e.lower(), e.lstrip(".").upper())
        if name not in seen:
            seen.add(name)
            names.append(name)
    return " and ".join(names)


def build_config(
    slug: str,
    repo_url: str,
    ref: str,
    *,
    default_github_path: str = "doc/",
    doc_extensions: list[str] | None = None,
    branch: str = "local",
) -> dict:
    """Build a setup_project-style config dict for one library."""
    if doc_extensions is None:
        doc_extensions = [".adoc"]
    repo = https_to_git_ssh(repo_url).replace("boostorg", "CppDigest")
    name = slug_to_project_name(slug)
    project_slug = slug_to_project_slug(slug)
    url_path = slug_to_doc_url_path(slug)
    web = f"https://www.boost.org/doc/libs/master/libs/{url_path}/doc/html/"
    push_branch = f"boost-{slug.replace('_', '-')}-zh_Hans-translation-{ref}"
    ext_fullname = extensions_to_fullname(doc_extensions)

    return {
        "project": {
            "name": f"Boost {name} Documentation",
            "slug": project_slug,
            "web": web,
            "instructions": (
                f"Please translate the Boost.{slug} documentation. "
                f"Maintain technical accuracy and follow {ext_fullname} formatting conventions."
            ),
            "access_control": 0,
            "commit_policy": 0,
        },
        "component_defaults": {
            "vcs": "github",
            "repo": repo,
            "push": repo,
            "branch": branch,
            "push_branch": push_branch,
            "edit_template": False,
            "source_language": "en",
            "license": "",
            "allow_translation_propagation": False,
            "enable_suggestions": True,
            "suggestion_voting": False,
            "suggestion_autoaccept": 0,
            "check_flags": "",
            "hide_glossary_matches": True,
            "language_regex": "^zh_Hans$",
        },
        "languages": ["zh_Hans"],
        "wait_for_ready": True,
        "trigger_update": True,
        "scan": {
            "github_path": default_github_path,
            "extensions": list(doc_extensions),
            "exclude_patterns": [],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate setup_project JSON configs from Boost libraries submodules list",
    )
    parser.add_argument(
        "--list",
        "-l",
        default="boost-1.90.0_libraries_list_submodules.txt",
        help="Path to submodules list file (default: boost-1.90.0_libraries_list_submodules.txt)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="boost-submodule-project-configs",
        help="Directory to write JSON files (default: boost-submodule-project-configs)",
    )
    parser.add_argument(
        "--github-path",
        default="doc/",
        help="Default scan path within repo (default: doc/)",
    )
    parser.add_argument(
        "--branch",
        default="local",
        help="Branch to use in config (default: local)",
    )
    args = parser.parse_args()

    list_path = Path(args.list)
    if not list_path.is_file():
        print(f"[ERROR] List file not found: {list_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    skipped = 0
    with open(list_path, "r", encoding="utf-8") as f:
        for line in f:
            row = parse_list_row(line)
            if row is None:
                continue
            slug, repo_url, names, ref, paths, exts = row
            if not slug or not repo_url:
                continue
            if not names.strip():
                skipped += 1
                continue
            github_path = paths_to_github_path(paths) if paths.strip() else args.github_path
            doc_exts = exts_to_doc_extensions(exts.strip())
            config = build_config(
                slug,
                repo_url,
                ref,
                default_github_path=github_path,
                doc_extensions=doc_exts,
                branch=args.branch,
            )
            out_name = f"setup_project_boost_{slug}.json"
            out_path = out_dir / out_name
            with open(out_path, "w", encoding="utf-8") as out:
                json.dump(config, out, indent=2, ensure_ascii=False)
                out.write("\n")
            count += 1

    print(f"Wrote {count} config(s) to {out_dir}", file=sys.stderr)
    if skipped:
        print(f"Skipped {skipped} row(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
