"""

Django Full-text search

Author: Patrick Carroll <patrick@patrickomatic.com>
Version: 0.1

"""
import math


# XXX UGLY
def zero_protect(val):
	if val == 0.0:
		return 0.00000001

	return val

	
def normalize_scores(scores, small_is_better=False):
	""" Given a dict of keys mapping to floats, it will proportionally
	fit all of the values between 0.0 and 1.0.  If small_is_better=True,
	the value range returned will be reversed so smaller values produce
	numbers closer to 1.0 """
	if not scores: 
		return {}
	elif len(scores) == 1:
		return {scores.keys()[0]: 1.0}

	vsmall = 0.000001

	min_score = min(scores.values())
	shift = vsmall
	if min_score >= vsmall:
		shift = min_score

	max_score = max(scores.values()) 
	if max_score == 0: 
		max_score = vsmall

	if small_is_better:
		return dict([(k, 1 - (float(v - shift) / zero_protect(max_score - shift)))
				for (k, v) in scores.iteritems()])
	else:
		return dict([(k, float(v - shift) / zero_protect(max_score - shift)) \
				for (k, v) in scores.iteritems()])


def location_score(rows):
	""" Scores search results based on their proximity to the beginning of the
	document. """
	locations = dict([(row[0], 1000000) for row in rows])

	for row in rows:
		loc = sum(row[1:])
		if loc < locations[row[0]]:
			locations[row[0]] = loc

	return normalize_scores(locations, small_is_better=True)


def frequency_score(rows):
	""" Scores search results based on the frequency with which they occur
	in the document. """
	counts = dict([(row[0], 0) for row in rows])

	for row in rows: 
		counts[row[0]] += 1

	return normalize_scores(counts)


def distance_score(rows):
	""" Scores search results by how close to each other they are.  The closer
	they are, the higher the score. """
	if len(rows) == 0:
		return {}
	elif len(rows[0]) <= 2:
		return dict([(row[0], 1.0) for row in rows])

	min_distance = dict([(row[0], 1000000) for row in rows])

	for row in rows:
		dist = sum([abs(row[i] - row[i - 1]) for i in range(2, len(row))])
		if dist < min_distance[row[0]]:
			min_distance[row[0]] = dist

	return normalize_scores(min_distance, small_is_better=True)


def rating_score(rows, get_rating_fn):
	""" Calculates a weight given a rating.  If the model has some kind of
	attribute representing a rating, you can use this function to weight
	using that.  You must supply a function which takes one argument (the
	model's id) and returns an integer representing it's rating. """
	ratings = {}

	for row in rows:
		if not row[0] in ratings:
			rating = get_rating_fn(row[0])
			ratings[row[0]] = rating

	return normalize_scores(ratings)


def physical_distance(a, b):
	return math.sqrt((b[0] - a[0])**2 + (b[1] - a[1])**2)

def physical_distance_score(rows, location, get_location_fn):
	""" Assuming some kind of 2-axis coordinate system, score the items by
	their physical location to each other.  Location is a point location given
	in a 2-value tuple (x, y).  get_location_fn is a function which given a
	document id, will return the physical location of that document in a 
	2-value tuple. """
	if not location: return dict([(row[0], 1.0) for row in rows])

	distances = {}
	for row in rows:
		if not row[0] in distances:
			x, y = get_location_fn(row[0])
			distances[row[0]] = physical_distance(location, (x, y))

	return normalize_scores(distances, small_is_better=True)
