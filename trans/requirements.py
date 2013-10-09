# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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
from weblate import GIT_VERSION
import importlib


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
                module,
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

    name = 'ICU'
    url = 'https://pypi.python.org/pypi/PyICU'
    mod = get_version_module('icu', name, url, True)
    if mod is not None:
        result.append((
            name,
            url,
            mod.VERSION,
            '1.0',
        ))

    name = 'pyLibravatar'
    url = 'https://pypi.python.org/pypi/pyLibravatar'
    mod = get_version_module('libravatar', name, url, True)
    if mod is not None:
        result.append((
            name,
            url,
            'N/A',
            '',
        ))

    return result


def get_versions():
    '''
    Returns list of used versions.
    '''
    result = []

    name = 'Django'
    url = 'https://www.djangoproject.com/'
    mod = get_version_module('django', name, url)
    result.append((
        name,
        url,
        mod.get_version(),
        '1.4',
    ))

    name = 'python-social-auth'
    url = 'http://psa.matiasaguirre.net/'
    mod = get_version_module('social', name, url)
    result.append((
        name,
        url,
        mod.__version__,
        '0.1',
    ))

    name = 'Translate Toolkit'
    url = 'http://toolkit.translatehouse.org/'
    mod = get_version_module('translate', name, url)
    result.append((
        name,
        url,
        mod.__version__.sver,
        '1.9.0',
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

    name = 'GitPython'
    url = 'https://github.com/gitpython-developers/GitPython'
    mod = get_version_module('git', name, url)
    result.append((
        name,
        url,
        mod.__version__,
        '0.3.2',
    ))

    name = 'Git'
    url = 'http://git-scm.com/'
    mod = get_version_module('git', name, url)
    try:
        result.append((
            name,
            url,
            mod.Git().version().replace('git version ', ''),
            '1.0',
        ))
    except TypeError:
        # Happens with too old GitPython
        pass

    name = 'South'
    url = 'http://south.aeracode.org/'
    mod = get_version_module('south', name, url)
    result.append((
        name,
        url,
        mod.__version__,
        '0.7',
    ))

    name = 'Pillow (PIL)'
    url = 'http://python-imaging.github.io/'
    mod = get_version_module('PIL.Image', name, url)
    result.append((
        name,
        url,
        mod.VERSION,
        '1.1.6',
    ))

    return result


def check_version(name, url, version, expected, highest=None):
    '''
    Check for single module version.
    '''
    if expected is None:
        return
    looseversion = LooseVersion(version)
    if looseversion < expected:
        print '*** %s <%s> is too old! ***' % (name, url)
        print 'Installed version %s, required %s' % (version, expected)
        return True
    if highest is not None and looseversion > highest:
        print '*** %s <%s> is not supported! ***' % (name, url)
        print 'Installed version %s, required %s' % (version, highest)
        return True

    return False


def get_versions_string():
    '''
    Returns string with version information summary.
    '''
    result = [' * Weblate %s' % GIT_VERSION]
    for version in get_versions() + get_optional_versions():
        result.append(
            ' * %s %s' % (
                version[0],
                version[2],
            )
        )
    return '\n'.join(result)
