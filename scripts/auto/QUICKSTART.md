# Weblate Automation - Quick Start

## 1. Create Configuration Files

### `web.json`
```json
{
  "weblate_url": "http://localhost:8080",
  "api_token": "wlu_YOUR_TOKEN_HERE"
}
```

### `setup.json`
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
  "languages": ["fr", "de", "es"]
}
```

## 2. Run Setup (One Command!)

```bash
python3 scripts/auto/setup_component.py --config setup.json
```

This creates the component **and** adds all translations in one go!

## Alternative: Step-by-Step

```bash
# Step 1: Create component
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

## Done! 🎉

See [README.md](README.md) for full documentation.

