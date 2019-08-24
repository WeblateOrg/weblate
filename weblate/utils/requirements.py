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

from __future__ import print_function, unicode_literals

import sys
from distutils.version import LooseVersion

import pkg_resources
from django.core.checks import Error
from django.core.exceptions import ImproperlyConfigured

import weblate
from weblate.utils.docs import get_doc_url
from weblate.vcs.git import (
    GithubRepository,
    GitRepository,
    GitWithGerritRepository,
    SubversionRepository,
)
from weblate.vcs.mercurial import HgRepository


def get_version_module(name, url, optional=False):
    """Return module object.

    On error raises verbose exception with name and URL.
    """
    try:
        return pkg_resources.get_distribution(name).version
    except pkg_resources.DistributionNotFound:
        if optional:
            return None
        raise ImproperlyConfigured(
            'Missing dependency, please install {0} from {1}'.format(name, url)
        )


def get_optional_module(result, name, url):
    """Get metadata for optional dependency"""
    version = get_version_module(name, url, True)
    if version is not None:
        result.append((name, url, version, None))


def get_optional_versions():
    """Return versions of optional modules."""
    result = []

    get_optional_module(
        result, 'ruamel.yaml', 'https://pypi.org/project/ruamel.yaml/'
    )

    get_optional_module(
        result, 'tesserocr', 'https://github.com/sirfz/tesserocr'
    )

    if HgRepository.is_supported():
        result.append((
            'Mercurial',
            'https://www.mercurial-scm.org/',
            HgRepository.get_version(),
            '2.8',
        ))

    if SubversionRepository.is_supported():
        result.append((
            'git-svn',
            'https://git-scm.com/docs/git-svn',
            SubversionRepository.get_version(),
            '1.6',
        ))

    if GitWithGerritRepository.is_supported():
        result.append((
            'git-review',
            'https://pypi.org/project/git-review/',
            GitWithGerritRepository.get_version(),
            '1.0',
        ))

    if GithubRepository.is_supported():
        result.append((
            'hub',
            'https://hub.github.com/',
            GithubRepository.get_version(),
            '1.0',
        ))

    return result


def get_single(name, url, required):
    """Return version information for single module"""
    return (
        name,
        url,
        get_version_module(name, url),
        required,
    )


def get_versions():
    """Return list of used versions."""
    result = []

    result.append((
        'Python',
        'https://www.python.org/',
        sys.version.split()[0],
        '2.7',
    ))

    result.append(get_single(
        'Django',
        'https://www.djangoproject.com/',
        '1.11',
    ))

    result.append(get_single(
        'Celery',
        'http://www.celeryproject.org/',
        '4.0',
    ))

    result.append(get_single(
        'celery-batches',
        'https://pypi.org/project/celery-batches/',
        '0.2',
    ))

    result.append(get_single(
        'six',
        'https://pypi.org/project/six/',
        '1.7.0',
    ))

    result.append(get_single(
        'social-auth-core',
        'https://python-social-auth.readthedocs.io/',
        '3.1.0',
    ))

    result.append(get_single(
        'social-auth-app-django',
        'https://python-social-auth.readthedocs.io/',
        '3.1.0',
    ))

    result.append(get_single(
        'django-appconf',
        'https://github.com/django-compressor/django-appconf',
        '1.0'
    ))

    result.append(get_single(
        'translate-toolkit',
        'https://toolkit.translatehouse.org/',
        '2.3.1',
    ))

    result.append(get_single(
        'translation-finder',
        'https://github.com/WeblateOrg/translation-finder',
        '1.4',
    ))

    result.append(get_single(
        'Whoosh',
        'https://bitbucket.org/mchaput/whoosh/',
        '2.7',
    ))

    result.append(get_single(
        'defusedxml',
        'https://github.com/tiran/defusedxml',
        '0.4',
    ))

    try:
        result.append((
            'Git',
            'https://git-scm.com/',
            GitRepository.get_version(),
            '1.6',
        ))
    except OSError:
        raise ImproperlyConfigured('Failed to run git, please install it.')

    result.append(get_single(
        'Pillow',
        'https://python-pillow.org/',
        '1.1.6',
    ))

    result.append(get_single(
        'python-dateutil',
        'https://labix.org/python-dateutil',
        '1.0'
    ))

    result.append(get_single(
        'lxml',
        'https://lxml.de/',
        '3.5.0',
    ))

    result.append(get_single(
        'django-crispy-forms',
        'https://django-crispy-forms.readthedocs.io/',
        '1.6.1',
    ))

    result.append(get_single(
        'django_compressor',
        'https://github.com/django-compressor/django-compressor',
        '2.1',
    ))

    result.append(get_single(
        'djangorestframework',
        'https://www.django-rest-framework.org/',
        '3.8',
    ))

    result.append(get_single(
        'user-agents',
        'https://github.com/selwin/python-user-agents',
        '1.1.0',
    ))

    result.append(get_single(
        'jellyfish',
        'https://github.com/jamesturk/jellyfish',
        '0.6.1',
    ))

    result.append(get_single(
        'diff-match-patch',
        'https://github.com/diff-match-patch-python/diff-match-patch',
        '20121119',
    ))

    return result


def check_version(version, expected):
    """Check for single module version."""
    if expected is None:
        return False
    return LooseVersion(version) < LooseVersion(expected)


def check_requirements(app_configs, **kwargs):
    """Perform check on requirements and raises an exception on error."""
    versions = get_versions() + get_optional_versions()
    errors = []
    message = '{0} <{1}> is too old. Installed version {2}, required {3}.'

    for name, url, version, expected in versions:
        if check_version(version, expected):
            errors.append(
                Error(
                    message.format(name, url, version, expected),
                    hint=get_doc_url('admin/install', 'requirements'),
                    id='weblate.E001',
                )
            )

    return errors


def get_versions_list():
    """Return list with version information summary."""
    return (
        [('Weblate', '', weblate.GIT_VERSION)]
        + get_versions()
        + get_optional_versions()
    )


def get_versions_string():
    """Return string with version information summary."""
    result = []
    for version in get_versions_list():
        result.append(
            ' * {0} {1}'.format(
                version[0],
                version[2]
            )
        )
    return '\n'.join(result)
