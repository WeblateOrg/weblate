# Copilot Instructions for Weblate

Weblate is a libre software web-based continuous localization system used by over 2500 libre projects and companies in more than 165 countries. This document provides guidelines for GitHub Copilot when working on the Weblate codebase.

## Project Overview

- **Technology Stack**: Django 5.1+, Python 3.12+, JavaScript, HTML/CSS
- **Purpose**: Web-based translation management platform with VCS integration
- **Architecture**: Django web application with Celery background tasks
- **Database**: PostgreSQL, MySQL, MariaDB support
- **Frontend**: Bootstrap-based UI with JavaScript enhancements

## Code Style and Standards

### Python Code

- Follow PEP 8 standards with line length of 88 characters (Black formatter)
- Use Django best practices and conventions
- Type hints are required (project uses `py.typed` and mypy)
- Use `from __future__ import annotations` for forward references
- Use `gettext_lazy` and `gettext_noop` for translatable strings
- Import Django components following Django conventions
- Use class-based views inheriting from appropriate mixins
- All files must include GPL-3.0-or-later license header
- Use `TYPE_CHECKING` imports for type-only imports to avoid circular dependencies

### Frontend Code

- Use Bootstrap 4/5 classes for styling
- Follow existing JavaScript patterns in the codebase
- Use jQuery for DOM manipulation (existing pattern)
- Maintain accessibility standards

### Templates

- Use Django template syntax with proper escaping
- Follow existing template structure and patterns
- Use `{% translate %}` and `{% blocktranslate %}` for i18n
- Maintain semantic HTML structure

## Development Workflow

### Testing

- Use pytest with Django integration (`pytest-django`)
- Test files are located in `*/tests/` directories
- Run tests with: `python manage.py test` or `pytest`
- Use Django's TestCase and TransactionTestCase appropriately
- Mock external VCS operations and API calls
- Test with different translation file formats
- Include tests for user permissions and access control
- Write unit tests for new functionality and integration tests for complex features

### Development Commands

- `python manage.py runserver` - Start development server
- `python manage.py shell` - Django shell with Weblate models loaded
- `python manage.py makemigrations` - Create database migrations
- `python manage.py migrate` - Apply database migrations
- `python manage.py collectstatic` - Collect static files
- `python manage.py test` - Run test suite

### Linting and Formatting

- Pre-commit hooks are configured (`.pre-commit-config.yaml`)
- Use pylint for Python code quality
- Follow existing code formatting patterns
- Run `pre-commit run --all-files` before committing

### Dependencies

- Manage dependencies in `pyproject.toml`
- Use dependency groups for different environments (dev, test, docs, etc.)
- Keep dependencies up to date with security considerations

### Weblate-Specific Patterns

#### Model Hierarchy

- **Project**: Top-level container for related components
- **Component**: Individual translatable resource (e.g., a software module)
- **Translation**: Language-specific version of a component
- **Unit**: Individual translatable string within a translation
- **Change**: Audit trail of all modifications

#### Key Mixins and Base Classes

- `ComponentViewMixin`: For views that operate on translation components
- `ProjectViewMixin`: For views that operate on projects
- `TranslationViewMixin`: For views that operate on translations
- `CacheKeyMixin`: Provides caching functionality
- `LockMixin`: Handles repository locking
- `PathMixin`: URL path handling utilities

#### VCS Integration Patterns

```python
# Always use try/except for VCS operations
try:
    component.repository.commit()
except Exception:
    # Handle VCS errors gracefully
    report_error("Repository operation failed")
```

### Internationalization (i18n)

- All user-facing strings must be translatable
- Use `gettext_lazy` for model fields and forms
- Use `{% translate %}` in templates
- Maintain plural forms correctly
- Consider RTL language support

### Version Control Integration

- Understand VCS abstraction layer in `weblate/vcs/`
- Support for Git, Mercurial, Subversion
- Repository operations should be atomic and safe
- Handle merge conflicts gracefully

### Translation Formats

- Support multiple file formats (PO, XLIFF, JSON, etc.)
- Format handlers are in `weblate/formats/`
- Maintain format integrity during operations
- Handle encoding issues properly

### Security Considerations

- Sanitize all user inputs, especially translation content
- Use Django's built-in security features (CSRF, XSS protection)
- Be extremely careful with file uploads and VCS operations
- Validate translation keys and values against injection attacks
- Consider script injection in translation content (especially for web formats)
- Use proper authentication and authorization decorators
- Validate file paths to prevent directory traversal
- Sanitize Git repository URLs and branch names
- Be cautious with eval() or exec() in format handlers
- Use Django's `mark_safe()` only when absolutely necessary and with sanitized content

## API and Integration

### REST API

- Django REST Framework patterns
- API versioning considerations
- Proper authentication and permissions
- Rate limiting awareness

### Webhooks and Automation

- GitHub, GitLab, Bitbucket integration
- Webhook security (signature verification)
- Asynchronous processing with Celery

## Documentation

### Code Documentation

- Use docstrings for all public methods
- Include type hints where beneficial
- Document complex algorithms and business logic
- Reference Django and Weblate documentation

### User Documentation

