#!/usr/bin/env python3
"""
List Weblate components and upload translation files via API.

Usage:
    # List all components
    python3 upload_translations.py

    # List components for a specific project
    python3 upload_translations.py --project boost-unordered-documentation

    # Map PO files to components
    python3 upload_translations.py --project boost-unordered-documentation --map-pofiles

    # Upload PO files to Weblate
    python3 upload_translations.py --project boost-unordered-documentation --upload --language zh_Hans

    # Upload with specific method and conflict handling
    python3 upload_translations.py --project boost-unordered-documentation --upload \\
        --language zh_Hans --method translate --conflicts replace-translated
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests

try:
    from translate.storage.pypo import pofile
    HAS_POLIB = True
except ImportError:
    HAS_POLIB = False


def extract_main_name(component_name: str) -> str:
    """
    Extract main name from component name.

    Examples:
        "Doc / Modules / Root / Pages / Reference / Unordered Node Map" -> "unordered_node_map"
        "Doc / Pages / Main" -> "main"
        "Doc / Pages / Io / Overview" -> "overview"
    """
    if not component_name:
        return ""

    # Split by " / " and get the last part
    parts = component_name.split(" / ")
    if not parts:
        return ""

    last_part = parts[-1].strip()

    # Convert to lowercase and replace spaces with underscores
    main_name = last_part.lower().replace(" ", "_")

    return main_name


def load_web_config(config_path: str = "web.json") -> Dict[str, Any]:
    """Load Weblate API configuration from JSON file."""
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] Config file not found: {config_path}", flush=True)
        print("[INFO] Create web.json with 'weblate_url' and 'api_token'", flush=True)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON in {config_path}: {e}", flush=True)
        sys.exit(1)


class WeblateComponentLister:
    """List Weblate components via API."""

    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.api_url = urljoin(self.base_url, "/api/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Token {api_token}",
                "Content-Type": "application/json",
            }
        )

    def upload_translation_file(
        self,
        project_slug: str,
        component_slug: str,
        language_code: str,
        po_file_path: str,
        method: str = "translate",
        conflicts: str = "replace-translated",
        fuzzy: str = "approve",
        author: str = "",
        email: str = "",
    ) -> bool:
        """
        Upload a translation file to Weblate.

        Args:
            project_slug: Project URL slug
            component_slug: Component URL slug
            language_code: Translation language code (e.g., 'zh_Hans')
            po_file_path: Path to the PO file to upload
            method: Upload method:
                - translate: Add as translation (default, most common)
                - approve: Add as approved translation
                - suggest: Add as suggestion
                - fuzzy: Add as translation needing edit
                - replace: Replace existing translation file (use with caution)
                - source: Update source strings
                - add: Add new strings only
            conflicts: How to deal with conflicts:
                - ignore: Change only untranslated strings
                - replace-translated: Replace existing translations but keep approved ones
                - replace-approved: Replace existing translations including approved ones
            fuzzy: How to handle strings needing edit (fuzzy strings):
                - empty: Do not import fuzzy strings
                - process: Import as string needing edit (keep fuzzy flag)
                - approve: Import as translated (remove fuzzy flag, accepts all units)
            author: Author name (requires admin permissions)
            email: Author e-mail (requires admin permissions)
        """
        endpoint = f"translations/{project_slug}/{component_slug}/{language_code}/file/"
        url = urljoin(self.api_url, endpoint)

        try:
            with open(po_file_path, 'rb') as f:
                files = {'file': (os.path.basename(po_file_path), f, 'text/plain')}
                data = {
                    'method': method,
                    'conflicts': conflicts,
                    'fuzzy': fuzzy,
                }
                if author:
                    data['author'] = author
                if email:
                    data['email'] = email

                # Use session.post() to maintain authentication
                # When files parameter is used, requests automatically sets Content-Type to multipart/form-data
                # So we temporarily remove Content-Type from session headers
                original_content_type = self.session.headers.pop('Content-Type', None)

                try:
                    response = self.session.post(url, files=files, data=data)
                    response.raise_for_status()

                    # Parse response to show detailed results
                    try:
                        result = response.json()
                        total = result.get('total', 0)
                        accepted = result.get('accepted', 0)
                        skipped = result.get('skipped', 0)
                        not_found = result.get('not_found', 0)
                        success = result.get('result', False)

                        if success and accepted > 0:
                            print(f"  ✓ Accepted: {accepted}/{total}", flush=True)
                            if skipped > 0:
                                print(f"    Skipped: {skipped}", flush=True)
                            if not_found > 0:
                                print(f"    Not found: {not_found}", flush=True)
                            return True
                        elif skipped == total:
                            print(f"  ⊘ All skipped ({total} units)", flush=True)
                            return True
                        else:
                            print(f"  ✗ Failed: Accepted={accepted}, Skipped={skipped}, Not found={not_found}", flush=True)
                            return False
                    except (ValueError, KeyError):
                        print(f"  ✓ Uploaded (response format unknown)", flush=True)
                        return True
                finally:
                    # Restore Content-Type header if it was present
                    if original_content_type:
                        self.session.headers['Content-Type'] = original_content_type

        except FileNotFoundError:
            print(f"  ✗ File not found: {po_file_path}", flush=True)
            return False
        except requests.exceptions.RequestException as e:
            print(f"  ✗ Error: {e}", flush=True)
            return False

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects."""
        all_projects = []
        url = "projects/"

        while url:
            full_url = urljoin(self.api_url, url)
            try:
                response = self.session.get(full_url)
                response.raise_for_status()
                data = response.json()
                projects = data.get("results", [])
                all_projects.extend(projects)

                # Check for next page
                url = data.get("next")
                if url:
                    url = url.replace(self.api_url, "")
                else:
                    url = None

            except requests.exceptions.RequestException:
                break

        return all_projects

    def project_exists(self, project_slug: str) -> bool:
        """Check if a project exists."""
        try:
            endpoint = f"projects/{project_slug}/"
            response = self.session.get(urljoin(self.api_url, endpoint))
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def get_translation_units(
        self, project_slug: str, component_slug: str, language_code: str
    ) -> List[Dict[str, Any]]:
        """Get all units for a translation to check their state."""
        endpoint = f"translations/{project_slug}/{component_slug}/{language_code}/units/"
        url = urljoin(self.api_url, endpoint)

        all_units = []
        while url:
            full_url = urljoin(self.api_url, url) if not url.startswith("http") else url
            try:
                response = self.session.get(full_url)
                response.raise_for_status()
                data = response.json()

                units = data.get("results", [])
                all_units.extend(units)

                url = data.get("next")
                if url and not url.startswith("http"):
                    url = url.replace(self.api_url, "")
            except requests.exceptions.RequestException:
                break

        return all_units

    def list_all_components(self, project_slug: str = None) -> List[Dict[str, Any]]:
        """List all components, optionally filtered by project."""
        all_components = []

        if project_slug:
            # Verify project exists first
            if not self.project_exists(project_slug):
                print(f"[ERROR] Project '{project_slug}' does not exist", flush=True)
                return []
            # List components for a specific project
            url = f"projects/{project_slug}/components/"
        else:
            # List all components
            url = "components/"

        while url:
            full_url = urljoin(self.api_url, url)
            try:
                response = self.session.get(full_url)
                response.raise_for_status()
                data = response.json()
                components = data.get("results", [])
                all_components.extend(components)

                # Check for next page
                url = data.get("next")
                if url:
                    url = url.replace(self.api_url, "")
                else:
                    url = None

            except requests.exceptions.RequestException:
                break

        return all_components


