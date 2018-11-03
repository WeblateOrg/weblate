# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals

import os
import sys
import unicodedata

from django.apps import apps
from django.core.cache import cache
from django.db.utils import OperationalError
from django.http import HttpResponseRedirect
from django.shortcuts import resolve_url, render as django_render, redirect
from django.utils import timezone
from django.utils.encoding import force_text
from django.utils.http import is_safe_url
from django.utils.translation import ugettext as _, ugettext_lazy

try:
    import pyuca  # pylint: disable=import-error
    HAS_PYUCA = True
except ImportError:
    HAS_PYUCA = False


import six
from six.moves.urllib.parse import urlparse

from weblate.utils.data import data_dir

PLURAL_SEPARATOR = '\x1e\x1e'

PRIORITY_CHOICES = (
    (60, ugettext_lazy('Very high')),
    (80, ugettext_lazy('High')),
    (100, ugettext_lazy('Medium')),
    (120, ugettext_lazy('Low')),
    (140, ugettext_lazy('Very low')),
)


def is_plural(text):
    """Check whether string is plural form."""
    return text.find(PLURAL_SEPARATOR) != -1


def split_plural(text):
    return text.split(PLURAL_SEPARATOR)


def join_plural(text):
    return PLURAL_SEPARATOR.join(text)


def get_string(text):
    """Return correctly formatted string from ttkit unit data."""
    # Check for null target (happens with XLIFF)
    if text is None:
        return ''
    if hasattr(text, 'strings'):
        return join_plural(text.strings)
    # We might get integer or float in some formats
    return force_text(text)


def is_repo_link(val):
    """Check whether repository is just a link for other one."""
    return val.startswith('weblate://')


def get_distinct_translations(units):
    """Return list of distinct translations.

    It should be possible to use
    distinct('target') since Django 1.4, but it is not supported with MySQL, so
    let's emulate that based on presumption we won't get too many results.
    """
    targets = {}
    result = []
    for unit in units:
        if unit.target in targets:
            continue
        targets[unit.target] = 1
        result.append(unit)
    return result


def translation_percent(translated, total, zero_complete=True):
    """Return translation percentage."""
    if total == 0:
        return 100.0 if zero_complete else 0.0
    if total is None:
        return 0.0
    perc = round(1000 * translated / total) / 10.0
    # Avoid displaying misleading rounded 0.0% or 100.0%
    if perc == 0.0 and translated != 0:
        return 0.1
    if perc == 100.0 and translated < total:
        return 99.9
    return perc


def add_configuration_error(name, message, force_cache=False):
    """Log configuration error.

    Uses cache in case database is not yet ready."""
    if apps.models_ready and not force_cache:
        from weblate.wladmin.models import ConfigurationError
        try:
            ConfigurationError.objects.add(name, message)
            return
        except OperationalError:
            # The table does not have to be created yet (eg. migration
            # is about to be executed)
            pass
    errors = cache.get('configuration-errors', [])
    errors.append({
        'name': name,
        'message': message,
        'timestamp': timezone.now(),
    })
    cache.set('configuration-errors', errors)


def delete_configuration_error(name, force_cache=False):
    """Delete configuration error.

    Uses cache in case database is not yet ready."""
    if apps.models_ready and not force_cache:
        from weblate.wladmin.models import ConfigurationError
        try:
            ConfigurationError.objects.remove(name)
            return
        except OperationalError:
            # The table does not have to be created yet (eg. migration
            # is about to be executed)
            pass
    errors = cache.get('configuration-errors', [])
    errors.append({
        'name': name,
        'delete': True,
    })
    cache.set('configuration-errors', errors)


def get_clean_env(extra=None):
    """Return cleaned up environment for subprocess execution."""
    environ = {
        'LANG': 'en_US.UTF-8',
        'HOME': data_dir('home'),
    }
    if extra is not None:
        environ.update(extra)
    variables = ('PATH', 'LD_LIBRARY_PATH', 'SystemRoot')
    for var in variables:
        if var in os.environ:
            environ[var] = os.environ[var]
    # Python 2 on Windows doesn't handle Unicode objects in environment
    # even if they can be converted to ASCII string, let's fix it here
    if six.PY2 and sys.platform == 'win32':
        return {
            str(key): str(val) for key, val in environ.items()
        }
    return environ


def cleanup_repo_url(url):
    """Remove credentials from repository URL."""
    parsed = urlparse(url)
    if parsed.username and parsed.password:
        return url.replace(
            '{0}:{1}@'.format(
                parsed.username,
                parsed.password
            ),
            ''
        )
    elif parsed.username:
        return url.replace(
            '{0}@'.format(
                parsed.username,
            ),
            ''
        )
    return url


def redirect_param(location, params, *args, **kwargs):
    """Redirect to a URL with parameters."""
    return HttpResponseRedirect(
        resolve_url(location, *args, **kwargs) + params
    )


def cleanup_path(path):
    """Remove leading ./ or / from path."""
    if path.startswith('./'):
        path = path[2:]
    if path.startswith('/'):
        path = path[1:]
    return path


def get_project_description(project):
    """Return verbose description for project translation"""
    return _(
        '{0} is translated into {1} languages using Weblate. '
        'Join the translation or start translating your own project.',
    ).format(
        project,
        project.stats.languages
    )


def render(request, template, context=None, status=None):
    """Wrapper around Django render to extend context"""
    if context is None:
        context = {}
    if 'project' in context and context['project'] is not None:
        context['description'] = get_project_description(context['project'])
    return django_render(request, template, context, status=status)


def path_separator(path):
    """Alway use / as path separator for consistency"""
    if os.path.sep != '/':
        return path.replace(os.path.sep, '/')
    return path


def sort_unicode(choices, key):
    """Unicode aware sorting if available"""
    if not HAS_PYUCA:
        return sorted(
            choices,
            key=lambda tup: remove_accents(key(tup)).lower()
        )
    collator = pyuca.Collator()
    return sorted(
        choices,
        key=lambda tup: collator.sort_key(force_text(key(tup)))
    )


def remove_accents(input_str):
    """Remove accents from a string."""
    nkfd_form = unicodedata.normalize('NFKD', force_text(input_str))
    only_ascii = nkfd_form.encode('ASCII', 'ignore')
    return only_ascii


def sort_choices(choices):
    """Sort choices alphabetically.

    Either using cmp or pyuca.
    """
    return sort_unicode(choices, lambda tup: tup[1])


def sort_objects(objects):
    """Sort objects alphabetically"""
    return sort_unicode(objects, force_text)


def redirect_next(next_url, fallback):
    """Redirect to next URL from request after validating it."""
    if (next_url is None or
            not is_safe_url(next_url, allowed_hosts=None) or
            not next_url.startswith('/')):
        return redirect(fallback)
    return HttpResponseRedirect(next_url)
