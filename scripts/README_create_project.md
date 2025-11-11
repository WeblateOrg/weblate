# Weblate Project Creation Script

Automatically create Weblate translation projects, components, and discover translations using the REST API.

## Features

- ✅ Create projects with full configuration
- ✅ Create components with VCS integration
- ✅ Trigger automatic translation discovery
- ✅ Interactive or config file-based setup
- ✅ Wait for component readiness
- ✅ Display translation statistics
- ✅ Support for all file formats (including AsciiDoc)

## Requirements

```bash
pip install requests
```

## Usage

### 1. Get Your API Token

1. Log in to Weblate
2. Go to your profile (click your username → Settings)
3. Navigate to "API access" tab
4. Copy your API token (starts with `wlu_` or `wlp_`)

### 2. Create Example Configuration

```bash
python scripts/create_weblate_project.py --example
```

This creates `weblate_config_example.json` with all available options.

### 3. Edit Configuration

Edit the generated JSON file with your settings:

```json
{
  "weblate_url": "http://localhost:8080",
  "api_token": "wlu_YOUR_TOKEN_HERE",
  "project": {
    "name": "My Project",
    "slug": "my-project",
    "web": "https://example.com"
  },
  "component": {
    "name": "Main Component",
    "slug": "main",
    "vcs": "git",
    "repo": "https://github.com/user/repo.git",
    "branch": "main",
    "filemask": "locales/*/LC_MESSAGES/django.po",
    "file_format": "po"
  }
}
```

### 4. Run the Script

```bash
# Using config file
python scripts/create_weblate_project.py --config weblate_config.json

# Interactive mode
python scripts/create_weblate_project.py --interactive

# With URL override
python scripts/create_weblate_project.py --config config.json --url https://weblate.example.com
```

## Configuration Options

### Project Configuration

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Project display name |
| `slug` | Yes | URL-friendly project identifier |
| `web` | Yes | Project website URL |
| `instructions` | No | Instructions for translators |
| `access_control` | No | 0=Public, 1=Protected, 100=Private, 200=Custom |
| `translation_review` | No | Enable translation reviews |
| `source_review` | No | Enable source reviews |
| `enable_hooks` | No | Enable VCS hooks |
| `use_shared_tm` | No | Use shared translation memory |
| `contribute_shared_tm` | No | Contribute to shared TM |

### Component Configuration

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Component display name |
| `slug` | Yes | URL-friendly component identifier |
| `vcs` | No | Version control system (default: git) |
| `repo` | Yes | Repository URL (can be HTTPS or SSH) |
| `branch` | No | Repository branch (default: main or master) |
| `push` | **Recommended** | Push URL for committing translations (SSH recommended) |
| `push_branch` | No | Push branch (if different from `branch`) |
| `filemask` | Yes | File mask for translations (e.g., `po/*.po`) |
| `file_format` | Yes | File format (po, json, xliff, asciidoc, etc.) |
| `template` | No | Template file for monolingual formats |
| `new_base` | No | Base file for new translations |
| `license` | No | License identifier |
| `allow_translation_propagation` | No | Allow translation propagation (default: true) |
| `enable_suggestions` | No | Enable suggestions (default: true) |
| `suggestion_voting` | No | Enable suggestion voting (default: false) |
| `suggestion_autoaccept` | No | Auto-accept threshold (0 = disabled) |
| `check_flags` | No | Translation check flags (comma-separated) |

### VCS Configuration Notes

**Repository URL (`repo`):**
- HTTPS: `https://github.com/user/repo.git` (read-only)
- SSH: `git@github.com:user/repo.git` (read/write with SSH keys)

**Push URL (`push`):**
- **Required for write access** - Allows Weblate to commit translations back to VCS
- Should use SSH format: `git@github.com:user/repo.git`
- Must configure SSH keys in Weblate admin interface
- Can be same as `repo` if using SSH for both

**Push Branch (`push_branch`):**
- Branch where translations are committed
- If not set, uses same as `branch`
- Useful for separate translation branches

## Examples

### Example 1: Gettext PO Files (with Push)

```json
{
  "weblate_url": "http://localhost:8080",
  "api_token": "wlu_YOUR_TOKEN",
  "project": {
    "name": "Django Application",
    "slug": "django-app",
    "web": "https://example.com"
  },
  "component": {
    "name": "Main App",
    "slug": "main",
    "vcs": "git",
    "repo": "git@github.com:user/django-app.git",
    "push": "git@github.com:user/django-app.git",
    "branch": "main",
    "filemask": "locale/*/LC_MESSAGES/django.po",
    "file_format": "po",
    "new_base": "locale/django.pot"
  }
}
```

**Note:** Using SSH URLs (`git@github.com:...`) for both `repo` and `push` enables write access.

