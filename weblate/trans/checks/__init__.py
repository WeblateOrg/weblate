# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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

# Compatibility imports
from weblate.trans.checks.same import SameCheck
from weblate.trans.checks.chars import BeginNewlineCheck
from weblate.trans.checks.chars import EndNewlineCheck
from weblate.trans.checks.chars import BeginSpaceCheck
from weblate.trans.checks.chars import EndSpaceCheck
from weblate.trans.checks.chars import EndStopCheck
from weblate.trans.checks.chars import EndColonCheck
from weblate.trans.checks.chars import EndQuestionCheck
from weblate.trans.checks.chars import EndExclamationCheck
from weblate.trans.checks.chars import EndEllipsisCheck
from weblate.trans.checks.format import PythonFormatCheck
from weblate.trans.checks.format import PHPFormatCheck
from weblate.trans.checks.format import CFormatCheck
from weblate.trans.checks.consistency import PluralsCheck
from weblate.trans.checks.consistency import ConsistencyCheck
from weblate.trans.checks.consistency import DirectionCheck
from weblate.trans.checks.chars import NewlineCountingCheck
from weblate.trans.checks.markup import BBCodeCheck
from weblate.trans.checks.chars import ZeroWidthSpaceCheck
from weblate.trans.checks.markup import XMLTagsCheck
from weblate.trans.checks.source import OptionalPluralCheck
from weblate.trans.checks.source import EllipsisCheck


# Initialize checks list
from weblate.trans import appsettings
from django.core.exceptions import ImproperlyConfigured
CHECKS = {}
for path in appsettings.CHECK_LIST:
    i = path.rfind('.')
    module, attr = path[:i], path[i + 1:]
    try:
        mod = __import__(module, {}, {}, [attr])
    except ImportError as e:
        raise ImproperlyConfigured(
            'Error importing translation check module %s: "%s"' %
            (module, e)
        )
    try:
        cls = getattr(mod, attr)
    except AttributeError:
        raise ImproperlyConfigured(
            'Module "%s" does not define a "%s" callable check' %
            (module, attr)
        )
    CHECKS[cls.check_id] = cls()
