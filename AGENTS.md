# Agents guidance for Weblate

This file captures agent-specific guidance for working in the Weblate codebase.
For application-developer workflows and broader product integration guidance, use
`docs/devel/` instead of repeating that material here.

## Project overview

- Weblate is a Django-based web translation platform with Celery background
  tasks.
- The primary stack is Python, Django, JavaScript, and HTML/CSS/Bootstrap.

## Code expectations

- Follow existing Django patterns and project conventions.
- Prefer the repository's configured Ruff-based formatting and linting rules.
- Prefer type hints and use `from __future__ import annotations` in Python
  modules.
- Use `TYPE_CHECKING` imports for type-only dependencies when that avoids
  runtime import cycles.
- All user-facing strings must be translatable using Django i18n helpers.
- In templates, use `{% translate %}` / `{% blocktranslate %}` for translatable
  text.
- Preserve accessibility and the existing Bootstrap/jQuery-based frontend
  patterns.
- Include the GPL-3.0-or-later license header in new Python files.

## Weblate-specific guardrails

- Be careful with repository, webhook, and file-handling code; validate inputs
  and avoid introducing path traversal, command injection, or script injection
  risks.
- Handle VCS operations defensively and surface failures cleanly.
- Mock external VCS operations and API calls in tests.
- For user-visible changes, add a changelog entry to the top section of
  `docs/changes.rst`.

## Testing and linting instructions

- Install the development dependencies first using
  `uv sync --all-extras --dev`.
- Prefer `prek run --all-files` as the primary linting/formatting command because
  it runs the repository's configured pre-commit framework checks.
- `prek` is a third-party reimplementation of the `pre-commit` tool.
- Use `pytest` to run the test suite: `pytest weblate`. On a fresh checkout,
  first follow the local test setup in `docs/contributing/tests.rst`
  (`DJANGO_SETTINGS_MODULE=weblate.settings_test`, `collectstatic`, and test
  database prerequisites). `scripts/test-database.sh` can be sourced to set up
  the database connection variables such as `CI_DB_USER`, `CI_DB_PASSWORD`,
  `CI_DB_HOST`, and `CI_DB_PORT`.
- Use `pylint` to lint the Python code: `pylint weblate/`
- Use `mypy` to type check the code: `mypy weblate/`
- All mentioned linting tools MUST pass.
