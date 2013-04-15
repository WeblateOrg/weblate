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

from distutils.version import LooseVersion


def get_version_module(module, name, url, optional=False):
    '''
    Returns module object, on error raises verbose
    exception with name and URL.
    '''
    try:
        mod = __import__(module)
    except ImportError:
        if not optional:
            raise Exception(
                'Failed to import %s, please install %s from %s' % (
                    module,
                    name,
                    url,
                )
            )
    return mod


def get_versions(optional=False):
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

    name = 'Django-registration'
    url = 'https://bitbucket.org/ubernostrum/django-registration/'
    mod = get_version_module('registration', name, url)
    result.append((
        name,
        url,
        mod.get_version(),
        '0.8',
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
        '2.3',
    ))

    name = 'GitPython'
    url = 'https://github.com/gitpython-developers/GitPython'
    mod = get_version_module('git', name, url)
    result.append((
        name,
        url,
        mod.__version__,
        '0.3',
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

    name = 'PyCairo'
    url = 'http://cairographics.org/pycairo/'
    mod = get_version_module('cairo', name, url)
    result.append((
        name,
        url,
        mod.version,
        '1.8',
    ))

    name = 'Pango (PyGtk)'
    url = 'http://www.pygtk.org/'
    mod = get_version_module('pango', name, url)
    result.append((
        name,
        url,
        mod.version_string(),
        '1.2',
    ))

    name = 'South'
    url = 'http://south.aeracode.org/'
    mod = get_version_module('south', name, url)
    result.append((
        name,
        url,
        mod.__version__,
        '0.7',
    ))

    if optional:
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


def check_version(name, url, version, expected):
    '''
    Check for single module version.
    '''
    if expected is None:
        return
    if LooseVersion(version) < expected:
        print '*** %s <%s> is too old! ***' % (name, url)
        print 'Installed version %s, required %s' % (version, expected)
        return True
    return False
