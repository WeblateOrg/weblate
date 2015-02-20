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

# For some reasons, this fails in PyLint sometimes...
# pylint: disable=E0611,F0401
from distutils.version import LooseVersion
from weblate.trans.vcs import GitRepository, HgRepository
import importlib
import sys


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

    name = 'Django'
    url = 'https://www.djangoproject.com/'
    mod = get_version_module('django', name, url)
    result.append((
        name,
        url,
        mod.get_version(),
        '1.7',
    ))

    name = 'python-social-auth'
    url = 'http://psa.matiasaguirre.net/'
    mod = get_version_module('social', name, url)
    result.append((
        name,
        url,
        mod.__version__,
        '0.2.0',
    ))

    name = 'Translate Toolkit'
    url = 'http://toolkit.translatehouse.org/'
    mod = get_version_module('translate.__version__', name, url)
    result.append((
        name,
        url,
        mod.sver,
        '1.10.0',
    ))

    name = 'Whoosh'
    url = 'http://bitbucket.org/mchaput/whoosh/'
    mod = get_version_module('whoosh', name, url)
    result.append((
        name,
        url,
        mod.versionstring(),
        '2.5',
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

    name = 'Pillow (PIL)'
    url = 'http://python-imaging.github.io/'
    mod = get_version_module('PIL.Image', name, url)
    result.append((
        name,
        url,
        mod.VERSION,
        '1.1.6',
    ))

    name = 'dateutil'
    url = 'http://labix.org/python-dateutil'
    mod = get_version_module('dateutil', name, url)
    result.append((
        name,
        url,
        mod.__version__,
        '1.0'
    ))

    name = 'lxml'
    url = 'http://lxml.de/'
    mod = get_version_module('lxml.etree', name, url)
    result.append((
        name,
        url,
        mod.__version__,
        '3.1.0',
    ))

    name = 'django-crispy-forms'
    url = 'http://django-crispy-forms.readthedocs.org/'
    mod = get_version_module('crispy_forms', name, url)
    result.append((
        name,
        url,
        mod.__version__,
        '1.4.0',
    ))

    return result


def check_version(name, url, version, expected):
    '''
    Check for single module version.
    '''
    if expected is None:
        return False
    looseversion = LooseVersion(version)
    if looseversion < expected:
        print '*** %s <%s> is too old! ***' % (name, url)
        print 'Installed version %s, required %s' % (version, expected)
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
