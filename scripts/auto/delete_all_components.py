#!/usr/bin/env python3
"""
Delete Weblate projects and components.

Usage:
    # Delete all components in a project
    python3 delete_all_components.py --project PROJECT_SLUG
    python3 delete_all_components.py --project PROJECT_SLUG --yes

    # Delete all projects (and their components)
    python3 delete_all_components.py --all-projects
    python3 delete_all_components.py --all-projects --yes

    # Delete everything (all projects and all components)
    python3 delete_all_components.py --all
    python3 delete_all_components.py --all --yes
"""

import argparse
import json
import sys
from typing import Any, Dict, List
from urllib.parse import urljoin

import requests


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


class WeblateDeleter:
    """Delete Weblate projects and components via API."""

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

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects."""
        all_projects = []
        url = "projects/"

        while url:
            full_url = urljoin(self.api_url, url)
            print(f"[API] GET {full_url}", flush=True)
            response = self.session.get(full_url)
            response.raise_for_status()
            data = response.json()
            all_projects.extend(data.get("results", []))
            url = data.get("next")
            if url:
                url = url.replace(self.api_url, "")

        return all_projects

    def list_components(self, project_slug: str) -> List[Dict[str, Any]]:
        """List all components in a project."""
        all_components = []
        url = f"projects/{project_slug}/components/"

        while url:
            full_url = urljoin(self.api_url, url)
            print(f"[API] GET {full_url}", flush=True)
            response = self.session.get(full_url)
            response.raise_for_status()
            data = response.json()
            all_components.extend(data.get("results", []))
            url = data.get("next")
            if url:
                url = url.replace(self.api_url, "")

        return all_components

    def delete_project(self, project_slug: str) -> bool:
        """Delete a project."""
        endpoint = f"projects/{project_slug}/"
        full_url = urljoin(self.api_url, endpoint)
        print(f"[DELETE] {full_url}", flush=True)

        try:
            response = self.session.delete(full_url)
            response.raise_for_status()
            return True
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"  [WARNING] Project {project_slug} not found", flush=True)
                return True  # Already deleted
            print(f"  [ERROR] Failed to delete project {project_slug}: {e}", flush=True)
            return False
        except Exception as e:
            print(f"  [ERROR] Failed to delete project {project_slug}: {e}", flush=True)
            return False

    def delete_component(self, project_slug: str, component_slug: str) -> bool:
        """Delete a component."""
        endpoint = f"components/{project_slug}/{component_slug}/"
        full_url = urljoin(self.api_url, endpoint)
        print(f"[DELETE] {full_url}", flush=True)

        try:
            response = self.session.delete(full_url)
            response.raise_for_status()
            return True
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"  [WARNING] Component {component_slug} not found", flush=True)
                return True  # Already deleted
            print(f"  [ERROR] Failed to delete {component_slug}: {e}", flush=True)
            return False
        except Exception as e:
            print(f"  [ERROR] Failed to delete {component_slug}: {e}", flush=True)
            return False

    def delete_all_components_in_project(self, project_slug: str) -> tuple[int, int]:
        """Delete all components in a project. Returns (deleted, failed)."""
        components = self.list_components(project_slug)
        if not components:
            return 0, 0

        deleted = 0
        failed = 0

        for comp in components:
            comp_slug = comp["slug"]
            if self.delete_component(project_slug, comp_slug):
                deleted += 1
                print(f"  [SUCCESS] Deleted {comp_slug}", flush=True)
            else:
                failed += 1

        return deleted, failed


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Delete Weblate projects and components"
    )
    parser.add_argument(
        "--project",
        help="Project slug (delete all components in this project)",
    )
    parser.add_argument(
        "--all-projects",
        action="store_true",
        help="Delete all projects (and their components)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Delete everything (all projects and all components)",
    )
    parser.add_argument(
        "--web-config",
        default="web.json",
        help="Path to web.json config file (default: web.json)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.project and not args.all_projects and not args.all:
        parser.error("Must specify --project, --all-projects, or --all")

    # Load configuration
    web_config = load_web_config(args.web_config)
    base_url = web_config.get("weblate_url")
    api_token = web_config.get("api_token")

    if not base_url or not api_token:
        print("[ERROR] Missing weblate_url or api_token in config", flush=True)
        return 1

    # Initialize deleter
    deleter = WeblateDeleter(base_url, api_token)

    # Handle different deletion modes
    if args.all:
        # Delete everything
        print("[INFO] Listing all projects...", flush=True)
        projects = deleter.list_projects()

        if not projects:
            print("[INFO] No projects found.", flush=True)
            return 0

        print(f"\n[INFO] Found {len(projects)} project(s):", flush=True)
        for proj in projects:
            comp_count = len(deleter.list_components(proj["slug"]))
            print(f"  - {proj['slug']}: {proj['name']} ({comp_count} components)", flush=True)

        if not args.yes:
            print(f"\n[WARNING] This will delete ALL {len(projects)} projects and ALL their components!", flush=True)
            confirm = input('Type "DELETE EVERYTHING" to confirm: ').strip()
            if confirm != "DELETE EVERYTHING":
                print("[INFO] Deletion cancelled.", flush=True)
                return 0

        # Delete all components in all projects, then delete projects
        total_components_deleted = 0
        total_components_failed = 0
        total_projects_deleted = 0
        total_projects_failed = 0

        print("\n[INFO] Step 1: Deleting all components in all projects...", flush=True)
        for proj in projects:
            proj_slug = proj["slug"]
            print(f"\n[INFO] Deleting components in project: {proj_slug}", flush=True)
            deleted, failed = deleter.delete_all_components_in_project(proj_slug)
            total_components_deleted += deleted
            total_components_failed += failed

        print("\n[INFO] Step 2: Deleting all projects...", flush=True)
        for proj in projects:
            proj_slug = proj["slug"]
            if deleter.delete_project(proj_slug):
                total_projects_deleted += 1
                print(f"  [SUCCESS] Deleted project {proj_slug}", flush=True)
            else:
                total_projects_failed += 1

        # Summary
        print("\n" + "=" * 60, flush=True)
        print("Deletion Summary (Everything)", flush=True)
        print("=" * 60, flush=True)
        print(f"Projects - Total: {len(projects)}, Deleted: {total_projects_deleted}, Failed: {total_projects_failed}", flush=True)
        print(f"Components - Deleted: {total_components_deleted}, Failed: {total_components_failed}", flush=True)
        print("=" * 60, flush=True)

        return 0 if (total_projects_failed == 0 and total_components_failed == 0) else 1

    elif args.all_projects:
        # Delete all projects
        print("[INFO] Listing all projects...", flush=True)
        projects = deleter.list_projects()

        if not projects:
            print("[INFO] No projects found.", flush=True)
            return 0

        print(f"\n[INFO] Found {len(projects)} project(s):", flush=True)
        for proj in projects:
            comp_count = len(deleter.list_components(proj["slug"]))
            print(f"  - {proj['slug']}: {proj['name']} ({comp_count} components)", flush=True)

        if not args.yes:
            print(f"\n[WARNING] This will delete ALL {len(projects)} projects (and their components)!", flush=True)
            confirm = input('Type "DELETE ALL PROJECTS" to confirm: ').strip()
            if confirm != "DELETE ALL PROJECTS":
                print("[INFO] Deletion cancelled.", flush=True)
                return 0

        # Delete all components in all projects first, then delete projects
        total_components_deleted = 0
        total_components_failed = 0
        total_projects_deleted = 0
        total_projects_failed = 0

        print("\n[INFO] Step 1: Deleting all components in all projects...", flush=True)
        for proj in projects:
            proj_slug = proj["slug"]
            print(f"\n[INFO] Deleting components in project: {proj_slug}", flush=True)
            deleted, failed = deleter.delete_all_components_in_project(proj_slug)
            total_components_deleted += deleted
            total_components_failed += failed

        print("\n[INFO] Step 2: Deleting all projects...", flush=True)
        for proj in projects:
            proj_slug = proj["slug"]
            if deleter.delete_project(proj_slug):
                total_projects_deleted += 1
                print(f"  [SUCCESS] Deleted project {proj_slug}", flush=True)
            else:
                total_projects_failed += 1

        # Summary
        print("\n" + "=" * 60, flush=True)
        print("Deletion Summary (All Projects)", flush=True)
        print("=" * 60, flush=True)
        print(f"Projects - Total: {len(projects)}, Deleted: {total_projects_deleted}, Failed: {total_projects_failed}", flush=True)
        print(f"Components - Deleted: {total_components_deleted}, Failed: {total_components_failed}", flush=True)
        print("=" * 60, flush=True)

        return 0 if (total_projects_failed == 0 and total_components_failed == 0) else 1

    else:
        # Delete all components in a specific project
        print(f"[INFO] Listing components in project: {args.project}", flush=True)
        components = deleter.list_components(args.project)

        if not components:
            print("[INFO] No components found in project.", flush=True)
            return 0

        # Show components
        print(f"\n[INFO] Found {len(components)} component(s):", flush=True)
        for comp in components:
            print(f"  - {comp['slug']}: {comp['name']}", flush=True)

        # Confirmation
        if not args.yes:
            print(f"\n[WARNING] This will delete ALL {len(components)} components!", flush=True)
            confirm = input('Type "DELETE ALL" to confirm: ').strip()
            if confirm != "DELETE ALL":
                print("[INFO] Deletion cancelled.", flush=True)
                return 0

        # Delete components
        print("\n[INFO] Deleting components...", flush=True)
        deleted = 0
        failed = []

        for comp in components:
            comp_slug = comp["slug"]
            if deleter.delete_component(args.project, comp_slug):
                deleted += 1
                print(f"  [SUCCESS] Deleted {comp_slug}", flush=True)
            else:
                failed.append(comp_slug)

        # Summary
        print("\n" + "=" * 60, flush=True)
        print("Deletion Summary", flush=True)
        print("=" * 60, flush=True)
        print(f"Total: {len(components)}", flush=True)
        print(f"Deleted: {deleted}", flush=True)
        if failed:
            print(f"Failed: {len(failed)}", flush=True)
            for comp_slug in failed:
                print(f"  - {comp_slug}", flush=True)
        print("=" * 60, flush=True)

        return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

