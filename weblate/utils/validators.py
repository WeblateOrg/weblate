# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import base64
import binascii
import os
import re
import sys
from email.errors import HeaderDefect
from email.headerregistry import Address
from gettext import c2py  # type: ignore[attr-defined]
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import unquote, urlparse

import regex
from confusable_homoglyphs import confusables
from disposable_email_domains import blocklist
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator as EmailValidatorDjango
from django.core.validators import (
    URLValidator,
    validate_domain_name,
    validate_ipv46_address,
)
from django.db.models.fields.files import FieldFile
from django.http.request import validate_host
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext, gettext_lazy
from PIL import Image

from weblate.trans.util import cleanup_path
from weblate.utils.const import WEBHOOKS_SECRET_PREFIX
from weblate.utils.data import data_dir
from weblate.utils.errors import report_error
from weblate.utils.files import is_excluded, read_file_bytes
from weblate.utils.outbound import (
    is_allowlisted_hostname,
    validate_outbound_hostname,
    validate_outbound_url,
    validate_runtime_url,
)
from weblate.utils.regex import REGEX_TIMEOUT, compile_regex

if TYPE_CHECKING:
    from django.core.files.base import File
    from django.core.files.base import File as DjangoFile

USERNAME_MATCHER = re.compile(r"^[\w@+-][\w.@+-]*$")

# Reject some suspicious e-mail addresses, based on checks enforced by Exim MTA
EMAIL_BLACKLIST = re.compile(r"^([./|]|.*([@%!`#&?]|/\.\./))")

# Matches Git condition on "name consists only of disallowed characters"
CRUD_RE = re.compile(r"^[.,;:<>\"'\\]+$")
# Block certain characters from full name
FULL_NAME_RESTRICT = re.compile(r'[<>"]')

ALLOWED_IMAGES = {"image/jpeg", "image/png", "image/apng", "image/gif", "image/webp"}
PIL_FORMATS = ["png", "jpeg", "webp", "gif"]

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


def validate_re(
    value: str,
    groups: list[str] | tuple[str, ...] | None = None,
    *,
    allow_empty: bool = True,
) -> None:
    try:
        compiled = compile_regex(value)
    except regex.error as error:
        raise ValidationError(
            gettext("Compilation failed: {0}").format(error)
        ) from error
    try:
        matches_empty = compiled.match("", timeout=REGEX_TIMEOUT)
    except TimeoutError as error:
        report_error("Regular expression validation timed out")
        raise ValidationError(
            gettext(
                "The regular expression is too complex and took too long to evaluate."
            )
        ) from error
    if not allow_empty and matches_empty:
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


def validate_re_nonempty(value: str) -> None:
    validate_re(value, allow_empty=False)


def validate_upload_size(value: DjangoFile) -> None:
    if value.size > settings.ALLOWED_ASSET_SIZE:
        raise ValidationError(gettext("Uploaded file is too big."))


def validate_bitmap(
    value: FieldFile | File | None,
) -> None:
    """Validate bitmap, based on django.forms.fields.ImageField."""
    if value is None:
        return
    if not (isinstance(value, FieldFile) and getattr(value, "_committed", True)):
        validate_upload_size(value)

    # Ensure we have image object and content type
    # Pretty much copy from django.forms.fields.ImageField:

    content_target: Any = value
    content = BytesIO(read_file_bytes(value))

    try:
        # load() could spot a truncated JPEG, but it loads the entire
        # image in memory, which is a DoS vector. See #3848 and #18520.
        image = Image.open(content, formats=PIL_FORMATS)
        # verify() must be called immediately after the constructor.
        image.verify()

        # Pillow doesn't detect the MIME type of all formats. In those
        # cases, content_type will be None.
        content_type = Image.MIME.get(cast("str", image.format))
        if content_target is not None:
            content_target.content_type = content_type
    except Exception as exc:
        # Pillow doesn't recognize it as an image.
        raise ValidationError(
            gettext("The uploaded image was invalid."), code="invalid_image"
        ).with_traceback(sys.exc_info()[2]) from exc

    # Check image type
    if content_type not in ALLOWED_IMAGES:
        image.close()
        raise ValidationError(gettext("Unsupported image type: %s") % content_type)

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

    if confusables.is_dangerous(val):
        raise ValidationError(
            gettext("This name cannot be registered. Please choose a different one.")
        )

    # Validates full name that would be rejected by Git
    if CRUD_RE.match(val):
        raise ValidationError(gettext("Name consists only of disallowed characters."))

    if FULL_NAME_RESTRICT.match(val):
        raise ValidationError(gettext("Name contains disallowed characters."))

    return val


