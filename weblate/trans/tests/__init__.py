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

from weblate.trans.test_chars_checks import BeginNewlineCheckTest
from weblate.trans.test_chars_checks import EndNewlineCheckTest
from weblate.trans.test_chars_checks import BeginSpaceCheckTest
from weblate.trans.test_chars_checks import EndSpaceCheckTest
from weblate.trans.test_chars_checks import EndStopCheckTest
from weblate.trans.test_chars_checks import EndColonCheckTest
from weblate.trans.test_chars_checks import EndQuestionCheckTest
from weblate.trans.test_chars_checks import EndExclamationCheckTest
from weblate.trans.test_chars_checks import EndEllipsisCheckTest
from weblate.trans.test_chars_checks import NewlineCountingCheckTest
from weblate.trans.test_chars_checks import ZeroWidthSpaceCheckTest
from weblate.trans.test_checks import CheckTestCase
from weblate.trans.test_commands import ImportTest
from weblate.trans.test_commands import PeriodicTest
from weblate.trans.test_commands import CheckGitTest
from weblate.trans.test_consistency_checks import PluralsCheckTest
from weblate.trans.test_diff import DiffTest
from weblate.trans.test_exports import ExportsViewTest
from weblate.trans.test_format_checks import PythonFormatCheckTest
from weblate.trans.test_format_checks import PHPFormatCheckTest
from weblate.trans.test_format_checks import CFormatCheckTest
from weblate.trans.test_hooks import HooksViewTest
from weblate.trans.test_markup_checks import BBCodeCheckTest
from weblate.trans.test_markup_checks import XMLTagsCheckTest
from weblate.trans.test_models import RepoTestCase
from weblate.trans.test_models import ProjectTest
from weblate.trans.test_models import SubProjectTest
from weblate.trans.test_models import TranslationTest
from weblate.trans.test_same_checks import SameCheckTest
from weblate.trans.test_source_checks import OptionalPluralCheckTest
from weblate.trans.test_source_checks import EllipsisCheckTest
from weblate.trans.test_views import ViewTestCase
from weblate.trans.test_views import BasicViewTest
from weblate.trans.test_views import EditTest
from weblate.trans.test_views import WidgetsTest
