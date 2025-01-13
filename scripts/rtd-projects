#!/usr/bin/env python3

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Synchronizes Read the Docs projects for all languages."""

import os
import subprocess

import requests
from weblate_language_data.docs import DOCUMENTATION_LANGUAGES

# List of translations
LOCALES = {
    locale.lower().replace("_", "-") for locale in DOCUMENTATION_LANGUAGES.values()
}

# Default values
FIELDS = {
    "tags": {"django", "gettext", "translate", "localize", "language"},
    "homepage": "https://weblate.org/",
    "programming_language": {"code": "py", "name": "Python"},
    "default_branch": "main",
}


def get_update(value):
    if isinstance(value, dict) and "code" in value:
        return value["code"]
    if isinstance(value, set):
        return list(value)
    return value


git_tag = subprocess.run(
    ["git", "describe", "--tags", "--abbrev=0"],
    capture_output=True,
    text=True,
    check=True,
)

LATEST_RELEASE = git_tag.stdout.strip()

# Read the authorization token
with open(os.path.expanduser("~/.config/readthedocs.token")) as handle:
    TOKEN = handle.read().strip()

AUTH = {"Authorization": f"Token {TOKEN}", "Content-Type": "application/json"}

response = requests.get(
    "https://readthedocs.org/api/v3/projects/weblate/", headers=AUTH, timeout=1
)
response.raise_for_status()
base = response.json()

result = {"next": "https://readthedocs.org/api/v3/projects/"}
while result["next"]:
    response = requests.get(result["next"], headers=AUTH, timeout=1)
    response.raise_for_status()
    result = response.json()
    for project in result["results"]:
        if project["name"].startswith("Weblate"):
            code = project["language"]["code"]
            # Check for defined locales
            if code not in LOCALES:
                print(f"Extra translation: {code}")
                continue
            LOCALES.remove(code)
            # Sync attributes
            for name, value in FIELDS.items():
                current = project[name]
                if isinstance(value, set):
                    current = set(current)
                if value != current:
                    print(
                        f"Different {name} on {project['name']}: {current}",
                        project["urls"]["home"],
                    )
                    response = requests.patch(
                        project["_links"]["_self"],
                        json={name: get_update(value)},
                        headers=AUTH,
                        timeout=1,
                    )
                    response.raise_for_status()
            if not project["translation_of"] and code != "en":
                print(f"Not a translation {project['name']}: ", project["urls"]["home"])
            # Check versions
            versions_response = requests.get(
                f"{project['_links']['versions']}?active=true", headers=AUTH, timeout=1
            )
            versions_response.raise_for_status()
            versions = versions_response.json()
            found = None
            while LATEST_RELEASE not in {
                version["slug"] for version in versions["results"]
            }:
                if versions["next"] is None:
                    print(
                        f"Missing release {LATEST_RELEASE} in  {project['name']}: ",
                        project["urls"]["home"],
                    )
                    break
                versions_response = requests.get(
                    versions["next"], headers=AUTH, timeout=1
                )
                versions_response.raise_for_status()
                versions = versions_response.json()

            if versions["count"] < 2:
                print(
                    f"Missing automation rule {project['name']}: ",
                    project["urls"]["home"],
                )


# Create missing ones
for language in LOCALES:
    print(f"Creating {language}")
    payload = {
        "language": language,
        "name": f"Weblate ({language})",
        "repository": {
            "url": "https://github.com/WeblateOrg/weblate.git",
            "type": "git",
        },
    }
    for name, value in FIELDS.items():
        payload[name] = get_update(value)
    response = requests.post(
        "https://readthedocs.org/api/v3/projects/",
        json=payload,
        headers=AUTH,
        timeout=1,
    )
    project = response.json()
    response.raise_for_status()
    print(f"Not a translation {project['name']}: ", project["urls"]["home"])
    print(f"Missing automation rule {project['name']}: ", project["urls"]["home"])
