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

from trans.machine.base import MachineTranslation


class GoogleTranslation(MachineTranslation):
    '''
    Google machine translation support.
    '''
    name = 'Google Translate'

    def is_supported(self, language):
        '''
        Any language is supported.
        '''
        return True

    def download_translations(self, language, text, unit):
        '''
        Downloads list of possible translations from a service.
        '''
        response = self.json_req(
            'http://translate.google.com/translate_a/t',
            client='t',
            text=text,
            sl='en',
            tl=language,
            ie='UTF-8',
            oe='UTF-8'
        )

        return [(response[0][0][0], 100, self.name, text)]
