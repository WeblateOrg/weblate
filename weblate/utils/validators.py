# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import re
import sys
from gettext import c2py
from io import BytesIO
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator as EmailValidatorDjango
from django.core.validators import validate_ipv46_address
from django.utils.translation import gettext, gettext_lazy
from PIL import Image

from weblate.trans.util import cleanup_path

USERNAME_MATCHER = re.compile(r"^[\w@+-][\w.@+-]*$")

# Reject some suspicious e-mail addresses, based on checks enforced by Exim MTA
EMAIL_BLACKLIST = re.compile(r"^([./|]|.*([@%!`#&?]|/\.\./))")

# Matches Git condition on "name consists only of disallowed characters"
CRUD_RE = re.compile(r"^[.,;:<>\"'\\]+$")

ALLOWED_IMAGES = {"image/jpeg", "image/png", "image/apng", "image/gif", "image/webp"}

# File formats we do not accept on translation/glossary upload
FORBIDDEN_EXTENSIONS = {
    ".png",
    ".jpg",
    ".gif",
    ".svg",
    ".doc",
    ".rtf",
    ".xls",
    ".docx",
    ".py",
    ".js",
    ".exe",
    ".dll",
    ".zip",
}


def validate_re(value, groups=None, allow_empty=True):
    try:
        compiled = re.compile(value)
    except re.error as error:
        raise ValidationError(
            gettext("Compilation failed: {0}").format(error)
        ) from error
    if not allow_empty and compiled.match(""):
        raise ValidationError(
            gettext("The regular expression can not match an empty string.")
        )
    if not groups:
        return
    for group in groups:
        if group not in compiled.groupindex:
            raise ValidationError(
                gettext(
                    'Regular expression is missing named group "{0}", '
                    "the simplest way to define it is {1}."
                ).format(group, f"(?P<{group}>.*)")
            )


def validate_re_nonempty(value):
    return validate_re(value, allow_empty=False)


def validate_bitmap(value):
    """Validate bitmap, based on django.forms.fields.ImageField."""
    if value is None:
        return

    # Ensure we have image object and content type
    # Pretty much copy from django.forms.fields.ImageField:

    # We need to get a file object for Pillow. We might have a path or we
    # might have to read the data into memory.
    if hasattr(value, "temporary_file_path"):
        content = value.temporary_file_path()
    elif hasattr(value, "read"):
        content = BytesIO(value.read())
    else:
        content = BytesIO(value["content"])

    try:
        # load() could spot a truncated JPEG, but it loads the entire
        # image in memory, which is a DoS vector. See #3848 and #18520.
        image = Image.open(content)
        # verify() must be called immediately after the constructor.
        image.verify()

        # Pillow doesn't detect the MIME type of all formats. In those
        # cases, content_type will be None.
        value.file.content_type = Image.MIME.get(image.format)
    except Exception as exc:
        # Pillow doesn't recognize it as an image.
        raise ValidationError(
            gettext("Invalid image!"), code="invalid_image"
        ).with_traceback(sys.exc_info()[2]) from exc
    if hasattr(value.file, "seek") and callable(value.file.seek):
        value.file.seek(0)

    # Check image type
    if value.file.content_type not in ALLOWED_IMAGES:
        image.close()
        raise ValidationError(
            gettext("Unsupported image type: %s") % value.file.content_type
        )

    # Check dimensions
    width, height = image.size
    if width > 2000 or height > 2000:
        image.close()
        raise ValidationError(
            gettext("The image is too big, please crop or scale it down.")
        )

    image.close()


def clean_fullname(val):
    """Remove special characters from user full name."""
    if not val:
        return val
    val = val.strip()
    for i in range(0x20):
        val = val.replace(chr(i), "")
    return val


def validate_fullname(val):
    if val != clean_fullname(val):
        raise ValidationError(
            gettext("Please avoid using special characters in the full name.")
        )
    # Validates full name that would be rejected by Git
    if CRUD_RE.match(val):
        raise ValidationError(gettext("Name consists only of disallowed characters."))

    return val


def validate_file_extension(value):
    """Simple extension based validation for uploads."""
    ext = os.path.splitext(value.name)[1]
    if ext.lower() in FORBIDDEN_EXTENSIONS:
        raise ValidationError(gettext("Unsupported file format."))
    return value


def validate_username(value):
    if value.startswith("."):
        raise ValidationError(gettext("The username can not start with a full stop."))
    if not USERNAME_MATCHER.match(value):
        raise ValidationError(
            gettext(
                "Username may only contain letters, "
                "numbers or the following characters: @ . + - _"
            )
        )


class EmailValidator(EmailValidatorDjango):
    message = gettext_lazy("Enter a valid e-mail address.")

    def __call__(self, value):
        super().__call__(value)
        user_part = value.rsplit("@", 1)[0]
        if EMAIL_BLACKLIST.match(user_part):
            raise ValidationError(gettext("Enter a valid e-mail address."))
        if not re.match(settings.REGISTRATION_EMAIL_MATCH, value):
            raise ValidationError(gettext("This e-mail address is disallowed."))


validate_email = EmailValidator()


def validate_plural_formula(value):
    try:
        c2py(value if value else "0")
    except ValueError as error:
        raise ValidationError(
            gettext("Could not evaluate plural formula: {}").format(error)
        ) from error


def validate_filename(value):
    if "../" in value or "..\\" in value:
        raise ValidationError(
            gettext("The filename can not contain reference to a parent directory.")
        )
    if os.path.isabs(value):
        raise ValidationError(gettext("The filename can not be an absolute path."))

    cleaned = cleanup_path(value)
    if value != cleaned:
        raise ValidationError(
            gettext(
                "The filename should be as simple as possible. "
                "Maybe you want to use: {}"
            ).format(cleaned)
        )


def validate_slug(value):
    """Prohibits some special values."""
    # This one is used as wildcard in the URL for widgets and translate pages
    if value == "-":
        raise ValidationError(gettext("This name is prohibited"))


def validate_language_aliases(value):
    """Validates language aliases - comma separated semi colon values."""
    if not value:
        return
    for part in value.split(","):
        if part.count(":") != 1:
            raise ValidationError(gettext("Syntax error in language aliases."))


def validate_project_name(value):
    """Prohibits some special values."""
    if settings.PROJECT_NAME_RESTRICT_RE is not None and re.match(
        settings.PROJECT_NAME_RESTRICT_RE, value
    ):
        raise ValidationError(gettext("This name is prohibited"))


def validate_project_web(value):
    # Regular expression filtering
    if settings.PROJECT_WEB_RESTRICT_RE is not None and re.match(
        settings.PROJECT_WEB_RESTRICT_RE, value
    ):
        raise ValidationError(gettext("This URL is prohibited"))
    parsed = urlparse(value)
    hostname = parsed.hostname or ""
    hostname = hostname.lower()

    # Hostname filtering
    if any(
        hostname.endswith(blocked) for blocked in settings.PROJECT_WEB_RESTRICT_HOST
    ):
        raise ValidationError(gettext("This URL is prohibited"))

    # Numeric address filtering
    if settings.PROJECT_WEB_RESTRICT_NUMERIC:
        try:
            validate_ipv46_address(hostname)
        except ValidationError:
            pass
        else:
            raise ValidationError(gettext("This URL is prohibited"))
