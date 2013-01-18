# Simple Diff for Python v 0.1
# (C) Paul Butler 2008 <http://www.paulbutler.org/>
# May be used and distributed under the zlib/libpng license
# <http://www.opensource.org/licenses/zlib-license.php>


def diff(old, new):
    """
    Find the differences between two lists. Returns a list of pairs, where
    the first value is in ['+','-','='] and represents an insertion, deletion,
    or no change for that list. The second value of the pair is the list of
    elements.
    """
    ohash = {}

    # Build a hash map with elements from old as keys, and
    # a list of indexes as values
    for i, val in enumerate(old):
        ohash.setdefault(val, []).append(i)

    # Find the largest substring common to old and new
    last_row = [0] * len(old)
    sub_start_old = sub_start_new = sub_length = 0

    for j, val in enumerate(new):
        this_row = [0] * len(old)
        for k in ohash.setdefault(val, []):
            this_row[k] = (k and last_row[k - 1]) + 1
            if(this_row[k] > sub_length):
                sub_length = this_row[k]
                sub_start_old = k - sub_length + 1
                sub_start_new = j - sub_length + 1
        last_row = this_row

    if sub_length == 0:
        # If no common substring is found, assume that an insert and
        # delete has taken place...
        return (old and [('-', old)] or []) + (new and [('+', new)] or [])
    else:
        # ...otherwise, the common substring is considered to have no change,
        # and we recurse on the text before and after the substring
        return (
            diff(
                old[:sub_start_old],
                new[:sub_start_new]
            ) +
            [('=', new[sub_start_new:sub_start_new + sub_length])] +
            diff(
                old[sub_start_old + sub_length:],
                new[sub_start_new + sub_length:]
            )
        )


def stringDiff(old, new):
    """
    Returns the difference between the old and new strings when split on
    whitespace. Considers punctuation a part of the word
    """
    return diff(old.split(), new.split())


def htmlDiff(old, new):
    """
    Returns the difference between two strings (as in stringDiff) in
    HTML format.

    >>> htmlDiff('First string', 'Second string')
    '<del>First</del><ins>Second</ins> string'

    >>> htmlDiff('First string', 'Second string new')
    '<del>First</del><ins>Second</ins> string<ins> new</ins>'

    """
    con = {
        '=': (lambda x: x),
        '+': (lambda x: "<ins>" + x + "</ins>"),
        '-': (lambda x: "<del>" + x + "</del>")
    }
    return "".join([(con[a])("".join(b)) for a, b in diff(old, new)])
