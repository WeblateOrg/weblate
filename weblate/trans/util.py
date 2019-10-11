# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

import locale
import os
import sys

import six
from django.apps import apps
from django.core.cache import cache
from django.db.utils import OperationalError, ProgrammingError
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.shortcuts import render as django_render
from django.shortcuts import resolve_url
from django.utils import timezone
from django.utils.encoding import force_text
from django.utils.http import is_safe_url
from django.utils.translation import ugettext as _
from django.utils.translation import ugettext_lazy
from lxml import etree
from six.moves.urllib.parse import urlparse
from translate.storage.placeables.lisa import parse_xliff, strelem_to_xml

from weblate.utils.data import data_dir

PLURAL_SEPARATOR = '\x1e\x1e'
LOCALE_SETUP = True

PRIORITY_CHOICES = (
    (60, ugettext_lazy('Very high')),
    (80, ugettext_lazy('High')),
    (100, ugettext_lazy('Medium')),
    (120, ugettext_lazy('Low')),
    (140, ugettext_lazy('Very low')),
)

# Initialize to sane locales for strxfrm
try:
    locale.setlocale(locale.LC_ALL, ('C', 'UTF-8'))
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, ('en_US', 'UTF-8'))
    except locale.Error:
        LOCALE_SETUP = False


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
        except (OperationalError, ProgrammingError):
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
        except (OperationalError, ProgrammingError):
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
        'LANG': 'C.UTF-8',
        'LC_ALL': 'C.UTF-8',
        'HOME': data_dir('home'),
        'PATH': '/bin:/usr/bin:/usr/local/bin',
    }
    if extra is not None:
        environ.update(extra)
    variables = (
        # Keep PATH setup
        'PATH',
        # Keep Python search path
        'PYTHONPATH',
        # Keep linker configuration
        'LD_LIBRARY_PATH',
        'LD_PRELOAD',
        # Needed by Git on Windows
        'SystemRoot',
        # Pass proxy configuration
        'http_proxy',
        'https_proxy',
        'HTTPS_PROXY',
        'NO_PROXY',
        # below two are nedded for openshift3 deployment,
        # where nss_wrapper is used
        # more on the topic on below link:
        # https://docs.openshift.com/enterprise/3.2/creating_images/guidelines.html
        'NSS_WRAPPER_GROUP',
        'NSS_WRAPPER_PASSWD',
    )
    for var in variables:
        if var in os.environ:
            environ[var] = os.environ[var]
    # Extend path to include virtualenv
    environ['PATH'] = '{}/bin:{}'.format(sys.exec_prefix, environ['PATH'])
    # Python 2 on Windows doesn't handle Unicode objects in environment
    # even if they can be converted to ASCII string, let's fix it here
    if six.PY2 and sys.platform == 'win32':
        return {
            str(key): str(val) for key, val in environ.items()
        }
    return environ


def cleanup_repo_url(url, text=None):
    """Remove credentials from repository URL."""
    if text is None:
        text = url
    parsed = urlparse(url)
    if parsed.username and parsed.password:
        return text.replace(
            '{0}:{1}@'.format(parsed.username, parsed.password),
            ''
        )
    if parsed.username:
        return text.replace(
            '{0}@'.format(parsed.username),
            ''
        )
    return text


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
    if six.PY2:
        return sorted(choices, key=lambda tup: locale.strxfrm(key(tup).encode('utf-8')))
    return sorted(choices, key=lambda tup: locale.strxfrm(key(tup)))


def sort_choices(choices):
    """Sort choices alphabetically."""
    return sort_unicode(choices, lambda tup: tup[1])


def sort_objects(objects):
    """Sort objects alphabetically"""
    return sort_unicode(objects, force_text)


def redirect_next(next_url, fallback):
    """Redirect to next URL from request after validating it."""
    if (next_url is None
            or not is_safe_url(next_url, allowed_hosts=None)
            or not next_url.startswith('/')):
        return redirect(fallback)
    return HttpResponseRedirect(next_url)


def xliff_string_to_rich(string):
    """Convert XLIFF string to StringElement.

    Transform a string containing XLIFF placeholders as XML
    into a rich content (StringElement)
    """
    if isinstance(string, list):
        return [parse_xliff(s) for s in string]
    return [parse_xliff(string)]


def rich_to_xliff_string(string_elements):
    """Convert StringElement to XLIFF string.

    Transform rich content (StringElement) into
    a string with placeholder kept as XML
    """
    # Create dummy root element
    xml = etree.Element(u'e')
    for string_element in string_elements:
        # Inject placeable from translate-toolkit
        strelem_to_xml(xml, string_element)

    # Remove any possible namespace
    for child in xml:
        if child.tag.startswith('{'):
            child.tag = child.tag[child.tag.index('}') + 1:]
    etree.cleanup_namespaces(xml)

    # Convert to string
    string_xml = etree.tostring(xml, encoding="unicode")

    # Strip dummy root element
    return string_xml[3:][:-4]
