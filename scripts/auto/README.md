# Weblate Automation Scripts

Automate Weblate project setup and translation management using the REST API.

## 📦 Scripts Included

1. **`batch_component_setup.py`** - Auto-generate and create multiple components from repository scan (bulk operations)
2. **`setup_component.py`** - Complete workflow: create component + add translations (single component)
3. **`create_component.py`** - Create projects and components
4. **`add_translation.py`** - Add language translations to components

## 🚀 Quick Start

### 1. Install Requirements

```bash
pip install requests
```

### 2. Create Configuration Files

#### `web.json` - Shared authentication config
```json
{
  "weblate_url": "http://localhost:8080",
  "api_token": "wlu_YOUR_TOKEN_HERE"
}
```

> **Security Note**: Keep `web.json` private! Add it to `.gitignore`.

#### `component.json` - Component-specific config
```json
{
  "project": {
    "name": "My Project",
    "slug": "my-project",
    "web": "https://example.com"
  },
  "component": {
    "name": "Main Component",
    "slug": "main",
    "vcs": "git",
    "repo": "git@github.com:user/repo.git",
    "branch": "main",
    "filemask": "locales/*.po",
    "file_format": "po"
  }
}
```

### 3. Get Your API Token

1. Log in to Weblate
2. Go to your profile → Settings
3. Navigate to "API access" tab
4. Copy your API token (starts with `wlu_` or `wlp_`)
5. Add it to `web.json`

### 4. Run Scripts

#### Option A: All-in-One (Recommended)

```bash
# Complete setup: create component + add translations
python3 scripts/auto/setup_component.py --config setup.json
```

#### Option B: Step-by-Step

```bash
# Step 1: Create project and component
python3 scripts/auto/create_component.py \
    --config component.json \
    --web-config web.json

# Step 2: Add translations
python3 scripts/auto/add_translation.py \
    --web-config web.json \
    --project my-project \
    --component main \
    --language fr,de,es
```

> **Note**: `setup_component.py` automatically loads `web.json`. Individual scripts (`create_component.py`, `add_translation.py`) require explicit `--web-config` or command-line credentials.

---

## 📖 Script 0: `batch_component_setup.py` (Batch Operations)

**The most powerful automation tool** - Scan a repository and automatically generate/create dozens of Weblate components in one command.

### Overview

`batch_component_setup.py` is designed for **bulk component creation**. Instead of manually creating each component, this script:

1. **Clones your repository** (or uses a local copy)
2. **Scans for translatable files** (e.g., `.adoc`, `.md`, `.po`, `.json`)
3. **Auto-generates component configs** for each file
4. **Optionally creates all components** in Weblate with proper synchronization

### Key Features

- ✅ **Automatic file discovery** - finds all translatable files in your repo
- ✅ **Smart naming** - generates component names/slugs from filenames
- ✅ **Path-aware** - handles subdirectories and complex structures
- ✅ **Sequential creation** - creates components one-by-one with delays to prevent conflicts
- ✅ **Configurable delays** - adjustable wait time between components (default: 5s)
- ✅ **Progress tracking** - detailed logs and status for each component
- ✅ **Dry-run mode** - preview what would be generated
- ✅ **Resume capability** - failed components are logged; you can retry individually
- ✅ **Single config file** - define project defaults once, apply to all components

### Quick Example

```bash
# Generate and create all components in one command
python3 batch_component_setup.py \
    --config project_config.json \
    --create-components
```

This could create **50+ components in minutes** with a single command!

### Usage Modes

#### 1. Generate Setup Files Only (Review First)

```bash
python3 batch_component_setup.py --config project_config.json
```

This creates `setup/*.json` files without touching Weblate. Review them first, then manually create components.

#### 2. Generate AND Create (Fully Automated)

```bash
python3 batch_component_setup.py \
    --config project_config.json \
    --create-components
```

Creates all components automatically with proper synchronization (5s delay between components).

#### 3. Custom Delay Between Components

