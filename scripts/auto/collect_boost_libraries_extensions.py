#!/usr/bin/env python3
"""
Collect all Boost library names and their GitHub paths from boostorg/boost.

1. Fetches .gitmodules from https://github.com/boostorg/boost
   (uses specified version or master by default).
2. For each submodule in libs/, fetches meta/libraries.json from the repo
   at the given release version (e.g. boost-1.90.0) or develop if not given.
3. Extracts library name and GitHub path from each libraries.json entry.
4. For each library, doc folder is subpath + "/doc"; fetches file list via
   GitHub API (git/trees recursive) and collects unique file extensions.
5. Writes two output files:
   - Per-library format: name_or_key, repo_url.git, "ref", "subpath", "extensions"
   - Per-submodule format: submodule_name, repo_url.git, "library_names", "ref", "subpaths", "extensions"

Usage:
    python collect_boost_libraries_extensions.py [--version BOOST_VERSION] [--output FILE]
    python collect_boost_libraries_extensions.py --version boost-1.90.0 -o list.txt
    python collect_boost_libraries_extensions.py --version boost-1.90.0 --no-extensions
    python collect_boost_libraries_extensions.py --token YOUR_GITHUB_TOKEN
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# {ref} = branch/tag (e.g. develop, boost-1.90.0, master)
GITMODULES_URL_TEMPLATE = "https://raw.githubusercontent.com/boostorg/boost/{ref}/.gitmodules"
# {repo} = submodule name, {ref} = branch/tag (e.g. develop, boost-1.90.0)
LIBS_JSON_TEMPLATE = (
    "https://raw.githubusercontent.com/boostorg/{repo}/{ref}/meta/libraries.json"
)
REPO_URL_TEMPLATE = "https://github.com/boostorg/{repo}.git"
GITHUB_API_BASE = "https://api.github.com"
DEFAULT_GITMODULES_REF = "master"
DEFAULT_LIBS_REF = "develop"
USER_AGENT = "BoostLibraryList/1.0"
ENV_FILENAME = ".env"
GITMODULES_PATH_PREFIX = "path = "


def load_dotenv_script_dir() -> None:
    """
    Load .env from the directory containing this script. Sets os.environ for
    KEY=value lines. Also supports JSON-like "github_token": "value" and
    sets GITHUB_TOKEN so the script picks it up.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, ENV_FILENAME)
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        print(f"Warning: could not read .env: {e}", file=sys.stderr)
        return
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Standard .env: GITHUB_TOKEN=value or KEY="value"
        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1].replace('""', '"')
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            if key and value:
                os.environ.setdefault(key, value)
            continue
        # JSON-like: "github_token": "value" -> set GITHUB_TOKEN
        m = re.match(r'"github_token"\s*:\s*"((?:[^"\\]|\\.)*)"', line)
        if m:
            os.environ.setdefault("GITHUB_TOKEN", m.group(1))
            continue


def quoted(s: str) -> str:
    """Return string wrapped in double quotes with internal quotes escaped."""
    return '"' + s.replace('"', '""') + '"'


def format_subpath_display(subpath: str) -> str:
    """Return 'root' for empty subpath, else 'root/subpath'."""
    return "root" if not subpath else f"root/{subpath}"


def fetch_url(url: str, token: Optional[str] = None) -> str:
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def fetch_json(url: str, token: Optional[str] = None) -> dict:
    """Fetch URL and parse response as JSON."""
    content = fetch_url(url, token=token)
    return json.loads(content)


def parse_repo_url(repo_url: str) -> Tuple[str, str]:
    """Extract (owner, repo) from https://github.com/owner/repo.git ."""
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", repo_url.strip())
    if not m:
        raise ValueError(f"Cannot parse repo URL: {repo_url}")
    return m.group(1), m.group(2).removesuffix(".git")


def group_by_submodule(
    libraries: List[Tuple[str, str, str, str]]
) -> Dict[Tuple[str, str], List[Tuple[str, str, str]]]:
    """
    Group libraries by (submodule_name, repo_url).
    Returns dict mapping (submodule, repo_url) -> [(lib_name, subpath, extensions), ...]
    """
    grouped: Dict[Tuple[str, str], List[Tuple[str, str, str]]] = defaultdict(list)
    for lib_name, repo_url, subpath, extensions in libraries:
        # Extract submodule name from repo URL (e.g., "algorithm" from "boostorg/algorithm.git")
        try:
            _, repo = parse_repo_url(repo_url)
            submodule_name = repo
        except ValueError:
            # Fallback: use lib_name if URL parsing fails
            submodule_name = lib_name
        grouped[(submodule_name, repo_url)].append((lib_name, subpath, extensions))
    return grouped


