"""

Django Full-text search

Author: Patrick Carroll <patrick@patrickomatic.com>
Version: 0.1

"""
import re
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from ftsearch.stemming import PorterStemmer
from ftsearch.weights import frequency_score, location_score, distance_score


VERSION = 0.1

try:
	getattr(settings, 'SEARCH_WEIGHTS')
except AttributeError:
	settings.SEARCH_WEIGHTS = (
			(1.0, frequency_score),
			(1.0, location_score),
			(1.0, distance_score),
	)


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