def validate_file_extension(value):
    """Validate file upload based on extension."""
    ext = os.path.splitext(value.name)[1]
    if ext.lower() in FORBIDDEN_EXTENSIONS:
        raise ValidationError(gettext("Unsupported file format."))
    return value


def validate_username(value) -> None:
    if value.startswith("."):
        raise ValidationError(gettext("The username can not start with a full stop."))
    if not USERNAME_MATCHER.match(value):
        raise ValidationError(
            gettext(
                "Username may only contain letters, "
                "numbers or the following characters: @ . + - _"
            )
        )
    if confusables.is_dangerous(value):
        raise ValidationError(
            gettext(
                "This username cannot be registered. Please choose a different one."
            )
        )


class EmailValidator(EmailValidatorDjango):
    message = gettext_lazy("Enter a valid e-mail address.")

    def __call__(self, value: str | None):
        super().__call__(value)
        if value is None:
            return
        user_part = value.rsplit("@", 1)[0]
        if EMAIL_BLACKLIST.match(user_part):
            raise ValidationError(gettext("Enter a valid e-mail address."))
        if not re.match(settings.REGISTRATION_EMAIL_MATCH, value):
            raise ValidationError(gettext("This e-mail address is disallowed."))
        try:
            address = Address(addr_spec=value)
        except HeaderDefect as error:
            raise ValidationError(
                gettext("Invalid e-mail address: {}").format(error)
            ) from error

        if (
            address.domain.lower().strip() in blocklist
            and not settings.REGISTRATION_ALLOW_DISPOSABLE_EMAILS
        ):
            raise ValidationError(gettext("Disposable e-mail domains are disallowed."))


validate_email = EmailValidator()


def validate_plural_formula(value) -> None:
    try:
        c2py(value or "0")
    except ValueError as error:
        raise ValidationError(
            gettext("Could not evaluate plural formula: {}").format(error)
        ) from error


def validate_filename(value: str, *, check_prohibited: bool = True) -> None:
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
    if check_prohibited and is_excluded(cleaned):
        raise ValidationError(gettext("The filename contains a prohibited folder."))


def validate_backup_path(value: str) -> None:
    # Lazily import borg as it pulls quite a lot of memory usage
    from borg.helpers import Location  # noqa: PLC0415

    try:
        loc = Location(value)
    except ValueError as err:
        raise ValidationError(str(err)) from err

    if loc.archive:
        msg = "No archive can be specified in backup location."
        raise ValidationError(msg)

    if loc.proto == "file":
        # Missing path
        if not loc.path:
            msg = "Backup location has to be an absolute path."
            raise ValidationError(msg)

        # The path is already normalized here
        path = Path(loc.path)

        # Restrict relative paths as the cwd might change
        if not path.is_absolute():
            msg = "Backup location has to be an absolute path."
            raise ValidationError(msg)

        # Restrict placing under Weblate backups as that will produce mess
        data_backups = Path(data_dir("backups"))
        if data_backups == path or data_backups in path.parents:
            msg = "Backup location should be outside Weblate backups in DATA_DIR."
            raise ValidationError(msg)