```bash
python3 batch_component_setup.py \
    --config project_config.json \
    --create-components \
    --delay 10
```

Increases delay to 10 seconds (useful for slower servers or large repositories).

#### 4. Dry Run (Preview)

```bash
python3 batch_component_setup.py \
    --config project_config.json \
    --dry-run
```

Shows what would be generated without creating any files.

#### 5. Use Local Repository (Skip Cloning)

```bash
python3 batch_component_setup.py \
    --config project_config.json \
    --local-repo /path/to/repo
```

Scans a local repository instead of cloning (faster for development).

#### 6. Custom Output Directory

```bash
python3 batch_component_setup.py \
    --config project_config.json \
    --output ./my-components
```

Saves generated configs to a custom directory (default: `./setup`).

#### 7. Background Execution

```bash
nohup python3 batch_component_setup.py \
    --config project_config.json \
    --create-components \
    > batch_creation.log 2>&1 &

# Monitor progress
tail -f batch_creation.log
```

### Configuration File Format

Create a `project_config.json` file with your project settings:

```json
{
  "project": {
    "name": "Boost Unordered Documentation",
    "slug": "boost-unordered-documentation",
    "web": "https://www.boost.org/doc/libs/master/libs/unordered/",
    "instructions": "Please translate the Boost.Unordered documentation. Maintain technical accuracy and follow AsciiDoc formatting conventions.",
    "access_control": 0
  },
  "component_defaults": {
    "vcs": "github",
    "repo": "git@github.com:user/unordered.git",
    "push": "git@github.com:user/unordered.git",
    "branch": "develop",
    "push_branch": "boost-unordered-zh-translation",
    "edit_template": false,
    "source_language": "en",
    "license": "BSL-1.0",
    "allow_translation_propagation": true,
    "enable_suggestions": true,
    "suggestion_voting": false,
    "suggestion_autoaccept": 0,
    "check_flags": "",
    "hide_glossary_matches": false
  },
  "languages": ["zh_Hans"],
  "wait_for_ready": true,
  "trigger_update": true,
  "scan": {
    "github_path": "doc/modules/ROOT",
    "extensions": [".adoc"],
    "exclude_patterns": ["test", "examples", "build", ".git"]
  }
}
```

### Configuration Options

#### Project Section

Defines the Weblate project (created once, shared by all components):

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Project display name |
| `slug` | Yes | URL-friendly identifier |
| `web` | Yes | Project website URL |
| `instructions` | No | Instructions for translators |
| `access_control` | No | 0=Public, 1=Protected, 100=Private |

#### Component Defaults Section

Default settings applied to **all** generated components:

| Field | Required | Description |
|-------|----------|-------------|
| `vcs` | Yes | VCS type (`git`, `github`, `gitlab`) |
| `repo` | Yes | Repository URL (SSH or HTTPS) |
| `push` | Yes | Push URL (typically same as `repo`) |
| `branch` | Yes | Branch to translate from |
| `push_branch` | No | **Single branch for all components** (e.g., `weblate-translations`) or omit to auto-generate per-component branches |
| `edit_template` | No | Allow template editing (default: `false`) |
| `source_language` | No | Source language code (default: `en`) |
| `license` | No | Translation license |
| `allow_translation_propagation` | No | Propagate translations between components |
| `enable_suggestions` | No | Enable translation suggestions |
| `suggestion_voting` | No | Enable voting on suggestions |
| `suggestion_autoaccept` | No | Auto-accept threshold (0 = disabled) |
| `check_flags` | No | Quality check flags |
| `hide_glossary_matches` | No | Hide glossary suggestions (default: `false`) |

#### Top-Level Settings

| Field | Required | Description |
|-------|----------|-------------|
| `languages` | Yes | Array of language codes to add (e.g., `["zh_Hans", "ja", "fr"]`) |
| `wait_for_ready` | No | Wait for component initialization (default: `true`) |
| `trigger_update` | No | Trigger VCS update after creation (default: `true`) |