def map_po_files_to_components(
    pofiles_dir: str,
    components: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Map PO files to components based on main name matching.

    Returns a dict mapping component slug to {component_info, po_file_path, main_name}
    """
    pofiles_path = Path(pofiles_dir)
    if not pofiles_path.exists():
        return {}

    # Build mapping: main_name -> component
    component_map = {}
    for comp in components:
        comp_name = comp.get("name", "")
        main_name = extract_main_name(comp_name)
        if main_name:
            component_map[main_name] = comp

    # Match PO files to components
    matches = {}
    for po_file in pofiles_path.glob("*.po"):
        # Extract main name: "benchmarks.adoc.po" -> "benchmarks"
        main_name = po_file.stem.replace(".adoc", "")

        if main_name in component_map:
            comp = component_map[main_name]
            matches[comp.get("slug", "")] = {
                "component": comp,
                "po_file": str(po_file),
                "main_name": main_name,
            }

    return matches


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="List Weblate components and upload translations")
    parser.add_argument(
        "--web-config",
        default="web.json",
        help="Path to web.json config file (default: web.json)",
    )
    parser.add_argument(
        "--project",
        help="Filter by project slug (e.g., boost-json-documentation)",
    )
    parser.add_argument(
        "--component",
        help="Filter by component slug (e.g., doc-modules-root-pages-reference-concurrent-flat-set). "
             "If specified, only this component will be uploaded.",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--pofiles-dir",
        default="pofiles",
        help="Directory containing PO files (default: pofiles)",
    )
    parser.add_argument(
        "--map-pofiles",
        action="store_true",
        help="Map PO files to components and show matches",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload PO files to Weblate (requires --project and --language)",
    )
    parser.add_argument(
        "--language",
        default="zh_Hans",
        help="Language code for upload (default: zh_Hans)",
    )
    parser.add_argument(
        "--method",
        default="translate",
        choices=["translate", "approve", "suggest", "fuzzy", "replace", "source", "add"],
        help="Upload method: translate (add as translation), approve (add as approved), "
             "suggest (add as suggestion), fuzzy (add as needing edit), replace (replace file), "
             "source (update source strings), add (add new strings only). Default: translate",
    )
    parser.add_argument(
        "--conflicts",
        default="replace-translated",
        choices=["ignore", "replace-translated", "replace-approved"],
        help="Conflict handling: ignore (only untranslated), replace-translated (replace but keep approved), "
             "replace-approved (replace including approved, requires reviews enabled). Default: replace-translated",
    )
    parser.add_argument(
        "--list-projects",
        action="store_true",
        help="List all available projects",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=10.0,
        help="Delay in seconds between uploads (default: 10.0)",
    )
    parser.add_argument(
        "--fuzzy",
        default="approve",
        choices=["empty", "process", "approve"],
        help="Fuzzy strings handling: empty (do not import), process (import as needing edit), "
             "approve (import as translated, accepts all units). Default: approve",
    )
    parser.add_argument(
        "--verify-po",
        action="store_true",
        help="Verify PO file content before upload (show first few units)",
    )

    args = parser.parse_args()

    # Load config
    config = load_web_config(args.web_config)
    base_url = config["weblate_url"]
    api_token = config["api_token"]

    # Initialize lister
    lister = WeblateComponentLister(base_url, api_token)

    # List projects if requested
    if args.list_projects:
        projects = lister.list_projects()
        if not projects:
            print("No projects found.", flush=True)
            return 0
        print(f"Projects ({len(projects)}):", flush=True)
        for project in sorted(projects, key=lambda x: x.get("slug", "")):
            print(f"  {project.get('slug', ''):<40} {project.get('name', 'Unknown')}", flush=True)
        return 0

    # Fetch components
    if not args.upload:
        if args.project:
            print(f"Fetching components for: {args.project}", flush=True)
        else:
            print("Fetching all components...", flush=True)

    components = lister.list_all_components(project_slug=args.project)

    if not components:
        print("No components found.", flush=True)
        return 0

    # Output results (skip verbose output when uploading)
    if not args.upload:
        if args.format == "json":
            print(json.dumps(components, indent=2, ensure_ascii=False), flush=True)
        else:
            # Group by project
            projects = {}
            for comp in components:
                project_slug = comp.get("project", {}).get("slug", "unknown")
                project_name = comp.get("project", {}).get("name", "Unknown")
                if project_slug not in projects:
                    projects[project_slug] = {"name": project_name, "components": []}
                projects[project_slug]["components"].append({
                    "slug": comp.get("slug", ""),
                    "name": comp.get("name", ""),
                    "main_name": extract_main_name(comp.get("name", "")),
                })

            print(f"\nComponents ({len(components)}):", flush=True)
            for project_slug, project_data in sorted(projects.items()):
                print(f"\n{project_data['name']} ({project_slug}): {len(project_data['components'])} components", flush=True)
                for comp in sorted(project_data["components"], key=lambda x: x["slug"]):
                    print(f"  {comp['slug']:<50} -> {comp['main_name']}", flush=True)

    # Map PO files to components if requested
    if args.map_pofiles or args.upload:
        matches = map_po_files_to_components(args.pofiles_dir, components)

        # Filter by component if specified
        if args.component:
            if args.component in matches:
                matches = {args.component: matches[args.component]}
            else:
                print(f"Component '{args.component}' not found. Available: {', '.join(sorted(matches.keys())[:5])}...", flush=True)
                matches = {}

        if not matches:
            print(f"No PO files found in {args.pofiles_dir}", flush=True)
        else:
            if args.map_pofiles:
                print(f"\nMatched {len(matches)} PO files:", flush=True)
                for comp_slug, match_info in sorted(matches.items()):
                    print(f"  {comp_slug} -> {os.path.basename(match_info['po_file'])}", flush=True)

            # Upload if requested
            if args.upload:
                if not args.project:
                    print("ERROR: --project is required for upload", flush=True)
                    return 1

                uploaded = 0
                failed = 0
                matches_list = sorted(matches.items())
                total_matches = len(matches_list)

                print(f"\nUploading {total_matches} component(s) (language: {args.language})", flush=True)
                if len(matches_list) > 1:
                    print(f"Note: Translations may propagate between components", flush=True)

                for idx, (comp_slug, match_info) in enumerate(matches_list, 1):
                    po_file = match_info["po_file"]
                    print(f"\n[{idx}/{total_matches}] {comp_slug}", flush=True)

                    # Check translation state if verify-po is enabled
                    if args.verify_po:
                        units = lister.get_translation_units(args.project, comp_slug, args.language)
                        approved_count = sum(1 for u in units if u.get("state") == 30)
                        translated_count = sum(1 for u in units if u.get("state") == 20)
                        print(f"  State: {len(units)} total, {translated_count} translated, {approved_count} approved", flush=True)

                        if HAS_POLIB and approved_count > 0:
                            try:
                                po_store = pofile(po_file)
                                weblate_units_by_source = {}
                                for u in units:
                                    source = u.get("source", [])
                                    if source:
                                        source_str = source[0] if isinstance(source, list) else str(source)
                                        weblate_units_by_source[source_str] = u

                                approved_matches = []
                                for unit in po_store.units:
                                    if not unit.isheader() and unit.source in weblate_units_by_source:
                                        wu = weblate_units_by_source[unit.source]
                                        if wu.get("state") == 30:
                                            approved_matches.append(unit.source[:50])

                                if approved_matches:
                                    print(f"  ⚠️  {len(approved_matches)} approved units will be skipped", flush=True)
                            except Exception:
                                pass

                    if lister.upload_translation_file(
                        project_slug=args.project,
                        component_slug=comp_slug,
                        language_code=args.language,
                        po_file_path=po_file,
                        method=args.method,
                        conflicts=args.conflicts,
                        fuzzy=args.fuzzy,
                    ):
                        uploaded += 1
                    else:
                        failed += 1

                    # Add delay between uploads
                    if idx < total_matches and args.delay > 0:
                        time.sleep(args.delay)

                print(f"\nSummary: {uploaded} uploaded, {failed} failed", flush=True)

                return 0 if failed == 0 else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
