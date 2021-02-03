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
"""Hardcoded length limitations."""

# Component name and slug length
COMPONENT_NAME_LENGTH = 100

# Project name and slug length
PROJECT_NAME_LENGTH = 60

# Repository length
REPO_LENGTH = 200

# Maximal length of filename or mask
FILENAME_LENGTH = 400

# User model length
# Note: This is currently limited by 192 to allow index on MySQL
FULLNAME_LENGTH = 150
USERNAME_LENGTH = 150
EMAIL_LENGTH = 190

# Language
LANGUAGE_CODE_LENGTH = 50
LANGUAGE_NAME_LENGTH = 100