#### Scan Section

Defines how the repository is scanned for files:

| Field | Required | Description |
|-------|----------|-------------|
| `github_path` | No | Relative path within repo to scan (e.g., `"doc/modules/ROOT"`) - omit to scan entire repo |
| `extensions` | Yes | File extensions to find (e.g., `[".adoc", ".md", ".po"]`) |
| `exclude_patterns` | No | Directories/patterns to skip (e.g., `["test", "examples", ".git"]`) |

### How Components Are Generated

For each file found, the script automatically generates:

| Generated Field | How It's Generated | Example File | Example Output |
|----------------|-------------------|--------------|----------------|
| **Component Name** | Title case from filename | `intro.adoc` | `Intro` |
| | | `unordered-map.adoc` | `Unordered Map` |
| **Component Slug** | Lowercase, hyphenated | `intro.adoc` | `intro` |
| | | `unordered_map.adoc` | `unordered-map` |
| **Filemask** | Adds `_*` before extension | `intro.adoc` | `doc/.../intro_*.adoc` |
| | | `nav.adoc` | `doc/.../nav_*.adoc` |
| **Template** | Original file path | `doc/.../intro.adoc` | `doc/.../intro.adoc` |
| **New Base** | Same as template | `doc/.../intro.adoc` | `doc/.../intro.adoc` |
| **Push Branch** | From config OR auto-generated | Config: `weblate-translations` | `weblate-translations` |
| | | Auto: `intro.adoc` | `weblate-intro` |
| **File Format** | Detected from extension | `.adoc` | `asciidoc` |
| | | `.po` | `po` |
| | | `.json` | `json` |
| | | `.md` | `markdown` |

### Synchronization & Safety

When using `--create-components`, the script ensures **safe sequential creation**:

1. **One-by-one processing** - Components created sequentially, never in parallel
2. **Configurable delays** - Default 5-second wait between components (use `--delay` to adjust)
3. **Error isolation** - One failure doesn't stop the entire batch
4. **Progress tracking** - Shows `[1/50]`, `[2/50]`, etc. with timing
5. **Final summary** - Lists success/failure counts and failed components
6. **Timeout protection** - 5-minute timeout per component

**Why sequential?** Parallel creation causes:
- Database locking issues
- VCS conflicts
- Component initialization race conditions

**Delays prevent:**
- Server overload
- Database constraint violations
- Incomplete component initialization

### Output Example

```
[INFO] Loading configuration from: project_config.json
[INFO] Cloning repository: git@github.com:user/unordered.git
[INFO] Branch: develop
[SUCCESS] Repository cloned to: /tmp/weblate_scan_xyz123
[INFO] Scanning subdirectory: doc/modules/ROOT
[INFO] Scanning for files with extensions: .adoc

[SUCCESS] Found 52 file(s)

[INFO] Processing: doc/modules/ROOT/pages/intro.adoc
[SUCCESS] Created: ./setup/setup_intro.json

[INFO] Processing: doc/modules/ROOT/pages/benchmarks.adoc
[SUCCESS] Created: ./setup/setup_benchmarks.json

... (50 more files) ...

============================================================
[SUCCESS] Generated 52 setup file(s) in: ./setup
============================================================

[INFO] Creating components in Weblate...

============================================================
Creating Components in Weblate (Sequential)
============================================================
[INFO] Total components to create: 52
[INFO] Delay between components: 5s
[INFO] This ensures proper synchronization and avoids conflicts

============================================================
[1/52] Component: intro
============================================================
[INFO] Config: ./setup/setup_intro.json
[INFO] Starting component creation...
[SUCCESS] Component created in 3.2s
[INFO] Waiting 5s before next component...

============================================================
[2/52] Component: benchmarks
============================================================
[INFO] Config: ./setup/setup_benchmarks.json
[INFO] Starting component creation...
[SUCCESS] Component created in 2.8s
[INFO] Waiting 5s before next component...

... (50 more components) ...

============================================================
Component Creation Summary
============================================================
  Total:   52
  Success: 51
  Failed:  1

Failed components:
  - unordered-map (will retry individually)

============================================================
```

