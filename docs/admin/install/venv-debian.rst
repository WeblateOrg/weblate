Installing on Debian and Ubuntu
===============================

.. include:: steps/hw.rst

.. include:: steps/install-system-devel.rst

.. code-block:: sh

   apt install \
      build-essential gir1.2-pango-1.0 libxml2-dev libxslt-dev libfreetype6-dev libjpeg-dev \
      libz-dev libyaml-dev libffi-dev libcairo-dev libmariadb-dev-compat libmariadb-dev \
      libgirepository1.0-dev libacl1-dev libssl-dev libpq-dev libjpeg62-turbo-dev \
      python3-gdbm python3-dev python3-pip python3-venv git -y

.. include:: steps/install-system-optional.rst

.. code-block:: sh

    apt install tesseract-ocr libtesseract-dev libleptonica-dev \
    libldap2-dev libldap-common libsasl2-dev \
    libxmlsec1-dev -y

.. include:: steps/install-system-server.rst

.. code-block:: sh

    # Web server option 1: NGINX and uWSGI
    apt install nginx uwsgi uwsgi-plugin-python3 -y

    # Web server option 2: Apache with ``mod_wsgi``
    apt install apache2 libapache2-mod-wsgi-py3 -y

    # Database server: PostgreSQL
    apt install postgresql postgresql-contrib -y

    # SMTP server
    apt install exim4 -y

Install Redis
--------
.. include:: redis.rst

.. include:: steps/install-python.rst

.. include:: steps/install-configure.rst

.. include:: steps/install-after.rst