Installing on macOS
===================

.. include:: steps/hw.rst

.. include:: steps/install-system-devel.rst

.. code-block:: sh

    brew install python pango cairo gobject-introspection libffi glib libyaml
    pip3 install virtualenv

Make sure pip will be able to find the ``libffi`` version provided by homebrew
— this will be needed during the installation build step.

.. code-block:: sh

    export PKG_CONFIG_PATH="/usr/local/opt/libffi/lib/pkgconfig"

.. include:: steps/install-system-optional.rst

.. code-block:: sh

    brew install tesseract

.. include:: steps/install-system-server.rst

.. code-block:: sh

    # Web server option 1: NGINX and uWSGI
    brew install nginx uwsgi

    # Web server option 2: Apache with ``mod_wsgi``
    brew install httpd

    # Caching backend: Redis
    brew install redis

    # Database server: PostgreSQL
    brew install postgresql

.. include:: steps/install-python.rst

.. include:: steps/install-configure.rst

.. include:: steps/install-after.rst
