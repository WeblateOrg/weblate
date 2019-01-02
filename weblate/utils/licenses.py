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

OSI_APPROVED = frozenset((
    '0BSD', 'AAL', 'AFL-1.1', 'AFL-1.2', 'AFL-2.0', 'AFL-2.1', 'AFL-3.0',
    'AGPL-3.0', 'AGPL-3.0-only', 'AGPL-3.0-or-later', 'APL-1.0', 'APSL-1.0',
    'APSL-1.1', 'APSL-1.2', 'APSL-2.0', 'Apache-1.1', 'Apache-2.0',
    'Artistic-1.0', 'Artistic-1.0-Perl', 'Artistic-1.0-cl8', 'Artistic-2.0',
    'BSD-2-Clause', 'BSD-2-Clause-Patent', 'BSD-3-Clause', 'BSL-1.0',
    'CATOSL-1.1', 'CDDL-1.0', 'CECILL-2.1', 'CNRI-Python', 'CPAL-1.0',
    'CPL-1.0', 'CUA-OPL-1.0', 'ECL-1.0', 'ECL-2.0', 'EFL-1.0', 'EFL-2.0',
    'EPL-1.0', 'EPL-2.0', 'EUDatagrid', 'EUPL-1.1', 'EUPL-1.2', 'Entessa',
    'Fair', 'Frameworx-1.0', 'GPL-2.0', 'GPL-2.0+', 'GPL-2.0-only',
    'GPL-2.0-or-later', 'GPL-3.0', 'GPL-3.0+', 'GPL-3.0-only',
    'GPL-3.0-or-later', 'GPL-3.0-with-GCC-exception', 'HPND', 'IPA', 'IPL-1.0',
    'ISC', 'Intel', 'LGPL-2.0', 'LGPL-2.0+', 'LGPL-2.0-only',
    'LGPL-2.0-or-later', 'LGPL-2.1', 'LGPL-2.1+', 'LGPL-2.1-only',
    'LGPL-2.1-or-later', 'LGPL-3.0', 'LGPL-3.0+', 'LGPL-3.0-only',
    'LGPL-3.0-or-later', 'LPL-1.0', 'LPL-1.02', 'LPPL-1.3c', 'LiLiQ-P-1.1',
    'LiLiQ-R-1.1', 'LiLiQ-Rplus-1.1', 'MIT', 'MIT-0', 'MPL-1.0', 'MPL-1.1',
    'MPL-2.0', 'MPL-2.0-no-copyleft-exception', 'MS-PL', 'MS-RL', 'MirOS',
    'Motosoto', 'Multics', 'NASA-1.3', 'NCSA', 'NGPL', 'NPOSL-3.0', 'NTP',
    'Naumen', 'Nokia', 'OCLC-2.0', 'OFL-1.1', 'OGTSL', 'OSET-PL-2.1',
    'OSL-1.0', 'OSL-2.0', 'OSL-2.1', 'OSL-3.0', 'PHP-3.0', 'PostgreSQL',
    'Python-2.0', 'QPL-1.0', 'RPL-1.1', 'RPL-1.5', 'RPSL-1.0', 'RSCPL',
    'SISSL', 'SPL-1.0', 'SimPL-2.0', 'Sleepycat', 'UPL-1.0', 'VSL-1.0', 'W3C',
    'Watcom-1.0', 'Xnet', 'ZPL-2.0', 'Zlib'
))

FSF_APPROVED = frozenset((
    'AFL-1.1', 'AFL-1.2', 'AFL-2.0', 'AFL-2.1', 'AFL-3.0', 'AGPL-1.0',
    'AGPL-3.0', 'AGPL-3.0-only', 'AGPL-3.0-or-later', 'APSL-2.0', 'Apache-1.0',
    'Apache-1.1', 'Apache-2.0', 'Artistic-2.0', 'BSD-2-Clause-FreeBSD',
    'BSD-3-Clause', 'BSD-3-Clause-Clear', 'BSD-4-Clause', 'BSL-1.0',
    'BitTorrent-1.1', 'CC-BY-4.0', 'CC-BY-SA-4.0', 'CC0-1.0', 'CDDL-1.0',
    'CECILL-2.0', 'CECILL-B', 'CECILL-C', 'CPAL-1.0', 'CPL-1.0', 'ClArtistic',
    'Condor-1.1', 'ECL-2.0', 'EFL-2.0', 'EPL-1.0', 'EPL-2.0', 'EUDatagrid',
    'EUPL-1.1', 'EUPL-1.2', 'FSFAP', 'FTL', 'GFDL-1.1', 'GFDL-1.1-only',
    'GFDL-1.1-or-later', 'GFDL-1.2', 'GFDL-1.2-only', 'GFDL-1.2-or-later',
    'GFDL-1.3', 'GFDL-1.3-only', 'GFDL-1.3-or-later', 'GPL-2.0', 'GPL-2.0+',
    'GPL-2.0-only', 'GPL-2.0-or-later', 'GPL-3.0', 'GPL-3.0+', 'GPL-3.0-only',
    'GPL-3.0-or-later', 'HPND', 'IJG', 'IPA', 'IPL-1.0', 'ISC', 'Imlib2',
    'Intel', 'LGPL-2.1', 'LGPL-2.1+', 'LGPL-2.1-only', 'LGPL-2.1-or-later',
    'LGPL-3.0', 'LGPL-3.0+', 'LGPL-3.0-only', 'LGPL-3.0-or-later', 'LPL-1.02',
    'LPPL-1.2', 'LPPL-1.3a', 'MIT', 'MPL-1.1', 'MPL-2.0', 'MS-PL', 'MS-RL',
    'NCSA', 'NOSL', 'NPL-1.0', 'NPL-1.1', 'Nokia', 'Nunit', 'ODbL-1.0',
    'OFL-1.0', 'OFL-1.1', 'OLDAP-2.3', 'OLDAP-2.7', 'OSL-1.0', 'OSL-1.1',
    'OSL-2.0', 'OSL-2.1', 'OSL-3.0', 'OpenSSL', 'PHP-3.01', 'Python-2.0',
    'QPL-1.0', 'RPSL-1.0', 'Ruby', 'SGI-B-2.0', 'SISSL', 'SMLNJ', 'SPL-1.0',
    'Sleepycat', 'StandardML-NJ', 'UPL-1.0', 'Unlicense', 'Vim', 'W3C',
    'WTFPL', 'X11', 'XFree86-1.1', 'YPL-1.1', 'ZPL-2.0', 'ZPL-2.1', 'Zend-2.0',
    'Zimbra-1.3', 'Zlib', 'eCos-2.0', 'gnuplot', 'iMatix', 'xinetd'
))


FIXUPS = (
    ('v2', '-2.0'),
    ('v3', '-3.0'),
    ('LGPL-2+', 'LGPL-2.1'),
    ('LGPL-2.0+', 'LGPL-2.1'),
    ('-or-later', '+'),
    (' ', '-'),
    ('--', '-'),
)


def is_approved(license, licenses):
    license = license.strip()

    if not license:
        return False

    # Simply tokenize
    for token in license.split():
        token = token.strip('+')
        if token in licenses:
            return True

    # Some replacements
    for fixup, replacement in FIXUPS:
        if fixup in license:
            if is_osi_approved(license.replace(fixup, replacement)):
                return True

    return False


def is_osi_approved(license):
    return is_approved(license, OSI_APPROVED)


def is_fsf_approved(license):
    return is_approved(license, FSF_APPROVED)