def get_doc_extensions(
    owner: str, repo: str, ref: str, doc_path: str, token: Optional[str] = None
) -> Set[str]:
    """
    List all files under doc_path in the repo at ref via GitHub Git Trees API.
    Returns the set of file extensions (e.g. {".html", ".adoc"}).
    """
    extensions: Set[str] = set()
    try:
        # Get commit for ref to obtain tree SHA
        commit_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{ref}"
        commit_data = fetch_json(commit_url, token=token)
        tree_sha = commit_data.get("commit", {}).get("tree", {}).get("sha")
        if not tree_sha:
            return extensions
        # Get full tree recursively
        tree_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1"
        tree_data = fetch_json(tree_url, token=token)
        tree_entries = tree_data.get("tree") or []
        prefix = doc_path.rstrip("/") + "/"
        for entry in tree_entries:
            if entry.get("type") != "blob":
                continue
            path = entry.get("path", "")
            if not path.startswith(prefix):
                continue
            _, ext = os.path.splitext(path)
            if ext:
                extensions.add(ext)
    except HTTPError as e:
        if e.code != 404:
            raise
    except (URLError, json.JSONDecodeError, KeyError) as e:
        print(
            f"get_doc_extensions failed for {owner}/{repo} {doc_path}: {e}",
            file=sys.stderr,
        )
    return extensions


def parse_gitmodules(content: str) -> List[Tuple[str, str]]:
    """Parse .gitmodules and return list of (submodule_name, path)."""
    entries = []
    current_name = None
    current_path = None
    for line in content.splitlines():
        line = line.strip()
        m = re.match(r'\[submodule\s+"([^"]+)"\]', line)
        if m:
            if current_name is not None and current_path is not None:
                entries.append((current_name, current_path))
            current_name = m.group(1)
            current_path = None
            continue
        if line.startswith(GITMODULES_PATH_PREFIX):
            current_path = line[len(GITMODULES_PATH_PREFIX):].strip()
    if current_name is not None and current_path is not None:
        entries.append((current_name, current_path))
    return entries


def get_libraries_from_repo(submodule_name: str, ref: str) -> List[Tuple[str, str, str]]:
    """
    Fetch meta/libraries.json for a submodule at ref (branch/tag).
    Returns list of (first_column, repo_url, subpath).
    - Root library (key == submodule): first_column = key, subpath = "".
    - Sub-library: first_column = name, subpath = path relative to repo (e.g. "minmax").
    """
    url = LIBS_JSON_TEMPLATE.format(repo=submodule_name, ref=ref)
    try:
        content = fetch_url(url)
    except HTTPError as e:
        if e.code == 404:
            return []
        raise
    except URLError:
        return []

    try:
        raw = json.loads(content)
    except json.JSONDecodeError:
        return []

    # Support both array ([{...}, ...]) and single object ({...}) formats
    if isinstance(raw, list):
        libs = raw
    elif isinstance(raw, dict):
        libs = [raw]
    else:
        return []

    repo_url = REPO_URL_TEMPLATE.format(repo=submodule_name)
    result = []
    for obj in libs:
        if not isinstance(obj, dict):
            continue
        name = obj.get("name") or obj.get("key", "")
        key = obj.get("key", "")
        if not name or not key:
            continue
        # Root: key == submodule -> first_col = key, subpath = ""
        # Sub: key is submodule/path -> first_col = name, subpath = relative path
        if key == submodule_name:
            first_column = key
            subpath = ""
        else:
            prefix = submodule_name + "/"
            first_column = name
            subpath = key[len(prefix):] if key.startswith(prefix) else key
        result.append((first_column, repo_url, subpath))
    return result


