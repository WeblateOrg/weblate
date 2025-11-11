#!/usr/bin/env python3
"""
Weblate Project & Component Creator

Automatically creates Weblate translation projects and components via API.
Supports both configuration files and interactive mode.

Usage:
    # Create from configuration file
    python create_weblate_project.py --config config.json
    
    # Interactive mode
    python create_weblate_project.py --interactive
    
    # Generate example configuration
    python create_weblate_project.py --example

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
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    print("Error: requests library not found.", flush=True)
    print("Install it with: pip install requests", flush=True)
    sys.exit(1)


# Configuration constants
MAX_LINE_LENGTH = 88  # PEP 8 line length limit
DEFAULT_WAIT_TIME = 600  # Seconds to wait for component to be ready
POLL_INTERVAL = 2  # Seconds between readiness checks


class WeblateProjectCreator:
    """Create Weblate projects and components via API."""

    def __init__(self, base_url: str, api_token: str):
        """Initialize the creator with API credentials."""
        self.base_url = base_url.rstrip('/')
        self.api_url = urljoin(self.base_url, '/api/')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Token {api_token}',
            'Content-Type': 'application/json',
        })

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        silent_on_404: bool = False,
    ) -> requests.Response:
        """Make an API request with error handling."""
        url = urljoin(self.api_url, endpoint)
        print(f"[API] {method} {url}", flush=True)
        
        try:
            response = self._execute_request(method, url, data, params)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            self._handle_http_error(e, silent_on_404)
            raise
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Request failed: {e}", flush=True)
            raise

    def _execute_request(
        self,
        method: str,
        url: str,
        data: Optional[Dict[str, Any]],
        params: Optional[Dict[str, Any]]
    ) -> requests.Response:
        """Execute the actual HTTP request."""
        method = method.upper()
        if method == 'GET':
            return self.session.get(url, params=params)
        elif method == 'POST':
            return self.session.post(url, json=data, params=params)
        elif method == 'PATCH':
            return self.session.patch(url, json=data)
        elif method == 'DELETE':
            return self.session.delete(url)
        else:
            raise ValueError(f"Unsupported method: {method}")

    def _handle_http_error(
        self,
        error: requests.exceptions.HTTPError,
        silent_on_404: bool
    ) -> None:
        """Handle HTTP errors with optional 404 suppression."""
        if not (silent_on_404 and error.response.status_code == 404):
            status = error.response.status_code
            text = error.response.text
            print(f"[ERROR] HTTP {status}: {text}", flush=True)

    def check_connection(self) -> bool:
        """Verify API connection and authentication."""
        try:
            self._make_request('GET', '')
            print("[SUCCESS] Connected to Weblate API", flush=True)
            return True
        except Exception as e:
            print(f"[ERROR] Cannot connect to Weblate API: {e}", flush=True)
            return False

    def project_exists(self, slug: str) -> bool:
        """Check if a project exists."""
        try:
            self._make_request(
                'GET',
                f'projects/{slug}/',
                silent_on_404=True
            )
            return True
        except requests.exceptions.HTTPError as e:
            return e.response.status_code != 404

    def create_project(
        self,
        project_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new project or return existing one."""
        slug = project_config.get('slug')
        
        if self.project_exists(slug):
            print(f"[WARNING] Project '{slug}' already exists", flush=True)
            return self._make_request('GET', f'projects/{slug}/').json()
        
        print(f"[INFO] Creating project: {project_config['name']}", flush=True)
        response = self._make_request(
            'POST',
            'projects/',
            data=project_config
        )
        project = response.json()
        print(f"[SUCCESS] Project created: {project['web_url']}", flush=True)
        return project

    def component_exists(
        self,
        project_slug: str,
        component_slug: str
    ) -> bool:
        """Check if a component exists."""
        try:
            endpoint = f'components/{project_slug}/{component_slug}/'
            self._make_request('GET', endpoint, silent_on_404=True)
            return True
        except requests.exceptions.HTTPError as e:
            return e.response.status_code != 404

    def create_component(
        self,
        project_slug: str,
        component_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new component or return existing one."""
        component_slug = component_config.get('slug')
        
        if self.component_exists(project_slug, component_slug):
            msg = f"[WARNING] Component '{component_slug}' already exists"
            print(msg, flush=True)
            endpoint = f'components/{project_slug}/{component_slug}/'
            return self._make_request('GET', endpoint).json()
        
        print(f"[INFO] Creating component: {component_config['name']}", flush=True)
        print(f"[INFO] Repository: {component_config.get('repo')}", flush=True)
        print(f"[INFO] Branch: {component_config.get('branch')}", flush=True)
        
        response = self._make_request(
            'POST',
            f'projects/{project_slug}/components/',
            data=component_config
        )
        component = response.json()
        print(f"[SUCCESS] Component created: {component['web_url']}", flush=True)
        return component

    def trigger_component_update(
        self,
        project_slug: str,
        component_slug: str
    ) -> bool:
        """Trigger VCS update for a component."""
        print(f"[INFO] Triggering VCS update for {project_slug}/{component_slug}", flush=True)
        
        try:
            endpoint = f'components/{project_slug}/{component_slug}/repository/'
            self._make_request('POST', endpoint, data={'operation': 'pull'})
            print("[SUCCESS] VCS update triggered", flush=True)
            return True
        except Exception as e:
            print(f"[ERROR] Failed to trigger update: {e}", flush=True)
            return False

    def verify_and_fix_component_settings(
        self,
        project_slug: str,
        component_slug: str,
        expected_config: Dict[str, Any]
    ) -> bool:
        """Verify and fix component settings to match JSON config."""
        print("[INFO] Verifying component settings match JSON config...", flush=True)
        
        try:
            current_config = self._get_component_config(
                project_slug,
                component_slug
            )
            updates_needed = self._find_config_differences(
                current_config,
                expected_config
            )
            
            if updates_needed:
                self._apply_config_updates(
                    project_slug,
                    component_slug,
                    updates_needed
                )
            else:
                print("[SUCCESS] Component settings match JSON config", flush=True)
            
            return True
        except Exception as e:
            print(f"[ERROR] Failed to verify/fix settings: {e}", flush=True)
            return False

    def _get_component_config(
        self,
        project_slug: str,
        component_slug: str
    ) -> Dict[str, Any]:
        """Get current component configuration."""
        endpoint = f'components/{project_slug}/{component_slug}/'
        response = self._make_request('GET', endpoint)
        return response.json()

    def _find_config_differences(
        self,
        current_config: Dict[str, Any],
        expected_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Find differences between current and expected config."""
        critical_fields = [
            'repo', 'vcs', 'branch', 'push', 'push_branch',
            'filemask', 'template', 'new_base', 'file_format',
            'edit_template', 'source_language'
        ]
        
        updates_needed = {}
        for field in critical_fields:
            if field not in expected_config:
                continue
            
            expected = self._normalize_value(
                expected_config[field],
                field
            )
            current = self._normalize_value(
                current_config.get(field),
                field
            )
            
            if current != expected:
                print(f"[WARNING] Field '{field}' mismatch:", flush=True)
                print(f"  Expected: {expected}", flush=True)
                print(f"  Current:  {current}", flush=True)
                updates_needed[field] = expected_config[field]
        
        return updates_needed

    def _normalize_value(
        self,
        value: Any,
        field: str
    ) -> Any:
        """Normalize a config value for comparison."""
        # Special handling for source_language
        if field == 'source_language' and isinstance(value, dict):
            return value.get('code')
        
        # Normalize empty strings and None
        if value == "" or value is None:
            return None
        
        return value

    def _apply_config_updates(
        self,
        project_slug: str,
        component_slug: str,
        updates: Dict[str, Any]
    ) -> None:
        """Apply configuration updates to component."""
        count = len(updates)
        print(f"[INFO] Applying {count} setting corrections...", flush=True)
        
        endpoint = f'components/{project_slug}/{component_slug}/'
        self._make_request('PATCH', endpoint, data=updates)
        print("[SUCCESS] Component settings corrected to match JSON config", flush=True)

    def wait_for_component_ready(
        self,
        project_slug: str,
        component_slug: str,
        max_wait: int = DEFAULT_WAIT_TIME
    ) -> bool:
        """Wait for component to be ready (repository cloned)."""
        print("[INFO] Waiting for component to be ready...", flush=True)
        print("[INFO] This may take a while for the first repository clone", flush=True)
        print(f"[INFO] Timeout in {max_wait}s. Checking every {POLL_INTERVAL}s...", flush=True)
        
        start_time = time.time()
        check_count = 0
        while time.time() - start_time < max_wait:
            check_count += 1
            elapsed = int(time.time() - start_time)
            
            # Show progress every 10 seconds
            if check_count % 5 == 0:  # Every 5 checks = 10 seconds
                print(f"[INFO] Still waiting... ({elapsed}s elapsed)", flush=True)
            
            if self._check_component_ready(
                project_slug,
                component_slug,
                silent=True
            ):
                return True
            time.sleep(POLL_INTERVAL)
        
        elapsed = int(time.time() - start_time)
        print(f"[INFO] Timeout after {elapsed}s (normal for large repositories)", flush=True)
        print("[INFO] Component created successfully, tasks continuing in background", flush=True)
        return False

    def _check_component_ready(
        self,
        project_slug: str,
        component_slug: str,
        silent: bool = False
    ) -> bool:
        """Check if component repository is cloned and ready."""
        try:
            endpoint = f'components/{project_slug}/{component_slug}/'
            
            # Make silent request without printing API call
            if silent:
                url = urljoin(self.api_url, endpoint)
                response = self.session.get(url)
                response.raise_for_status()
            else:
                response = self._make_request('GET', endpoint)
            
            component = response.json()
            
            # Check if component is not locked (locked = repository error)
            locked = component.get('locked', False)
            if locked:
                if not silent:
                    print("[WARNING] Component is locked (repository error)", flush=True)
                return False
            
            # Check if background task is complete (task_url will be None)
            task_url = component.get('task_url')
            if task_url:
                if not silent:
                    print("[INFO] Background task still running...", flush=True)
                return False
            
            # Component is ready if accessible and not locked
            # For monolingual components, translation_count can be 0
            count = component.get('translation_count', 0)
            if not silent:
                msg = f"[SUCCESS] Component ready with {count} translation(s)"
                print(msg, flush=True)
            return True
            
        except Exception as e:
            if not silent:
                print(f"[WARNING] Error checking component status: {e}", flush=True)
            return False

    def list_translations(
        self,
        project_slug: str,
        component_slug: str
    ) -> List[Dict[str, Any]]:
        """List all translations for a component."""
        try:
            endpoint = f'components/{project_slug}/{component_slug}/translations/'
            response = self._make_request('GET', endpoint)
            return response.json().get('results', [])
        except Exception as e:
            print(f"[ERROR] Failed to list translations: {e}", flush=True)
            return []

    def get_statistics(
        self,
        project_slug: str,
        component_slug: str
    ) -> Dict[str, Any]:
        """Get translation statistics for a component."""
        try:
            endpoint = f'components/{project_slug}/{component_slug}/statistics/'
            response = self._make_request('GET', endpoint)
            return response.json()
        except Exception as e:
            print(f"[ERROR] Failed to get statistics: {e}", flush=True)
            return {}


def load_config_from_file(config_file: str) -> Dict[str, Any]:
    """Load configuration from JSON file."""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] Config file not found: {config_file}", flush=True)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON in config file: {e}", flush=True)
        sys.exit(1)