def validate_slug(value) -> None:
    """Prohibits some special values."""
    # This one is used as wildcard in the URL for widgets and translate pages
    if value == "-":
        raise ValidationError(gettext("This name is prohibited"))


def validate_language_aliases(value) -> None:
    """Validate language aliases - comma separated semi colon values."""
    if not value:
        return
    for part in value.split(","):
        if part.count(":") != 1:
            raise ValidationError(gettext("Syntax error in language aliases."))


def validate_project_name(value) -> None:
    """Prohibits some special values."""
    if settings.PROJECT_NAME_RESTRICT_RE is not None and re.match(
        settings.PROJECT_NAME_RESTRICT_RE, value
    ):
        raise ValidationError(gettext("This name is prohibited"))


def _validate_runtime_public_url(
    value: str,
    *,
    allow_private_targets: bool,
    allowed_domains: list[str] | tuple[str, ...] = (),
) -> None:
    hostname = urlparse(value).hostname or ""
    if allow_private_targets or is_allowlisted_hostname(hostname, allowed_domains):
        return

    try:
        validate_runtime_url(value, allow_private_targets=False)
    except ValidationError as error:
        if not isinstance(error.__cause__, OSError):
            raise


def is_project_web_allowlisted(project_slug: str | None) -> bool:
    if project_slug is None:
        return False

    normalized_slug = project_slug.lower()
    return normalized_slug in {
        slug.lower() for slug in settings.PROJECT_WEB_RESTRICT_ALLOWLIST
    }


def validate_project_web(value: str, *, project_slug: str | None = None) -> None:
    allowlisted = is_project_web_allowlisted(project_slug)

    # Regular expression filtering
    if (
        not allowlisted
        and settings.PROJECT_WEB_RESTRICT_RE is not None
        and re.match(settings.PROJECT_WEB_RESTRICT_RE, value)
    ):
        raise ValidationError(
            gettext("This URL is prohibited because it matches a restricted pattern.")
        )
    parsed = urlparse(value)
    hostname = parsed.hostname or ""
    hostname = hostname.lower()

    # Hostname filtering
    if not allowlisted and any(
        hostname.endswith(blocked) for blocked in settings.PROJECT_WEB_RESTRICT_HOST
    ):
        raise ValidationError(
            gettext("This URL is prohibited because it uses a restricted host.")
        )

    # Numeric address filtering
    if not allowlisted and settings.PROJECT_WEB_RESTRICT_NUMERIC:
        try:
            validate_ipv46_address(hostname)
        except ValidationError:
            pass
        else:
            raise ValidationError(
                gettext("This URL is prohibited because it uses a numeric IP address.")
            )

    _validate_runtime_public_url(
        value,
        allow_private_targets=allowlisted or not settings.PROJECT_WEB_RESTRICT_PRIVATE,
    )


def validate_webhook_secret_string(value: str) -> None:
    """Validate that the given string is a valid base64 encoded string."""
    if not value:
        return
    value = value.removeprefix(WEBHOOKS_SECRET_PREFIX)
    try:
        decoded = base64.b64decode(value)
    except binascii.Error as error:
        raise ValidationError(gettext("Invalid base64 encoded string")) from error

    if len(decoded) < 24:
        raise ValidationError(gettext("The provided secret is too short."))
    if len(decoded) > 64:
        raise ValidationError(gettext("The provided secret is too long."))


class WeblateURLValidator(URLValidator):
    """Validator for http and https URLs only."""

    schemes: list[str] = [  # noqa: RUF012
        "http",
        "https",
    ]

    def __call__(self, value: str | None) -> None:
        super().__call__(value)
        if value and confusables.is_dangerous(value):
            raise ValidationError(
                gettext("This website cannot be used. Please provide a different one.")
            )