### Workflow Recommendations

#### For Production (Recommended)

1. **Generate first, review, then create:**

```bash
# Step 1: Generate configs
python3 batch_component_setup.py --config project_config.json --output ./review

# Step 2: Review generated files
ls -l ./review/
cat ./review/setup_intro.json

# Step 3: Create all components
python3 batch_component_setup.py \
    --config project_config.json \
    --output ./review \
    --create-components
```

#### For Development (Fast Iteration)

```bash
# Use local repo to skip cloning
python3 batch_component_setup.py \
    --config project_config.json \
    --local-repo ~/projects/my-repo \
    --create-components
```

#### For CI/CD

```bash
# Run in background, monitor logs
nohup python3 batch_component_setup.py \
    --config project_config.json \
    --create-components \
    --delay 3 \
    > batch_$(date +%Y%m%d_%H%M%S).log 2>&1 &
```

### Handling Failures

If some components fail to create, the summary shows which ones:

```
Failed components:
  - unordered-map
  - concurrent-set
```

**To retry failed components manually:**

```bash
# Find the generated config
cd setup/

# Retry individual component
python3 ../setup_component.py --config setup_unordered-map.json
python3 ../setup_component.py --config setup_concurrent-set.json
```

### Advanced: Custom Setup Script Location

If `setup_component.py` is in a different location:

```bash
python3 batch_component_setup.py \
    --config project_config.json \
    --create-components \
    --setup-script /path/to/setup_component.py
```

### Real-World Example: Boost Documentation

**Scenario**: Translate 52 AsciiDoc files in `doc/modules/ROOT/pages/`

**Single command:**
```bash
python3 batch_component_setup.py \
    --config project_config.json \
    --create-components \
    --delay 5
```

**Result**: 52 components created in ~5 minutes (52 components × 5s delay + creation time)

Without this script: **2+ hours of manual work** (create each component individually via UI or API)

### Comparison: Batch vs. Manual

| Task | Manual (UI/Script) | batch_component_setup.py |
|------|-------------------|-------------------------|
| 1 component | ~2 minutes | ~5 seconds |
| 10 components | ~20 minutes | ~1 minute |
| 50 components | ~2 hours | ~5 minutes |
| 100 components | ~4 hours | ~10 minutes |

**Time savings increase exponentially with component count.**

---

## 📖 Script 1: `setup_component.py` (All-in-One)

Complete workflow that creates a component and adds translations in one command.

### Features

- ✅ One-command complete setup
- ✅ Creates project and component
- ✅ Adds multiple translations automatically
- ✅ **Sequential translation addition with proper synchronization**
- ✅ Waits for component initialization before adding translations
- ✅ Waits between each translation to ensure stability
- ✅ Verification of component and translation accessibility
- ✅ Interactive mode
- ✅ Progress feedback for each step

### Usage

#### From Setup Config (with languages included)

```bash
python3 scripts/auto/setup_component.py --config setup.json
```

**setup.json format:**
```json
{
  "project": {
    "name": "My Project",
    "slug": "my-project",
    "web": "https://example.com"
  },
  "component": {
    "name": "Main Component",
    "slug": "main",
    "vcs": "git",
    "repo": "git@github.com:user/repo.git",
    "branch": "main",
    "filemask": "locales/*.po",
    "file_format": "po"
  },
  "languages": ["fr", "de", "es", "ja"],
  "wait_for_ready": true,
  "trigger_update": true
}
```

#### From Component Config with Language List

```bash
python3 scripts/auto/setup_component.py \
    --config component.json \
    --languages fr,de,es,ja
```

#### Interactive Mode

```bash
python3 scripts/auto/setup_component.py --interactive
```

### Synchronization & Timing

The script implements **proper synchronization** to ensure reliability:

