# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys
from pathlib import Path

import sphinx.builders.gettext
from matplotlib import font_manager
from sphinx.util.tags import Tags

# -- Path setup --------------------------------------------------------------

file_dir = Path(__file__).parent.resolve()
font_locations = (
    "weblate/static/js/vendor/fonts/font-source/",
    "weblate/static/vendor/font-kurinto/",
)

weblate_dir = file_dir.parent
# Our extension
sys.path.append(str(file_dir / "_ext"))
# Weblate code
sys.path.append(str(weblate_dir))


class WeblateTags(Tags):
    def eval_condition(self, condition):
        # Exclude blocks marked as not gettext
        return condition != "not gettext"


def setup(app) -> None:
    # Monkey path gettext build tags handling, this is workaround until
    # https://github.com/sphinx-doc/sphinx/issues/13307 is addressed.
    sphinx.builders.gettext.I18nTags = WeblateTags
    # Used in Sphinx docs, needed for intersphinx links to it
    app.add_object_type(
        "confval",
        "confval",
        objname="configuration value",
        indextemplate="pair: %s; configuration value",
    )

    font_dirs: list[str] = []

    for font_location in font_locations:
        font_dir = weblate_dir / font_location
        if not font_dir.is_dir():
            msg = f"Font directory not found: {font_dir}"
            raise NotADirectoryError(msg)
        font_dirs.append(str(font_dir))

    font_files = font_manager.findSystemFonts(fontpaths=font_dirs)

    for font_file in font_files:
        font_manager.fontManager.addfont(font_file)


# -- Project information -----------------------------------------------------

project = "Weblate"
project_copyright = "Michal Čihař"
author = "Michal Čihař"

# The full version, including alpha/beta/rc tags
release = "5.13.2"

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "djangodocs",
    "sphinxcontrib.httpdomain",
    "sphinx.ext.autodoc",
    "sphinx.ext.graphviz",
    "sphinx.ext.intersphinx",
    "sphinx-jsonschema",
    "sphinx_copybutton",
    "sphinxext.opengraph",
    "sphinx_reredirects",
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "devel/reporting-example.rst",
]

ogp_social_cards = {
    "image": "../weblate/static/logo-1024.png",
    "line_color": "#144d3f",
    "site_url": "docs.weblate.org",
    "font": [
        "Source Sans 3",
        "Kurinto Sans JP",
        "Kurinto Sans KR",
        "Kurinto Sans SC",
        "Kurinto Sans TC",
        "Kurinto Sans",
    ],
}
ogp_custom_meta_tags = (
    '<meta property="fb:app_id" content="741121112629028" />',
    '<meta property="fb:page_id" content="371217713079025" />',
    '<meta name="twitter:site" content="@WeblateOrg" />',
)

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
# html_theme = "sphinx_rtd_theme"
html_theme = "furo"

# Define the canonical URL if you are using a custom domain on Read the Docs
html_baseurl = os.environ.get("READTHEDOCS_CANONICAL_URL", "")

# Tell Jinja2 templates the build is running on Read the Docs
if os.environ.get("READTHEDOCS", "") == "True":
    if "html_context" not in globals():
        html_context = {}
    html_context["READTHEDOCS"] = True

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["../weblate/static/"]

html_logo = "images/logo-text.svg"


html_theme_options = {
    "source_repository": "https://github.com/WeblateOrg/weblate/",
    "source_branch": "main",
    "source_directory": "docs/",
    "sidebar_hide_name": True,
    "dark_css_variables": {
        "font-stack": '"Source Sans 3", sans-serif',
        "font-stack--monospace": '"Source Code Pro", monospace',
        "color-brand-primary": "#1fa385",
        "color-brand-content": "#1fa385",
    },
    "light_css_variables": {
        "font-stack": '"Source Sans 3", sans-serif',
        "font-stack--monospace": '"Source Code Pro", monospace',
        "color-brand-primary": "#1fa385",
        "color-brand-content": "#1fa385",
    },
}

html_css_files = [
    "https://weblate.org/static/vendor/font-source/source-sans-3.css",
    "https://weblate.org/static/vendor/font-source/source-code-pro.css",
]

# -- Options for HTMLHelp output ---------------------------------------------

