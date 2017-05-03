# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

from django.conf import settings

from weblate.trans.machine.base import MachineTranslation, MissingConfiguration

from six.moves.urllib.parse import quote


class TMServerTranslation(MachineTranslation):
    """tmserver machine translation support."""
    name = 'tmserver'

    def __init__(self):
        """Check configuration."""
        super(TMServerTranslation, self).__init__()
        self.url = self.get_server_url()

    def get_server_url(self):
        """Return URL of a server."""
        if settings.MT_TMSERVER is None:
            raise MissingConfiguration(
                'Not configured tmserver URL'
            )

        return settings.MT_TMSERVER.rstrip('/')

    def convert_language(self, language):
        """Convert language to service specific code."""
        return language.replace('-', '_').lower()

    def download_languages(self):
        """Download list of supported languages from a service."""
        data = self.json_req('{0}/languages/'.format(self.url))
        return [
            (src, tgt)
            for src in data['sourceLanguages']
            for tgt in data['targetLanguages']
        ]

    def is_supported(self, source, language):
        """Check whether given language combination is supported."""
        if len(self.supported_languages) == 0:
            # Fallback for old tmserver which does not export list of
            # supported languages
            return True
        return (source, language) in self.supported_languages

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        url = '{0}/{1}/{2}/unit/{3}'.format(
            self.url,
            quote(source),
            quote(language),
            quote(text[:500].replace('\r', ' ').encode('utf-8'))
        )
        response = self.json_req(url)

        return [(line['target'], line['quality'], self.name, line['source'])
                for line in response]


class AmagamaTranslation(TMServerTranslation):
    """Specific instance of tmserver ran by Virtaal authors."""
    name = 'Amagama'

    def get_server_url(self):
        return 'https://amagama-live.translatehouse.org/api/v1'