PROFILE_URL_BLOCKED_EXTENSIONS = (
    ".7z",
    ".apk",
    ".appimage",
    ".bat",
    ".bin",
    ".bz2",
    ".cmd",
    ".deb",
    ".dmg",
    ".exe",
    ".gz",
    ".hta",
    ".iso",
    ".jar",
    ".js",
    ".lnk",
    ".msi",
    ".pkg",
    ".ps1",
    ".rar",
    ".reg",
    ".rpm",
    ".scr",
    ".sh",
    ".tar",
    ".vbs",
    ".wsf",
    ".xz",
    ".zip",
)

CODE_SITE_PROFILE_SEGMENT = re.compile(r"^~?[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")
CODE_SITE_REJECTED_TOP_LEVEL_SEGMENTS = {
    "-",
    "about",
    "admin",
    "api",
    "explore",
    "help",
    "login",
    "oauth",
    "org",
    "organizations",
    "projects",
    "session",
    "settings",
    "signup",
    "users",
}
FEDIVERSE_PROFILE_PREFIXES = {"accounts", "channel", "profile", "u", "users"}
FEDIVERSE_REJECTED_TOP_LEVEL_SEGMENTS = {
    "about",
    "admin",
    "api",
    "auth",
    "directory",
    "explore",
    "featured",
    "groups",
    "home",
    "interact",
    "login",
    "media",
    "notifications",
    "oauth",
    "objects",
    "posts",
    "public",
    "search",
    "settings",
    "share",
    "tags",
    "users",
    "webfinger",
}
FEDIVERSE_PROFILE_SEGMENT = re.compile(r"^@?[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")
FEDIVERSE_HANDLE_SEGMENT = re.compile(
    r"^@[A-Za-z0-9][A-Za-z0-9_.-]{0,254}(?:@[A-Za-z0-9.-]+)?$"
)
FEDIVERSE_PROFILE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_public_profile_url(
    value: str | None,
    *,
    credentials_message: str,
) -> None:
    """Reject unsafe public profile URLs before path-shape checks."""
    if not value:
        return

    parsed = urlparse(value)
    if parsed.username or parsed.password:
        raise ValidationError(credentials_message)

    validate_outbound_url(value, allow_private_targets=False)


def _has_blocked_profile_url_extension(value: str) -> bool:
    path = unquote(urlparse(value).path).lower().rstrip("/")
    return path.endswith(PROFILE_URL_BLOCKED_EXTENSIONS)


def _validate_profile_like_url(
    value: str | None,
    *,
    credentials_message: str,
    blocked_extension_message: str,
) -> None:
    """Validate common profile/contact URL safety checks."""
    _validate_public_profile_url(value, credentials_message=credentials_message)
    if value and _has_blocked_profile_url_extension(value):
        raise ValidationError(gettext(blocked_extension_message))


def _get_profile_path_segments(value: str) -> list[str]:
    parsed = urlparse(value)
    if parsed.query or parsed.fragment:
        return []
    return [
        segment for segment in unquote(parsed.path).strip("/").split("/") if segment
    ]


def validate_profile_url(value: str | None) -> None:
    """Reject unsafe public profile URLs."""
    _validate_profile_like_url(
        value,
        credentials_message=gettext(
            "Profile URL cannot include username or password credentials."
        ),
        blocked_extension_message=(
            "Profile URL should link to a profile page, "
            "not directly to a file download."
        ),
    )


def validate_code_site_url(value: str | None) -> None:
    """Reject URLs not matching common code hosting profile shapes."""
    _validate_profile_like_url(
        value,
        credentials_message=gettext(
            "Profile URL cannot include username or password credentials."
        ),
        blocked_extension_message=(
            "Profile URL should link to a profile page, "
            "not directly to a file download."
        ),
    )
    if not value:
        return

    segments = _get_profile_path_segments(value)
    is_profile_like = (
        len(segments) == 1
        and segments[0] not in CODE_SITE_REJECTED_TOP_LEVEL_SEGMENTS
        and CODE_SITE_PROFILE_SEGMENT.match(segments[0])
    )
    is_repository_like = (
        len(segments) >= 2
        and segments[0] not in CODE_SITE_REJECTED_TOP_LEVEL_SEGMENTS
        and all(segment != "-" for segment in segments)
        and all(CODE_SITE_PROFILE_SEGMENT.match(segment) for segment in segments)
    )
    if is_profile_like:
        return
    if is_repository_like:
        return
    if len(segments) == 3 and segments[:2] == ["-", "u"] and segments[2].isdigit():
        return

    raise ValidationError(
        gettext(
            "Code site URL should link to a user profile or repository page on a "
            "code hosting site."
        )
    )


