#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import gettext
import os
import re
import sys
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email as validate_email_django
from django.utils.translation import gettext as _
from PIL import Image

from weblate.trans.util import cleanup_path

USERNAME_MATCHER = re.compile(r"^[\w@+-][\w.@+-]*$")

# Reject some suspicious e-mail addresses, based on checks enforced by Exim MTA
EMAIL_BLACKLIST = re.compile(r"^([./|]|.*([@%!`#&?]|/\.\./))")

# Matches Git condition on "name consists only of disallowed characters"
CRUD_RE = re.compile(r"^[.,;:<>\"'\\]+$")

ALLOWED_IMAGES = {"image/jpeg", "image/png", "image/apng", "image/gif"}

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
        raise ValidationError(_("Compilation failed: {0}").format(error))
    if not allow_empty and compiled.match(""):
        raise ValidationError(
            _("The regular expression can not match an empty string.")
        )
    if not groups:
        return
    for group in groups:
        if group not in compiled.groupindex:
            raise ValidationError(
                _(
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
    else:
        if hasattr(value, "read"):
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
    except Exception:
        # Pillow doesn't recognize it as an image.
        raise ValidationError(_("Invalid image!"), code="invalid_image").with_traceback(
            sys.exc_info()[2]
        )
    if hasattr(value.file, "seek") and callable(value.file.seek):
        value.file.seek(0)

    # Check image type
    if value.file.content_type not in ALLOWED_IMAGES:
        image.close()
        raise ValidationError(_("Unsupported image type: %s") % value.file.content_type)

    # Check dimensions
    width, height = image.size
    if width > 2000 or height > 2000:
        image.close()
        raise ValidationError(_("The image is too big, please crop or scale it down."))

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
            _("Please avoid using special characters in the full name.")
        )
    # Validates full name that would be rejected by Git
    if CRUD_RE.match(val):
        raise ValidationError(_("Name consists only of disallowed characters."))

    return val


def validate_file_extension(value):
    """Simple extension based validation for uploads."""
    ext = os.path.splitext(value.name)[1]
    if ext.lower() in FORBIDDEN_EXTENSIONS:
        raise ValidationError(_("Unsupported file format."))
    return value


def validate_username(value):
    if value.startswith("."):
        raise ValidationError(_("The username can not start with a full stop."))
    if not USERNAME_MATCHER.match(value):
        raise ValidationError(
            _(
                "Username may only contain letters, "
                "numbers or the following characters: @ . + - _"
            )
        )


def validate_email(value):
    try:
        validate_email_django(value)
    except ValidationError:
        raise ValidationError(_("Enter a valid e-mail address."))
    user_part = value.rsplit("@", 1)[0]
    if EMAIL_BLACKLIST.match(user_part):
        raise ValidationError(_("Enter a valid e-mail address."))
    if not re.match(settings.REGISTRATION_EMAIL_MATCH, value):
        raise ValidationError(_("This e-mail address is disallowed."))


def validate_plural_formula(value):
    try:
        gettext.c2py(value if value else "0")
    except ValueError as error:
        raise ValidationError(_("Could not evaluate plural formula: {}").format(error))


def validate_filename(value):
    if "../" in value or "..\\" in value:
        raise ValidationError(
            _("The filename can not contain reference to a parent directory.")
        )
    if os.path.isabs(value):
        raise ValidationError(_("The filename can not be an absolute path."))

    cleaned = cleanup_path(value)
    if value != cleaned:
        raise ValidationError(
            _(
                "The filename should be as simple as possible. "
                "Maybe you want to use: {}"
            ).format(cleaned)
        )


def validate_slug(value):
    """Prohibits some special values."""
    # This one is used as wildcard in the URL for widgets and translate pages
    if value == "-":
        raise ValidationError(_("This name is prohibited"))


def validate_language_aliases(value):
    """Validates language aliases - comma separated semi colon values."""
    if not value:
        return
    for part in value.split(","):
        if part.count(":") != 1:
            raise ValidationError(_("Syntax error in language aliases."))
