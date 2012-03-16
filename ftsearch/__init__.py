"""

Django Full-text search

Author: Patrick Carroll <patrick@patrickomatic.com>
Version: 0.1

"""
import re
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from ftsearch.stemming import PorterStemmer

try:
	getattr(settings, 'SEARCH_STEMMER')

	# make sure it has a callable .stem() method
	try:
		settings.SEARCH_STEMMER().stem('foo')
	except AttributeError:
		raise ImproperlyConfigured("The supplied stemmer must support a stem() method")
except AttributeError:
	settings.SEARCH_STEMMER = PorterStemmer


try:
	getattr(settings, 'SEARCH_WORD_SPLIT_REGEX')
except AttributeError:
	settings.SEARCH_WORD_SPLIT_REGEX = re.compile(r'\W*')