def validate_contact_url(value: str | None) -> None:
    """Reject unsafe public contact URLs."""
    _validate_profile_like_url(
        value,
        credentials_message=gettext(
            "Contact URL cannot include username or password credentials."
        ),
        blocked_extension_message=(
            "Contact URL should link to a contact or profile page, "
            "not directly to a file download."
        ),
    )


def validate_fediverse_url(value: str | None) -> None:
    """Reject URLs not matching common Fediverse profile shapes."""
    validate_profile_url(value)
    if not value:
        return

    segments = _get_profile_path_segments(value)
    if len(segments) == 1 and FEDIVERSE_HANDLE_SEGMENT.match(segments[0]):
        return
    if (
        len(segments) == 1
        and segments[0] not in FEDIVERSE_REJECTED_TOP_LEVEL_SEGMENTS
        and "." not in segments[0]
        and FEDIVERSE_PROFILE_SEGMENT.match(segments[0])
    ):
        return
    if (
        len(segments) == 2
        and segments[0] in FEDIVERSE_PROFILE_PREFIXES
        and (segments[0] != "profile" or "." not in segments[1])
        and FEDIVERSE_PROFILE_SEGMENT.match(segments[1])
    ):
        return
    if (
        len(segments) == 2
        and segments[0] == "web"
        and FEDIVERSE_HANDLE_SEGMENT.match(segments[1])
    ):
        return
    if (
        len(segments) == 2
        and segments[0] == "people"
        and FEDIVERSE_PROFILE_ID.match(segments[1])
    ):
        return

    raise ValidationError(
        gettext("Fediverse URL should link to a Fediverse user profile.")
    )


def validate_asset_url(value: str) -> None:
    WeblateURLValidator()(value)
    if not validate_host(
        urlparse(value).hostname or "", settings.ALLOWED_ASSET_DOMAINS
    ):
        raise ValidationError(gettext("URL domain is not allowed."))


def validate_machinery_url(value: str, *, allow_private_targets: bool = True) -> None:
    WeblateServiceURLValidator()(value)
    validate_outbound_url(
        value,
        allow_private_targets=allow_private_targets,
        allowed_domains=settings.ALLOWED_MACHINERY_DOMAINS,
    )


def validate_machinery_hostname(
    value: str, *, allow_private_targets: bool = True
) -> None:
    validate_outbound_hostname(
        value,
        allow_private_targets=allow_private_targets,
        allowed_domains=settings.ALLOWED_MACHINERY_DOMAINS,
    )


def validate_webhook_url(value: str) -> None:
    WeblateServiceURLValidator()(value)
    validate_outbound_url(
        value,
        allow_private_targets=not settings.WEBHOOK_RESTRICT_PRIVATE,
        allowed_domains=settings.WEBHOOK_PRIVATE_ALLOWLIST,
    )
    _validate_runtime_public_url(
        value,
        allow_private_targets=not settings.WEBHOOK_RESTRICT_PRIVATE,
        allowed_domains=settings.WEBHOOK_PRIVATE_ALLOWLIST,
    )


