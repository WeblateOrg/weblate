#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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


from django.test import SimpleTestCase

from weblate.utils.licenses import convert_license

# Licenses extracted from Hosted Weblate service
TEST_DATA = {
    "": "",
    "GNU AGPLv3": "AGPL-3.0-only",
    "AGPL-3.0+": "AGPL-3.0-or-later",
    "GNU GPLv3": "GPL-3.0-only",
    "MPL-2.0": "MPL-2.0",
    "Apache-2.0": "Apache-2.0",
    "Polymer License": "BSD-3-Clause",
    "Beerware": "Beerware",
    "BSD-3-clause": "BSD-3-Clause",
    "GPL-2.0+": "GPL-2.0-or-later",
    "AGPL-3.0-or-later": "AGPL-3.0-or-later",
    "CC-BY-2.0": "CC-BY-2.0",
    "BSD beerware derivative": "Beerware",
    "GPL-2.0": "GPL-2.0-only",
    "GPL-3.0+": "GPL-3.0-or-later",
    "GPL-2.0+ or CC-BY-SA-3.0": "GPL-2.0-or-later",
    "LGPL-3.0+": "LGPL-3.0-or-later",
    "CC-BY-ND-4.0": "CC-BY-ND-4.0",
    "BSD-2-Clause": "BSD-2-Clause",
    "MIT": "MIT",
    "Please see the Contribution License Agreement": "proprietary",
    "LGPL-2+": "LGPL-2.0-or-later",
    "Apache License 2.0": "Apache-2.0",
    "Zlib": "Zlib",
    "CC-BY-SA-4.0": "CC-BY-SA-4.0",
    "CC0-1.0": "CC0-1.0",
    "Proprietary": "proprietary",
    "ISC": "ISC",
    "LGPL-2.0+": "LGPL-2.0-or-later",
    "WTFPL": "WTFPL",
    "LPPL-1.3c": "LPPL-1.3c",
    " Apache-2.0": "Apache-2.0",
    "GNU GPL v3": "GPL-3.0-only",
    "CC-BY-3.0": "CC-BY-3.0",
    "MIT like license": "MIT",
    "GPLv3": "GPL-3.0-only",
    "BSD-3-Clause": "BSD-3-Clause",
    "Apache 2.0": "Apache-2.0",
    "GNU General Public Licence": "GPL-2.0-or-later",
    "GPL-3.0-or-later": "GPL-3.0-or-later",
    "LGPL-2.1+": "LGPL-2.1-or-later",
    "AGPL v3": "AGPL-3.0-only",
    "GPLv2": "GPL-2.0-only",
    "GPL-3.0": "GPL-3.0-only",
    "AGPL-3.0": "AGPL-3.0-only",
}


class LicenseTest(SimpleTestCase):
    def test_convert(self):
        for source, expected in TEST_DATA.items():
            self.assertEqual(
                expected,
                convert_license(source),
                "License conversion failed for {}".format(source),
            )