1. **Component Creation**: Waits for repository cloning and initialization
2. **Stability Check**: 3-second wait after component creation
3. **Component Verification**: Confirms component is accessible
4. **Sequential Translation Addition**: Adds translations one at a time
5. **Inter-Translation Wait**: 2-second pause between each translation
6. **Final Verification**: Confirms all translations are accessible

This prevents race conditions and ensures each step completes before the next begins.

### Output Example

```
============================================================
STEP 1: Creating Component
============================================================

[INFO] Loading web config from: /path/to/web.json
[API] GET http://localhost:8080/api/
[SUCCESS] Connected to Weblate API
[INFO] Creating component: Main Component
[SUCCESS] Component created!

[INFO] Waiting for component to be fully initialized...
[INFO] Ensuring component is ready for translations...
[SUCCESS] Component created and ready!

============================================================
STEP 2: Adding 3 Translation(s)
============================================================

[INFO] Validating inputs...
[SUCCESS] Component 'my-project/main' exists
[SUCCESS] All language codes are valid

[INFO] Adding translations sequentially...

[INFO] [1/3] Adding fr...
[SUCCESS] Translation created: French
[INFO] Waiting 2s before next translation...

[INFO] [2/3] Adding de...
[SUCCESS] Translation created: German
[INFO] Waiting 2s before next translation...

[INFO] [3/3] Adding es...
[SUCCESS] Translation created: Spanish

[SUCCESS] Added 3/3 translation(s)

[INFO] Verifying all translations are accessible...
[SUCCESS] All 3 translation(s) verified

============================================================
SETUP COMPLETE!
============================================================
[INFO] Project: my-project
[INFO] Component: main
[INFO] Translations: 3/3 added
[INFO] URL: http://localhost:8080/projects/my-project/main/
```

---

## 📖 Script 1: `create_component.py`

Creates Weblate projects and components with full VCS integration.

### Features

- ✅ Automatic project and component creation
- ✅ VCS integration (Git, GitHub, GitLab, etc.)
- ✅ Settings verification and correction
- ✅ Repository cloning and translation discovery
- ✅ Interactive mode
- ✅ Configuration file support

### Usage

#### With Web Config File

```bash
python3 scripts/auto/create_component.py \
    --config component.json \
    --web-config web.json
```

#### With Command-Line Credentials

```bash
python3 scripts/auto/create_component.py \
    --config component.json \
    --url http://localhost:8080 \
    --token wlu_YOUR_TOKEN
```

#### Interactive Mode

```bash
python3 scripts/auto/create_component.py --interactive
```

### Configuration Options

#### Project Configuration

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Project display name |
| `slug` | Yes | URL-friendly project identifier |
| `web` | Yes | Project website URL |
| `instructions` | No | Instructions for translators |
| `access_control` | No | 0=Public, 1=Protected, 100=Private |

#### Component Configuration

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Component display name |
| `slug` | Yes | URL-friendly component identifier |
| `vcs` | Yes | VCS type (git, github, gitlab, etc.) |
| `repo` | Yes | Repository URL (SSH or HTTPS) |
| `branch` | Yes | Repository branch to translate |
| `push` | No | Push URL (for SSH authentication) |
| `push_branch` | No | Branch for pushing changes |
| `filemask` | Yes | File pattern (e.g., `locales/*.po`) |
| `file_format` | Yes | File format (po, json, xliff, etc.) |
| `template` | No | Template file (for monolingual formats) |
| `new_base` | No | Base file for new translations |
| `edit_template` | No | Allow template editing (default: false) |
| `source_language` | No | Source language code (default: en) |
| `license` | No | Translation license |
| `allow_translation_propagation` | No | Propagate translations |
| `enable_suggestions` | No | Enable translation suggestions |
| `suggestion_voting` | No | Enable suggestion voting |
| `suggestion_autoaccept` | No | Auto-accept suggestions threshold |

### Output Example

