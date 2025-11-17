#!/usr/bin/env python3
"""
Weblate Translation Creator

Adds new language translations to existing Weblate components.

Usage:
    # Add single translation
    python add_translation.py --project my-project --component main \
        --language fr
    
    # Add multiple translations
    python add_translation.py --project my-project --component main \
        --language fr,de,es
    
    # Interactive mode
    python add_translation.py --interactive

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
    print("Error: requests library not found.")
    print("Install it with: pip install requests")
    sys.exit(1)


def load_web_config(config_file: str) -> Dict[str, Any]:
    """Load web configuration from JSON file."""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] Config file not found: {config_file}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON in config file: {e}")
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
        print(f"[INFO] Loading web config from: {web_config_path}")
        return load_web_config(web_config_path)
    
    return {}


class WeblateTranslationCreator:
    """Add translations to Weblate components via API."""

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
            print(f"[ERROR] HTTP {status}: {text}")

    def check_connection(self) -> bool:
        """Verify API connection and authentication."""
        try:
            self._make_request('GET', '')
            print("[SUCCESS] Connected to Weblate API")
            return True
        except Exception as e:
            print(f"[ERROR] Cannot connect to Weblate API: {e}")
            return False

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

    def language_exists(self, language_code: str) -> bool:
        """Check if a language code is valid in Weblate."""
        try:
            endpoint = f'languages/{language_code}/'
            self._make_request('GET', endpoint, silent_on_404=True)
            return True
        except requests.exceptions.HTTPError as e:
            return e.response.status_code != 404

    def translation_exists(
        self,
        project_slug: str,
        component_slug: str,
        language_code: str
    ) -> bool:
        """Check if a translation already exists."""
        try:
            endpoint = (
                f'translations/{project_slug}/{component_slug}/'
                f'{language_code}/'
            )
            self._make_request('GET', endpoint, silent_on_404=True)
            return True
        except requests.exceptions.HTTPError as e:
            return e.response.status_code != 404

    def get_component_info(
        self,
        project_slug: str,
        component_slug: str
    ) -> Dict[str, Any]:
        """Get component information."""
        endpoint = f'components/{project_slug}/{component_slug}/'
        response = self._make_request('GET', endpoint)
        return response.json()

    def get_language_info(self, language_code: str) -> Dict[str, Any]:
        """Get language information."""
        endpoint = f'languages/{language_code}/'
        response = self._make_request('GET', endpoint)
        return response.json()

    def _get_translation_info(
        self,
        project_slug: str,
        component_slug: str,
        language_code: str
    ) -> Dict[str, Any]:
        """Get complete translation information."""
        endpoint = (
            f'translations/{project_slug}/{component_slug}/'
            f'{language_code}/'
        )
        response = self._make_request('GET', endpoint)
        return response.json()

    def add_translation(
        self,
        project_slug: str,
        component_slug: str,
        language_code: str
    ) -> Dict[str, Any]:
        """Add a new translation to a component."""
        # Check if translation already exists
        print(f"[INFO] Checking if '{language_code}' translation exists...", flush=True)
        if self.translation_exists(project_slug, component_slug, language_code):
            print(f"[WARNING] Translation '{language_code}' already exists, fetching info...", flush=True)
            endpoint = (
                f'translations/{project_slug}/{component_slug}/'
                f'{language_code}/'
            )
            response = self._make_request('GET', endpoint)
            return response.json()

        print(f"[INFO] Creating translation: {language_code}", flush=True)
        
        # Create the translation
        endpoint = f'components/{project_slug}/{component_slug}/translations/'
        data = {'language_code': language_code}
        
        self._make_request('POST', endpoint, data=data)
        print(f"[INFO] Translation created, fetching details...", flush=True)
        
        # Fetch the complete translation info
        translation = self._get_translation_info(
            project_slug,
            component_slug,
            language_code
        )
        
        # Print translation info
        self._print_translation_info(translation)
        
        return translation

    def _print_translation_info(self, translation: Dict[str, Any]) -> None:
        """Print translation details."""
        lang = translation.get('language', {})
        print(f"\n[SUCCESS] Translation created: {lang.get('name', 'Unknown')}", flush=True)
        print(f"  Language code: {lang.get('code', '?')}", flush=True)
        print(f"  URL: {translation.get('web_url', 'N/A')}", flush=True)
        print(f"  File: {translation.get('filename', 'N/A')}", flush=True)
        
        # Show statistics if available
        if 'total' in translation:
            total = translation.get('total', 0)
            translated = translation.get('translated', 0)
            # print(f"  Progress: {translated}/{total} strings translated", flush=True)

    def list_available_languages(self) -> List[Dict[str, Any]]:
        """List all available languages in Weblate."""
        try:
            endpoint = 'languages/'
            response = self._make_request('GET', endpoint)
            data = response.json()
            return data.get('results', [])
        except Exception as e:
            print(f"[ERROR] Failed to list languages: {e}")
            return []

    def list_component_translations(
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
            print(f"[ERROR] Failed to list translations: {e}")
            return []


def parse_language_codes(language_arg: str) -> List[str]:
    """Parse comma-separated language codes."""
    return [code.strip() for code in language_arg.split(',') if code.strip()]


def validate_inputs(
    creator: WeblateTranslationCreator,
    project_slug: str,
    component_slug: str,
    language_codes: List[str]
) -> bool:
    """Validate that project, component, and languages exist."""
    print("[INFO] Validating inputs...", flush=True)
    
    # Check component exists
    if not creator.component_exists(project_slug, component_slug):
        print(f"[ERROR] Component '{project_slug}/{component_slug}' not found", flush=True)
        return False
    
    print(f"[SUCCESS] Component '{project_slug}/{component_slug}' exists", flush=True)
    
    # Note: We skip language validation because the API only returns
    # languages that already have translations. New languages won't be
    # visible via API until they're used, so we'll let Weblate validate
    # the language codes when creating the translation.
    print(f"[INFO] Will attempt to add {len(language_codes)} language(s)", flush=True)
    
    return True


def interactive_mode(creator: WeblateTranslationCreator) -> Dict[str, Any]:
    """Interactively gather parameters."""
    print("=== Add Translation - Interactive Mode ===\n")
    
    # Get project and component
    project_slug = input("Project slug: ").strip()
    component_slug = input("Component slug: ").strip()
    
    if not creator.component_exists(project_slug, component_slug):
        print(f"[ERROR] Component '{project_slug}/{component_slug}' not found")
        sys.exit(1)
    
    # Show component info
    comp_info = creator.get_component_info(project_slug, component_slug)
    print(f"\n[INFO] Component: {comp_info.get('name')}")
    print(f"[INFO] File format: {comp_info.get('file_format')}")
    
    # Show existing translations
    existing = creator.list_component_translations(project_slug, component_slug)
    if existing:
        print(f"\n[INFO] Existing translations ({len(existing)}):")
        for trans in existing[:10]:  # Show first 10
            lang = trans.get('language', {})
            print(f"  - {lang.get('name')} ({lang.get('code')})")
        if len(existing) > 10:
            print(f"  ... and {len(existing) - 10} more")
    
    # Get language codes
    print("\n[INFO] Enter language codes to add (comma-separated)")
    print("[INFO] Example: fr, de, es")
    lang_input = input("Language codes: ").strip()
    language_codes = parse_language_codes(lang_input)
    
    return {
        'project_slug': project_slug,
        'component_slug': component_slug,
        'language_codes': language_codes
    }


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description='Add language translations to Weblate components',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add single translation with web config
  %(prog)s --web-config web.json --project my-project --component main \
      --language fr

  # Add multiple translations
  %(prog)s --web-config web.json --project my-project --component main \
      --language fr,de,es

  # With command-line credentials
  %(prog)s --url http://localhost:8080 --token wlu_xxx \
      --project my-project --component main --language fr

  # Interactive mode
  %(prog)s --interactive
  
  # List available languages
  %(prog)s --web-config web.json --list-languages

  # List component translations
  %(prog)s --web-config web.json --project my-project --component main --list

Note:
  You must provide credentials via --web-config, command-line args
  (--url, --token), or WEBLATE_TOKEN environment variable.
  
  For automatic web.json loading, use create_component_and_add_translation.py instead.
        """
    )
    
    parser.add_argument(
        '--project',
        type=str,
        help='Project slug'
    )
    parser.add_argument(
        '--component',
        type=str,
        help='Component slug'
    )
    parser.add_argument(
        '--language',
        type=str,
        help='Language code(s), comma-separated (e.g., fr,de,es)'
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Interactive mode'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List existing translations for component'
    )
    parser.add_argument(
        '--list-languages',
        action='store_true',
        help='List all available language codes'
    )
    parser.add_argument(
        '--web-config',
        type=str,
        help='Web configuration JSON file with weblate_url and api_token'
    )
    parser.add_argument(
        '--url',
        type=str,
        default='http://localhost:8080',
        help='Weblate base URL (default: http://localhost:8080)'
    )
    parser.add_argument(
        '--token',
        type=str,
        help='API token (or set WEBLATE_TOKEN environment variable)'
    )
    
    return parser


