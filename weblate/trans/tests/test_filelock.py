# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from unittest import TestCase
import shutil
import tempfile
import os.path
from multiprocessing import Process
from weblate.trans.filelock import FileLock, FileLockException


class LockTest(TestCase):
    def setUp(self):
        self.testdir = tempfile.mkdtemp()
        self.testfile = os.path.join(self.testdir, 'lock-test')

    def tearDown(self):
        shutil.rmtree(self.testdir)

    def test_lock(self):
        '''
        Basic locking test.
        '''
        lock = FileLock(self.testfile)
        lock.acquire()
        self.assertTrue(lock.is_locked)
        self.assertTrue(lock.check_lock())
        lock.release()
        self.assertFalse(lock.is_locked)
        self.assertFalse(lock.check_lock())

    def test_lock_twice(self):
        '''
        Basic locking test.
        '''
        lock = FileLock(self.testfile)
        lock.acquire()
        lock.acquire()
        self.assertTrue(lock.is_locked)
        lock.release()
        self.assertFalse(lock.is_locked)

    def test_lock_invalid(self):
        '''
        Basic locking test.
        '''
        lock = FileLock(os.path.join(self.testdir, 'invalid', 'lock', 'path'))
        self.assertRaises(OSError, lock.acquire)

    def test_context(self):
        '''
        Test of context handling.
        '''
        lock = FileLock(self.testfile)
        lock2 = FileLock(self.testfile, timeout=0)
        with lock:
            self.assertTrue(lock.is_locked)
            self.assertTrue(lock.check_lock())
            self.assertRaises(FileLockException, lock2.acquire)
        self.assertFalse(lock.is_locked)
        self.assertFalse(lock.check_lock())

    def test_double(self):
        '''
        Test of double locking.
        '''
        lock1 = FileLock(self.testfile)
        lock2 = FileLock(self.testfile, timeout=0)
        lock1.acquire()
        self.assertRaises(FileLockException, lock2.acquire)
        lock1.release()
        lock2.acquire()
        lock2.release()

    def test_stale(self):
        '''
        Handling of stale lock files.
        '''
        lock = FileLock(self.testfile)
        lockfile = open(lock.lockfile, 'w')
        lock.acquire()
        lockfile.close()
        lock.release()

    def second_lock(self):
        lock = FileLock(self.testfile, timeout=0)
        lock.acquire()
        lock.release()

    def test_process(self):
        '''
        Test of double locking.
        '''
        lock = FileLock(self.testfile)
        lock.acquire()
        process = Process(target=self.second_lock)
        process.start()
        process.join()
        self.assertEqual(process.exitcode, 1)
        lock.release()
        process = Process(target=self.second_lock)
        process.start()
        process.join()
        self.assertEqual(process.exitcode, 0)