```
[INFO] Loading web config from: /path/to/web.json
[API] GET http://localhost:8080/api/
[SUCCESS] Connected to Weblate API
[INFO] Creating component: Main Component
[INFO] Repository: git@github.com:user/repo.git
[INFO] Branch: main
[API] POST http://localhost:8080/api/projects/my-project/components/
[SUCCESS] Component created: http://localhost:8080/projects/my-project/main/
[INFO] Verifying component settings match JSON config...
[SUCCESS] Component settings match JSON config
[INFO] Triggering VCS update for my-project/main
[SUCCESS] VCS update triggered
[INFO] Waiting for component to be ready...
[SUCCESS] Component ready with 3 translation(s)

[SUCCESS] Setup complete!
[INFO] Project URL: http://localhost:8080/projects/my-project/
[INFO] Component URL: http://localhost:8080/projects/my-project/main/
```

---

## 📖 Script 2: `add_translation.py`

Adds new language translations to existing Weblate components.

### Features

- ✅ Add single or multiple translations at once
- ✅ **Sequential translation addition with proper synchronization**
- ✅ Waits 2 seconds between each translation
- ✅ Progress counter for multiple translations
- ✅ Final verification of all translations
- ✅ Language code validation
- ✅ Duplicate detection
- ✅ List available languages
- ✅ List component translations
- ✅ Interactive mode

### Usage

#### Add Single Translation

```bash
python3 scripts/auto/add_translation.py \
    --web-config web.json \
    --project my-project \
    --component main \
    --language fr
```

#### Add Multiple Translations

```bash
python3 scripts/auto/add_translation.py \
    --web-config web.json \
    --project my-project \
    --component main \
    --language fr,de,es,ja,zh_Hans
```

#### With Command-Line Credentials

```bash
python3 scripts/auto/add_translation.py \
    --url http://localhost:8080 \
    --token wlu_YOUR_TOKEN \
    --project my-project \
    --component main \
    --language fr
```

#### Interactive Mode

```bash
python3 scripts/auto/add_translation.py --interactive
```

#### List Available Languages

```bash
python3 scripts/auto/add_translation.py --web-config web.json --list-languages
```

#### List Component Translations

```bash
python3 scripts/auto/add_translation.py \
    --web-config web.json \
    --project my-project \
    --component main \
    --list
```

### Common Language Codes

| Code | Language |
|------|----------|
| `ar` | Arabic |
| `de` | German |
| `es` | Spanish |
| `fr` | French |
| `it` | Italian |
| `ja` | Japanese |
| `ko` | Korean |
| `pt` | Portuguese |
| `pt_BR` | Portuguese (Brazil) |
| `ru` | Russian |
| `zh_Hans` | Chinese (Simplified) |
| `zh_Hant` | Chinese (Traditional) |

### Synchronization

When adding multiple translations, the script:
1. Adds translations **sequentially** (one at a time)
2. Waits **2 seconds** between each translation
3. Shows **progress counter** `[1/3]`, `[2/3]`, `[3/3]`
4. Continues even if one translation fails
5. Verifies all translations are accessible (for 2+ translations)

This prevents race conditions and ensures stable translation creation.

### Output Example (Multiple Translations)

```
[INFO] Loading web config from: /path/to/web.json
[API] GET http://localhost:8080/api/
[SUCCESS] Connected to Weblate API
[INFO] Validating inputs...
[SUCCESS] Component 'my-project/main' exists
[SUCCESS] All language codes are valid

[INFO] Adding 3 translation(s) sequentially...

[INFO] [1/3] Adding fr...
[API] POST http://localhost:8080/api/components/my-project/main/translations/

[SUCCESS] Translation created: French
  Language code: fr
  URL: http://localhost:8080/projects/my-project/main/fr/
  File: locales/fr.po
  Progress: 0/150 strings translated

[INFO] Waiting 2s before next translation...

[INFO] [2/3] Adding de...
[API] POST http://localhost:8080/api/components/my-project/main/translations/

[SUCCESS] Translation created: German
  Language code: de
  URL: http://localhost:8080/projects/my-project/main/de/
  File: locales/de.po
  Progress: 0/150 strings translated

[INFO] Waiting 2s before next translation...

[INFO] [3/3] Adding es...
[API] POST http://localhost:8080/api/components/my-project/main/translations/

[SUCCESS] Translation created: Spanish
  Language code: es
  URL: http://localhost:8080/projects/my-project/main/es/
  File: locales/es.po
  Progress: 0/150 strings translated

[SUCCESS] Added 3/3 translation(s)

[INFO] Verifying all translations are accessible...
[SUCCESS] All 4 translation(s) verified
```