def get_api_credentials(
    args: argparse.Namespace
) -> tuple[str, str]:
    """Get API URL and token from args, config, or environment."""
    url = args.url
    token = args.token
    
    # Load from web config if explicitly specified
    if args.web_config:
        web_config = load_web_config(args.web_config)
        url = web_config.get('weblate_url', url)
        token = web_config.get('api_token', token)
    
    # Fall back to environment variable for token
    token = token or os.environ.get('WEBLATE_TOKEN')
    
    if not token:
        print("[ERROR] API token required")
        print("[INFO] Provide via --token, --web-config, or WEBLATE_TOKEN")
        sys.exit(1)
    
    return url, token


def handle_list_languages(creator: WeblateTranslationCreator) -> None:
    """Handle --list-languages option."""
    print("[INFO] Fetching available languages...\n")
    languages = creator.list_available_languages()
    
    if not languages:
        print("[ERROR] No languages found")
        return
    
    print(f"Available languages ({len(languages)}):\n")
    for lang in languages:
        code = lang.get('code', '?')
        name = lang.get('name', 'Unknown')
        direction = lang.get('direction', 'ltr')
        print(f"  {code:8} - {name:30} ({direction})")


def handle_list_translations(
    creator: WeblateTranslationCreator,
    project_slug: str,
    component_slug: str
) -> None:
    """Handle --list option."""
    print(f"[INFO] Listing translations for {project_slug}/{component_slug}...\n")
    
    translations = creator.list_component_translations(project_slug, component_slug)
    
    if not translations:
        print("[INFO] No translations found")
        return
    
    print(f"Existing translations ({len(translations)}):\n")
    for trans in translations:
        lang = trans.get('language', {})
        code = lang.get('code', '?')
        name = lang.get('name', 'Unknown')
        total = trans.get('total', 0)
        translated = trans.get('translated', 0)
        percent = trans.get('translated_percent', 0.0)
        print(f"  {code:8} - {name:30} {translated:4}/{total:4} ({percent:5.1f}%)")


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Get API credentials
    url, token = get_api_credentials(args)
    
    # Create API client
    creator = WeblateTranslationCreator(url, token)
    
    if not creator.check_connection():
        return 1
    
    # Handle --list-languages
    if args.list_languages:
        handle_list_languages(creator)
        return 0
    
    # Handle --list
    if args.list:
        if not args.project or not args.component:
            print("[ERROR] --list requires --project and --component")
            return 1
        handle_list_translations(creator, args.project, args.component)
        return 0
    
    # Get parameters (interactive or from args)
    if args.interactive:
        params = interactive_mode(creator)
    elif args.project and args.component and args.language:
        params = {
            'project_slug': args.project,
            'component_slug': args.component,
            'language_codes': parse_language_codes(args.language)
        }
    else:
        parser.print_help()
        print("\n[ERROR] Provide --project, --component, and --language")
        print("[INFO] Or use --interactive mode")
        return 1
    
    # Add translations using the batch function
    success_count = add_translations_batch(
        creator,
        params['project_slug'],
        params['component_slug'],
        params['language_codes']
    )
    
    return 0 if success_count > 0 else 1