def parse_args():
    """Parse command-line arguments and validate output path. Returns (args, gitmodules_ref, libs_ref)."""
    load_dotenv_script_dir()
    parser = argparse.ArgumentParser(
        description="Collect Boost library names and GitHub paths"
    )
    parser.add_argument(
        "--version",
        "-v",
        metavar="REF",
        default=None,
        help=(
            f"Version/ref for .gitmodules and libraries.json (e.g. boost-1.90.0). "
            f"Default: {DEFAULT_GITMODULES_REF} / {DEFAULT_LIBS_REF}"
        ),
    )
    parser.add_argument(
        "--output",
        "-o",
        default="boost_libraries_list.txt",
        help="Output file path (default: boost_libraries_list.txt)",
    )
    parser.add_argument(
        "--no-extensions",
        action="store_true",
        help="Do not fetch doc folder file extensions (output 4 columns only)",
    )
    parser.add_argument(
        "--token",
        "-t",
        metavar="GITHUB_TOKEN",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub token for API (avoids rate limit; or set GITHUB_TOKEN)",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        metavar="N",
        default=None,
        help="Process only first N lib submodules (for quick testing)",
    )
    args = parser.parse_args()

    out_dir = os.path.dirname(args.output)
    if out_dir and not os.path.exists(out_dir):
        print(f"Error: Output directory '{out_dir}' does not exist", file=sys.stderr)
        sys.exit(1)

    if args.version is not None:
        # Use the same version for both .gitmodules and libraries.json
        gitmodules_ref = args.version
        libs_ref = args.version
    else:
        # Use separate defaults
        gitmodules_ref = DEFAULT_GITMODULES_REF
        libs_ref = DEFAULT_LIBS_REF

    return args, gitmodules_ref, libs_ref


