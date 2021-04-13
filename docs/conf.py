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

# -- Path setup --------------------------------------------------------------

# sys.path.insert(0, os.path.abspath('.'))
# Our extension
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "_ext")))
# Weblate code
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def setup(app):
    app.add_css_file("https://s.weblate.org/cdn/font-source/source-sans-pro.css")
    app.add_css_file("https://s.weblate.org/cdn/font-source/source-code-pro.css")
    app.add_css_file("docs.css")
    # Used in Sphinx docs, needed for intersphinx links to it
    app.add_object_type(
        "confval",
        "confval",
        objname="configuration value",
        indextemplate="pair: %s; configuration value",
    )


# -- Project information -----------------------------------------------------

project = "Weblate"
copyright = "2012 - 2021 Michal Čihař"
author = "Michal Čihař"

# The full version, including alpha/beta/rc tags
release = "4.6"


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
    "sphinx_rtd_theme",
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "admin/install/steps/*.rst"]


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "sphinx_rtd_theme"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["../weblate/static/"]


html_logo = "../weblate/static/logo-128.png"


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
latex_documents = [
    ("latexindex", "Weblate.tex", "The Weblate Manual", author, "manual")
]

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
epub_copyright = copyright

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
rtd_lang = os.environ.get("READTHEDOCS_LANGUAGE")

python_doc_url = "https://docs.python.org/3.9/"
if rtd_lang == "pt_BR":
    python_doc_url = "https://docs.python.org/pt-br/3.9/"
elif rtd_lang in ("es", "fr", "ja", "ko"):
    python_doc_url = f"https://docs.python.org/{rtd_lang}/3.9/"
elif rtd_lang == "zh_CN":
    python_doc_url = "https://docs.python.org/zh-cn/3.9/"
elif rtd_lang == "zh_TW":
    python_doc_url = "https://docs.python.org/zh-tw/3.9/"

django_doc_url = "https://docs.djangoproject.com/en/stable/"
if rtd_lang in ("el", "es", "fr", "id", "ja", "ko", "pl"):
    django_doc_url = f"https://docs.djangoproject.com/{rtd_lang}/stable/"
elif rtd_lang == "pt_BR":
    django_doc_url = "https://docs.djangoproject.com/pt-br/stable/"
elif rtd_lang == "zh_CN":
    django_doc_url = "https://docs.djangoproject.com/zh-hans/stable/"

sphinx_doc_url = "https://www.sphinx-doc.org/en/stable/"
if rtd_lang in (
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
):
    sphinx_doc_url = f"https://www.sphinx-doc.org/{rtd_lang}/stable/"

# Configuration for intersphinx
intersphinx_mapping = {
    "python": (python_doc_url, None),
    "django": (django_doc_url, f"{django_doc_url}_objects/"),
    "psa": ("https://python-social-auth.readthedocs.io/en/latest/", None),
    "tt": (
        "http://docs.translatehouse.org/projects/translate-toolkit/en/latest/",
        None,
    ),
    "amagama": ("https://docs.translatehouse.org/projects/amagama/en/latest/", None),
    "virtaal": ("http://docs.translatehouse.org/projects/virtaal/en/latest/", None),
    "ldap": ("https://django-auth-ldap.readthedocs.io/en/latest/", None),
    "celery": ("https://docs.celeryproject.org/en/latest/", None),
    "sphinx": (sphinx_doc_url, None),
    "rtd": ("https://docs.readthedocs.io/en/latest/", None),
    "venv": ("https://virtualenv.pypa.io/en/stable/", None),
    "borg": ("https://borgbackup.readthedocs.io/en/stable/", None),
    "pip": ("https://pip.pypa.io/en/stable/", None),
    "compressor": ("https://django-compressor.readthedocs.io/en/stable/", None),
}
# See https://github.com/sphinx-doc/sphinx/pull/8981
intersphinx_strict_prefix = True

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
linkcheck_ignore = ["http://127.0.0.1:8080/"]

# HTTP docs
http_index_ignore_prefixes = ["/api/"]
http_strict_mode = True

# Autodocs
autodoc_mock_imports = [
    "django",
    "celery",
    "sentry_sdk",
    "crispy_forms",
    "weblate.trans.discovery",
    "weblate.checks.models",
    "weblate.trans.forms",
    "weblate.addons.forms",
    "weblate.trans.tasks",
    "dateutil",
    "filelock",
    "redis_lock",
    "django_redis",
    "lxml",
    "translate",
    "siphashc",
    "git",
    "PIL",
    "weblate.addons.models",
    "weblate.trans.models",
    "weblate.lang.models",
    "weblate.vcs.git",
    "weblate.utils.files",
]

# Gettext / i18n
gettext_compact = "docs"
