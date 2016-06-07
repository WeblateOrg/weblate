# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import print_function, unicode_literals

import importlib
import sys
# For some reasons, this fails in PyLint sometimes...
# pylint: disable=E0611,F0401
from distutils.version import LooseVersion
from weblate.trans.vcs import GitRepository, HgRepository


def get_version_module(module, name, url, optional=False):
    '''
    Returns module object, on error raises verbose
    exception with name and URL.
    '''
    try:
        mod = importlib.import_module(module)
    except ImportError:
        if optional:
            return None
        raise Exception(
            'Failed to import %s, please install %s from %s' % (
                module.replace('.__version__', ''),
                name,
                url,
            )
        )
    return mod


def get_optional_versions():
    '''
    Returns versions of optional modules.
    '''
    result = []

    name = 'pytz'
    url = 'https://pypi.python.org/pypi/pytz/'
    mod = get_version_module('pytz', name, url, True)
    if mod is not None:
        result.append((
            name,
            url,
            mod.__version__,
            None,
        ))

    name = 'pyuca'
    url = 'https://github.com/jtauber/pyuca'
    mod = get_version_module('pyuca', name, url, True)
    if mod is not None:
        result.append((
            name,
            url,
            'N/A',
            None,
        ))

    name = 'python-bidi'
    url = 'https://github.com/MeirKriheli/python-bidi'
    mod = get_version_module('bidi', name, url, True)
    if mod is not None:
        result.append((
            name,
            url,
            mod.VERSION,
            None,
        ))

    name = 'pyLibravatar'
    url = 'https://pypi.python.org/pypi/pyLibravatar'
    mod = get_version_module('libravatar', name, url, True)
    if mod is not None:
        result.append((
            name,
            url,
            'N/A',
            None,
        ))

    if HgRepository.is_supported():
        result.append((
            'Mercurial',
            'http://mercurial.selenic.com/',
            HgRepository.get_version(),
            '2.8',
        ))

    return result


def get_single(name, url, module, required, getter='__version__'):
    """Returns version information for single module"""
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
    '''
    Returns list of used versions.
    '''
    result = []

    result.append((
        'Python',
        'http://www.python.org/',
        sys.version.split()[0],
        '2.7',
    ))

    result.append(get_single(
        'Django',
        'https://www.djangoproject.com/',
        'django',
        '1.8',
        'get_version'
    ))

    result.append(get_single(
        'six',
        'https://pypi.python.org/pypi/six',
        'six',
        '1.7.0',
    ))

    result.append(get_single(
        'python-social-auth',
        'http://psa.matiasaguirre.net/',
        'social',
        '0.2.0',
    ))

    result.append(get_single(
        'Translate Toolkit',
        'http://toolkit.translatehouse.org/',
        'translate.__version__',
        '1.14.0-rc1',
        'sver',
    ))

    result.append(get_single(
        'Whoosh',
        'http://bitbucket.org/mchaput/whoosh/',
        'whoosh',
        '2.5',
        'versionstring',
    ))

    try:
        result.append((
            'Git',
            'http://git-scm.com/',
            GitRepository.get_version(),
            '1.6',
        ))
    except OSError:
        raise Exception('Failed to run git, please install it.')

    result.append(get_single(
        'Pillow (PIL)',
        'http://python-imaging.github.io/',
        'PIL.Image',
        '1.1.6',
        'VERSION',
    ))

    result.append(get_single(
        'dateutil',
        'http://labix.org/python-dateutil',
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
        'http://django-crispy-forms.readthedocs.org/',
        'crispy_forms',
        '1.4.0',
    ))

    result.append(get_single(
        'compressor',
        'https://github.com/django-compressor/django-compressor',
        'compressor',
        '1.5',
    ))

    result.append(get_single(
        'djangorestframework',
        'http://www.django-rest-framework.org/',
        'rest_framework',
        '3.3',
    ))

    return result


def check_version(name, url, version, expected):
    '''
    Check for single module version.
    '''
    if expected is None:
        return False
    if LooseVersion(version) < LooseVersion(expected):
        print('*** {0} <{1}> is too old! ***'.format(name, url))
        print('Installed version {0}, required {1}'.format(version, expected))
        return True

    return False


def check_requirements():
    '''
    Performs check on requirements and raises an exception on error.
    '''
    versions = get_versions() + get_optional_versions()
    failure = False

    for version in versions:
        failure |= check_version(*version)

    if failure:
        raise Exception(
            'Some of required modules are missing or too old! '
            'Check above output for details.'
        )