# Output file base name for HTML help builder.
htmlhelp_basename = "Weblatedoc"


# -- Options for LaTeX output ------------------------------------------------

PREAMBLE = r"""
\pagestyle{fancy}
\setcounter{tocdepth}{1}
\usepackage{hyperref}
"""

latex_elements = {
    # The paper size ('letterpaper' or 'a4paper').
    "papersize": "a4paper",
    # The font size ('10pt', '11pt' or '12pt').
    # 'pointsize': '10pt',
    # Additional stuff for the LaTeX preamble.
    "preamble": PREAMBLE,
    # Avoid opening chapter only on even pages
    "extraclassoptions": "openany",
    # Latex figure (float) alignment
    # 'figure_align': 'htbp',
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title,
#  author, documentclass [howto, manual, or own class]).
latex_documents = [("index", "Weblate.tex", "The Weblate Manual", author, "manual")]

# Include logo on title page
latex_logo = "../weblate/static/logo-1024.png"
# Use xelatex engine for better unicode support
latex_engine = "xelatex"
# Disable using xindy as it does not work on readthedocs.org
latex_use_xindy = False

# -- Options for manual page output ------------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [("wlc", "wlc", "Weblate Client Documentation", [author], 1)]


# -- Options for Texinfo output ----------------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    (
        "index",
        "Weblate",
        project,
        author,
        "Weblate",
        "One line description of project.",
        "Miscellaneous",
    )
]


# -- Options for Epub output -------------------------------------------------

# Bibliographic Dublin Core info.
epub_title = project
epub_author = author
epub_publisher = author
epub_copyright = project_copyright

# The unique identifier of the text. This can be a ISBN number
# or the project homepage.
#
# epub_identifier = ''

# A unique identification for the text.
#
# epub_uid = ''

# A list of files that should not be packed into the epub file.
epub_exclude_files = ["search.html"]


graphviz_output_format = "svg"

# Use localized Python docs on Read the Docs build
language = os.environ.get("READTHEDOCS_LANGUAGE", "en")
# RTD uses no but the correct code is nb
if language == "no":
    language = "nb"
if "-" in language:
    # RTD normalized their language codes to ll-cc (e.g. zh-cn),
    # but Sphinx did not and still uses ll_CC (e.g. zh_CN).
    # `language` is the Sphinx configuration so it needs to be converted back.
    (lang_name, lang_country) = language.split("-")
    language = lang_name + "_" + lang_country.upper()

python_doc_url = "https://docs.python.org/3/"
if language == "pt_BR":
    python_doc_url = "https://docs.python.org/pt-br/3/"
elif language in {"es", "fr", "ja", "ko", "tr"}:
    python_doc_url = f"https://docs.python.org/{language}/3/"
elif language == "zh_CN":
    python_doc_url = "https://docs.python.org/zh-cn/3/"
elif language == "zh_TW":
    python_doc_url = "https://docs.python.org/zh-tw/3/"

django_doc_url = "https://docs.djangoproject.com/en/stable/"
if language in {"el", "es", "fr", "id", "ja", "ko", "pl"}:
    django_doc_url = f"https://docs.djangoproject.com/{language}/stable/"
elif language == "pt_BR":
    django_doc_url = "https://docs.djangoproject.com/pt-br/stable/"
elif language == "zh_CN":
    django_doc_url = "https://docs.djangoproject.com/zh-hans/stable/"

sphinx_doc_url = "https://www.sphinx-doc.org/en/master/"
if language in {
    "ar",
    "ca",
    "de",
    "ru",
    "es",
    "fr",
    "it",
    "ja",
    "ko",
    "pl",
    "pt_BR",
    "sr",
    "zh_CN",
}:
    sphinx_doc_url = f"https://www.sphinx-doc.org/{language}/master/"
elif language in {"zh_TW", "ta"}:
    sphinx_doc_url = f"https://www.sphinx-doc.org/{language}/latest/"

if language != "en":
    tags.add("i18n")  # noqa: F821


