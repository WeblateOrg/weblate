#!/usr/bin/env python3
"""
Weblate Component Setup - Complete Workflow

Creates a Weblate component and adds translations in one command.
This is a convenience wrapper around create_component.py and add_translation.py.

Usage:
    # From configuration file
    python create_component_and_add_translation.py --config setup.json
    
    # From component config with language list
    python create_component_and_add_translation.py --config component.json --languages fr,de,es
    
    # Interactive mode
    python create_component_and_add_translation.py --interactive

Requirements:
    pip install requests

Author: Weblate Team
License: GPL-3.0-or-later
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List

# Import the other scripts
try:
    from create_component import (
        WeblateProjectCreator,
        load_config_from_file,
        load_web_config_auto,
        merge_configs,
        validate_config,
        setup_project_and_component,
        trigger_and_wait,
    )
    from add_translation import (
        WeblateTranslationCreator,
        parse_language_codes,
        add_translations_batch,
    )
except ImportError as e:
    print(f"[ERROR] Failed to import required modules: {e}", flush=True)
    print("[INFO] Make sure create_component.py and add_translation.py are present", flush=True)
    sys.exit(1)


def load_setup_config(config_file: str) -> Dict[str, Any]:
    """Load setup configuration with component and languages."""
    config = load_config_from_file(config_file)
    
    # Auto-load web.json
    web_config = load_web_config_auto()
    if web_config:
        config = merge_configs(web_config, config)
    
    return config


def interactive_setup() -> Dict[str, Any]:
    """Interactively gather setup parameters."""
    print("=== Weblate Component Setup - Interactive Mode ===\n", flush=True)
    
    print("[INFO] First, let's create the component...", flush=True)
    print("[INFO] (If you already have a component.json, press Ctrl+C and use --config)", flush=True)
    print()
    
    # Get basic info
    project_name = input("Project name: ").strip()
    project_slug = input("Project slug: ").strip()
    project_web = input("Project website: ").strip()
    
    component_name = input("\nComponent name: ").strip()
    component_slug = input("Component slug: ").strip()
    
    repo = input("\nRepository URL (SSH or HTTPS): ").strip()
    branch = input("Branch (default: main): ").strip() or "main"
    
    vcs_type = input("VCS type (git/github/gitlab, default: git): ").strip() or "git"
    
    if vcs_type in ["github", "gitlab"]:
        push_branch = input("Push branch for PRs/MRs: ").strip()
    else:
        push = input("Push URL (leave empty if same as repo): ").strip()
        push_branch = input("Push branch (leave empty to use same as branch): ").strip()
    
    filemask = input("\nFile mask (e.g., locales/*.po): ").strip()
    file_format = input("File format (e.g., po, json, xliff): ").strip()
    
    # Check if monolingual
    if file_format in ["json", "html", "markdown", "asciidoc", "txt"]:
        template = input("Template file path: ").strip()
        new_base = input("New base file path (or same as template): ").strip()
        new_base = new_base or template
    else:
        template = ""
        new_base = ""
    
    # Get languages
    print("\n[INFO] Which languages do you want to add?", flush=True)
    print("[INFO] Enter comma-separated language codes (e.g., fr,de,es)", flush=True)
    print("[INFO] Leave empty to skip adding translations", flush=True)
    languages_input = input("Languages: ").strip()
    languages = parse_language_codes(languages_input) if languages_input else []
    
    # Build config
    config = {
        "project": {
            "name": project_name,
            "slug": project_slug,
            "web": project_web,
        },
        "component": {
            "name": component_name,
            "slug": component_slug,
            "vcs": vcs_type,
            "repo": repo,
            "branch": branch,
            "filemask": filemask,
            "file_format": file_format,
        },
        "languages": languages,
        "wait_for_ready": True,
        "trigger_update": True,
    }
    
    # Add optional fields
    if vcs_type in ["github", "gitlab"]:
        config["component"]["push_branch"] = push_branch
    else:
        if push:
            config["component"]["push"] = push
        if push_branch:
            config["component"]["push_branch"] = push_branch
    
    if template:
        config["component"]["template"] = template
        config["component"]["edit_template"] = False
    if new_base:
        config["component"]["new_base"] = new_base
    
    return config


def create_component_wrapper(config: Dict[str, Any]) -> tuple[str, str]:
    """Create component and return project/component slugs."""
    print("\n" + "="*60, flush=True)
    print("STEP 1: Creating Component", flush=True)
    print("="*60 + "\n", flush=True)
    
    creator = WeblateProjectCreator(
        config['weblate_url'],
        config['api_token']
    )
    
    if not creator.check_connection():
        raise Exception("Failed to connect to Weblate API")
    
    project, component, project_slug, component_slug = \
        setup_project_and_component(creator, config)
    
    # Trigger update and wait for component to be ready
    print("\n[INFO] Waiting for component to be fully initialized...", flush=True)
    trigger_and_wait(creator, project_slug, component_slug, config)
    
    # Additional wait to ensure component is stable
    print("[INFO] Ensuring component is ready for translations...", flush=True)
    time.sleep(3)
    
    # Verify component is accessible
    if not _verify_component_accessible(creator, project_slug, component_slug):
        raise Exception("Component not accessible after creation")
    
    print(f"\n[SUCCESS] Component created and ready!", flush=True)
    print(f"[INFO] URL: {component['web_url']}", flush=True)
    
    return project_slug, component_slug


def _verify_component_accessible(
    creator: WeblateProjectCreator,
    project_slug: str,
    component_slug: str
) -> bool:
    """Verify component is accessible and ready."""
    try:
        return creator.component_exists(project_slug, component_slug)
    except Exception as e:
        print(f"[ERROR] Failed to verify component: {e}", flush=True)
        return False


def add_translations_wrapper(
    config: Dict[str, Any],
    project_slug: str,
    component_slug: str,
    languages: List[str]
) -> int:
    """Add translations to the component using add_translation.py logic."""
    if not languages:
        print("\n[INFO] No languages specified, skipping translation addition", flush=True)
        return 0
    
    print("\n" + "="*60, flush=True)
    print(f"STEP 2: Adding {len(languages)} Translation(s)", flush=True)
    print("="*60 + "\n", flush=True)
    
    # Create translation creator
    creator = WeblateTranslationCreator(
        config['weblate_url'],
        config['api_token']
    )
    
    # Use the shared batch function from add_translation.py
    success_count = add_translations_batch(
        creator,
        project_slug,
        component_slug,
        languages
    )
    
    return success_count


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description='Complete Weblate component setup with translations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # From setup config (includes languages)
  %(prog)s --config setup.json

  # From component config with language list
  %(prog)s --config component.json --languages fr,de,es,ja

  # Interactive mode
  %(prog)s --interactive

  # Custom web config location
  %(prog)s --config setup.json --web-config /path/to/web.json

Setup Config Format (setup.json):
  {
    "project": { ... },
    "component": { ... },
    "languages": ["fr", "de", "es"],
    "wait_for_ready": true,
    "trigger_update": true
  }

Note:
  Automatically loads web.json from script directory or current directory.
        """
    )
    
    parser.add_argument(
        '--config',
        type=str,
        help='Setup configuration JSON file'
    )
    parser.add_argument(
        '--languages',
        type=str,
        help='Language codes to add (comma-separated, e.g., fr,de,es)'
    )
    parser.add_argument(
        '--web-config',
        type=str,
        help='Web configuration JSON file (optional, auto-loads web.json)'
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Interactive mode'
    )
    parser.add_argument(
        '--url',
        type=str,
        help='Override Weblate base URL'
    )
    parser.add_argument(
        '--token',
        type=str,
        help='Override API token'
    )
    
    return parser


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Load or gather configuration
    if args.interactive:
        config = interactive_setup()
    elif args.config:
        config = load_setup_config(args.config)
        
        # Override languages if specified on command line
        if args.languages:
            config['languages'] = parse_language_codes(args.languages)
        
        # Load web config if specified
        if args.web_config:
            web_config = load_config_from_file(args.web_config)
            config = merge_configs(web_config, config)
    else:
        parser.print_help()
        print("\n[ERROR] Please specify --config or use --interactive", flush=True)
        return 1
    
    # Override with command line arguments
    if args.url:
        config['weblate_url'] = args.url
    if args.token:
        config['api_token'] = args.token
    
    # Validate configuration
    if not validate_config(config):
        return 1
    
    # Extract languages (may be in config or empty)
    languages = config.get('languages', [])
    
    try:
        # Step 1: Create component
        project_slug, component_slug = create_component_wrapper(config)
        
        # Step 2: Add translations
        success_count = add_translations_wrapper(
            config,
            project_slug,
            component_slug,
            languages
        )
        
        # Final summary
        print("\n" + "="*60, flush=True)
        print("SETUP COMPLETE!", flush=True)
        print("="*60, flush=True)
        print(f"[INFO] Project: {project_slug}", flush=True)
        print(f"[INFO] Component: {component_slug}", flush=True)
        if languages:
            print(f"[INFO] Translations: {success_count}/{len(languages)} added", flush=True)
        print(f"[INFO] URL: {config['weblate_url']}/projects/{project_slug}/{component_slug}/", flush=True)
        print()
        
        return 0
    
    except Exception as e:
        print(f"\n[ERROR] Setup failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())

