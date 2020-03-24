Installing on macOS
===================

.. warning::

   This guide is currently untested, please provide feedback or corrections to it.


.. include:: steps/hw.rst

.. include:: steps/install-system-devel.rst

.. code-block:: sh

    brew install pango cairo libjpeg python git libyaml gobject-introspection
    pip3 install virtualenv

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
