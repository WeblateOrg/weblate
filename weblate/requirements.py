# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

import importlib
import sys
# For some reasons, this fails in PyLint sometimes...
# pylint: disable=E0611,F0401
from distutils.version import LooseVersion
from weblate.trans.vcs import (
    GitRepository, HgRepository, SubversionRepository, GitWithGerritRepository,
    GithubRepository,
)


def get_version_module(module, name, url, optional=False):
    """Return module object.

    On error raises verbose exception with name and URL.
    """
    try:
        mod = importlib.import_module(module)
    except ImportError:
        if optional:
            return None
        raise Exception(
            'Failed to import {0}, please install {1} from {2}'.format(
                module.replace('.__version__', ''),
                name,
                url
            )
        )
    return mod


def get_optional_module(result, module, name, url, attr='__version__'):
    """Get metadata for optional dependency"""
    mod = get_version_module(module, name, url, True)
    if mod is not None:
        result.append((
            name,
            url,
            getattr(mod, attr) if attr else 'N/A',
            None,
        ))


def get_optional_versions():
    """Return versions of optional modules."""
    result = []

    get_optional_module(
        result, 'pytz', 'pytz', 'https://pypi.python.org/pypi/pytz/'
    )

    get_optional_module(
        result, 'pyuca', 'pyuca', 'https://github.com/jtauber/pyuca', None
    )

    get_optional_module(
        result, 'bidi', 'python-bidi',
        'https://github.com/MeirKriheli/python-bidi', 'VERSION'
    )

    get_optional_module(
        result, 'libravatar', 'pyLibravatar',
        'https://pypi.python.org/pypi/pyLibravatar', None
    )

    get_optional_module(
        result, 'yaml', 'PyYAML', 'http://pyyaml.org/wiki/PyYAML'
    )

    get_optional_module(
        result, 'tesserocr', 'tesserocr', 'https://github.com/sirfz/tesserocr'
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
            'https://pypi.python.org/pypi/git-review',
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


def get_single(name, url, module, required, getter='__version__'):
    """Return version information for single module"""
    mod = get_version_module(module, name, url)
    version_getter = getattr(mod, getter)
    if hasattr(version_getter, '__call__'):
        current = version_getter()
    else:
        current = version_getter
    return (
        name,
        url,
        current,
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
        'django',
        '1.10',
        'get_version'
    ))

    result.append(get_single(
        'six',
        'https://pypi.python.org/pypi/six',
        'six',
        '1.7.0',
    ))

    result.append(get_single(
        'social-auth-core',
        'https://python-social-auth.readthedocs.io/',
        'social_core',
        '1.3.0',
    ))

    result.append(get_single(
        'social-auth-app-django',
        'https://python-social-auth.readthedocs.io/',
        'social_django',
        '1.2.0',
    ))

    result.append(get_single(
        'django-appconf',
        'https://github.com/django-compressor/django-appconf',
        'appconf',
        '1.0'
    ))

    result.append(get_single(
        'Translate Toolkit',
        'http://toolkit.translatehouse.org/',
        'translate.__version__',
        '2.0.0',
        'sver',
    ))

    result.append(get_single(
        'Whoosh',
        'https://bitbucket.org/mchaput/whoosh/',
        'whoosh',
        '2.7',
        'versionstring',
    ))

    result.append(get_single(
        'defusedxml',
        'https://bitbucket.org/tiran/defusedxml',
        'defusedxml',
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
        raise Exception('Failed to run git, please install it.')

    result.append(get_single(
        'Pillow (PIL)',
        'https://python-pillow.org/',
        'PIL.Image',
        '1.1.6',
        'VERSION',
    ))

    result.append(get_single(
        'dateutil',
        'https://labix.org/python-dateutil',
        'dateutil',
        '1.0'
    ))

    result.append(get_single(
        'lxml',
        'http://lxml.de/',
        'lxml.etree',
        '3.1.0',
    ))

    result.append(get_single(
        'django-crispy-forms',
        'https://django-crispy-forms.readthedocs.io/',
        'crispy_forms',
        '1.6.1',
    ))

    result.append(get_single(
        'compressor',
        'https://github.com/django-compressor/django-compressor',
        'compressor',
        '2.1',
    ))

    result.append(get_single(
        'djangorestframework',
        'http://www.django-rest-framework.org/',
        'rest_framework',
        '3.4',
    ))

    return result


def check_version(name, url, version, expected):
    """Check for single module version."""
    if expected is None:
        return False
    if LooseVersion(version) < LooseVersion(expected):
        print('*** {0} <{1}> is too old! ***'.format(name, url))
        print('Installed version {0}, required {1}'.format(version, expected))
        return True

    return False


def check_requirements():
    """Perform check on requirements and raises an exception on error."""
    versions = get_versions() + get_optional_versions()
    failure = False

    for version in versions:
        failure |= check_version(*version)

    if failure:
        raise Exception(
            'Some of required modules are missing or too old! '
            'Check above output for details.'
        )
