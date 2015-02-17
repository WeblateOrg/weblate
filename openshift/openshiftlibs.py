#!/usr/bin/env python

# Copyright 2011-2014 Red Hat Inc. and/or its affiliates and other
# contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import hashlib
import inspect
import os
import random
import sys


# Gets the secret token provided by OpenShift
# or generates one (this is slightly less secure, but good enough for now)
def get_openshift_secret_token():
    token = os.getenv('OPENSHIFT_SECRET_TOKEN')
    name = os.getenv('OPENSHIFT_APP_NAME')
    uuid = os.getenv('OPENSHIFT_APP_UUID')
    if token is not None:
        return token
    elif name is not None and uuid is not None:
        return hashlib.sha256(name + '-' + uuid).hexdigest()
    return None


# Loop through all provided variables and generate secure versions
# If not running on OpenShift, returns defaults and logs an error message
#
# This function calls secure_function and passes an array of:
#  {
#    'hash':     generated sha hash,
#    'variable': name of variable,
#    'original': original value
#  }
def openshift_secure(default_keys, secure_function='make_secure_key'):
    # Attempts to get secret token
    my_token = get_openshift_secret_token()

    # Only generate random values if on OpenShift
    my_list = default_keys

    if my_token is not None:
        # Loop over each default_key and set the new value
        for key, value in default_keys.iteritems():
            # Create hash out of token and this key's name
            sha = hashlib.sha256(my_token + '-' + key).hexdigest()
            # Pass a dictionary so we can add stuff without breaking existing
            # calls
            vals = {
                'hash': sha, 'variable': key, 'original': value
            }
            # Call user specified function or just return hash
            my_list[key] = sha
            if secure_function is not None:
                # Pick through the global and local scopes to find the
                # function.
                possibles = globals().copy()
                possibles.update(locals())
                supplied_function = possibles.get(secure_function)
                if not supplied_function:
                    raise Exception("Cannot find supplied security function")
                else:
                    my_list[key] = supplied_function(vals)
    else:
        calling_file = inspect.stack()[1][1]
        if os.getenv('OPENSHIFT_REPO_DIR'):
            base = os.getenv('OPENSHIFT_REPO_DIR')
            calling_file.replace(base, '')
        sys.stderr.write(
            "OPENSHIFT WARNING: Using default values for secure variables, " +
            "please manually modify in " + calling_file + "\n"
        )

    return my_list


# This function transforms default keys into per-deployment random keys;
def make_secure_key(key_info):
    hashcode = key_info['hash']
    original = key_info['original']

    # These are the legal password characters
    # as per the Django source code
    # (django/contrib/auth/models.py)
    chars = 'abcdefghjkmnpqrstuvwxyz'
    chars += 'ABCDEFGHJKLMNPQRSTUVWXYZ'
    chars += '23456789'

    # Use the hash to seed the RNG
    random.seed(int("0x" + hashcode[:8], 0))

    # Create a random string the same length as the default
    rand_key = ''
    for dummy in range(len(original)):
        rand_pos = random.randint(0, len(chars))
        rand_key += chars[rand_pos:(rand_pos + 1)]

    # Reset the RNG
    random.seed()

    # Set the value
    return rand_key
