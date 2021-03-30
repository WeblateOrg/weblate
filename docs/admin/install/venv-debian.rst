Installing on Debian and Ubuntu
===============================

.. include:: steps/hw.rst

.. include:: steps/install-system-devel.rst

.. code-block:: sh

   apt install \
      libxml2-dev libxslt-dev libfreetype6-dev libjpeg-dev libz-dev libyaml-dev \
      libcairo-dev gir1.2-pango-1.0 libgirepository1.0-dev libacl1-dev libssl-dev \
      build-essential python3-gdbm python3-dev python3-pip python3-virtualenv virtualenv git

.. include:: steps/install-system-optional.rst

.. code-block:: sh

    apt install tesseract-ocr libtesseract-dev libleptonica-dev

.. include:: steps/install-system-server.rst

.. code-block:: sh

    # Web server option 1: NGINX and uWSGI
    apt install nginx uwsgi uwsgi-plugin-python3

    # Web server option 2: Apache with ``mod_wsgi``
    apt install apache2 libapache2-mod-wsgi

    # Caching backend: Redis
    apt install redis-server

    # Database server: PostgreSQL
    apt install postgresql postgresql-contrib

    # SMTP server
    apt install exim4


.. include:: steps/install-python.rst

.. include:: steps/install-configure.rst

.. include:: steps/install-after.rst