def fetch_gitmodules(ref: str) -> str:
    """Fetch .gitmodules from boostorg/boost at specified ref. Exits on failure."""
    url = GITMODULES_URL_TEMPLATE.format(ref=ref)
    print(f"Fetching .gitmodules from boostorg/boost at {ref}...", file=sys.stderr)
    try:
        return fetch_url(url)
    except HTTPError as e:
        print(f"Failed to fetch .gitmodules: HTTP {e.code} - {e.reason}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"Failed to fetch .gitmodules: {e.reason}", file=sys.stderr)
        sys.exit(1)


def collect_all_libraries(
    lib_submodules: List[Tuple[str, str]], ref: str
) -> List[Tuple[str, str, str]]:
    """Fetch library metadata for each submodule. Returns list of (first_col, repo_url, subpath)."""
    all_libraries: List[Tuple[str, str, str]] = []
    seen: Set[Tuple[str, str, str]] = set()

    for i, (submodule_name, _path_in_boost) in enumerate(lib_submodules, 1):
        print(
            f"  [{i}/{len(lib_submodules)}] {submodule_name} ...",
            file=sys.stderr,
            end=" ",
            flush=True,
        )
        try:
            libs = get_libraries_from_repo(submodule_name, ref)
            for first_col, repo_url, subpath in libs:
                key = (first_col, repo_url, subpath)
                if key not in seen:
                    seen.add(key)
                    all_libraries.append((first_col, repo_url, subpath))
            print(len(libs), file=sys.stderr)
        except (HTTPError, URLError, json.JSONDecodeError) as e:
            print(f"error: {e}", file=sys.stderr)

    return all_libraries


def fetch_extensions_for_libraries(
    all_libraries: List[Tuple[str, str, str]],
    ref: str,
    token: Optional[str],
) -> List[Tuple[str, str, str, str]]:
    """Fetch doc folder file extensions for each library. Returns list of 4-tuples."""
    n_libs = len(all_libraries)
    print(f"Fetching doc folder extensions via GitHub API ({n_libs} libraries)...", file=sys.stderr)
    rows_with_ext: List[Tuple[str, str, str, str]] = []
    for i, (first_col, repo_url, subpath) in enumerate(all_libraries, 1):
        doc_path = "doc" if not subpath else f"{subpath}/doc"
        try:
            owner, repo = parse_repo_url(repo_url)
            exts = get_doc_extensions(owner, repo, ref, doc_path, token=token)
            ext_str = "|".join(sorted(exts)) if exts else ""
            rows_with_ext.append((first_col, repo_url, subpath, ext_str))
            print(f"  [{i}/{n_libs}] {first_col} -> {ext_str or '(none)'}", file=sys.stderr)
        except (ValueError, HTTPError, URLError, KeyError, json.JSONDecodeError) as e:
            print(f"  [{i}/{n_libs}] {first_col} error: {e}", file=sys.stderr)
            rows_with_ext.append((first_col, repo_url, subpath, ""))
    return rows_with_ext


def write_library_output(
    all_libraries: List[Tuple[str, str, str, str]],
    out_path: str,
    ref: str,
    include_extensions: bool,
) -> None:
    """Write per-library output file. Exits on write failure."""
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            for row in all_libraries:
                first_col, repo_url, subpath = row[0], row[1], row[2]
                subpath_display = format_subpath_display(subpath)
                line = (
                    f"{quoted(first_col)}, {quoted(repo_url)}, "
                    f"{quoted(ref)}, {quoted(subpath_display)}"
                )
                if include_extensions:
                    line += f", {quoted(row[3])}"
                line += "\n"
                f.write(line)
    except OSError as e:
        print(f"Failed to write output file: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Wrote {len(all_libraries)} libraries to {out_path}", file=sys.stderr)


def write_submodule_output(
    all_libraries: List[Tuple[str, str, str, str]],
    lib_submodules: List[Tuple[str, str]],
    out_path: str,
    ref: str,
) -> None:
    """Write per-submodule output file (one row per lib submodule). Exits on write failure."""
    submodule_out_path = out_path.replace(".txt", "_submodules.txt")
    if submodule_out_path == out_path:
        submodule_out_path = out_path + "_submodules"

    grouped = group_by_submodule(all_libraries)
    submodule_rows: List[Tuple[str, str, str, str, str, str]] = []

    # Build one row per lib submodule so submodules with 0 libraries get an empty row
    for submodule_name, _path_in_boost in lib_submodules:
        repo_url = REPO_URL_TEMPLATE.format(repo=submodule_name)
        libs_data = grouped.get((submodule_name, repo_url), [])

        if not libs_data:
            submodule_rows.append((submodule_name, repo_url, "", ref, "", ""))
            continue

        lib_names = [lib[0] for lib in libs_data]
        subpaths = [format_subpath_display(lib[1]) for lib in libs_data]

        all_exts: Set[str] = set()
        for lib in libs_data:
            ext_str = lib[2]
            if ext_str:
                all_exts.update(ext_str.split("|"))
        combined_exts = "|".join(sorted(all_exts)) if all_exts else ""

        submodule_rows.append((
            submodule_name,
            repo_url,
            "|".join(lib_names),
            ref,
            "|".join(subpaths),
            combined_exts,
        ))

    try:
        with open(submodule_out_path, "w", encoding="utf-8") as f:
            for row in submodule_rows:
                submodule, repo_url, lib_names, ref_val, subpaths, exts = row
                line = (
                    f"{quoted(submodule)}, {quoted(repo_url)}, "
                    f"{quoted(lib_names)}, {quoted(ref_val)}, "
                    f"{quoted(subpaths)}, {quoted(exts)}\n"
                )
                f.write(line)
    except OSError as e:
        print(f"Failed to write submodule output file: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Wrote {len(submodule_rows)} submodules to {submodule_out_path}", file=sys.stderr)


def main() -> None:
    """Orchestrate fetching, collecting, and writing library and submodule outputs."""
    args, gitmodules_ref, libs_ref = parse_args()
    out_path = args.output

    print(f"Using .gitmodules ref: {gitmodules_ref}", file=sys.stderr)
    print(f"Using libraries.json ref: {libs_ref}", file=sys.stderr)

    gitmodules = fetch_gitmodules(gitmodules_ref)
    submodules = parse_gitmodules(gitmodules)
    lib_submodules = [(n, p) for n, p in submodules if p.startswith("libs/")]
    if args.limit is not None:
        lib_submodules = lib_submodules[: args.limit]
        print(f"Limited to first {len(lib_submodules)} libs submodules.", file=sys.stderr)
    print(f"Found {len(lib_submodules)} libs submodules.", file=sys.stderr)

    all_libraries = collect_all_libraries(lib_submodules, libs_ref)
    if not all_libraries:
        print("Warning: No libraries found!", file=sys.stderr)
        sys.exit(1)

    include_extensions = not args.no_extensions
    if include_extensions:
        all_libraries = fetch_extensions_for_libraries(
            all_libraries, libs_ref, args.token
        )
    else:
        all_libraries = [(f, u, s, "") for f, u, s in all_libraries]

    write_library_output(all_libraries, out_path, libs_ref, include_extensions)
    write_submodule_output(all_libraries, lib_submodules, out_path, libs_ref)


if __name__ == "__main__":
    main()

