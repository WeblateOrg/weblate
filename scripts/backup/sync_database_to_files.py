#!/usr/bin/env python3
"""
Script to synchronize Weblate database translations to files.

This script updates translation files on disk with the current state
of the database. It's useful when database and files are out of sync.

Usage:
    python3 sync_database_to_files.py <project_slug>/<component_slug>
    python3 sync_database_to_files.py --all
    python3 sync_database_to_files.py --project <project_slug>
"""

import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "weblate.settings")
django.setup()

from django.db import transaction
from weblate.trans.models import Component, Project


def sync_component(component: Component) -> bool:
    """Sync a single component's database to files."""
    print(f"Syncing component: {component}")
    try:
        with transaction.atomic():
            component.do_file_sync(request=None)
        print(f"  ✓ Sync initiated for {component}")
        return True
    except Exception as e:
        print(f"  ✗ Error syncing {component}: {e}")
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync Weblate database translations to files"
    )
    parser.add_argument(
        "component",
        nargs="?",
        help="Component slug in format 'project/component'",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Sync all components",
    )
    parser.add_argument(
        "--project",
        help="Sync all components in a project",
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Wait for sync to complete (default: async via Celery)",
    )

    args = parser.parse_args()

    if args.all:
        components = Component.objects.all()
        print(f"Syncing all {components.count()} components...")
    elif args.project:
        try:
            project = Project.objects.get(slug=args.project)
            components = project.component_set.all()
            print(f"Syncing {components.count()} components in project '{project}'...")
        except Project.DoesNotExist:
            print(f"Error: Project '{args.project}' not found")
            sys.exit(1)
    elif args.component:
        parts = args.component.split("/")
        if len(parts) != 2:
            print("Error: Component must be in format 'project/component'")
            sys.exit(1)
        project_slug, component_slug = parts
        try:
            component = Component.objects.get(
                project__slug=project_slug, slug=component_slug
            )
            components = [component]
        except Component.DoesNotExist:
            print(f"Error: Component '{args.component}' not found")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    success_count = 0
    for component in components:
        if sync_component(component):
            success_count += 1

    print(f"\n✓ Successfully initiated sync for {success_count}/{len(components)} components")
    if not args.foreground:
        print(
            "\nNote: Sync runs asynchronously via Celery. "
            "Check Celery logs or Weblate UI for completion status."
        )


if __name__ == "__main__":
    main()