### Example 2: JSON i18next (Read-Only)

```json
{
  "component": {
    "name": "Web App",
    "slug": "webapp",
    "repo": "https://github.com/user/webapp.git",
    "branch": "main",
    "filemask": "locales/*.json",
    "file_format": "i18next",
    "template": "locales/en.json"
  }
}
```

**Note:** HTTPS URL without `push` setting = read-only mode (no commits back to repo).

### Example 3: AsciiDoc Documentation (Boost Unordered - BUD_03)

This is the actual configuration used for the Boost Unordered Documentation project:

```json
{
  "weblate_url": "http://localhost:8080",
  "api_token": "wlu_YOUR_TOKEN_HERE",
  "project": {
    "name": "Boost Unordered Documentation",
    "slug": "boost-unordered-documentation",
    "web": "https://www.boost.org/doc/libs/develop/doc/html/unordered.html",
    "instructions": "Please translate the Boost.Unordered documentation. Maintain technical accuracy and follow AsciiDoc formatting conventions.",
    "access_control": 0
  },
  "component": {
    "name": "BUD 03",
    "slug": "bud_03",
    "vcs": "git",
    "repo": "git@github.com:Giggly19890103/unordered.git",
    "push": "git@github.com:Giggly19890103/unordered.git",
    "branch": "develop",
    "push_branch": "develop",
    "filemask": "doc/modules/ROOT/pages/*.adoc",
    "file_format": "asciidoc",
    "template": "doc/modules/ROOT/pages/intro.adoc",
    "new_base": "doc/modules/ROOT/pages/intro.adoc",
    "license": "Boost Software License",
    "allow_translation_propagation": true,
    "enable_suggestions": true,
    "suggestion_voting": false,
    "suggestion_autoaccept": 0,
    "check_flags": "safe-html,strict-same,md-text"
  },
  "wait_for_ready": true,
  "trigger_update": true
}
```

**Key points:**
- Uses SSH URLs for both `repo` and `push` (requires SSH keys)
- Targets specific directory: `doc/modules/ROOT/pages/`
- Matches 52 .adoc files in that directory
- Uses `intro.adoc` as the template for monolingual translation
- Includes AsciiDoc-specific check flags

### Example 4: Android XML Resources (with Separate Push Branch)

```json
{
  "component": {
    "name": "Android App",
    "slug": "android",
    "repo": "git@github.com:user/android-app.git",
    "push": "git@github.com:user/android-app.git",
    "branch": "main",
    "push_branch": "translations",
    "filemask": "app/src/main/res/values-*/strings.xml",
    "file_format": "aresource",
    "template": "app/src/main/res/values/strings.xml"
  }
}
```

**Note:** This configuration:
- Pulls from `main` branch
- Pushes translations to `translations` branch
- Useful for review workflow before merging to main

### Example 5: Multiple Components

Create multiple configuration files and run them sequentially:

```bash
python scripts/create_weblate_project.py --config project1.json
python scripts/create_weblate_project.py --config project2.json
```

Or use the same project, different components:

```json
// component1.json
{
  "project": {"name": "App", "slug": "app", "web": "https://app.com"},
  "component": {
    "name": "Backend",
    "slug": "backend",
    "repo": "https://github.com/user/app.git",
    "filemask": "backend/locale/*/LC_MESSAGES/django.po",
    "file_format": "po"
  }
}

// component2.json  
{
  "project": {"name": "App", "slug": "app", "web": "https://app.com"},
  "component": {
    "name": "Frontend",
    "slug": "frontend",
    "repo": "https://github.com/user/app.git",
    "filemask": "frontend/src/locales/*.json",
    "file_format": "i18next"
  }
}
```

## Script Options

```
--config FILE         JSON configuration file
--interactive         Interactive configuration mode
--example            Create example configuration file
--url URL            Override Weblate base URL
--token TOKEN        Override API token
```

## Output

The script provides detailed progress information:

```
[API] POST https://weblate.example.com/api/projects/
[SUCCESS] Project created: https://weblate.example.com/projects/my-project/
[INFO] Creating component: Main App
[API] POST https://weblate.example.com/api/projects/my-project/components/
[SUCCESS] Component created: https://weblate.example.com/projects/my-project/main/
[INFO] Triggering VCS update for my-project/main
[API] POST https://weblate.example.com/api/components/my-project/main/repository/
[SUCCESS] VCS update triggered
[INFO] Waiting for component to be ready...
[SUCCESS] Component ready with 5 translations

[INFO] Discovered translations:
  - English (en)
  - Spanish (es)
  - French (fr)
  - German (de)
  - Chinese (zh_Hans)

[INFO] Statistics: 0/150 strings translated

[SUCCESS] Setup complete!
[INFO] Project URL: https://weblate.example.com/projects/my-project/
[INFO] Component URL: https://weblate.example.com/projects/my-project/main/
```

