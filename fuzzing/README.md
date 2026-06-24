<!--
Copyright © Weblate contributors

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Weblate Fuzzing

This directory contains parser-focused fuzz targets for high-risk input
surfaces in Weblate:

- `translation_formats`
- `webhooks`
- `backups`
- `markup`
- `memory_import`
- `ssh`

The targets are packaged through a shared `atheris` runner so ClusterFuzzLite
only needs to bundle the Python environment once.

## Local Runs

Use the existing virtual environment and point the runner at one target and its
seed corpus:

```sh
CI_DB_HOST=127.0.0.1 CI_DB_USER=weblate CI_DB_PASSWORD=weblate \
  .venv/bin/python fuzzing/runner.py translation_formats \
  fuzzing/corpus/translation_formats -runs=0
```

Replace `translation_formats` with any target name listed above.

## Sentry reporting

Batch fuzzing can report findings to Sentry when the `SENTRY_FUZZING_DSN`
GitHub Actions secret is configured. The fuzzing runner captures unexpected
Python exceptions directly so Sentry keeps the original traceback and target
metadata. It attaches the fuzz input to the captured Sentry event, capped at 1
MiB, so the reproducer is available without enabling local variable capture.
The batch workflow also reports ClusterFuzzLite SARIF and crash summaries as a
fallback for failures that do not raise a Python exception, such as sanitizer
aborts, OOMs, and timeouts.

PR fuzzing does not report to Sentry because secrets are not available for
untrusted fork pull requests. Both fuzzing workflows print a human-readable
findings report in the GitHub Actions log and step summary, and upload crash
summary artifacts.

## Seed Corpora

`fuzzing/corpus/<target>/` contains small seed inputs intended to get each
target past basic parsing and into format-specific logic quickly. The corpus is
kept intentionally small; larger mutation corpora should come from
ClusterFuzzLite batch runs.
