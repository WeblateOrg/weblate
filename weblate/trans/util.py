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

import locale
import os
import sys
from urllib.parse import urlparse

from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.shortcuts import render as django_render
from django.shortcuts import resolve_url
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from lxml import etree
from translate.misc.multistring import multistring
from translate.storage.placeables.lisa import parse_xliff, strelem_to_xml

from weblate.utils.data import data_dir

PLURAL_SEPARATOR = "\x1e\x1e"
LOCALE_SETUP = True

PRIORITY_CHOICES = (
    (60, gettext_lazy("Very high")),
    (80, gettext_lazy("High")),
    (100, gettext_lazy("Medium")),
    (120, gettext_lazy("Low")),
    (140, gettext_lazy("Very low")),
)

# Initialize to sane locales for strxfrm
try:
    locale.setlocale(locale.LC_ALL, ("C", "UTF-8"))
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, ("en_US", "UTF-8"))
    except locale.Error:
        LOCALE_SETUP = False


def is_plural(text):
    """Check whether string is plural form."""
    return text.find(PLURAL_SEPARATOR) != -1


def split_plural(text):
    return text.split(PLURAL_SEPARATOR)


def join_plural(text):
    return PLURAL_SEPARATOR.join(text)


def get_string(text):
    """Return correctly formatted string from ttkit unit data."""
    # Check for null target (happens with XLIFF)
    if text is None:
        return ""
    if isinstance(text, multistring):
        return join_plural(get_string(str(item)) for item in text.strings)
    if isinstance(text, str):
        # Remove possible surrogates in the string. There doesn't seem to be
        # a cheap way to detect this, so do the conversion in both cases. In
        # case of failure, this at least fails when parsing the file instead
        # being that later when inserting the data to the database.
        return text.encode("utf-16", "surrogatepass").decode("utf-16")
    # We might get integer or float in some formats
    return str(text)


def is_repo_link(val):
    """Check whether repository is just a link for other one."""
    return val.startswith("weblate://")


def get_distinct_translations(units):
    """Return list of distinct translations.

    It should be possible to use distinct('target') since Django 1.4, but it is not
    supported with MySQL, so let's emulate that based on presumption we won't get too
    many results.
    """
    targets = {}
    result = []
    for unit in units:
        if unit.target in targets:
            continue
        targets[unit.target] = 1
        result.append(unit)
    return result


def translation_percent(translated, total, zero_complete=True):
    """Return translation percentage."""
    if total == 0:
        return 100.0 if zero_complete else 0.0
    if total is None:
        return 0.0
    perc = (1000 * translated // total) / 10.0
    # Avoid displaying misleading rounded 0.0% or 100.0%
    if perc == 0.0 and translated != 0:
        return 0.1
    if perc == 100.0 and translated < total:
        return 99.9
    return perc


def get_clean_env(extra=None):
    """Return cleaned up environment for subprocess execution."""
    environ = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HOME": data_dir("home"),
        "PATH": "/bin:/usr/bin:/usr/local/bin",
    }
    if extra is not None:
        environ.update(extra)
    variables = (
        # Keep PATH setup
        "PATH",
        # Keep Python search path
        "PYTHONPATH",
        # Keep linker configuration
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        # Needed by Git on Windows
        "SystemRoot",
        # Pass proxy configuration
        "http_proxy",
        "https_proxy",
        "HTTPS_PROXY",
        "NO_PROXY",
        # below two are nedded for openshift3 deployment,
        # where nss_wrapper is used
        # more on the topic on below link:
        # https://docs.openshift.com/enterprise/3.2/creating_images/guidelines.html
        "NSS_WRAPPER_GROUP",
        "NSS_WRAPPER_PASSWD",
    )
    for var in variables:
        if var in os.environ:
            environ[var] = os.environ[var]
    # Extend path to include virtualenv, avoid insert already existing ones to
    # not break existing ordering (for example PATH injection used in tests)
    venv_path = os.path.join(sys.exec_prefix, "bin")
    if venv_path not in environ["PATH"]:
        environ["PATH"] = "{}:{}".format(venv_path, environ["PATH"])
    return environ


def cleanup_repo_url(url, text=None):
    """Remove credentials from repository URL."""
    if text is None:
        text = url
    try:
        parsed = urlparse(url)
    except ValueError:
        # The URL can not be parsed, so avoid stripping
        return text
    if parsed.username and parsed.password:
        return text.replace(f"{parsed.username}:{parsed.password}@", "")
    if parsed.username:
        return text.replace(f"{parsed.username}@", "")
    return text


