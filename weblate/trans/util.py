# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.core.exceptions import ImproperlyConfigured
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.shortcuts import resolve_url
from importlib import import_module
import os
import urlparse
import hashlib

PLURAL_SEPARATOR = '\x1e\x1e'


def calculate_checksum(source, context):
    """Calculates checksum identifying translation."""
    md5 = hashlib.md5()
    if source is not None:
        md5.update(source.encode('utf-8'))
    md5.update(context.encode('utf-8'))
    return md5.hexdigest()


def is_plural(text):
    '''
    Checks whether string is plural form.
    '''
    return text.find(PLURAL_SEPARATOR) != -1


def split_plural(text):
    return text.split(PLURAL_SEPARATOR)


def join_plural(text):
    return PLURAL_SEPARATOR.join(text)


def get_string(text):
    '''
    Returns correctly formatted string from ttkit unit data.
    '''
    # Check for null target (happens with XLIFF)
    if text is None:
        return ''
    if hasattr(text, 'strings'):
        return join_plural(text.strings)
    return text


def is_repo_link(val):
    '''
    Checks whether repository is just a link for other one.
    '''
    return val.startswith('weblate://')


def get_site_url(url=''):
    '''
    Returns root url of current site with domain.
    '''
    from weblate.appsettings import ENABLE_HTTPS
    from django.contrib.sites.models import Site
    site = Site.objects.get_current()
    return '{0}://{1}{2}'.format(
        'https' if ENABLE_HTTPS else 'http',
        site.domain,
        url
    )


def load_class(name):
    '''
    Imports module and creates class given by name in string.
    '''
    module, attr = name.rsplit('.', 1)
    try:
        mod = import_module(module)
    except ImportError as error:
        raise ImproperlyConfigured(
            'Error importing module %s: "%s"' %
            (module, error)
        )
    try:
        cls = getattr(mod, attr)
    except AttributeError:
        raise ImproperlyConfigured(
            'Module "%s" does not define a "%s" class' %
            (module, attr)
        )
    return cls


def get_distinct_translations(units):
    '''
    Returns list of distinct translations. It should be possible to use
    distinct('target') since Django 1.4, but it is not supported with MySQL, so
    let's emulate that based on presumption we won't get too many results.
    '''
    targets = {}
    result = []
    for unit in units:
        if unit.target in targets:
            continue
        targets[unit.target] = 1
        result.append(unit)
    return result


def translation_percent(translated, total):
    '''
    Returns translation percentage.
    '''
    return (1000 * translated / total) / 10.0


def add_configuration_error(name, message):
    """
    Logs configuration error.
    """
    errors = cache.get('configuration-errors', [])
    errors.append({
        'name': name,
        'message': message,
    })
    cache.set('configuration-errors', errors)


def get_configuration_errors():
    """
    Returns all configuration errors.
    """
    return cache.get('configuration-errors', [])


def get_clean_env(extra=None):
    """
    Returns cleaned up environment for subprocess execution.
    """
    environ = {}
    if extra is not None:
        environ.update(extra)
    variables = ('HOME', 'PATH', 'LANG', 'LD_LIBRARY_PATH')
    for var in variables:
        if var in os.environ:
            environ[var] = os.environ[var]
    return environ


def cleanup_repo_url(url):
    """
    Removes credentials from repository URL.
    """
    parsed = urlparse.urlparse(url)
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
    """
    Redirects to a URL with parameters.
    """
    return HttpResponseRedirect(
        resolve_url(location, *args, **kwargs) + params
    )
