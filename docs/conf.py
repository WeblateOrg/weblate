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

import sphinx.transforms.i18n
import sphinx.util.i18n

# -- Path setup --------------------------------------------------------------

# sys.path.insert(0, os.path.abspath('.'))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "_ext")))

# Hacky way to have all localized content in single domain
sphinx.transforms.i18n.docname_to_domain = (
    sphinx.util.i18n.docname_to_domain
) = lambda docname, compact: "docs"


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
copyright = "2012 - 2020 Michal Čihař"
author = "Michal Čihař"

# The full version, including alpha/beta/rc tags
release = "4.2.2"


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "djangodocs",
    "sphinxcontrib.httpdomain",
    "sphinx.ext.graphviz",
    "sphinx.ext.intersphinx",
    "sphinx-jsonschema",
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

# Configuration for intersphinx
intersphinx_mapping = {
    "python": ("https://docs.python.org/3.7", None),
    "django": (
        "https://docs.djangoproject.com/en/stable/",
        "https://docs.djangoproject.com/en/stable/_objects/",
    ),
    "psa": ("https://python-social-auth.readthedocs.io/en/latest/", None),
    "tt": (
        "http://docs.translatehouse.org/projects/translate-toolkit/en/latest/",
        None,
    ),
    "amagama": ("https://docs.translatehouse.org/projects/amagama/en/latest/", None),
    "virtaal": ("http://docs.translatehouse.org/projects/virtaal/en/latest/", None),
    "ldap": ("https://django-auth-ldap.readthedocs.io/en/latest/", None),
    "celery": ("https://docs.celeryproject.org/en/latest/", None),
    "sphinx": ("https://www.sphinx-doc.org/en/stable/", None),
    "rtd": ("https://docs.readthedocs.io/en/latest/", None),
    "venv": ("https://virtualenv.pypa.io/en/stable/", None),
    "borg": ("https://borgbackup.readthedocs.io/en/stable/", None),
    "pip": ("https://pip.pypa.io/en/stable/", None),
    "compressor": ("https://django-compressor.readthedocs.io/en/stable/", None),
}

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
]

# Number of retries and timeout for linkcheck
linkcheck_retries = 10
linkcheck_timeout = 10
linkcheck_ignore = ["http://127.0.0.1:8080/"]
