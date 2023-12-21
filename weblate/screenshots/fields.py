# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db.models import ImageField

from weblate.utils.validators import validate_bitmap


class ScreenshotField(ImageField):
    """File field which forces certain image types."""

    default_validators = [validate_bitmap]
