Installing on SUSE and openSUSE
===============================

.. include:: steps/hw.rst

.. include:: steps/install-system-devel.rst

.. code-block:: sh

   zypper install \
      libxslt-devel libxml2-devel freetype-devel libjpeg-devel zlib-devel libyaml-devel \
      cairo-devel typelib-1_0-Pango-1_0 gobject-introspection-devel libacl-devel \
      python3-pip python3-virtualenv python3-devel git

.. include:: steps/install-system-optional.rst

.. code-block:: sh

    zypper install tesseract-ocr tesseract-devel leptonica-devel

.. include:: steps/install-system-server.rst

.. code-block:: sh

    # Web server option 1: NGINX and uWSGI
    zypper install nginx uwsgi uwsgi-plugin-python3

    # Web server option 2: Apache with ``mod_wsgi``
    zypper install apache2 apache2-mod_wsgi

    # Caching backend: Redis
    zypper install redis-server

    # Database server: PostgreSQL
    zypper install postgresql postgresql-contrib

    # SMTP server
    zypper install postfix

.. include:: steps/install-python.rst

.. include:: steps/install-configure.rst

.. include:: steps/install-after.rst
