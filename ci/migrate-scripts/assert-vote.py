# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Assertion for votes migration."""

from weblate.trans.models import Vote

Vote.objects.get(value=1)