def _verify_translations(
    creator: WeblateTranslationCreator,
    project_slug: str,
    component_slug: str,
    expected_count: int
) -> bool:
    """Verify translations are accessible."""
    try:
        translations = creator.list_component_translations(
            project_slug,
            component_slug
        )
        actual_count = len(translations)
        
        if actual_count >= expected_count:
            print(f"[SUCCESS] All {actual_count} translation(s) verified", flush=True)
            return True
        else:
            print(f"[WARNING] Expected {expected_count}, found {actual_count}", flush=True)
            return False
            
    except Exception as e:
        print(f"[WARNING] Could not verify translations: {e}", flush=True)
        return False


def add_translations_batch(
    creator: WeblateTranslationCreator,
    project_slug: str,
    component_slug: str,
    language_codes: List[str]
) -> int:
    """
    Add multiple translations sequentially with synchronization.
    
    This is a public API function that can be called from other scripts.
    Returns the number of successfully added translations.
    """
    if not language_codes:
        return 0
    
    # Validate inputs
    if not validate_inputs(creator, project_slug, component_slug, language_codes):
        return 0
    
    # Add translations sequentially with synchronization
    total = len(language_codes)
    print(f"\n[INFO] Adding {total} translation(s) sequentially...\n", flush=True)
    
    success_count = 0
    
    for idx, lang_code in enumerate(language_codes, 1):
        try:
            print(f"[INFO] [{idx}/{total}] Adding {lang_code}...", flush=True)
            
            # Add translation
            creator.add_translation(project_slug, component_slug, lang_code)
            success_count += 1
            
            # Wait between translations to ensure synchronization
            if idx < total:  # Don't wait after the last one
                wait_time = 2
                print(f"[INFO] Waiting {wait_time}s before next translation...", flush=True)
                time.sleep(wait_time)
            
        except Exception as e:
            print(f"[ERROR] Failed to add {lang_code}: {e}", flush=True)
            # Continue with next language even if one fails
            continue
    
    # Print summary
    print(f"\n[SUCCESS] Added {success_count}/{total} translation(s)", flush=True)
    
    # Final verification
    if success_count > 0 and total > 1:
        print("\n[INFO] Verifying all translations are accessible...", flush=True)
        _verify_translations(creator, project_slug, component_slug, success_count)
    
    return success_count


if __name__ == '__main__':
    sys.exit(main())

