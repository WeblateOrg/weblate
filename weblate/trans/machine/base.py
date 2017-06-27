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
"""Base code for machine translation services."""

from __future__ import unicode_literals

import sys
import json

from six.moves.urllib.request import Request, urlopen

from django.core.cache import cache
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.http import urlencode

from weblate import USER_AGENT
from weblate.logger import LOGGER
from weblate.utils.errors import report_error
from weblate.trans.site import get_site_url


class MachineTranslationError(Exception):
    """Generic Machine translation error."""


class MissingConfiguration(ImproperlyConfigured):
    """Exception raised when configuraiton is wrong."""


class MachineTranslation(object):
    """Generic object for machine translation services."""
    name = 'MT'
    default_languages = []

    def __init__(self):
        """Create new machine translation object."""
        self.mtid = self.name.lower().replace(' ', '-')
        self.request_url = None
        self.request_params = None

    def get_identifier(self):
        return self.mtid

    def authenticate(self, request):
        """Hook for backends to allow add authentication headers to request."""
        return

    def json_req(self, url, http_post=False, skip_auth=False, raw=False,
                 **kwargs):
        """Perform JSON request."""
        # Encode params
        if len(kwargs) > 0:
            params = urlencode(kwargs)
        else:
            params = ''

        # Store for exception handling
        self.request_url = url
        self.request_params = params

        # Append parameters
        if len(params) > 0 and not http_post:
            url = '?'.join((url, params))

        # Create request object with custom headers
        request = Request(url)
        request.timeout = 0.5
        request.add_header('User-Agent', USER_AGENT)
        request.add_header('Referer', get_site_url())
        # Optional authentication
        if not skip_auth:
            self.authenticate(request)

        # Fire request
        if http_post:
            handle = urlopen(request, params.encode('utf-8'))
        else:
            handle = urlopen(request)

        # Read and possibly convert response
        text = handle.read()
        # Needed for Microsoft
        if text[:3] == b'\xef\xbb\xbf':
            text = text.decode('UTF-8-sig')
        else:
            text = text.decode('utf-8')
        # Replace literal \t
        text = text.strip().replace(
            '\t', '\\t'
        ).replace(
            '\r', '\\r'
        )
        # Needed for Google
        while ',,' in text or '[,' in text:
            text = text.replace(',,', ',null,').replace('[,', '[')

        if raw:
            return text

        # Parse JSON
        response = json.loads(text)

        # Return data
        return response

    def json_status_req(self, url, http_post=False, skip_auth=False, **kwargs):
        """Perform JSON request with checking response status."""
        # Perform request
        response = self.json_req(url, http_post, skip_auth, **kwargs)

        # Check response status
        if response['responseStatus'] != 200:
            raise MachineTranslationError(response['responseDetails'])

        # Return data
        return response

    def download_languages(self):
        """Download list of supported languages from a service."""
        return []

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service.

        Should return tuple - (translation text, translation quality, source of
        translation, source string).

        You can use self.name as source of translation, if you can not give
        better hint and text parameter as source string if you do no fuzzy
        matching.
        """
        raise NotImplementedError()

    def convert_language(self, language):
        """Convert language to service specific code."""
        return language

    def report_error(self, exc, message):
        """Wrapper for handling error situations"""
        report_error(
            exc, sys.exc_info(),
            {'mt_url': self.request_url, 'mt_params': self.request_params}
        )
        LOGGER.error(
            message,
            self.name,
        )
        LOGGER.error(
            'Last fetched URL: %s, params: %s',
            self.request_url,
            self.request_params,
        )

    @property
    def supported_languages(self):
        """Return list of supported languages."""
        cache_key = '{0}-languages'.format(self.mtid)

        # Try using list from cache
        languages = cache.get(cache_key)
        if languages is not None:
            return languages

        # Download
        try:
            languages = set(self.download_languages())
        except Exception as exc:
            self.report_error(
                exc,
                'Failed to fetch languages from %s, using defaults',
            )
            if settings.DEBUG:
                raise
            return self.default_languages

        # Update cache
        cache.set(cache_key, languages, 3600 * 48)

        return languages

    def is_supported(self, source, language):
        """Check whether given language combination is supported."""
        return (
            language in self.supported_languages and
            source in self.supported_languages
        )

    def translate(self, language, text, unit, user):
        """Return list of machine translations."""
        if text == '':
            return []

        language = self.convert_language(language)
        source = self.convert_language(
            unit.translation.subproject.project.source_language.code
        )
        if not self.is_supported(source, language):
            # Try without country code
            if '_' in language or '-' in language:
                language = language.replace('-', '_').split('_')[0]
                if source == language:
                    return []
                if not self.is_supported(source, language):
                    return []
            else:
                return []

        try:
            translations = self.download_translations(
                source, language, text, unit, user
            )

            return [
                {
                    'text': trans[0],
                    'quality': trans[1],
                    'service': trans[2],
                    'source': trans[3]
                }
                for trans in translations
            ]
        except Exception as exc:
            self.report_error(
                exc,
                'Failed to fetch translations from %s',
            )
            raise MachineTranslationError('{0}: {1}'.format(
                exc.__class__.__name__,
                str(exc)
            ))
