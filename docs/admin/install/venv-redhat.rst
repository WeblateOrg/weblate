Installing on RedHat, Fedora and CentOS
=======================================

.. include:: steps/hw.rst

.. include:: steps/install-system-devel.rst

.. code-block:: sh

   dnf install \
      libxslt-devel libxml2-devel freetype-devel libjpeg-devel zlib-devel libyaml-devel \
      cairo-devel pango-devel gobject-introspection-devel libacl-devel \
      python3-pip python3-virtualenv python3-devel git

.. include:: steps/install-system-optional.rst

.. code-block:: sh

    dnf install tesseract-langpack-eng tesseract-devel leptonica-devel

.. include:: steps/install-system-server.rst

.. code-block:: sh

    # Web server option 1: NGINX and uWSGI
    dnf install nginx uwsgi uwsgi-plugin-python3

    # Web server option 2: Apache with ``mod_wsgi``
    dnf install apache2 apache2-mod_wsgi

    # Caching backend: Redis
    dnf install redis

    # Database server: PostgreSQL
    dnf install postgresql postgresql-contrib

    # SMTP server
    dnf install postfix

.. include:: steps/install-python.rst

.. include:: steps/install-configure.rst

.. include:: steps/install-after.rst
