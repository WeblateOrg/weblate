# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db.models import CharField

from weblate.utils.validators import validate_re


class RegexField(CharField):
    default_validators = [validate_re]
