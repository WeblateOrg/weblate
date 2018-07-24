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

import weblate


def get_doc_url(page, anchor=''):
    """Return URL to documentation."""
    # Should we use tagged release or latest version
    if '-dev' in weblate.VERSION:
        version = 'latest'
    else:
        version = 'weblate-{0}'.format(weblate.VERSION)
    # Generate URL
    url = 'https://docs.weblate.org/en/{0}/{1}.html'.format(version, page)
    # Optionally append anchor
    if anchor != '':
        url += '#{0}'.format(anchor)

    return url
