Installing on macOS
===================

.. include:: steps/hw.rst

.. include:: steps/install-system-devel.rst

.. code-block:: sh

   # Use Python 3.14 until all dependencies support Python 3.15.
   brew install python@3.14 libyaml pkgconf zstd lz4 xxhash libxmlsec1 uv
   export UV_PYTHON="$(brew --prefix python@3.14)/bin/python3.14"

.. include:: steps/install-system-server.rst

.. code-block:: sh

    # Web server option 1: NGINX and uWSGI
    brew install nginx uwsgi

    # Web server option 2: Apache with ``mod_wsgi``
    brew install httpd

    # Caching backend: Valkey
    brew install valkey

    # Database server: PostgreSQL
    brew install postgresql

    # Gettext tools for gettext POT/PO update add-ons
    brew install gettext

.. include:: steps/install-python.rst

.. include:: steps/install-configure.rst

.. include:: steps/install-after.rst
