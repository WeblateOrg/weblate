# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.core.validators import validate_image_file_extension
from django.db.models import ImageField

from weblate.utils.validators import validate_bitmap


class ScreenshotField(ImageField):
    """File field which forces certain image types."""

    # ruff: ignore[mutable-class-default]
    default_validators = [validate_image_file_extension, validate_bitmap]
