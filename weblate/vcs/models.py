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

from appconf import AppConf

from weblate.utils.classloader import ClassLoader


class VcsClassLoader(ClassLoader):
    def __init__(self):
        super(VcsClassLoader, self).__init__('VCS_BACKENDS', False)

    def load_data(self):
        result = super(VcsClassLoader, self).load_data()

        for key, vcs in list(result.items()):
            if not vcs.is_supported():
                result.pop(key)

        return result


# Initialize VCS list
VCS_REGISTRY = VcsClassLoader()


class VCSConf(AppConf):
    BACKENDS = (
        'weblate.vcs.git.GitRepository',
        'weblate.vcs.git.GitWithGerritRepository',
        'weblate.vcs.git.SubversionRepository',
        'weblate.vcs.git.GithubRepository',
        'weblate.vcs.mercurial.HgRepository',
    )

    class Meta(object):
        prefix = 'VCS'
