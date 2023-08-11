# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Hardcoded length limitations."""

# Component name and slug length
COMPONENT_NAME_LENGTH = 100

# Project name and slug length
PROJECT_NAME_LENGTH = 60

# Repository length
REPO_LENGTH = 300
BRANCH_LENGTH = 200

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

# Variant
VARIANT_REGEX_LENGTH = 190
# Needed for unique index on MySQL
VARIANT_KEY_LENGTH = 576

# Maximal categories depth
CATEGORY_DEPTH = 3