- Update docs in `docs/` directory (reStructuredText)
- Follow existing documentation structure
- Include examples and use cases
- Consider translation workflow impact
- Include changelog entry for all user visible changes

## Common Patterns to Follow

### Models

```python
from django.db import models
from django.utils.translation import gettext_lazy


class MyModel(models.Model):
    name = models.CharField(max_length=100, verbose_name=gettext_lazy("Name"))

    class Meta:
        verbose_name = gettext_lazy("My Model")
```

### Views

```python
from django.contrib.auth.decorators import login_required
from weblate.utils.views import ComponentViewMixin


class MyComponentView(ComponentViewMixin, TemplateView):
    template_name = "my_template.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add component-specific context
        return context
```

### Models with Proper Structure

```python
# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.utils.translation import gettext_lazy

if TYPE_CHECKING:
    from weblate.auth.models import User


class MyModel(models.Model):
    name = models.CharField(
        max_length=100,
        verbose_name=gettext_lazy("Name"),
        help_text=gettext_lazy("Human readable name of the object"),
    )

    class Meta:
        verbose_name = gettext_lazy("My Model")
        verbose_name_plural = gettext_lazy("My Models")
```

### Forms

```python
from django import forms
from django.utils.translation import gettext_lazy


class MyForm(forms.Form):
    field = forms.CharField(label=gettext_lazy("Field"))
```

## File Organization

- Models: Organize in app-specific `models/` directories with separate files per model type
- Views: Organize by functionality in `views/` directories or `views.py`
- Forms: Keep in `forms.py` within relevant apps
- Templates: Store in `templates/` with app-specific subdirectories
- Static files: Organize in `static/` directories
- Tests: Place in `tests/` directories within apps
- Management commands: Store in `management/commands/` directories

## Supported Integrations

### Version Control Systems

- Git (primary), Mercurial, Subversion
- GitHub, GitLab, Bitbucket, Gitea, Azure DevOps
- Repository webhooks for automatic updates

### Translation Formats

- GNU gettext PO files
- XLIFF 1.2 and 2.1
- JSON (various flavors)
- Android strings, iOS strings
- Qt TS files, Windows RC files
- And many more in `weblate/formats/`

### Machine Translation Services

- Google Translate, Microsoft Translator
- DeepL, Amazon Translate
- LibreTranslate, ModernMT
- Custom MT engines via API

## Performance Considerations

- Use select_related() and prefetch_related() for database queries
- Cache expensive operations appropriately (Redis/Memcached)
- Consider memory usage with large translation files
- Optimize VCS operations for performance
- Use Celery for background tasks (imports, exports, VCS operations)
- Implement proper database indexes for query performance
- Use database-level constraints where appropriate

## Error Handling and Logging

### Error Reporting

```python
from weblate.utils.errors import report_error

try:
    # Risky operation
    pass
except Exception as error:
    report_error("Operation failed", request=request)
    # Handle gracefully
```

### Background Tasks with Celery

```python
from celery import shared_task


@shared_task(bind=True)
def my_background_task(self, component_id):
    try:
        component = Component.objects.get(pk=component_id)
        # Perform background operation
    except Exception as error:
        self.retry(countdown=60, max_retries=3)
```

## Contribution Guidelines

- Follow the existing code patterns and conventions
- Write tests for new features and bug fixes
- Update documentation when adding new features
- Consider backwards compatibility
- Be mindful of security implications
- Test with different VCS backends when relevant
- Respect the GPL-3.0-or-later license requirements

## Common Gotchas and Best Practices

### Translation Handling

- Always check for plural forms when dealing with translations
- Be aware of RTL (Right-to-Left) language requirements
- Handle translation conflicts gracefully
- Consider context and disambiguation in translation keys

### VCS Operations

- Repository operations should be atomic when possible
- Always handle VCS exceptions and provide user feedback
- Use proper file locking for concurrent access
- Test with different repository states (clean, dirty, conflicts)

### Database Operations

- Use transactions for multi-model operations
- Be careful with large datasets and memory usage
- Consider database performance with complex joins
- Use appropriate indexes for frequent queries

### Internationalization

- Never hardcode strings that users will see
- Use proper pluralization rules
- Consider cultural differences in date/time formatting
- Test with languages that have different text directions

## AI-Generated Code Guidelines

When using GitHub Copilot or other AI tools with Weblate:

- **Security First**: AI-generated code must be thoroughly reviewed for security vulnerabilities, especially in VCS operations and user input handling
- **License Compliance**: Ensure all generated code complies with GPL-3.0-or-later license requirements
- **Translation Accuracy**: Be extra careful with AI suggestions for translation-related code - test with multiple languages and formats
- **Test Coverage**: Always write tests for AI-generated functionality
- **Code Review**: Have AI-generated code reviewed by maintainers familiar with Weblate's architecture
- **Documentation**: Document any complex AI-generated algorithms or patterns

## Resources

- [Weblate Documentation](https://docs.weblate.org/)
- [Django Documentation](https://docs.djangoproject.com/)
- [Contributing Guide](CONTRIBUTING.md)
- [Issue Tracker](https://github.com/WeblateOrg/weblate/issues)
- [Security Policy](SECURITY.md)
- [Development Setup](https://docs.weblate.org/en/latest/contributing/start.html)
