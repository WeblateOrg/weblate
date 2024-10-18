# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The following characters are considered problematic for CSV files
# - due to how they are interpreted by Excel
# - due to the risk of CSV injection attacks
PROHIBITED_INITIAL_CHARS = {"=", "+", "-", "@", "|", "%"}
