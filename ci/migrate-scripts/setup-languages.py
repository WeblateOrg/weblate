# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Cleanup languages for fixture import."""

from weblate.lang.models import Language

Language.objects.all().delete()