## Troubleshooting

### Authentication Error

```
[ERROR] HTTP 403: Forbidden
```

- Verify your API token is correct
- Check token hasn't expired
- Ensure token has necessary permissions

### Project Already Exists

```
[WARNING] Project 'my-project' already exists, skipping creation
```

- This is normal if project exists
- Component creation will proceed
- Change `slug` to create a new project

### Component Not Ready

```
[WARNING] Timeout waiting for component to be ready
```

- Translation files might not match `filemask`
- Check repository access
- Verify `file_format` is correct
- Manually trigger update in Weblate UI

### Repository Access Denied

```
[ERROR] Failed to trigger update: 401 Unauthorized
```

- Ensure repository is accessible
- For private repos, configure SSH keys in Weblate
- See: https://docs.weblate.org/en/latest/vcs.html

## SSH Configuration for Push Access

To enable Weblate to push translations back to your repository, you need to configure SSH keys.

### Step 1: Generate or Get Weblate SSH Key

```bash
# In Weblate web interface:
# 1. Go to: http://localhost:8080/admin/
# 2. Click "SSH keys" in the sidebar
# 3. Copy the public key (Ed25519 or RSA)
```

### Step 2: Add SSH Key to GitHub/GitLab

**For GitHub:**
1. Go to repository → Settings → Deploy keys
2. Click "Add deploy key"
3. Paste Weblate's public SSH key
4. ✅ Check "Allow write access"
5. Save

**For GitLab:**
1. Go to repository → Settings → Repository → Deploy Keys
2. Add key with write access

**For Personal Account (Multiple Repos):**
1. Go to your GitHub/GitLab profile → Settings → SSH keys
2. Add Weblate's public SSH key
3. Grant access to repositories

### Step 3: Test SSH Connection

```bash
# In Weblate container or server:
ssh -T git@github.com
# Should see: "Hi username! You've successfully authenticated..."
```

### Step 4: Use SSH URLs in Configuration

```json
{
  "component": {
    "repo": "git@github.com:user/repo.git",
    "push": "git@github.com:user/repo.git"
  }
}
```

### Troubleshooting SSH

**Permission Denied:**
```
[ERROR] Permission denied (publickey)
```
- SSH key not added to GitHub/GitLab
- Wrong repository permissions
- SSH key mismatch

**Host Key Verification Failed:**
```
[ERROR] Host key verification failed
```
- In Weblate admin → SSH keys → Add host key
- Enter: `github.com` or `gitlab.com`
- Verify fingerprint

## Advanced Usage

### Quick Start: Create BUD_03 Component

The `weblate_config_asciidoc_example.json` file is pre-configured for the BUD_03 component:

```bash
# 1. Get your API token from Weblate
# 2. Edit the config file
nano scripts/weblate_config_asciidoc_example.json
# Change "api_token": "YOUR_API_TOKEN_HERE" to your actual token

# 3. Run the script
python scripts/create_weblate_project.py \
  --config scripts/weblate_config_asciidoc_example.json
```

This will create:
- Project: "Boost Unordered Documentation"
- Component: "BUD 03"
- Discover ~52 .adoc translation files
- Enable push to `git@github.com:Giggly19890103/unordered.git`

### Using with Docker

```bash
# From inside Weblate container
docker exec -it weblate bash
cd /app
python scripts/create_weblate_project.py --config /data/config.json
```

### Automation with CI/CD

```yaml
# .github/workflows/setup-weblate.yml
name: Setup Weblate

on:
  push:
    branches: [main]

jobs:
  setup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup Weblate project
        run: |
          pip install requests
          python scripts/create_weblate_project.py \
            --url ${{ secrets.WEBLATE_URL }} \
            --token ${{ secrets.WEBLATE_TOKEN }} \
            --config weblate_config.json
```

### Batch Creation Script

```bash
#!/bin/bash
# create_multiple.sh

for config in configs/*.json; do
  echo "Processing $config..."
  python scripts/create_weblate_project.py --config "$config"
  sleep 5  # Rate limiting
done
```

## API Reference

For more details on API endpoints and parameters:

- API Documentation: https://docs.weblate.org/en/latest/api.html
- OpenAPI Schema: `http://your-weblate-url/api/schema/`
- API Browser: `http://your-weblate-url/api/docs/`

## Related Documentation

- [Adding Projects in Weblate](https://docs.weblate.org/en/latest/admin/projects.html)
- [Component Configuration](https://docs.weblate.org/en/latest/admin/projects.html#component)
- [File Formats](https://docs.weblate.org/en/latest/formats.html)
- [VCS Integration](https://docs.weblate.org/en/latest/vcs.html)

## License

This script is part of the Weblate project and follows the same GPL-3.0 license.

