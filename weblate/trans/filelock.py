# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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

'''
File based locking for Unix systems.
'''

import os
import time
import errno
import fcntl


class FileLockException(Exception):
    """
    Exception raised when locking is not possible.
    """
    pass


class FileLock(object):
    """
    A file locking mechanism for Unix systems based on flock.

    It can be also used as a context-manager using with statement.
    """

    def __init__(self, file_name, timeout=10, delay=.05):
        """
        Prepare the file locker. Specify the file to lock and optionally
        the maximum timeout and the delay between each attempt to lock.
        """
        # Lock file
        self.lockfile = file_name
        # Remember parameters
        self.timeout = timeout
        self.delay = delay

        # Initial state
        self.is_locked = False
        self.handle = None

    def acquire(self):
        """
        Acquire the lock, if possible.

        If the lock is in use, it check again every `wait` seconds. It does
        this until it either gets the lock or exceeds `timeout` number of
        seconds, in which case it throws an exception.
        """
        if self.is_locked:
            return

        # Timer for timeout
        start_time = time.time()

        # Open file
        self.handle = os.open(self.lockfile, os.O_CREAT | os.O_WRONLY)

        # Try to acquire lock
        while True:
            try:
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except IOError as error:
                if error.errno not in [errno.EACCES, errno.EAGAIN]:
                    raise

                if (time.time() - start_time) >= self.timeout:
                    raise FileLockException("Timeout occured.")

                time.sleep(self.delay)

        self.is_locked = True

    def check_lock(self):
        '''
        Checks whether lock is locked.
        '''
        handle = os.open(self.lockfile, os.O_CREAT | os.O_WRONLY)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(handle, fcntl.LOCK_UN)
            return False
        except IOError as error:
            if error.errno not in [errno.EACCES, errno.EAGAIN]:
                raise
            return True

    def release(self):
        """
        Release the lock and delete underlaying file.
        """
        if self.is_locked:
            fcntl.flock(self.handle, fcntl.LOCK_UN)
            os.close(self.handle)
            self.handle = None
            try:
                os.unlink(self.lockfile)
            except OSError:
                pass
            self.is_locked = False

    def __enter__(self):
        """
        Context-manager support, executed when entering with statement.

        Automatically acquires lock.
        """
        self.acquire()
        return self

    def __exit__(self, typ, value, traceback):
        """
        Context-manager support, executed when leaving with statement.

        Automatically releases lock.
        """
        self.release()

    def __del__(self):
        """
        Make sure that the FileLock instance doesn't leave a lockfile
        lying around.
        """
        self.release()
