
PLURAL_SEPARATOR = '\x00\x00'

def is_plural(s):
    '''
    Checks whether string is plural form.
    '''
    return s.find(PLURAL_SEPARATOR) != -1

def split_plural(s):
    return s.split(PLURAL_SEPARATOR)

def join_plural(s):
    return PLURAL_SEPARATOR.join(s)