class WeblateEditorURLValidator(WeblateURLValidator):
    schemes: list[str] = [  # noqa: RUF012
        "editor",
        "netbeans",
        "txmt",
        "pycharm",
        "phpstorm",
        "idea",
        "jetbrains",
    ]

    regex = re.compile(
        r"^(?:[a-z0-9.+-]*)://"  # scheme is validated separately
        r"(?:" + WeblateURLValidator.hostname_re + ")"
        r"(?:[/?#][^\s]*)?"  # resource path
        r"\Z",
        re.IGNORECASE,
    )


class WeblateServiceURLValidator(WeblateURLValidator):
    """
    Validator allowing local URLs like http://domain:5000.

    This is useful for using dockerized services.
    """

    host_re = f"({WeblateURLValidator.hostname_re}{WeblateURLValidator.domain_re}{WeblateURLValidator.tld_re}|{WeblateURLValidator.hostname_re})"
    regex = re.compile(
        r"^(?:[a-z0-9.+-]*)://"  # scheme is validated separately
        r"(?:[^\s:@/]+(?::[^\s:@/]*)?@)?"  # user:pass authentication
        r"(?:"
        + WeblateURLValidator.ipv4_re
        + "|"
        + WeblateURLValidator.ipv6_re
        + "|"
        + host_re
        + ")"
        r"(?::[0-9]{1,5})?"  # port
        r"(?:[/?#][^\s]*)?"  # resource path
        r"\Z",
        re.IGNORECASE,
    )


def validate_repo_url(url: str) -> None:
    normalized_url = url
    parsed = urlparse(normalized_url)
    if not parsed.scheme:
        if os.path.isabs(url) or url.startswith(("./", "../")):
            if "file" not in settings.VCS_ALLOW_SCHEMES:
                raise ValidationError(
                    gettext("Fetching VCS repository using %s is not allowed.") % "file"
                )
            return
        # assume all links without schema are ssh links
        normalized_url = f"ssh://{url}"
        try:
            parsed = urlparse(normalized_url)
        except ValueError as error:
            raise ValidationError(
                gettext("Could not parse URL: {}").format(error)
            ) from error

    # Allow Weblate internal URLs
    if parsed.scheme in {"weblate", "local"}:
        return

    # Filter out schemes early
    if parsed.scheme not in settings.VCS_ALLOW_SCHEMES:
        raise ValidationError(
            gettext("Fetching VCS repository using %s is not allowed.") % parsed.scheme
        )

    # URL validation using for http (the URL validator is too strict to handle others)
    if parsed.scheme in {"http", "https"}:
        validator = URLValidator(schemes=list(settings.VCS_ALLOW_SCHEMES))
        validator(normalized_url)

    hostname = parsed.hostname

    if parsed.scheme == "file":
        if hostname is None:
            return
        raise ValidationError(gettext("Could not parse URL."))

    if hostname is None:
        raise ValidationError(gettext("Could not parse URL."))

    # Filter hosts if configured
    if settings.VCS_ALLOW_HOSTS and hostname not in settings.VCS_ALLOW_HOSTS:
        raise ValidationError(
            gettext("Fetching VCS repository from %s is not allowed.") % hostname
        )

    allowlisted = hostname in settings.VCS_ALLOW_HOSTS
    allow_private_targets = allowlisted or not settings.VCS_RESTRICT_PRIVATE

    validate_outbound_url(
        normalized_url,
        allow_private_targets=allow_private_targets,
    )
    _validate_runtime_public_url(
        normalized_url,
        allow_private_targets=allow_private_targets,
    )


@deconstructible
class DomainOrIPValidator:
    def __call__(self, value: str):
        try:
            validate_ipv46_address(value)
        except ValidationError:
            try:
                # Note: Django's DomainNameValidator (or validate_domain_name function)
                # does not accept IP addresses as valid domain names, which is what we want.
                validate_domain_name(value)
            except ValidationError:
                # If both fail, raise a final ValidationError
                raise ValidationError(
                    gettext("Enter a valid domain name or IP address."),
                    code="invalid_domain_or_ip",
                ) from None