def redirect_param(location, params, *args, **kwargs):
    """Redirect to a URL with parameters."""
    return HttpResponseRedirect(resolve_url(location, *args, **kwargs) + params)


def cleanup_path(path):
    """Remove leading ./ or / from path."""
    if not path:
        return path

    # interpret absolute pathname as relative, remove drive letter or
    # UNC path, redundant separators, "." and ".." components.
    path = os.path.splitdrive(path)[1]
    invalid_path_parts = ("", os.path.curdir, os.path.pardir)
    path = os.path.sep.join(
        x for x in path.split(os.path.sep) if x not in invalid_path_parts
    )

    return os.path.normpath(path)


def get_project_description(project):
    """Return verbose description for project translation."""
    # Cache the count as it might be expensive to calculate (it pull
    # all project stats) and there is no need to always have up to date
    # count here
    cache_key = f"project-lang-count-{project.id}"
    count = cache.get(cache_key)
    if count is None:
        count = project.stats.languages
        cache.set(cache_key, count, 6 * 3600)
    return _(
        "{0} is translated into {1} languages using Weblate. "
        "Join the translation or start translating your own project."
    ).format(project, count)


def render(request, template, context=None, status=None):
    """Wrapper around Django render to extend context."""
    if context is None:
        context = {}
    if "project" in context and context["project"] is not None:
        context["description"] = get_project_description(context["project"])
    return django_render(request, template, context, status=status)


def path_separator(path):
    """Alway use / as path separator for consistency."""
    if os.path.sep != "/":
        return path.replace(os.path.sep, "/")
    return path


def sort_unicode(choices, key):
    """Unicode aware sorting if available."""
    return sorted(choices, key=lambda tup: locale.strxfrm(key(tup)))


def sort_choices(choices):
    """Sort choices alphabetically."""
    return sort_unicode(choices, lambda tup: tup[1])


def sort_objects(objects):
    """Sort objects alphabetically."""
    return sort_unicode(objects, str)


def redirect_next(next_url, fallback):
    """Redirect to next URL from request after validating it."""
    if (
        next_url is None
        or not url_has_allowed_host_and_scheme(next_url, allowed_hosts=None)
        or not next_url.startswith("/")
    ):
        return redirect(fallback)
    return HttpResponseRedirect(next_url)


def xliff_string_to_rich(string):
    """Convert XLIFF string to StringElement.

    Transform a string containing XLIFF placeholders as XML into a rich content
    (StringElement)
    """
    if isinstance(string, list):
        return [parse_xliff(s) for s in string]
    return [parse_xliff(string)]


def rich_to_xliff_string(string_elements):
    """Convert StringElement to XLIFF string.

    Transform rich content (StringElement) into a string with placeholder kept as XML
    """
    # Create dummy root element
    xml = etree.Element("e")
    for string_element in string_elements:
        # Inject placeable from translate-toolkit
        strelem_to_xml(xml, string_element)

    # Remove any possible namespace
    for child in xml:
        if child.tag.startswith("{"):
            child.tag = child.tag[child.tag.index("}") + 1 :]
    etree.cleanup_namespaces(xml)

    # Convert to string
    string_xml = etree.tostring(xml, encoding="unicode")

    # Strip dummy root element
    return string_xml[3:][:-4]


def get_state_css(unit):
    """Return state flags."""
    flags = []

    if unit.fuzzy:
        flags.append("state-need-edit")
    elif not unit.translated:
        flags.append("state-empty")
    elif unit.readonly:
        flags.append("state-readonly")
    elif unit.approved:
        flags.append("state-approved")
    elif unit.translated:
        flags.append("state-translated")

    if unit.has_failing_check:
        flags.append("state-check")
    if unit.dismissed_checks:
        flags.append("state-dismissed-check")
    if unit.has_comment:
        flags.append("state-comment")
    if unit.has_suggestion:
        flags.append("state-suggest")

    return flags


def check_upload_method_permissions(user, translation, method: str):
    """Check whether user has permission to perform upload method."""
    if method == "source":
        return (
            translation.is_source
            and user.has_perm("upload.perform", translation)
            and hasattr(translation.component.file_format_cls, "update_bilingual")
        )
    if method == "add":
        return user.has_perm("unit.add", translation)
    if method in ("translate", "fuzzy"):
        return user.has_perm("unit.edit", translation)
    if method == "suggest":
        return user.has_perm("suggestion.add", translation)
    if method == "approve":
        return user.has_perm("unit.review", translation)
    if method == "replace":
        return translation.filename and user.has_perm("component.edit", translation)
    raise ValueError(f"Invalid method: {method}")
