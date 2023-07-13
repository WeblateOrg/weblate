# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.utils.classloader import ClassLoader

# Initialize machinery list
# TODO: Drop in Weblate 5.1
MACHINE_TRANSLATION_SERVICES = ClassLoader("MT_SERVICES", construct=False)
