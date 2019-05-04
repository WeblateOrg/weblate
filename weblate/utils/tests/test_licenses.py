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

from django.test import SimpleTestCase

from weblate.utils.licenses import is_fsf_approved, is_osi_approved

# Licenses extracted from Hosted Weblate service
LICENSES = (
    '', 'MIT like license', 'CC-BY-SA-4.0', 'ISC', 'Beerware', 'GPL-3.0',
    'GPL-2.0', 'LGPL-2.0+', 'GPL-2.0+ or CC-BY-SA-3.0', 'LPPL-1.3c',
    'GPL-2.0+', 'MPL-2.0', 'CC-BY-ND-4.0', 'MIT', 'AGPL-3.0-or-later',
    'Public', 'CC0-1.0', 'LGPL-2+', 'GPLv3', 'CC-BY-2.0', 'AGPL-3.0+', 'GPLv2',
    'WTFPL', ' Apache-2.0', 'AGPL v3', 'LGPL-3.0+', 'Polymer License',
    'LGPL-2.1+', 'BSD-2-Clause', 'GPL-3.0+', 'AGPL-3.0', 'CC-BY-3.0',
    'Proprietary', 'Apache-2.0', 'BSD-3-Clause', 'Apache 2.0'
)

NON_OSI = {
    '', 'Polymer License', 'Proprietary', 'CC-BY-ND-4.0', 'CC0-1.0',
    'CC-BY-3.0', 'Public', 'Beerware', 'CC-BY-2.0', 'CC-BY-SA-4.0',
    'WTFPL',
}

NON_FSF = {
    '', 'Polymer License', 'Proprietary', 'CC-BY-ND-4.0',
    'CC-BY-3.0', 'Public', 'Beerware', 'CC-BY-2.0', 'LPPL-1.3c',
    'BSD-2-Clause',
}


class LicenseTest(SimpleTestCase):
    def test_osi(self):
        for license in LICENSES:
            self.assertEqual(
                is_osi_approved(license),
                license not in NON_OSI,
                'Wrong OSI state for {}'.format(license)
            )

    def test_fsf(self):
        for license in LICENSES:
            self.assertEqual(
                is_fsf_approved(license),
                license not in NON_FSF,
                'Wrong FSF state for {}'.format(license)
            )