---

## 🔧 Configuration Files

### Two-File Approach (Recommended)

Separate authentication from project configuration for better security and reusability.

#### `web.json` (Shared)
```json
{
  "weblate_url": "http://localhost:8080",
  "api_token": "wlu_gnEeSZUJv4kDAKvcWWNQNThRlzocIQhYNXWn"
}
```

#### `component.json` (Project-specific)
```json
{
  "project": {
    "name": "My Project",
    "slug": "my-project",
    "web": "https://example.com"
  },
  "component": {
    "name": "Main Component",
    "slug": "main",
    "vcs": "git",
    "repo": "git@github.com:user/repo.git",
    "branch": "main",
    "filemask": "locales/*.po",
    "file_format": "po"
  },
  "wait_for_ready": true,
  "trigger_update": true
}
```

### Single-File Approach

Combine everything in one file (less secure):

```json
{
  "weblate_url": "http://localhost:8080",
  "api_token": "wlu_YOUR_TOKEN",
  "project": { ... },
  "component": { ... }
}
```

### Credential Management

**`setup_component.py`** (all-in-one script):
- Automatically searches for `web.json` in:
  1. Script directory: `scripts/auto/web.json`
  2. Current directory: `./web.json`
- Override with `--web-config /custom/path.json`

**`create_component.py` and `add_translation.py`** (individual scripts):
- Require explicit credentials via:
  - `--web-config web.json`
  - `--url` and `--token` command-line args
  - `WEBLATE_TOKEN` environment variable
- Do NOT auto-load `web.json` (by design)

---

## 📝 Example: AsciiDoc Component

### Configuration (`component.json`)

```json
{
  "project": {
    "name": "Boost Unordered Documentation",
    "slug": "boost-unordered-documentation",
    "web": "https://www.boost.org/doc/libs/master/libs/unordered/",
    "instructions": "Please maintain technical accuracy and AsciiDoc formatting."
  },
  "component": {
    "name": "Intro",
    "slug": "intro",
    "vcs": "github",
    "repo": "git@github.com:user/unordered.git",
    "push": "git@github.com:user/unordered.git",
    "branch": "develop",
    "push_branch": "weblate-intro",
    "filemask": "doc/modules/ROOT/pages/intro_*.adoc",
    "template": "doc/modules/ROOT/pages/intro.adoc",
    "new_base": "doc/modules/ROOT/pages/intro.adoc",
    "file_format": "asciidoc",
    "edit_template": false,
    "source_language": "en",
    "license": "BSL-1.0",
    "allow_translation_propagation": true,
    "enable_suggestions": true
  },
  "wait_for_ready": true,
  "trigger_update": true
}
```

### Create Component

```bash
cd scripts/auto
python3 create_weblate_project.py --config component.json
```

### Add Translations

```bash
# Add multiple languages
python3 add_translation.py \
    --project boost-unordered-documentation \
    --component intro \
    --language ja,zh_Hans,fr,de
```

---

## 🔐 VCS Setup

### For GitHub Push Access