def find_web_config() -> Optional[str]:
    """Find web.json in script directory or common locations."""
    # Check script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    web_config_path = os.path.join(script_dir, 'web.json')
    
    if os.path.exists(web_config_path):
        return web_config_path
    
    # Check current working directory
    if os.path.exists('web.json'):
        return 'web.json'
    
    return None


def load_web_config_auto() -> Dict[str, Any]:
    """Automatically load web.json if it exists."""
    web_config_path = find_web_config()
    
    if web_config_path:
        print(f"[INFO] Loading web config from: {web_config_path}", flush=True)
        return load_config_from_file(web_config_path)
    
    return {}


def merge_configs(
    web_config: Dict[str, Any],
    component_config: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge web and component configuration files."""
    merged = {}
    merged.update(web_config)
    merged.update(component_config)
    return merged


def interactive_config() -> Dict[str, Any]:
    """Interactively gather configuration from user."""
    print("=== Weblate Project Creation - Interactive Mode ===\n", flush=True)
    
    config = {
        'weblate_url': _prompt("Weblate URL", "http://localhost:8080"),
        'api_token': _prompt("API Token (from your profile)", required=True),
        'project': _gather_project_config(),
        'component': _gather_component_config(),
    }
    
    return config


def _prompt(message: str, default: str = "", required: bool = False) -> str:
    """Prompt user for input with optional default."""
    if default:
        value = input(f"{message} (default: {default}): ").strip()
        return value or default
    else:
        value = input(f"{message}: ").strip()
        if required and not value:
            print("[ERROR] This field is required", flush=True)
            return _prompt(message, default, required)
        return value


def _gather_project_config() -> Dict[str, Any]:
    """Gather project configuration interactively."""
    print("\n--- Project Configuration ---", flush=True)
    return {
        'name': _prompt("Project name", required=True),
        'slug': _prompt("Project slug (URL-friendly)", required=True),
        'web': _prompt("Project website URL", required=True),
        'instructions': _prompt("Instructions for translators (optional)"),
    }


def _gather_component_config() -> Dict[str, Any]:
    """Gather component configuration interactively."""
    print("\n--- Component Configuration ---", flush=True)
    
    config = {
        'name': _prompt("Component name", required=True),
        'slug': _prompt("Component slug (URL-friendly)", required=True),
        'vcs': _prompt("VCS type", default="git"),
        'repo': _prompt("Repository URL", required=True),
        'branch': _prompt("Branch", default="main"),
        'filemask': _prompt("File mask", required=True),
        'file_format': _prompt("File format", required=True),
    }
    
    # Add template for monolingual formats
    monolingual_formats = ['json', 'html', 'markdown', 'asciidoc']
    if config['file_format'] in monolingual_formats:
        template = _prompt("Template file path (for monolingual format)")
        if template:
            config['template'] = template
    
    return config


def get_example_config() -> Dict[str, Any]:
    """Get example configuration dictionary."""
    return {
        "weblate_url": "http://localhost:8080",
        "api_token": "YOUR_API_TOKEN_HERE",
        "project": {
            "name": "My Translation Project",
            "slug": "my-project",
            "web": "https://example.com",
            "instructions": "Please follow our translation guidelines.",
            "access_control": 0
        },
        "component": {
            "name": "Main Application",
            "slug": "main-app",
            "vcs": "git",
            "repo": "https://github.com/user/repo.git",
            "branch": "main",
            "push": "git@github.com:user/repo.git",
            "filemask": "locales/*/LC_MESSAGES/django.po",
            "file_format": "po",
            "new_base": "locales/django.pot",
            "license": "MIT",
            "allow_translation_propagation": True,
            "enable_suggestions": True
        },
        "wait_for_ready": True,
        "trigger_update": True
    }


def create_example_config_file(
    filename: str = 'weblate_config_example.json'
) -> None:
    """Create an example configuration file."""
    example_config = get_example_config()
    
    with open(filename, 'w') as f:
        json.dump(example_config, f, indent=2)
    
    print(f"[SUCCESS] Example config created: {filename}", flush=True)
    print(f"[INFO] Edit this file with your settings and run:", flush=True)
    print(f"       python {sys.argv[0]} --config {filename}", flush=True)


def setup_project_and_component(
    creator: WeblateProjectCreator,
    config: Dict[str, Any]
) -> tuple:
    """Create project and component, return their data."""
    project = creator.create_project(config['project'])
    project_slug = project['slug']
    
    component = creator.create_component(
        project_slug,
        config['component']
    )
    component_slug = component['slug']
    
    # Verify and fix settings to match JSON config
    creator.verify_and_fix_component_settings(
        project_slug,
        component_slug,
        config['component']
    )
    
    return project, component, project_slug, component_slug


def trigger_and_wait(
    creator: WeblateProjectCreator,
    project_slug: str,
    component_slug: str,
    config: Dict[str, Any]
) -> None:
    """Trigger VCS update and wait for component to be ready."""
    if config.get('trigger_update', True):
        creator.trigger_component_update(project_slug, component_slug)
    
    if config.get('wait_for_ready', True):
        if creator.wait_for_component_ready(project_slug, component_slug):
            _print_translation_info(creator, project_slug, component_slug)


def _print_translation_info(
    creator: WeblateProjectCreator,
    project_slug: str,
    component_slug: str
) -> None:
    """Print discovered translations and statistics."""
    translations = creator.list_translations(project_slug, component_slug)
    
    if translations:
        print("\n[INFO] Discovered translations:", flush=True)
        for trans in translations:
            lang = trans.get('language', {})
            name = lang.get('name', 'Unknown')
            code = lang.get('code', '?')
            print(f"  - {name} ({code})", flush=True)
    else:
        print("\n[INFO] No translations discovered yet", flush=True)
    
    stats = creator.get_statistics(project_slug, component_slug)
    if stats:
        total = stats.get('total', 0)
        translated = stats.get('translated', 0)
        # print(f"\n[INFO] Statistics: {translated}/{total} strings translated", flush=True)


def print_success_summary(
    project: Dict[str, Any],
    component: Dict[str, Any]
) -> None:
    """Print success summary with URLs."""
    print("\n[SUCCESS] Setup complete!", flush=True)
    print(f"[INFO] Project URL: {project['web_url']}", flush=True)
    print(f"[INFO] Component URL: {component['web_url']}", flush=True)


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser with all options."""
    parser = argparse.ArgumentParser(
        description='Automatically create Weblate projects and components',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create example config file
  %(prog)s --example

  # Create from component config with web config
  %(prog)s --config component.json --web-config web.json

  # Create from single merged config file
  %(prog)s --config weblate_config.json

  # Interactive mode
  %(prog)s --interactive

  # With command-line overrides
  %(prog)s --config config.json --url http://localhost:8080 --token wlu_xxx

Note:
  You must provide credentials via --web-config, merged config file,
  command-line args (--url, --token), or interactive mode.
  
  For automatic web.json loading, use setup_component.py instead.
        """
    )
    
    parser.add_argument(
        '--config',
        type=str,
        help='Component configuration JSON file'
    )
    parser.add_argument(
        '--web-config',
        type=str,
        help='Web configuration JSON file with weblate_url and api_token'
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Interactive configuration mode'
    )
    parser.add_argument(
        '--example',
        action='store_true',
        help='Create example configuration file'
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


def load_config(args: argparse.Namespace) -> Dict[str, Any]:
    """Load configuration based on command line arguments."""
    if args.config:
        # Load component config
        config = load_config_from_file(args.config)
        
        # Load web config if explicitly specified
        if args.web_config:
            web_config = load_config_from_file(args.web_config)
            config = merge_configs(web_config, config)
    elif args.interactive:
        config = interactive_config()
    else:
        return {}
    
    # Override with command line arguments
    if args.url:
        config['weblate_url'] = args.url
    if args.token:
        config['api_token'] = args.token
    
    return config


def validate_config(config: Dict[str, Any]) -> bool:
    """Validate required configuration fields."""
    if not config.get('weblate_url') or not config.get('api_token'):
        print("[ERROR] Missing Weblate URL or API token", flush=True)
        return False
    return True


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Handle example config creation
    if args.example:
        create_example_config_file()
        return 0
    
    # Load configuration
    config = load_config(args)
    if not config:
        parser.print_help()
        print("\n[ERROR] Please specify --config, --interactive, or --example", flush=True)
        return 1
    
    # Validate configuration
    if not validate_config(config):
        return 1
    
    # Create project and component
    creator = WeblateProjectCreator(
        config['weblate_url'],
        config['api_token']
    )
    
    if not creator.check_connection():
        return 1
    
    try:
        project, component, project_slug, component_slug = \
            setup_project_and_component(creator, config)
        
        trigger_and_wait(creator, project_slug, component_slug, config)
        
        print_success_summary(project, component)
        return 0
    
    except Exception as e:
        print(f"\n[ERROR] Failed to create project/component: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
