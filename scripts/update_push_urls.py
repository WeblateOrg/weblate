#!/usr/bin/env python3
"""
Script to update repository URLs (both repo and push) for all Weblate components.

Usage:
    # Update all components to use a new repository URL
    python update_push_urls.py --new-url "git@github.com:user/repo.git"
    
    # Update only components matching a pattern
    python update_push_urls.py --old-url "git@github.com:old/repo.git" --new-url "git@github.com:new/repo.git"
    
    # Dry run (show what would be changed without actually changing)
    python update_push_urls.py --new-url "git@github.com:user/repo.git" --dry-run
    
    # Update specific components by name pattern
    python update_push_urls.py --new-url "git@github.com:user/repo.git" --component-pattern "intro"
    
    # Update only repo URL (not push URL)
    python update_push_urls.py --new-url "git@github.com:user/repo.git" --repo-only
    
    # Update only push URL (not repo URL)
    python update_push_urls.py --new-url "git@github.com:user/repo.git" --push-only
"""

import argparse
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "weblate.settings")
django.setup()

from weblate.trans.models import Component


def update_push_urls(
    new_url: str,
    old_url: str | None = None,
    component_pattern: str | None = None,
    dry_run: bool = False,
    repo_only: bool = False,
    push_only: bool = False,
) -> None:
    """Update repository URLs (both repo and push) for components."""
    
    # Get all components
    components = Component.objects.all()
    
    # Filter by old URL if provided (check both repo and push)
    if old_url:
        from django.db.models import Q
        components = components.filter(Q(repo=old_url) | Q(push=old_url))
        print(f"Filtering components with repo or push URL: {old_url}")
    
    # Filter by component name pattern if provided
    if component_pattern:
        components = components.filter(name__icontains=component_pattern)
        print(f"Filtering components matching pattern: {component_pattern}")
    
    # Count components
    total = components.count()
    
    if total == 0:
        print("No components found matching the criteria.")
        return
    
    # Determine what to update
    update_repo = not push_only
    update_push = not repo_only
    
    print(f"\nFound {total} component(s) to update:")
    print("-" * 80)
    
    # Show what will be changed
    for component in components:
        old_repo = component.repo or "(empty)"
        old_push = component.push or "(empty)"
        print(f"  {component.project.slug}/{component.slug}")
        print(f"    Name: {component.name}")
        if update_repo:
            print(f"    Current repo URL: {old_repo}")
            print(f"    New repo URL:     {new_url}")
        if update_push:
            print(f"    Current push URL: {old_push}")
            print(f"    New push URL:     {new_url}")
        print()
    
    if dry_run:
        print("DRY RUN: No changes made. Remove --dry-run to apply changes.")
        return
    
    # Confirm
    update_desc = []
    if update_repo:
        update_desc.append("repo URL")
    if update_push:
        update_desc.append("push URL")
    response = input(f"\nUpdate {' and '.join(update_desc)} for {total} component(s)? (yes/no): ")
    if response.lower() != "yes":
        print("Cancelled.")
        return
    
    # Update components
    updated = 0
    update_fields = []
    if update_repo:
        update_fields.append("repo")
    if update_push:
        update_fields.append("push")
    
    for component in components:
        if update_repo:
            component.repo = new_url
        if update_push:
            component.push = new_url
        component.save(update_fields=update_fields)
        updated += 1
        print(f"✓ Updated {component.project.slug}/{component.slug}")
    
    print(f"\n✓ Successfully updated {updated} component(s)")


def main():
    parser = argparse.ArgumentParser(
        description="Update repository URLs (both repo and push) for Weblate components"
    )
    parser.add_argument(
        "--new-url",
        required=True,
        help="New repository URL to set for all matching components",
    )
    parser.add_argument(
        "--old-url",
        help="Only update components with this specific repo or push URL (optional)",
    )
    parser.add_argument(
        "--component-pattern",
        help="Only update components whose name contains this pattern (optional)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without actually making changes",
    )
    parser.add_argument(
        "--repo-only",
        action="store_true",
        help="Only update the repo URL, not the push URL",
    )
    parser.add_argument(
        "--push-only",
        action="store_true",
        help="Only update the push URL, not the repo URL",
    )
    
    args = parser.parse_args()
    
    if args.repo_only and args.push_only:
        print("Error: Cannot use both --repo-only and --push-only")
        return
    
    update_push_urls(
        new_url=args.new_url,
        old_url=args.old_url,
        component_pattern=args.component_pattern,
        dry_run=args.dry_run,
        repo_only=args.repo_only,
        push_only=args.push_only,
    )


if __name__ == "__main__":
    main()