1. **Generate SSH Key** (if you don't have one):
   ```bash
   ssh-keygen -t ed25519 -C "weblate@example.com"
   ```

2. **Get Weblate's SSH Public Key**:
   - In Weblate, go to Component → Settings → Version Control
   - Copy the SSH public key displayed

3. **Add to GitHub**:
   - Go to your repository → Settings → Deploy keys
   - Click "Add deploy key"
   - Paste Weblate's public key
   - ✅ **Check "Allow write access"** (required for push)

4. **Create Push Branch**:
   ```bash
   git checkout -b weblate-intro
   git push origin weblate-intro
   ```

5. **Configure Component**:
   ```json
   {
     "vcs": "github",
     "repo": "git@github.com:user/repo.git",
     "push": "git@github.com:user/repo.git",
     "branch": "develop",
     "push_branch": "weblate-intro"
   }
   ```

### VCS Types

| VCS | Description | Use Case |
|-----|-------------|----------|
| `git` | Plain Git (no PR integration) | Manual merge workflow |
| `github` | GitHub with PR integration | Automatic pull requests |
| `gitlab` | GitLab with MR integration | Automatic merge requests |
| `gitea` | Gitea with PR integration | Self-hosted Git |

---

## 🛠️ Troubleshooting

### "API token required"

**Solution**: Ensure `web.json` exists in the script directory or use `--token`:
```bash
python3 add_translation.py --token wlu_YOUR_TOKEN --project ... --component ... --language ...
```

### "Component not found"

**Solution**: Verify project and component slugs:
```bash
# List projects (via API)
curl -H "Authorization: Token YOUR_TOKEN" http://localhost:8080/api/projects/
```

### "Invalid language code"

**Solution**: List available languages:
```bash
python3 add_translation.py --list-languages
```

### "Host key verification failed"

**Solution**: Add GitHub to known hosts:
```bash
ssh-keyscan github.com >> ~/.ssh/known_hosts
```

Or in Weblate container:
```bash
docker exec weblate ssh-keyscan github.com >> /home/weblate/.ssh/known_hosts
```

### "Permission denied (publickey)"

**Solution**: Ensure Weblate's SSH key is added to GitHub with write access.

### "Timeout waiting for component"

This is **normal** for first-time repository cloning. The component was created successfully, and Weblate continues processing in the background.

---

## 📚 Advanced Usage

### Environment Variables

```bash
export WEBLATE_TOKEN="wlu_YOUR_TOKEN"
python3 add_translation.py --project my-project --component main --language fr
```

### Batch Processing

```bash
# Create multiple components
for config in components/*.json; do
    python3 create_weblate_project.py --config "$config"
done

# Add same languages to multiple components
for comp in main docs api; do
    python3 add_translation.py \
        --project my-project \
        --component "$comp" \
        --language fr,de,es
done
```

### CI/CD Integration

```yaml
# .github/workflows/weblate-setup.yml
name: Setup Weblate Component

on:
  push:
    branches: [main]

jobs:
  setup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install dependencies
        run: pip install requests
      
      - name: Create web.json
        run: |
          echo '{
            "weblate_url": "${{ secrets.WEBLATE_URL }}",
            "api_token": "${{ secrets.WEBLATE_TOKEN }}"
          }' > scripts/auto/web.json
      
      - name: Create Weblate component
        run: |
          python3 scripts/auto/create_weblate_project.py \
            --config scripts/auto/component.json
```

---

## 🔍 API Reference

### Create Project
```
POST /api/projects/
```

### Create Component
```
POST /api/projects/{project}/components/
```

### Add Translation
```
POST /api/components/{project}/{component}/translations/
```

### List Translations
```
GET /api/components/{project}/{component}/translations/
```

### Trigger VCS Update
```
POST /api/components/{project}/{component}/repository/
```

Full API documentation: https://docs.weblate.org/en/latest/api.html

---

## 📄 License

GPL-3.0-or-later

## 👥 Authors

Weblate Team

## 🤝 Contributing

Contributions welcome! Please ensure:
- Code passes linting
- Line length ≤ 88 characters (PEP 8)
- Type hints included
- Documentation updated

---

## 📞 Support

- Documentation: https://docs.weblate.org/
- Issues: https://github.com/WeblateOrg/weblate/issues
- Forum: https://discussions.weblate.org/

