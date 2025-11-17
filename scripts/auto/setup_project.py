#!/usr/bin/env python3
"""
Auto-generate Weblate component setup files from repository files.

This script scans a repository for files with specific extensions and
generates a setup JSON file for each file, ready to be used with
create_component_and_add_translation.py.

Usage:
    python generate_component_configs.py --config project_config.json
    
Author: Weblate Team
License: GPL-3.0-or-later
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_config(config_file: str) -> Dict[str, Any]:
    """Load project configuration from JSON file."""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] Config file not found: {config_file}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON in config file: {e}")
        sys.exit(1)


def clone_repository(repo_url: str, branch: str, target_dir: str) -> bool:
    """Clone a git repository to a temporary directory."""
    try:
        print(f"[INFO] Cloning repository: {repo_url}")
        print(f"[INFO] Branch: {branch}")
        
        # Convert SSH URL to HTTPS if needed for cloning
        clone_url = repo_url
        if repo_url.startswith("git@github.com:"):
            # Convert git@github.com:user/repo.git to https://github.com/user/repo.git
            clone_url = repo_url.replace("git@github.com:", "https://github.com/")
        
        cmd = ["git", "clone", "-b", branch, "--depth", "1", clone_url, target_dir]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"[ERROR] Failed to clone repository: {result.stderr}")
            return False
        
        print(f"[SUCCESS] Repository cloned to: {target_dir}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Exception during clone: {e}")
        return False


def find_files_with_extensions(
    directory: str,
    extensions: List[str],
    exclude_patterns: Optional[List[str]] = None
) -> List[str]:
    """Find all files with given extensions in directory."""
    if exclude_patterns is None:
        exclude_patterns = []
    
    found_files = []
    
    print(f"[INFO] Scanning for files with extensions: {', '.join(extensions)}")
    
    for root, dirs, files in os.walk(directory):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        # Check exclude patterns
        rel_root = os.path.relpath(root, directory)
        skip = False
        for pattern in exclude_patterns:
            if pattern in rel_root or rel_root.startswith(pattern):
                skip = True
                break
        
        if skip:
            continue
        
        for file in files:
            file_path = os.path.join(root, file)
            
            # Check if file has one of the target extensions
            for ext in extensions:
                if file.endswith(ext):
                    rel_path = os.path.relpath(file_path, directory)
                    found_files.append(rel_path)
                    break
    
    return sorted(found_files)


def generate_component_name(file_path: str, remove_extension: bool = True) -> str:
    """Generate a component name from file path."""
    # Get the filename without directory
    filename = os.path.basename(file_path)
    
    # Remove extension if requested
    if remove_extension:
        filename = os.path.splitext(filename)[0]
    
    # Convert to title case and replace underscores/hyphens with spaces
    name = filename.replace('_', ' ').replace('-', ' ')
    name = ' '.join(word.capitalize() for word in name.split())
    
    return name


def generate_component_slug(file_path: str, remove_extension: bool = True) -> str:
    """Generate a component slug from file path."""
    # Get the filename without directory
    filename = os.path.basename(file_path)
    
    # Remove extension if requested
    if remove_extension:
        filename = os.path.splitext(filename)[0]
    
    # Convert to lowercase and replace spaces/underscores with hyphens
    slug = filename.lower()
    slug = re.sub(r'[_\s]+', '-', slug)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    
    return slug


def generate_filemask(file_path: str, language_placeholder: str = "*") -> str:
    """Generate filemask for translation files."""
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    name, ext = os.path.splitext(filename)
    
    # Generate pattern: path/filename_*.ext
    filemask = os.path.join(directory, f"{name}_{language_placeholder}{ext}")
    
    return filemask


def generate_push_branch(component_slug: str, prefix: str = "weblate") -> str:
    """Generate push branch name."""
    return f"{prefix}-{component_slug}"


def generate_component_config(
    file_path: str,
    project_config: Dict[str, Any],
    component_defaults: Dict[str, Any],
    languages: List[str],
    wait_for_ready: bool,
    trigger_update: bool
) -> Dict[str, Any]:
    """Generate complete component configuration for a file."""
    
    # Generate component-specific values
    component_name = generate_component_name(file_path)
    component_slug = generate_component_slug(file_path)
    filemask = generate_filemask(file_path)
    
    # Use push_branch from component_defaults if specified, otherwise auto-generate
    if "push_branch" in component_defaults and component_defaults["push_branch"]:
        push_branch = component_defaults["push_branch"]
    else:
        push_branch = generate_push_branch(component_slug)
    
    # Determine file format from extension
    ext = os.path.splitext(file_path)[1]
    format_map = {
        '.adoc': 'asciidoc',
        '.po': 'po',
        '.pot': 'po',
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.xliff': 'xliff',
        '.xlf': 'xliff',
        '.md': 'markdown',
        '.txt': 'txt',
        '.html': 'html',
    }
    file_format = format_map.get(ext.lower(), 'auto')
    
    # Build component configuration
    component = {
        "name": component_name,
        "slug": component_slug,
        "vcs": component_defaults.get("vcs", "github"),
        "repo": component_defaults.get("repo"),
        "push": component_defaults.get("push"),
        "branch": component_defaults.get("branch", "develop"),
        "push_branch": push_branch,
        "filemask": filemask,
        "template": file_path,
        "new_base": file_path,
        "file_format": file_format,
        "edit_template": component_defaults.get("edit_template", False),
        "source_language": component_defaults.get("source_language", "en"),
        "license": component_defaults.get("license", ""),
        "allow_translation_propagation": component_defaults.get("allow_translation_propagation", True),
        "enable_suggestions": component_defaults.get("enable_suggestions", True),
        "suggestion_voting": component_defaults.get("suggestion_voting", False),
        "suggestion_autoaccept": component_defaults.get("suggestion_autoaccept", 0),
        "check_flags": component_defaults.get("check_flags", ""),
        "hide_glossary_matches": component_defaults.get("hide_glossary_matches", False),
        # Restrict language_regex to only match valid language codes (BCP47 format)
        # This prevents matching non-translation files like *_fwd.adoc
        # Pattern: 2-3 lowercase letters (language), optional script (_Script), optional region (_REGION)
        # Explicitly allows Chinese: zh, zh_Hans, zh_Hant, zh_CN, zh_TW, zh_Hans_CN, etc.
        "language_regex": component_defaults.get(
            "language_regex",
            r"^[a-z]{2,3}(_[A-Z][a-z]{3})?(_[A-Z]{2})?$"
        ),
    }
    
    # Build full setup configuration
    setup_config = {
        "project": project_config,
        "component": component,
        "languages": languages,
        "wait_for_ready": wait_for_ready,
        "trigger_update": trigger_update,
    }
    
    return setup_config


def save_component_config(config: Dict[str, Any], output_dir: str, component_slug: str) -> str:
    """Save component configuration to JSON file."""
    output_file = os.path.join(output_dir, f"setup_{component_slug}.json")
    
    with open(output_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    return output_file


def create_components_from_setup_files(
    setup_files: List[str],
    setup_script: str,
    delay_between_components: int = 5
) -> Dict[str, bool]:
    """
    Create components in Weblate using generated setup files.
    
    Components are created sequentially with delays to avoid conflicts.
    
    Args:
        setup_files: List of setup JSON file paths
        setup_script: Path to create_component_and_add_translation.py script
        delay_between_components: Delay in seconds between component creations (default: 5)
    
    Returns a dict mapping setup file paths to success status.
    """
    results = {}
    
    print(f"\n{'='*60}")
    print(f"Creating Components in Weblate (Sequential)")
    print(f"{'='*60}")
    print(f"[INFO] Total components to create: {len(setup_files)}")
    print(f"[INFO] Delay between components: {delay_between_components}s")
    print(f"[INFO] This ensures proper synchronization and avoids conflicts\n")
    
    if not os.path.exists(setup_script):
        print(f"[ERROR] Setup script not found: {setup_script}")
        return results
    
    total = len(setup_files)
    success_count = 0
    failed_count = 0
    failed_components = []
    
    for idx, setup_file in enumerate(setup_files, 1):
        component_name = os.path.basename(setup_file).replace('setup_', '').replace('.json', '')
        
        print(f"\n{'='*60}")
        print(f"[{idx}/{total}] Component: {component_name}")
        print(f"{'='*60}")
        print(f"[INFO] Config: {setup_file}")
        
        try:
            # Run create_component_and_add_translation.py for this setup file
            cmd = [sys.executable, setup_script, '--config', setup_file]
            
            print(f"[INFO] Starting component creation...")
            start_time = time.time()
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout per component
            )
            
            elapsed = time.time() - start_time
            
            if result.returncode == 0:
                print(f"[SUCCESS] Component created in {elapsed:.1f}s")
                results[setup_file] = True
                success_count += 1
                
                # Add delay before next component (except for last one)
                if idx < total:
                    print(f"[INFO] Waiting {delay_between_components}s before next component...")
                    time.sleep(delay_between_components)
            else:
                print(f"[ERROR] Failed to create component (exit code: {result.returncode})")
                if result.stderr:
                    # Print first few lines of error
                    error_lines = result.stderr.strip().split('\n')
                    print(f"[ERROR] Details:")
                    for line in error_lines[:5]:
                        print(f"  {line}")
                    if len(error_lines) > 5:
                        print(f"  ... ({len(error_lines) - 5} more lines)")

                # Retry once after a short backoff (transient lock/timing issues)
                print(f"[INFO] Retrying once after {delay_between_components}s...")
                time.sleep(delay_between_components)
                retry = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if retry.returncode == 0:
                    elapsed2 = time.time() - start_time
                    print(f"[SUCCESS] Component created on retry in {elapsed2:.1f}s")
                    results[setup_file] = True
                    success_count += 1
                else:
                    print(f"[ERROR] Retry failed (exit code: {retry.returncode})")
                    if retry.stderr:
                        retry_err_lines = retry.stderr.strip().split('\n')
                        for line in retry_err_lines[:5]:
                            print(f"  {line}")
                        if len(retry_err_lines) > 5:
                            print(f"  ... ({len(retry_err_lines) - 5} more lines)")
                    results[setup_file] = False
                    failed_count += 1
                    failed_components.append(component_name)
                
                # Add delay before next component (except for last one)
                if idx < total:
                    print(f"[INFO] Waiting {delay_between_components}s before continuing...")
                    time.sleep(delay_between_components)
                
        except subprocess.TimeoutExpired:
            print(f"[ERROR] Timeout - component creation took longer than 5 minutes")
            results[setup_file] = False
            failed_count += 1
            failed_components.append(component_name)
            
            # Add delay after timeout
            if idx < total:
                print(f"[INFO] Waiting {delay_between_components}s before continuing...")
                time.sleep(delay_between_components)
                
        except Exception as e:
            print(f"[ERROR] Exception: {e}")
            results[setup_file] = False
            failed_count += 1
            failed_components.append(component_name)
            
            # Add delay after exception
            if idx < total:
                print(f"[INFO] Waiting {delay_between_components}s before continuing...")
                time.sleep(delay_between_components)
    
    # Final Summary
    print(f"\n{'='*60}")
    print(f"Component Creation Summary")
    print(f"{'='*60}")
    print(f"  Total:   {total}")
    print(f"  Success: {success_count}")
    print(f"  Failed:  {failed_count}")
    
    if failed_components:
        print(f"\nFailed components:")
        for comp in failed_components:
            print(f"  - {comp}")
    
    print(f"{'='*60}\n")
    
    return results


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description='Auto-generate Weblate component setup files from repository',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate configs from a project configuration file
  %(prog)s --config project_config.json

  # Generate configs and automatically create all components in Weblate
  %(prog)s --config project_config.json --create-components

  # Generate and create components with custom delay (10 seconds)
  %(prog)s --config project_config.json --create-components --delay 10

  # Generate with custom output directory
  %(prog)s --config project_config.json --output ./my-configs

  # Scan local directory instead of cloning
  %(prog)s --config project_config.json --local-repo /path/to/repo
  
  # Dry run to see what would be generated
  %(prog)s --config project_config.json --dry-run

Project configuration file format:
{
  "project": {
    "name": "Project Name",
    "slug": "project-slug",
    "web": "https://example.com",
    "instructions": "Translation instructions...",
    "access_control": 0
  },
  "component_defaults": {
    "vcs": "github",
    "repo": "git@github.com:user/repo.git",
    "push": "git@github.com:user/repo.git",
    "branch": "develop",
    "source_language": "en"
  },
  "languages": ["zh_Hans"],
  "wait_for_ready": true,
  "trigger_update": true,
  "scan": {
    "github_path": "doc/modules/ROOT",
    "extensions": [".adoc", ".md"],
    "exclude_patterns": ["test", "examples", "build", ".git"]
  }
}

Notes:
  - github_path: (optional) Relative path within the repository to scan.
                 If omitted, scans the entire repository root.
  - extensions: List of file extensions to search for (e.g., [".adoc", ".md"])
  - exclude_patterns: Directories/patterns to skip during scanning
        """
    )
    
    parser.add_argument(
        '--config',
        type=str,
        required=True,
        help='Project configuration JSON file'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='./setup',
        help='Output directory for generated setup files (default: ./setup)'
    )
    parser.add_argument(
        '--local-repo',
        type=str,
        help='Path to local repository (skip cloning)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be generated without creating files'
    )
    parser.add_argument(
        '--create-components',
        action='store_true',
        help='Automatically create components in Weblate after generating setup files'
    )
    parser.add_argument(
        '--setup-script',
        type=str,
        default='./create_component_and_add_translation.py',
        help='Path to create_component_and_add_translation.py script (default: ./create_component_and_add_translation.py)'
    )
    parser.add_argument(
        '--delay',
        type=int,
        default=5,
        help='Delay in seconds between component creations (default: 5)'
    )
    
    return parser


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Load project configuration
    print(f"[INFO] Loading configuration from: {args.config}")
    config = load_config(args.config)
    
    # Validate configuration
    if 'project' not in config:
        print("[ERROR] Missing 'project' section in config")
        return 1
    
    if 'component_defaults' not in config:
        print("[ERROR] Missing 'component_defaults' section in config")
        return 1
    
    if 'scan' not in config or 'extensions' not in config['scan']:
        print("[ERROR] Missing 'scan.extensions' in config")
        return 1
    
    project_config = config['project']
    component_defaults = config['component_defaults']
    scan_config = config['scan']
    
    # Get top-level settings
    languages = config.get('languages', ['zh_Hans'])
    wait_for_ready = config.get('wait_for_ready', True)
    trigger_update = config.get('trigger_update', True)
    
    # Determine repository location
    if args.local_repo:
        repo_dir = args.local_repo
        print(f"[INFO] Using local repository: {repo_dir}")
    else:
        # Clone repository to temporary directory
        repo_url = component_defaults.get('repo')
        branch = component_defaults.get('branch', 'develop')
        
        if not repo_url:
            print("[ERROR] No repository URL in component_defaults.repo")
            return 1
        
        temp_dir = tempfile.mkdtemp(prefix='weblate_scan_')
        repo_dir = temp_dir
        
        if not clone_repository(repo_url, branch, repo_dir):
            return 1
    
    # Determine scan directory
    scan_dir = repo_dir
    github_path = scan_config.get('github_path')
    
    if github_path:
        # github_path is a relative path within the repository
        # e.g., "doc/modules/ROOT" or "src/locales"
        scan_dir = os.path.join(repo_dir, github_path)
        print(f"[INFO] Scanning subdirectory: {github_path}")
        
        if not os.path.exists(scan_dir):
            print(f"[ERROR] Scan directory does not exist: {scan_dir}")
            return 1
    
    # Find files with target extensions
    extensions = scan_config['extensions']
    exclude_patterns = scan_config.get('exclude_patterns', [])
    
    files = find_files_with_extensions(scan_dir, extensions, exclude_patterns)
    
    # Convert absolute paths back to repository-relative paths
    if scan_dir != repo_dir:
        subdir_rel = os.path.relpath(scan_dir, repo_dir)
        files = [os.path.join(subdir_rel, f) for f in files]
    
    if not files:
        print(f"[WARNING] No files found with extensions: {', '.join(extensions)}")
        return 0
    
    print(f"\n[SUCCESS] Found {len(files)} file(s)")
    
    # Create output directory if it doesn't exist
    output_dir = args.output
    if not args.dry_run:
        os.makedirs(output_dir, exist_ok=True)
        print(f"[INFO] Output directory: {output_dir}\n")
    
    # Generate component configurations
    generated_count = 0
    generated_files = []  # Track generated files for --create-components
    
    for file_path in files:
        print(f"\n[INFO] Processing: {file_path}")
        
        # Generate configuration
        component_config = generate_component_config(
            file_path,
            project_config,
            component_defaults,
            languages,
            wait_for_ready,
            trigger_update
        )
        
        component_slug = component_config['component']['slug']
        
        if args.dry_run:
            print(f"[DRY-RUN] Would create: setup_{component_slug}.json")
            print(f"  Component: {component_config['component']['name']}")
            print(f"  Filemask: {component_config['component']['filemask']}")
        else:
            # Save configuration
            output_file = save_component_config(
                component_config,
                output_dir,
                component_slug
            )
            print(f"[SUCCESS] Created: {output_file}")
            generated_files.append(output_file)
            generated_count += 1
    
    # Summary
    print(f"\n{'='*60}")
    if args.dry_run:
        print(f"[DRY-RUN] Would generate {len(files)} setup file(s) in: {output_dir}")
        if args.create_components:
            print(f"[DRY-RUN] Would also create {len(files)} components in Weblate")
    else:
        print(f"[SUCCESS] Generated {generated_count} setup file(s) in: {output_dir}")
        
        if not args.create_components:
            print(f"\nNext steps:")
            print(f"  1. Review the generated setup files in {output_dir}/")
            print(f"  2. Run each setup file:")
            print(f"     cd {os.path.dirname(os.path.abspath(__file__))}")
            print(f"     for file in {output_dir}/setup_*.json; do")
            print(f"       python3 ./create_component_and_add_translation.py --config \"$file\"")
            print(f"     done")
            print(f"  Or run with --create-components to auto-create all components")
    print(f"{'='*60}")
    
    # Create components if requested
    if args.create_components and not args.dry_run and generated_files:
        print(f"\n[INFO] Creating components in Weblate...")
        create_components_from_setup_files(
            generated_files,
            args.setup_script,
            delay_between_components=args.delay
        )
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