# Configuration for intersphinx
intersphinx_mapping = {
    "python": (python_doc_url, None),
    "django": (django_doc_url, f"{django_doc_url}_objects/"),
    "psa": ("https://python-social-auth.readthedocs.io/en/latest/", None),
    "tt": (
        "https://docs.translatehouse.org/projects/translate-toolkit/en/latest/",
        None,
    ),
    "amagama": ("https://docs.translatehouse.org/projects/amagama/en/latest/", None),
    "virtaal": ("https://docs.translatehouse.org/projects/virtaal/en/latest/", None),
    "ldap": ("https://django-auth-ldap.readthedocs.io/en/latest/", None),
    "celery": ("https://docs.celeryq.dev/en/stable/", None),
    "sphinx": (sphinx_doc_url, None),
    "rtd": ("https://docs.readthedocs.io/en/latest/", None),
    "venv": ("https://virtualenv.pypa.io/en/stable/", None),
    "borg": ("https://borgbackup.readthedocs.io/en/stable/", None),
    "pip": ("https://pip.pypa.io/en/stable/", None),
    "compressor": ("https://django-compressor.readthedocs.io/en/stable/", None),
    "drf-standardized-error": (
        "https://drf-standardized-errors.readthedocs.io/en/latest/",
        None,
    ),
}
intersphinx_disabled_reftypes = ["*"]

# Ignore missing targets for the http:obj <type>, it's how we declare the types
# for input/output fields in the API docs.
nitpick_ignore = [
    ("http:obj", "array"),
    ("http:obj", "boolean"),
    ("http:obj", "int"),
    ("http:obj", "float"),
    ("http:obj", "object"),
    ("http:obj", "string"),
    ("http:obj", "timestamp"),
    ("http:obj", "file"),
]

# Number of retries and timeout for linkcheck
linkcheck_retries = 10
linkcheck_timeout = 10
linkcheck_ignore = [
    # Local URL to Weblate
    "http://127.0.0.1:8080/",
    "http://127.0.0.1:1080/",
    # Requires a valid token
    "https://api.deepl.com/v2/translate",
    # Requires authentication
    "https://gitlab.com/profile/applications",
    # Anchors are used to specify channel name here
    "https://web.libera.chat/#",
    # Site is unreliable
    "https://docwiki.embarcadero.com/",
    # Example URL
    "https://my-instance.openai.azure.com",
    # These are PDF and fails with Unicode decode error
    "http://ftp.pwg.org/",
    # Access to our service has been temporarily blocked
    "https://yandex.com/dev/translate/",
    # 403
    "https://openai.com/",
    "https://platform.openai.com/api-keys",
    "https://platform.openai.com/docs/models",
    "https://translate.systran.net/en/account",
    # Seems unstable
    "https://pagure.io/",
    "https://azure.microsoft.com/en-us/products/ai-services/ai-translator",
    "https://wiki.gnupg.org/",
    "https://www.bis.doc.gov/",
    "https://www.libravatar.org/",
    "https://akismet.com/",
    # These seems to block bots/GitHub
    "https://docs.github.com/",
    "https://translate.yandex.com/",
    "https://www.gnu.org/",
    "https://dev.mysql.com/",
]

# HTTP docs
http_index_ignore_prefixes = ["/api/"]
http_strict_mode = True

# Autodocs
autodoc_mock_imports = [
    "django",
    "unidecode",
    "nh3",
    "html2text",
    "weblate_language_data",
    "celery",
    "sentry_sdk",
    "crispy_forms",
    "social_django",
    "social_core",
    "weblate.utils.errors",
    "weblate.trans.discovery",
    "weblate.checks.models",
    "weblate.trans.forms",
    "weblate.addons.forms",
    "weblate.trans.tasks",
    "weblate.formats",
    "weblate.trans.templatetags.translations",
    "dateutil",
    "filelock",
    "redis_lock",
    "django_redis",
    "lxml",
    "translate",
    "siphashc",
    "git",
    "PIL",
    "borg",
    "appconf",
    "weblate.addons.models",
    "weblate.trans.models",
    "weblate.lang.models",
    "weblate.vcs.git",
    "weblate.utils.files",
    "weblate.utils.validators",
    "django_otp",
    "django_otp_webauthn",
    "rest_framework",
]

# Create single gettext PO file for while documentation,
# instead of having one file per chapter.
gettext_compact = "docs"

redirects = {
    "devel/thirdparty": "third-party.html",  # codespell:ignore thirdparty
    "contributing/security": "security/index.html",
    "formats/moko": "formats/moko-resources.html",
}
