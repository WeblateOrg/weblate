import hashlib

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

def msg_checksum(source, context):
    '''
    Returns checksum of source string, used for quick lookup.

    We use MD5 as it is faster than SHA1.
    '''
    m = hashlib.md5()
    m.update(source.encode('utf-8'))
    m.update(context.encode('utf-8'))
    return m.hexdigest()

