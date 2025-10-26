Installing on macOS
===================

.. include:: steps/hw.rst

.. include:: steps/install-system-devel.rst

.. code-block:: sh

   brew install python pango cairo gobject-introspection glib libyaml pkgconf zstd lz4 xxhash libxmlsec1 librsvg uv

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

    # Gettext for the msgmerge add-on
    brew install gettext

.. include:: steps/install-python.rst

.. include:: steps/install-configure.rst

.. include:: steps/install-after.rst
