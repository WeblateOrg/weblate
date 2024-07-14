# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from django.core.exceptions import ValidationError
from django.utils.translation import gettext

from weblate.fonts.utils import get_font_name


def validate_font(value):
    """Validate font upload based on extension."""
    ext = os.path.splitext(value.name)[1]
    if ext.lower() not in {".ttf", ".otf"}:
        raise ValidationError(gettext("Unsupported file format."))
    try:
        get_font_name(value)
    except OSError as error:
        raise ValidationError(gettext("Unsupported file format.")) from error
    return value
