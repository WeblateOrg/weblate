#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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


from contextlib import contextmanager
from locale import LC_ALL, Error, getlocale, setlocale


@contextmanager
def c_locale():
    """Context to execute something in C locale."""
    # List of locales to reset
    locales = [("C", "UTF-8"), ("en_US", "UTF-8"), ""]
    try:
        # If locale is set, insert it to the top
        currlocale = getlocale()
        if currlocale[0]:
            locales.insert(0, currlocale)
    except Error:
        pass
    # Set C locale for the execution
    setlocale(LC_ALL, "C")
    try:
        # Here the context gets executed
        yield
    finally:
        for currlocale in locales:
            try:
                setlocale(LC_ALL, currlocale)
            except Error:
                continue
            # If getlocale returns None, the locale is most
            # likely not working properly
            if getlocale()[0]:
                break
